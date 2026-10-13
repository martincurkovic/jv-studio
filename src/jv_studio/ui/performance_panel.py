"""The Performances side of the main window: the open performance, its buttons and the editor. The sibling of the patch panel that lives in `main_window.py`.

It owns the same working-copy rules, adapted: edits go to a copy; Send to Temporary Performance and Write to USER are the only things that write to the unit (both read back; the
second saves the slot's old performance to a file first and writes nothing if that fails); live edits go to the TEMPORARY performance only while the shown performance is the one
the unit holds there; reading or opening another performance over edits asks first. The unit has to be in PERFORMANCE mode to play what is in its temporary performance.
The host (the main window) supplies the worker, the session, the status bar and the "back up first?" question.
"""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QCheckBox,
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

from jv_studio.core import app_config, debug_log, params, performance, sysex, validate
from jv_studio.ui import theme
from jv_studio.ui.performance_editor import PerformanceEditor
from jv_studio.ui.qt_helpers import item_heading
from jv_studio.ui.unit_dialogs import SlotDialog


class PerformancePanel(QWidget):
    #: a USER performance now holds a performance with this name (the host updates its list)
    slot_changed = Signal(int, str)

    UNDO_LIMIT = 200

    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self.worker = host.worker
        self._shown = None  # (label, working Performance, base address); label is "temporary", "user:N" or "file"
        self._original = None
        self._where = ""
        self._temp_synced = False
        self._sent_snapshot = None
        self._writing_shown_to = None
        self._undo, self._redo = [], []
        self._names = []  # USER performance names read from the unit

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 0, 15, 8)
        self.label = QLabel("No performance open. Read the temporary performance, double-click a USER performance, or open a .syx file.")
        self.label.setObjectName("sectionHeader")
        self.label.setWordWrap(True)
        self.problems_label = QLabel()
        self.problems_label.setObjectName("mutedLabel")
        self.problems_label.setWordWrap(True)
        self.problems_label.setVisible(False)
        actions = QHBoxLayout()
        self.btn_read = QPushButton("Read Temporary Performance")
        self.btn_read.setToolTip("Reads the performance in the unit's temporary performance memory (read-only: nothing is written).")
        self.btn_read.clicked.connect(self.read_temporary)
        self.btn_send = QPushButton("Send to Temporary Performance")
        self.btn_send.setToolTip("Puts the shown performance in the unit's temporary performance memory, then reads it back to check. Not stored.")
        self.btn_send.clicked.connect(self.send_temporary)
        self.btn_write = QPushButton("Write to USER...")
        self.btn_write.setToolTip("Stores the shown performance in a USER performance slot. The slot's current performance is saved to a file first.")
        self.btn_write.clicked.connect(self.write_user)
        self.btn_revert = QPushButton("Revert Edits")
        self.btn_revert.setToolTip("Go back to the performance as it was read or opened.")
        self.btn_revert.clicked.connect(self.revert_edits)
        for button in (self.btn_read, self.btn_send, self.btn_write, self.btn_revert):
            actions.addWidget(button)
        actions.addStretch()
        self.live_check = QCheckBox("Live edits")
        self.live_check.setChecked(True)
        self.live_check.setToolTip(
            "Hear your edits on the unit as you make them: each one is sent to its temporary performance (not stored) when you finish it, and read back. "
            "Works once the shown performance is the one in the temporary performance: read it from there, or use Send. Put the unit in Performance mode to hear it. "
            "Otherwise edits stay in the editor."
        )
        actions.insertWidget(actions.count() - 1, self.live_check)  # on the button row, after Revert Edits (before the stretch)
        # the editor (about 200 widgets) is built the first time it is needed: when the Performances mode is first shown, or a performance first arrives
        self.editor = None
        self.tree = None
        self._user_patch_names = None
        for item in (self.label, self.problems_label):
            layout.addWidget(item)
        layout.addLayout(actions)
        self._layout = layout

        self.worker.performance_read.connect(self._on_read)
        self.worker.write_done.connect(self._on_write_done)

    def ensure_editor(self):
        """Build the editor on first use. Returns it."""
        if self.editor is None:
            self.editor = PerformanceEditor()
            self.editor.param_committed.connect(self._on_param_committed)
            self.editor.edits_recorded.connect(self._on_edits_recorded)
            self.tree = QTreeWidget()  # the editor's last tab: every value as the unit holds it
            self.tree.setHeaderLabels(["Parameter", "Value", "Raw"])
            self.editor.add_extra_tab(self.tree, "Raw Values")
            self.editor.tabs.currentChanged.connect(lambda _i: self._refresh_tree_if_shown())
            self._layout.addWidget(self.editor, 1)
            self.editor.set_user_patch_names(self._user_patch_names)
            if self._shown is not None:
                self.editor.set_performance(self._shown[1])
        return self.editor

    def showEvent(self, event):
        self.ensure_editor()
        super().showEvent(event)

    # -- state the window needs --------------------------------------------------------------------------------------------

    def has_shown(self):
        return self._shown is not None

    def is_dirty(self):
        return self._shown is not None and self._original is not None and self._shown[1] != self._original

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def shown_label(self):
        return self._shown[0] if self._shown else None

    def set_names(self, names):
        self._names = list(names)

    def set_user_patch_names(self, names):
        self._user_patch_names = list(names) if names else None
        if self.editor is not None:
            self.editor.set_user_patch_names(names)

    # -- reading ---------------------------------------------------------------------------------------------------------

    def confirm_discard(self):
        """Edits would be lost by showing another performance: ask (default No). True to carry on."""
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
        self.host.statusBar().showMessage("Reading the temporary performance...")
        self.worker.submit("perf_temporary")

    def open_user(self, number):
        if number is None or not self.worker.is_idle() or not self.confirm_discard():
            return
        self.host.statusBar().showMessage(f"Reading USER performance {number + 1:02d}...")
        self.worker.submit("perf_user", number)

    def _on_read(self, label, read, problems):
        base = performance.TEMPORARY_BASE if label == "temporary" else performance.user_base(int(label.split(":")[1]))
        where = "the temporary performance" if label == "temporary" else f"USER performance {int(label.split(':')[1]) + 1:02d}"
        self._show(label, read, base, problems, where)

    def _show(self, label, read, base, problems, where):
        self._shown = (label, read, base)
        self._original = read.copy()
        self._where = where
        self._temp_synced = label == "temporary"
        self._undo.clear()
        self._redo.clear()
        self.ensure_editor().set_performance(read)
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

    def _on_param_committed(self, block, key, part, value):
        debug_log.get_logger().info(f"edit: {self._where} {block}{'' if part < 0 else f' part {part + 1}'} {key} = {value!r}")
        self._update_label()
        self._refresh_tree_if_shown()
        if self._live():
            self.worker.submit("perf_write_param", block, key, None if part < 0 else part, value)
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
        for block, key, part, old, new in (reversed(edits) if reverse else edits):
            value = old if reverse else new
            working.set(block, key, value, part=None if part < 0 else part)
            if self._live():
                self.worker.submit("perf_write_param", block, key, None if part < 0 else part, value)
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
        self.editor.set_performance(self._shown[1])
        self._update_label()
        self._refresh_tree_if_shown()
        if self._live():
            self.host.statusBar().showMessage("Reverted. Send to Temporary Performance to put it back on the unit.")
            self._temp_synced = False  # the unit's temporary performance still holds the edits
        self.host._refresh_connection()

    def on_live_failed(self, message):
        """A live edit the unit didn't take: switch live sending off, once (queued edits fail too)."""
        if self.live_check.isChecked():
            self.live_check.setChecked(False)
            self._temp_synced = False
            debug_log.get_logger().warning(f"live performance edit failed, live sending switched off: {message}")
            QMessageBox.warning(self, "JV-1010", f"{message}\n\nLive sending is off. Send to Temporary Performance to try again.")
        self.host._refresh_connection()

    # -- writing to the unit -----------------------------------------------------------------------------------------------

    def send_temporary(self):
        if self._shown is None or not self.host.session.is_open or not self.worker.is_idle():
            return
        shown = self._shown[1]
        self.host.statusBar().showMessage(f'Sending "{shown.name}" to the temporary performance...')
        self._sent_snapshot = shown.copy()
        self.worker.submit("perf_send_temporary", self._sent_snapshot)

    def write_user(self):
        if self._shown is None or not self.host.session.is_open or not self.worker.is_idle():
            return
        label, shown, base = self._shown
        default = base[1] if base[0] == 0x10 else 0
        dialog = SlotDialog(
            "Write to USER", f'Write "{shown.name}" to:', self._names, default, "Overwrite",
            f"The slot's current performance is saved to {app_config.backups_dir()} first, and the write is read back to check it.",
            self, count=performance.USER_PERFORMANCE_COUNT, label="USER:{:02d}",
        )
        if dialog.exec() != SlotDialog.DialogCode.Accepted:
            return
        number = dialog.slot()
        if not self.host._offer_backup_first(f"overwriting USER performance {number + 1:02d}"):
            return
        self.host.statusBar().showMessage(f'Writing "{shown.name}" to USER performance {number + 1:02d}...')
        self._writing_shown_to = number
        self.worker.submit("perf_write_user", number, shown.copy())

    def _on_write_done(self, label, name, backup_path):
        if not label.startswith("perf:"):
            return
        if label == "perf:temporary":
            self.host.statusBar().showMessage(f'"{name}" sent to the temporary performance and read back', 5000)
            self._temp_synced = self._shown is not None and self._shown[1] == self._sent_snapshot
        else:
            number = int(label.split(":")[1])
            if self._writing_shown_to == number and self._shown is not None:
                self._original = self._shown[1].copy()
                self._update_label()
            self._writing_shown_to = None
            self.host.statusBar().showMessage(f'USER performance {number + 1:02d} is now "{name}" (read back); the old one is in {Path(backup_path).name}', 10000)
            if number < len(self._names):
                self._names[number] = name
            self.slot_changed.emit(number, name)
        self.host._refresh_connection()

    # -- files -----------------------------------------------------------------------------------------------------------

    def open_syx(self):
        if not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open performance .syx", str(Path.home()), "SysEx files (*.syx);;All files (*)")
        if not path:
            return
        try:
            found = performance.parse_syx(Path(path).read_bytes())
        except (OSError, sysex.SysexError) as e:
            debug_log.get_logger().error(f"couldn't open {path}", exc_info=True)
            QMessageBox.critical(self, "Open", f"Couldn't read the file: {e}")
            return
        if not found:
            QMessageBox.information(self, "Open", "That file holds no JV-1010 performance.")
            return
        bases = list(found)
        if len(bases) > 1:
            names = [f"{self._base_title(b)}  {found[b].name}" for b in bases]
            choice, ok = QInputDialog.getItem(self, "Open", f"The file holds {len(bases)} performances. Show:", names, 0, False)
            if not ok:
                return
            base = bases[names.index(choice)]
        else:
            base = bases[0]
        chosen = found[base]
        self._show("file", chosen, base, validate.out_of_range_performance(chosen), f"{Path(path).name} ({self._base_title(base)})")

    @staticmethod
    def _base_title(base):
        return "temporary performance" if base == performance.TEMPORARY_BASE else f"USER performance {base[1] + 1:02d}"

    def save_syx(self):
        if self._shown is None:
            return
        _, shown, base = self._shown
        suggested = "".join(c if c.isalnum() or c in " -_." else "_" for c in shown.name).strip() or "performance"
        path, _ = QFileDialog.getSaveFileName(self, "Save performance as .syx", str(Path.home() / f"{suggested}.syx"), "SysEx files (*.syx)")
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
        flagged = {(p.block, p.tone, p.key) for p in validate.out_of_range_performance(working)}
        warning = QBrush(QColor(theme.current_palette()["warning"]))
        table = params.load_table()
        self.tree.clear()
        sections = [(performance.COMMON, None, "Common", working.common)] + [(performance.PART, i, f"Part {i + 1}", p) for i, p in enumerate(working.parts)]
        for block_key, part, title, buffer in sections:
            parent = QTreeWidgetItem([title])
            self.tree.addTopLevelItem(parent)
            for param in table.block(block_key).params:
                value = params.read(buffer, param)
                item = QTreeWidgetItem([param.name, params.format_value(param, value), repr(value) if param.string else str(value)])
                if (block_key, part, param.key) in flagged:
                    for column in range(3):
                        item.setForeground(column, warning)
                parent.addChild(item)
            parent.setExpanded(part is None)
        self.tree.resizeColumnToContents(0)

    # -- enabling --------------------------------------------------------------------------------------------------------

    def refresh_state(self, ready):
        """`ready`: ports open and the worker idle."""
        self.btn_read.setEnabled(ready)
        self.btn_send.setEnabled(ready and self._shown is not None)
        self.btn_write.setEnabled(ready and self._shown is not None)
        self.btn_revert.setEnabled(self._shown is not None and self.is_dirty())
