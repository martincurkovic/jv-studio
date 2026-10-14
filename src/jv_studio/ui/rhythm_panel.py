"""The Rhythm Sets side of the main window: the open rhythm set, its buttons and the editor. The sibling of `performance_panel.py` (same working-copy rules).

Edits go to a copy; Send to Temporary Rhythm Set and Write to USER are the only things that write to the unit (both read back; the second saves the slot's old set to a file first and
writes nothing if that fails); live edits go to the TEMPORARY rhythm set (02 09 00 00, the one Part 10 plays in Performance mode) only while the shown set is the one the unit holds there;
reading or opening another set over edits asks first. The host (the main window) supplies the worker, the session, the status bar, the audition bar's velocity and the "back up first?" question.
"""

from pathlib import Path

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from jv_studio.core import app_config, audition, debug_log, params, rhythm, sysex, validate
from jv_studio.ui import theme
from jv_studio.ui.qt_helpers import item_heading, set_primary
from jv_studio.ui.rhythm_editor import RhythmEditor
from jv_studio.ui.unit_dialogs import SlotDialog

NOTE_LENGTH_MS = 350  # a clicked key sounds this long (a rhythm part ignores Note Off when its Envelope Mode is NO-SUS anyway)
WHOLE_KEY_FROM = 4  # a key with more changed values than this goes to the unit as one block, not one DT1 and read-back per value


class RhythmPanel(QWidget):
    #: a USER rhythm set now holds a set with this name (the host updates its list)
    slot_changed = Signal(int, str)

    UNDO_LIMIT = 200

    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self.worker = host.worker
        self._shown = None  # (label, working RhythmSet, base address); label is "temporary", "user:N" or "file"
        self._original = None
        self._where = ""
        self._temp_synced = False
        self._sent_snapshot = None
        self._writing_shown_to = None
        self._undo, self._redo = [], []
        self._names = []  # USER rhythm set names read from the unit

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 0, 15, 8)
        self.label = QLabel("No rhythm set open. Read the temporary rhythm set, double-click a USER set, or open a .syx file.")
        self.label.setObjectName("sectionHeader")
        self.label.setWordWrap(True)
        self.problems_label = QLabel()
        self.problems_label.setObjectName("mutedLabel")
        self.problems_label.setWordWrap(True)
        self.problems_label.setVisible(False)
        actions = QHBoxLayout()
        self.btn_read = QPushButton("Read Temporary")
        self.btn_read.setToolTip("Reads the rhythm set the unit's Part 10 is playing now (read-only: nothing is written).")
        self.btn_read.clicked.connect(self.read_temporary)
        self.btn_send = QPushButton("Send to Temporary")
        self.btn_send.setToolTip("Puts the shown set in the unit's temporary rhythm set, then reads it back to check. Not stored.")
        self.btn_send.clicked.connect(self.send_temporary)
        self.btn_write = QPushButton("Write to USER...")
        self.btn_write.setToolTip("Stores the shown set in a USER rhythm set. The slot's current set is saved to a file first.")
        self.btn_write.clicked.connect(self.write_user)
        self.btn_revert = QPushButton("Revert Edits")
        self.btn_revert.setToolTip("Go back to the rhythm set as it was read or opened.")
        self.btn_revert.clicked.connect(self.revert_edits)
        for button in (self.btn_read, self.btn_send, self.btn_write, self.btn_revert):
            actions.addWidget(button)
        self.live_check = QCheckBox("Live edits")
        self.live_check.setChecked(True)
        self.live_check.setToolTip(
            "Hear your edits on the unit as you make them: each one is sent to its temporary rhythm set (not stored) when you finish it, and read back. "
            "Works once the shown set is the one in the temporary rhythm set: read it from there, or use Send. Otherwise edits stay in the editor."
        )
        actions.addWidget(self.live_check)
        actions.addStretch()
        channel_row = QHBoxLayout()
        self.channel_combo = QComboBox()
        for number in range(1, 17):
            self.channel_combo.addItem(str(number))
        self.channel_combo.setCurrentIndex(9)  # channel 10
        self.channel_combo.setToolTip("The MIDI channel of Part 10, which plays the rhythm set (10 unless you changed it in the performance). Clicked keys play on it.")
        channel_row.addWidget(QLabel("Part 10 channel"))
        channel_row.addWidget(self.channel_combo)
        self.hint_label = QLabel(
            "Keys sound with the unit in Performance or Rhythm mode. Choose a rhythm set on the unit (right-click a set in the list), then Read Temporary."
        )
        self.hint_label.setObjectName("mutedLabel")
        self.hint_label.setWordWrap(True)
        self.editor = None  # built the first time it is needed (about 100 widgets)
        self.tree = None
        for item in (self.label, self.problems_label):
            layout.addWidget(item)
        channel_row.addWidget(self.hint_label, 1)
        layout.addLayout(actions)
        layout.addLayout(channel_row)
        self._layout = layout

        self.worker.rhythm_read.connect(self._on_read)
        self.worker.write_done.connect(self._on_write_done)

    def ensure_editor(self):
        if self.editor is None:
            self.editor = RhythmEditor()
            self.editor.param_committed.connect(self._on_param_committed)
            self.editor.edits_recorded.connect(self._on_edits_recorded)
            self.editor.keys_changed.connect(self._on_keys_changed)
            self.editor.key_clicked.connect(self.play_key)
            self.tree = QTreeWidget()  # the editor's last tab: every value of the shown key and the common block, as the unit holds them
            self.tree.setHeaderLabels(["Parameter", "Value", "Raw"])
            self.editor.add_extra_tab(self.tree, "Raw Values")
            self.editor.set_extra_tab_visible(self.tree, self.host.show_raw_values())
            self.editor.tabs.currentChanged.connect(lambda _i: self._refresh_tree_if_shown())
            self.editor.key_changed.connect(lambda _k: self._refresh_tree_if_shown())
            self._layout.addWidget(self.editor, 1)
            if self._shown is not None:
                self.editor.set_rhythm(self._shown[1])
        return self.editor

    def showEvent(self, event):
        self.ensure_editor()
        super().showEvent(event)

    # -- state the window needs --------------------------------------------------------------------------------------------

    def apply_raw_visibility(self):
        if self.editor is not None:
            self.editor.set_extra_tab_visible(self.tree, self.host.show_raw_values())

    def has_shown(self):
        return self._shown is not None

    def is_dirty(self):
        return self._shown is not None and self._original is not None and self._shown[1] != self._original

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def set_names(self, names):
        self._names = list(names)

    # -- sounding --------------------------------------------------------------------------------------------------------

    def channel(self):
        return self.channel_combo.currentIndex()

    def play_key(self, key):
        """Sound `key` on Part 10's channel for a moment, at the audition bar's velocity."""
        velocity = self.host.audition.velocity.value()
        channel = self.channel()
        self.host._send_midi(audition.note_on(channel, key, velocity))
        QTimer.singleShot(NOTE_LENGTH_MS, lambda: self.host._send_midi(audition.note_off(channel, key)))

    def select_on_unit(self, number):
        """Choose USER rhythm set `number` on Part 10 by Bank Select + Program Change: the unit loads it into its temporary rhythm set."""
        for message in audition.rhythm_select(self.channel(), "USER", number):
            self.host._send_midi(message)
        self._temp_synced = False  # the unit's temporary rhythm set is now a different one
        self.host.statusBar().showMessage(f"Chose USER rhythm set {number + 1} on channel {self.channel() + 1}. Read Temporary Rhythm Set to edit what you hear.", 8000)
        self.host._refresh_connection()

    # -- reading ---------------------------------------------------------------------------------------------------------

    def confirm_discard(self):
        if not self.is_dirty():
            return True
        answer = QMessageBox.question(
            self, "Discard edits?", f'"{self._shown[1].name}" has edits that are not written anywhere. Discard them?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def read_temporary(self):
        if not self.confirm_discard():
            return
        self.host._start_progress("Reading the temporary rhythm set...", cancellable=False)
        self.worker.submit("rhythm_temporary")

    def open_user(self, number):
        if number is None or not self.worker.is_idle() or not self.confirm_discard():
            return
        self.host._start_progress(f"Reading USER rhythm set {number + 1}...", cancellable=False)
        self.worker.submit("rhythm_user", number)

    def _on_read(self, label, read, problems):
        base = rhythm.TEMPORARY_BASE if label == "temporary" else rhythm.user_base(int(label.split(":")[1]))
        where = "the temporary rhythm set" if label == "temporary" else f"USER rhythm set {int(label.split(':')[1]) + 1}"
        self._show(label, read, base, problems, where)

    def _show(self, label, read, base, problems, where):
        self._shown = (label, read, base)
        self._original = read.copy()
        self._where = where
        self._temp_synced = label == "temporary"
        self._undo.clear()
        self._redo.clear()
        self.ensure_editor().set_rhythm(read)
        self._update_label()
        if problems:
            shown = "; ".join(str(p) for p in problems[:3])
            more = f" (and {len(problems) - 3} more)" if len(problems) > 3 else ""
            self.problems_label.setText(f"{len(problems)} value(s) outside the manual's ranges: {shown}{more}. Details are in the log.")
        else:
            self.problems_label.clear()
        self.problems_label.setVisible(bool(problems))
        self._refresh_tree_if_shown()
        self.host.statusBar().showMessage(f"Read {where}", 5000)
        self.host._refresh_connection()

    def _update_label(self):
        if self._shown is not None:
            self.label.setText(item_heading(self._where, self._shown[1].name, self.is_dirty()))

    # -- editing ---------------------------------------------------------------------------------------------------------

    def _live(self):
        return self.live_check.isChecked() and self._temp_synced and self.host.session.is_open

    def _send_live(self, edits):
        """Send these edits to the temporary rhythm set: a key with several changed values goes as one block (a copy or a swap), the rest value by value."""
        per_key = {}
        for block, key, note, _old, new in edits:
            per_key.setdefault((block, note), []).append((key, new))
        for (block, note), items in per_key.items():
            if block == rhythm.NOTE and len(items) > WHOLE_KEY_FROM:
                self.worker.submit("rhythm_write_note", note, bytes(self._shown[1].notes[note]))
            else:
                for key, value in items:
                    self.worker.submit("rhythm_write_param", block, key, None if note < 0 else note, value)

    def _on_param_committed(self, block, key, note, value):
        debug_log.get_logger().info(f"edit: {self._where} {block}{'' if note < 0 else f' key {note}'} {key} = {value!r}")
        self._update_label()
        self._refresh_tree_if_shown()
        if self._live():
            self.worker.submit("rhythm_write_param", block, key, None if note < 0 else note, value)
        self.host._refresh_connection()

    def _on_keys_changed(self, keys):
        """A copy or a swap changed whole keys (the individual values were recorded for Undo): send each key as a block."""
        self._update_label()
        self._refresh_tree_if_shown()
        if self._live():
            for key in keys:
                self.worker.submit("rhythm_write_note", key, bytes(self._shown[1].notes[key]))
        self.host._refresh_connection()

    def _on_edits_recorded(self, edits):
        self._undo.append(edits)
        del self._undo[: -self.UNDO_LIMIT]
        self._redo.clear()
        self.host._refresh_connection()

    def undo(self):
        self._step(self._undo, self._redo, reverse=True)

    def redo(self):
        self._step(self._redo, self._undo, reverse=False)

    def _step(self, take_from, put_on, reverse):
        if self._shown is None or not take_from:
            return
        edits = take_from.pop()
        working = self._shown[1]
        applied = []
        for block, key, note, old, new in (reversed(edits) if reverse else edits):
            value = old if reverse else new
            working.set(block, key, value, key=None if note < 0 else note)
            applied.append((block, key, note, old, value))
        if self._live():
            self._send_live(applied)
        put_on.append(edits)
        self.editor.refresh()
        self._update_label()
        self._refresh_tree_if_shown()
        debug_log.get_logger().info(f"{'undo' if reverse else 'redo'}: {len(edits)} value(s) on {self._where}")
        self.host._refresh_connection()

    def revert_edits(self):
        if self._shown is None or not self.is_dirty():
            return
        label, _, base = self._shown
        self._shown = (label, self._original.copy(), base)
        self._undo.clear()
        self._redo.clear()
        self.editor.set_rhythm(self._shown[1])
        self._update_label()
        self._refresh_tree_if_shown()
        if self._live():
            self.host.statusBar().showMessage("Reverted. Send to Temporary Rhythm Set to put it back on the unit.")
            self._temp_synced = False  # the unit's temporary rhythm set still holds the edits
        self.host._refresh_connection()

    def on_live_failed(self, message):
        """A live edit the unit didn't take: switch live sending off, once (queued edits fail too)."""
        if self.live_check.isChecked():
            self.live_check.setChecked(False)
            self._temp_synced = False
            debug_log.get_logger().warning(f"live rhythm edit failed, live sending switched off: {message}")
            QMessageBox.warning(self, "JV-1010", f"{message}\n\nLive sending is off. Send to Temporary Rhythm Set to try again.")
        self.host._refresh_connection()

    # -- writing to the unit -----------------------------------------------------------------------------------------------

    def send_temporary(self):
        if self._shown is None or not self.host.session.is_open or not self.worker.is_idle():
            return
        shown = self._shown[1]
        self.host.statusBar().showMessage(f'Sending "{shown.name}" to the temporary rhythm set...')
        self._sent_snapshot = shown.copy()
        self.worker.submit("rhythm_send_temporary", self._sent_snapshot)

    def write_user(self):
        if self._shown is None or not self.host.session.is_open or not self.worker.is_idle():
            return
        label, shown, base = self._shown
        default = base[1] - 0x40 if base[0] == 0x10 else 0
        dialog = SlotDialog(
            "Write to USER", f'Write "{shown.name}" to:', self._names, default, "Overwrite",
            f"The slot's current rhythm set is saved to {app_config.backups_dir()} first, and the write is read back to check it.",
            self, count=rhythm.USER_RHYTHM_COUNT, label="USER:{}",
        )
        if dialog.exec() != SlotDialog.DialogCode.Accepted:
            return
        number = dialog.slot()
        if not self.host._offer_backup_first(f"overwriting USER rhythm set {number + 1}"):
            return
        self.host.statusBar().showMessage(f'Writing "{shown.name}" to USER rhythm set {number + 1}...')
        self._writing_shown_to = number
        self.worker.submit("rhythm_write_user", number, shown.copy())

    def _on_write_done(self, label, name, backup_path):
        if not label.startswith("rhythm:"):
            return
        if label == "rhythm:temporary":
            self.host.statusBar().showMessage(f'"{name}" sent to the temporary rhythm set and read back', 5000)
            self._temp_synced = self._shown is not None and self._shown[1] == self._sent_snapshot
        else:
            number = int(label.split(":")[1])
            if self._writing_shown_to == number and self._shown is not None:
                self._original = self._shown[1].copy()
                self._update_label()
            self._writing_shown_to = None
            self.host.statusBar().showMessage(f'USER rhythm set {number + 1} is now "{name}" (read back); the old one is in {Path(backup_path).name}', 10000)
            if number < len(self._names):
                self._names[number] = name
            self.slot_changed.emit(number, name)
        self.host._refresh_connection()

    # -- files -----------------------------------------------------------------------------------------------------------

    def open_syx(self):
        if not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open rhythm set .syx", str(Path.home()), "SysEx files (*.syx);;All files (*)")
        if not path:
            return
        try:
            found = rhythm.parse_syx(Path(path).read_bytes())
        except (OSError, sysex.SysexError) as e:
            debug_log.get_logger().error(f"couldn't open {path}", exc_info=True)
            QMessageBox.critical(self, "Open", f"Couldn't read the file: {e}")
            return
        if not found:
            QMessageBox.information(self, "Open", "That file holds no JV-1010 rhythm set.")
            return
        bases = list(found)
        if len(bases) > 1:
            names = [f"{self._base_title(b)}  {found[b].name}" for b in bases]
            choice, ok = QInputDialog.getItem(self, "Open", f"The file holds {len(bases)} rhythm sets. Show:", names, 0, False)
            if not ok:
                return
            base = bases[names.index(choice)]
        else:
            base = bases[0]
        chosen = found[base]
        self._show("file", chosen, base, validate.out_of_range_rhythm(chosen), f"{Path(path).name} ({self._base_title(base)})")

    @staticmethod
    def _base_title(base):
        return "temporary rhythm set" if base == rhythm.TEMPORARY_BASE else f"USER rhythm set {base[1] - 0x40 + 1}"

    def save_syx(self):
        if self._shown is None:
            return
        _, shown, base = self._shown
        suggested = "".join(c if c.isalnum() or c in " -_." else "_" for c in shown.name).strip() or "rhythm set"
        path, _ = QFileDialog.getSaveFileName(self, "Save rhythm set as .syx", str(Path.home() / f"{suggested}.syx"), "SysEx files (*.syx)")
        if not path:
            return
        try:
            Path(path).write_bytes(shown.to_syx(base))
        except OSError as e:
            debug_log.get_logger().error(f"couldn't save {path}", exc_info=True)
            QMessageBox.critical(self, "Save", f"Couldn't save the file: {e}")
            return
        self.host.statusBar().showMessage(f"Saved {Path(path).name}", 5000)

    # -- the raw values tab ----------------------------------------------------------------------------------------------

    def _refresh_tree_if_shown(self):
        if self._shown is None or self.editor is None or self.editor.tabs.currentWidget() is not self.tree:
            return
        working = self._shown[1]
        key = self.editor.chosen_key()
        flagged = {(p.block, p.tone, p.key) for p in validate.out_of_range_rhythm(working)}
        warning = QBrush(QColor(theme.current_palette()["warning"]))
        table = params.load_table()
        self.tree.clear()
        sections = [(rhythm.COMMON, None, "Common", working.common), (rhythm.NOTE, key, f"Key {key} ({params.note_name(key)})", working.notes[key])]
        for block_key, note, title, buffer in sections:
            parent = QTreeWidgetItem([title])
            self.tree.addTopLevelItem(parent)
            for param in table.block(block_key).params:
                value = params.read(buffer, param)
                item = QTreeWidgetItem([param.name, params.format_value(param, value), repr(value) if param.string else str(value)])
                if (block_key, note, param.key) in flagged:
                    for column in range(3):
                        item.setForeground(column, warning)
                parent.addChild(item)
            parent.setExpanded(True)
        self.tree.resizeColumnToContents(0)

    # -- enabling --------------------------------------------------------------------------------------------------------

    def refresh_state(self, ready):
        """`ready`: ports open and the worker idle."""
        self.btn_read.setEnabled(ready)
        self.btn_send.setEnabled(ready and self._shown is not None)
        self.btn_write.setEnabled(ready and self._shown is not None)
        self.btn_revert.setEnabled(self._shown is not None and self.is_dirty())
        set_primary(self.btn_write, self.is_dirty())
