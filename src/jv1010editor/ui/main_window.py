import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QBrush, QColor, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QInputDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from jv1010editor.core import app_config, backup, debug_log, midi, midi_diagnostics, params, patch, stock, sysex, validate
from jv1010editor.ui import theme
from jv1010editor.ui.about_dialog import AboutDialog
from jv1010editor.ui.diagnostics_ui import add_open_log_folder_action
from jv1010editor.ui.midi_session import MidiSession
from jv1010editor.ui.patch_editor import PatchEditor
from jv1010editor.ui.qt_helpers import build_scroll_area, build_section_card, set_enabled_without_scrolling
from jv1010editor.ui.settings_dialog import SettingsDialog
from jv1010editor.ui.unit_dialogs import RestoreDialog, WriteUserDialog
from jv1010editor.ui.unit_worker import UnitWorker


class MainWindow(QMainWindow):
    """The application window: the connection, a hardware check, a look at the unit's patches, whole-unit backup and restore, and the only two places
    that write to the unit: Send to Temporary Patch and Write to USER (both read back; the second saves the slot's old patch first).
    The editor itself arrives in phase 3 (dev_docs/roadmap.md)."""

    def __init__(self, session=None, worker=None, start_worker=True):
        super().__init__()
        self.setWindowTitle("JV-1010 Editor")
        self.setMinimumSize(820, 640)
        app_config.ensure_defaults_saved()
        self.session = session if session is not None else MidiSession()
        self.worker = worker if worker is not None else UnitWorker(self.session)
        self.session.changed.connect(self._refresh_connection)
        self.worker.patch_read.connect(self._on_patch_read)
        self.worker.names_read.connect(self._on_names_read)
        self.worker.backup_done.connect(self._on_backup_done)
        self.worker.restore_done.connect(self._on_restore_done)
        self.worker.write_done.connect(self._on_write_done)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.param_written.connect(self._on_param_written)
        self.worker.progress.connect(self._on_progress)
        self.worker.failed.connect(self._on_failed)
        self.worker.busy_changed.connect(self._refresh_connection)
        self._shown = None  # (label, working Patch, base address); the patch is the WORKING COPY the editor changes; label is "temporary", "user:N" or "file"
        self._original = None  # what was read or opened, for Revert and for the "edited" mark
        self._where = ""  # how the shown patch is described ("USER:005")
        self._temp_synced = False  # the unit's temporary patch holds the working copy as it was last sent/read: only then can edits be heard live
        self._sent_snapshot = None  # a copy of the patch at the moment Send to Temporary Patch was queued
        self._long_job = False  # a job with a progress bar is running (names, backup, restore)
        self._summaries = []  # unit.PatchSummary of the USER patches read so far
        self._backed_up = False  # a whole-unit backup was saved in this session

        self._build_menus()
        self._build_central()
        self.statusBar()
        self._restore_saved_ports()
        self._refresh_connection()
        if start_worker:
            self.worker.start()

    # -- layout ------------------------------------------------------------------------------------------------------------

    def _build_menus(self):
        file_menu = self.menuBar().addMenu("&File")
        self.open_action = QAction("Open Patch .syx...", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.open_syx)
        file_menu.addAction(self.open_action)
        self.save_action = QAction("Save Patch as .syx...", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self.save_shown_patch)
        file_menu.addAction(self.save_action)
        file_menu.addSeparator()
        self.backup_action = QAction("Back Up Unit...", self)
        self.backup_action.triggered.connect(self.back_up_unit)
        file_menu.addAction(self.backup_action)
        self.restore_action = QAction("Restore Unit...", self)
        self.restore_action.triggered.connect(self.restore_unit)
        file_menu.addAction(self.restore_action)
        file_menu.addSeparator()
        self.settings_action = QAction("Settings...", self)
        self.settings_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        # Qt only binds Preferences to a key on macOS (Cmd+,); elsewhere Ctrl+, is the nearest equivalent
        self.settings_action.setShortcut(QKeySequence.StandardKey.Preferences if sys.platform == "darwin" else "Ctrl+,")
        self.settings_action.triggered.connect(self.open_settings)
        file_menu.addAction(self.settings_action)
        quit_action = QAction("Quit", self)
        quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        hardware_menu = self.menuBar().addMenu("&Hardware")
        self.detect_action = QAction("Detect JV-1010", self)
        self.detect_action.setShortcut("Ctrl+D")
        self.detect_action.triggered.connect(self.detect_hardware)
        hardware_menu.addAction(self.detect_action)
        self.read_action = QAction("Read Temporary Patch", self)
        self.read_action.setShortcut("Ctrl+R")
        self.read_action.triggered.connect(self.read_temporary)
        hardware_menu.addAction(self.read_action)
        hardware_menu.addSeparator()
        self.send_action = QAction("Send to Temporary Patch", self)
        self.send_action.setShortcut("Ctrl+Return")
        self.send_action.triggered.connect(self.send_temporary)
        hardware_menu.addAction(self.send_action)
        self.write_action = QAction("Write to USER...", self)
        self.write_action.triggered.connect(self.write_user)
        hardware_menu.addAction(self.write_action)

        help_menu = self.menuBar().addMenu("&Help")
        add_open_log_folder_action(help_menu, self)
        about_action = QAction("About JV-1010 Editor...", self)
        about_action.setMenuRole(QAction.MenuRole.AboutRole)
        about_action.triggered.connect(lambda: AboutDialog(self).exec())
        help_menu.addAction(about_action)

    def _build_central(self):
        connection = QVBoxLayout()
        self.connection_label = QLabel()
        self.connection_label.setWordWrap(True)
        connection.addWidget(self.connection_label)
        self.detect_results_label = QLabel()
        self.detect_results_label.setWordWrap(True)
        connection.addWidget(self.detect_results_label)
        buttons = QHBoxLayout()
        self.btn_settings = QPushButton("Settings...")
        self.btn_settings.clicked.connect(self.open_settings)
        self.btn_detect = QPushButton("Detect JV-1010")
        self.btn_detect.clicked.connect(self.detect_hardware)
        buttons.addWidget(self.btn_settings)
        buttons.addWidget(self.btn_detect)
        buttons.addStretch()
        connection.addLayout(buttons)

        # the viewer: what the unit holds, read-only
        viewer = QVBoxLayout()
        row = QHBoxLayout()
        self.btn_read_temporary = QPushButton("Read Temporary Patch")
        self.btn_read_temporary.setToolTip("Reads the patch the unit is playing now (read-only: nothing is written).")
        self.btn_read_temporary.clicked.connect(self.read_temporary)
        self.btn_open = QPushButton("Open .syx...")
        self.btn_open.clicked.connect(self.open_syx)
        self.btn_save = QPushButton("Save as .syx...")
        self.btn_save.clicked.connect(self.save_shown_patch)
        row.addWidget(self.btn_read_temporary)
        row.addWidget(self.btn_open)
        row.addWidget(self.btn_save)
        row.addStretch()
        viewer.addLayout(row)
        write_row = QHBoxLayout()
        self.btn_send = QPushButton("Send to Temporary Patch")
        self.btn_send.setToolTip("Plays the shown patch on the unit without storing it, then reads it back to check.")
        self.btn_send.clicked.connect(self.send_temporary)
        self.btn_write = QPushButton("Write to USER...")
        self.btn_write.setToolTip("Stores the shown patch in a USER slot. The slot's current patch is saved to a file first.")
        self.btn_write.clicked.connect(self.write_user)
        write_row.addWidget(self.btn_send)
        write_row.addWidget(self.btn_write)
        write_row.addStretch()
        viewer.addLayout(write_row)
        self.patch_label = QLabel("Nothing read yet.")
        self.patch_label.setWordWrap(True)
        viewer.addWidget(self.patch_label)
        self.problems_label = QLabel()
        self.problems_label.setWordWrap(True)
        self.problems_label.setObjectName("mutedLabel")
        viewer.addWidget(self.problems_label)
        edit_row = QHBoxLayout()
        self.live_check = QCheckBox("Hear edits on the unit as I make them")
        self.live_check.setChecked(True)
        self.live_check.setToolTip(
            "Each edit is sent to the unit's temporary patch (not stored) when you finish it, and read back. "
            "Works once the shown patch is on the unit's temporary patch: read it from there, or use Send to Temporary Patch."
        )
        self.live_check.toggled.connect(self._update_edit_hint)
        self.btn_revert = QPushButton("Revert Edits")
        self.btn_revert.setToolTip("Go back to the patch as it was read or opened.")
        self.btn_revert.clicked.connect(self.revert_edits)
        edit_row.addWidget(self.live_check)
        edit_row.addWidget(self.btn_revert)
        edit_row.addStretch()
        viewer.addLayout(edit_row)
        self.edit_hint = QLabel()
        self.edit_hint.setWordWrap(True)
        self.edit_hint.setObjectName("mutedLabel")
        viewer.addWidget(self.edit_hint)
        self.editor = PatchEditor()
        self.editor.setMinimumHeight(520)
        self.editor.param_committed.connect(self._on_param_committed)
        viewer.addWidget(self.editor)
        raw = QVBoxLayout()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Parameter", "Value", "Raw"])
        self.tree.setMinimumHeight(260)
        raw.addWidget(self.tree)

        library = QVBoxLayout()
        lib_row = QHBoxLayout()
        self.btn_read_names = QPushButton("Read USER Patch Names")
        self.btn_read_names.setToolTip("Reads the 128 USER patch names, one request each (read-only), and checks them against the factory list. Double-click a name to read that patch.")
        self.btn_read_names.clicked.connect(self.read_names)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.worker.cancel)
        self.names_progress = QProgressBar()
        self.names_progress.setVisible(False)
        lib_row.addWidget(self.btn_read_names)
        lib_row.addWidget(self.btn_cancel)
        lib_row.addWidget(self.names_progress, 1)
        library.addLayout(lib_row)
        self.stock_label = QLabel()
        self.stock_label.setWordWrap(True)
        self.stock_label.setObjectName("mutedLabel")
        library.addWidget(self.stock_label)
        self.names_list = QListWidget()
        self.names_list.setMinimumHeight(180)
        self.names_list.itemDoubleClicked.connect(self._read_user_from_item)
        library.addWidget(self.names_list)

        whole = QVBoxLayout()
        whole_row = QHBoxLayout()
        self.btn_backup = QPushButton("Back Up Unit...")
        self.btn_backup.setToolTip("Saves all USER patches, performances, rhythm sets and the system settings to one .syx file (read-only on the unit).")
        self.btn_backup.clicked.connect(self.back_up_unit)
        self.btn_restore = QPushButton("Restore Unit...")
        self.btn_restore.setToolTip("Writes a backup file back to the unit.")
        self.btn_restore.clicked.connect(self.restore_unit)
        whole_row.addWidget(self.btn_backup)
        whole_row.addWidget(self.btn_restore)
        whole_row.addStretch()
        whole.addLayout(whole_row)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(build_section_card("Connection", connection))
        layout.addWidget(build_section_card("Whole Unit", whole))
        layout.addWidget(build_section_card("Patch", viewer))
        self.raw_card = build_section_card("Raw Values", raw, collapse_key="main_window/Raw Values")
        self.raw_card.set_collapsed(True, remember=False)
        self.raw_card.collapsed_changed.connect(lambda collapsed: None if collapsed or self._shown is None else self._fill_tree(self._shown[1], validate.out_of_range(self._shown[1])))
        layout.addWidget(self.raw_card)
        layout.addWidget(build_section_card("USER Patches", library))
        layout.addStretch()
        self.setCentralWidget(build_scroll_area(page))

    # -- connection --------------------------------------------------------------------------------------------------------

    def _restore_saved_ports(self):
        """Reopen the ports used last time, if the system still offers them."""
        input_name, output_name = app_config.get_saved_ports()
        if not input_name or not output_name:
            return
        if input_name not in midi.list_input_names() or output_name not in midi.list_output_names():
            debug_log.get_logger().info(f"startup: the saved MIDI ports {input_name!r}/{output_name!r} are not available")
            self.statusBar().showMessage("The MIDI ports used last time are not available: choose them in Settings")
            return
        try:
            self.session.open(input_name, output_name)
        except Exception:
            debug_log.get_logger().error("startup: couldn't reopen the saved MIDI ports", exc_info=True)
            self.statusBar().showMessage("Couldn't open the saved MIDI ports: choose them in Settings")

    def _refresh_connection(self, *_):
        if self.session.is_open:
            self.connection_label.setText(f"MIDI input: {self.session.input_name}\nMIDI output: {self.session.output_name}")
        else:
            self.connection_label.setText("No MIDI ports are open. Choose the interface the JV-1010 is connected to in Settings.")
        idle = self.worker.is_idle()
        ready = self.session.is_open and idle
        for control in (self.btn_detect, self.detect_action, self.btn_read_temporary, self.read_action, self.btn_read_names):
            control.setEnabled(ready)
        for control in (self.btn_backup, self.backup_action, self.btn_restore, self.restore_action):
            control.setEnabled(ready)
        for control in (self.btn_send, self.send_action, self.btn_write, self.write_action):
            control.setEnabled(ready and self._shown is not None)
        for control in (self.btn_open, self.open_action):
            control.setEnabled(idle)
        self.btn_revert.setEnabled(self._shown is not None and self._is_dirty())
        for control in (self.btn_settings, self.settings_action):
            control.setEnabled(idle)  # Settings closes and reopens the connection: never under a running job
        self.btn_cancel.setVisible(self._long_job and not idle)
        self.names_progress.setVisible(self._long_job)
        self.btn_save.setEnabled(self._shown is not None)
        self.save_action.setEnabled(self._shown is not None)

    def open_settings(self):
        if not self.worker.is_idle():
            self.statusBar().showMessage("Wait for the read to finish first")
            return
        SettingsDialog(self.session, self).exec()

    def detect_hardware(self):
        if not self.session.is_open:
            QMessageBox.information(self, "Detect JV-1010", "Choose the MIDI ports in Settings first.")
            return
        set_enabled_without_scrolling(self.btn_detect, False)
        self.btn_detect.setText("Detecting...")
        QApplication.processEvents()
        try:
            result = midi_diagnostics.detect_hardware(self.session.connection, pump=QApplication.processEvents)
        except Exception as e:
            debug_log.get_logger().error("detect hardware failed", exc_info=True)
            QMessageBox.critical(self, "Detect JV-1010", f"Couldn't run the check: {e}")
            return
        finally:
            self.btn_detect.setEnabled(self.session.is_open and self.worker.is_idle())
            self.btn_detect.setText("Detect JV-1010")
        self.detect_results_label.setText(result.message)
        log = debug_log.get_logger()
        log.info(f"detect: {result.status}")
        for line in result.log_lines:
            log.info(f"detect: {line}")
        self.statusBar().showMessage("JV-1010 found" if result.found else "No JV-1010 found", 5000)

    # -- reading (read-only) -----------------------------------------------------------------------------------------------

    def read_temporary(self):
        if not self._confirm_discard():
            return
        self.statusBar().showMessage("Reading the temporary patch...")
        self.worker.submit("temporary")

    def read_names(self):
        self.names_list.clear()
        self.stock_label.clear()
        self._start_progress("Reading the USER patch names...")
        self.worker.submit("names")

    def _start_progress(self, message):
        self._long_job = True
        self.names_progress.setRange(0, 100)
        self.names_progress.setValue(0)
        self.statusBar().showMessage(message)

    def _read_user_from_item(self, item):
        number = item.data(Qt.ItemDataRole.UserRole)
        if number is not None and self.worker.is_idle() and self._confirm_discard():
            self.statusBar().showMessage(f"Reading USER:{number + 1:03d}...")
            self.worker.submit("user", number)

    def _on_progress(self, done, total):
        self.names_progress.setRange(0, total)
        self.names_progress.setValue(done)

    def _on_names_read(self, summaries):
        self._long_job = False
        self._summaries = list(summaries)
        self.names_list.clear()
        warning = QBrush(QColor(theme.current_palette()["warning"]))
        for number, ((status, factory), summary) in enumerate(zip(stock.compare(summaries), summaries)):
            item = QListWidgetItem(f"{number + 1:03d}  {summary.name}")
            item.setData(Qt.ItemDataRole.UserRole, number)
            if status == stock.DIFFERENT:
                item.setForeground(warning)
                item.setToolTip(f'The factory patch here is "{factory.name}" ({factory.key_assign}).')
            self.names_list.addItem(item)
        same = stock.count_same(summaries)
        self.stock_label.setText(
            f"{same} of {len(summaries)} match the factory patch list by name and key assign mode; the others are highlighted. "
            "A matching name does not prove the patch is unchanged."
        )
        self.statusBar().showMessage(f"Read {len(summaries)} USER patch names", 5000)
        self._refresh_connection()

    def _on_failed(self, label, message):
        self._long_job = False
        if label == "write_param":  # a live edit the unit didn't take: stop sending live (one message, not one per queued edit)
            if self.live_check.isChecked():
                self.live_check.setChecked(False)
                self._temp_synced = False
                debug_log.get_logger().warning(f"live edit failed, live sending switched off: {message}")
                QMessageBox.warning(self, "JV-1010", f"{message}\n\nLive sending is off. Send to Temporary Patch to try again.")
            self._refresh_connection()
            return
        self.statusBar().showMessage(message)
        QMessageBox.warning(self, "JV-1010", message)
        self._refresh_connection()

    def _on_patch_read(self, label, read, problems):
        base = patch.TEMPORARY_BASE if label == "temporary" else patch.user_base(int(label.split(":")[1]))
        where = "the temporary patch" if label == "temporary" else f"USER:{int(label.split(':')[1]) + 1:03d}"
        self._show_patch(label, read, base, problems, where)

    def _show_patch(self, label, read, base, problems, where):
        self._shown = (label, read, base)
        self._original = read.copy()
        self._where = where
        self._temp_synced = label == "temporary"
        self.editor.set_patch(read)
        self._update_patch_label()
        self._update_edit_hint()
        if problems:
            shown = "; ".join(str(p) for p in problems[:3])
            more = f" (and {len(problems) - 3} more)" if len(problems) > 3 else ""
            self.problems_label.setText(f"{len(problems)} value(s) outside the manual's ranges: {shown}{more}. Details are in the log.")
        else:
            self.problems_label.setText("Every value is inside the manual's ranges.")
        self._fill_tree(read, problems)
        self.statusBar().showMessage(f"Read {where}", 5000)
        self._refresh_connection()

    # -- editing the shown patch (the working copy) -------------------------------------------------------------------------

    def _is_dirty(self):
        return self._shown is not None and self._original is not None and self._shown[1] != self._original

    def _update_patch_label(self):
        if self._shown is None:
            return
        edited = "  (edited)" if self._is_dirty() else ""
        self.patch_label.setText(f'{self._where}: "{self._shown[1].name}"{edited}')

    def _update_edit_hint(self, *_):
        if self._shown is None:
            self.edit_hint.clear()
        elif not self.live_check.isChecked():
            self.edit_hint.setText("Edits stay in the editor until you send or write the patch.")
        elif self._temp_synced:
            self.edit_hint.setText("Edits are sent to the unit's temporary patch as you make them (not stored).")
        else:
            self.edit_hint.setText("Send to Temporary Patch to hear your edits: the unit is playing a different patch.")

    def _confirm_discard(self):
        """Edits would be lost by showing another patch: ask (default No). True to carry on."""
        if not self._is_dirty():
            return True
        answer = QMessageBox.question(
            self,
            "Discard edits?",
            f'"{self._shown[1].name}" has edits that are not written anywhere. Discard them?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _on_param_committed(self, block, key, tone, value):
        working = self._shown[1]
        self._update_patch_label()
        debug_log.get_logger().info(f"edit: {self._where} {block}{'' if tone < 0 else f' tone {tone + 1}'} {key} = {value!r}")
        if not self.raw_card.is_collapsed():
            self._fill_tree(working, validate.out_of_range(working))
        if self.live_check.isChecked() and self._temp_synced and self.session.is_open:
            self.worker.submit("write_param", block, key, None if tone < 0 else tone, value)
        self._update_edit_hint()
        self._refresh_connection()

    def _on_param_written(self, block, key, tone, value):
        self.statusBar().showMessage("Sent to the unit", 1500)

    def revert_edits(self):
        if self._shown is None or not self._is_dirty():
            return
        label, _, base = self._shown
        self._shown = (label, self._original.copy(), base)
        self.editor.set_patch(self._shown[1])
        self._update_patch_label()
        self._fill_tree(self._shown[1], validate.out_of_range(self._shown[1]))
        if self.live_check.isChecked() and self._temp_synced and self.session.is_open:
            self.statusBar().showMessage("Reverted. Send to Temporary Patch to put it back on the unit.")
            self._temp_synced = False  # the unit's temporary patch still holds the edits
        self._update_edit_hint()
        self._refresh_connection()

    def _fill_tree(self, read, problems):
        flagged = {(p.block, p.tone, p.key) for p in problems}
        warning = QBrush(QColor(theme.current_palette()["warning"]))
        table = params.load_table()
        self.tree.clear()
        groups = [(patch.COMMON, None, "Common", read.common)] + [(patch.TONE, i, f"Tone {i + 1}", t) for i, t in enumerate(read.tones)]
        for block_key, tone, title, buffer in groups:
            parent = QTreeWidgetItem([title])
            self.tree.addTopLevelItem(parent)
            for param in table.block(block_key).params:
                value = params.read(buffer, param)
                item = QTreeWidgetItem([param.name, params.format_value(param, value), repr(value) if param.string else str(value)])
                if (block_key, tone, param.key) in flagged:
                    for column in range(3):
                        item.setForeground(column, warning)
                parent.addChild(item)
            parent.setExpanded(tone is None)
        self.tree.resizeColumnToContents(0)

    def save_shown_patch(self):
        if self._shown is None:
            return
        label, read, base = self._shown
        suggested = "".join(c if c.isalnum() or c in " -_." else "_" for c in read.name).strip() or "patch"
        path, _ = QFileDialog.getSaveFileName(self, "Save patch as .syx", str(Path.home() / f"{suggested}.syx"), "SysEx files (*.syx)")
        if not path:
            return
        try:
            Path(path).write_bytes(read.to_syx(base))
        except OSError as e:
            debug_log.get_logger().error(f"couldn't save {path}", exc_info=True)
            QMessageBox.critical(self, "Save", f"Couldn't save the file: {e}")
            return
        debug_log.get_logger().info(f"saved {read.name!r} ({label}) to {path}")
        self.statusBar().showMessage(f"Saved {Path(path).name}", 5000)

    # -- opening a file ----------------------------------------------------------------------------------------------------

    def open_syx(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open patch .syx", str(Path.home()), "SysEx files (*.syx);;All files (*)")
        if not path:
            return
        try:
            found = patch.parse_syx(Path(path).read_bytes())
        except (OSError, sysex.SysexError) as e:
            debug_log.get_logger().error(f"couldn't open {path}", exc_info=True)
            QMessageBox.critical(self, "Open", f"Couldn't read the file: {e}")
            return
        if not found:
            QMessageBox.information(self, "Open", "That file holds no JV-1010 patch.")
            return
        bases = list(found)
        if len(bases) > 1:
            names = [f"{self._base_title(b)}  {found[b].name}" for b in bases]
            choice, ok = QInputDialog.getItem(self, "Open", f"The file holds {len(bases)} patches. Show:", names, 0, False)
            if not ok:
                return
            base = bases[names.index(choice)]
        else:
            base = bases[0]
        chosen = found[base]
        problems = validate.out_of_range(chosen)
        self._show_patch("file", chosen, base, problems, f"{Path(path).name} ({self._base_title(base)})")
        debug_log.get_logger().info(f"opened {path}: {len(bases)} patch(es), showing {chosen.name!r}")

    @staticmethod
    def _base_title(base):
        return "temporary patch" if base == patch.TEMPORARY_BASE else f"USER:{base[1] + 1:03d}"

    # -- writing to the unit -----------------------------------------------------------------------------------------------

    def _offer_backup_first(self, what):
        """Before the first change to the unit this session, offer a whole-unit backup. Returns True to carry on with `what`."""
        if self._backed_up:
            return True
        answer = QMessageBox.question(
            self,
            "Back up the unit first?",
            f"You haven't backed up the unit in this session. Back it up now, before {what}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Yes:
            self.back_up_unit()
            self.statusBar().showMessage("Backing up first: run it again when the backup is done")
            return False
        return True

    def send_temporary(self):
        if self._shown is None or not self.session.is_open or not self.worker.is_idle():
            return
        _, shown, _ = self._shown
        self.statusBar().showMessage(f'Sending "{shown.name}" to the temporary patch...')
        self._sent_snapshot = shown.copy()
        self.worker.submit("send_temporary", self._sent_snapshot)

    def write_user(self):
        if self._shown is None or not self.session.is_open or not self.worker.is_idle():
            return
        label, shown, base = self._shown
        default = base[1] if base[0] == 0x11 else 0
        names = [s.name for s in self._summaries]
        dialog = WriteUserDialog(shown.name, names, default, app_config.backups_dir(), self)
        if dialog.exec() != WriteUserDialog.DialogCode.Accepted:
            return
        number = dialog.slot()
        if not self._offer_backup_first(f"overwriting USER:{number + 1:03d}"):
            return
        self.statusBar().showMessage(f'Writing "{shown.name}" to USER:{number + 1:03d}...')
        self.worker.submit("write_user", number, shown.copy())

    def back_up_unit(self):
        if not self.session.is_open or not self.worker.is_idle():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Back up the unit", str(Path.home() / backup.default_backup_name()), "SysEx files (*.syx)")
        if not path:
            return
        self._start_progress("Backing up the unit...")
        self.worker.submit("backup", path)

    def restore_unit(self):
        if not self.session.is_open or not self.worker.is_idle():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Restore the unit from a backup", str(Path.home()), "SysEx files (*.syx);;All files (*)")
        if not path:
            return
        try:
            saved = backup.parse_backup(Path(path).read_bytes())
        except (OSError, sysex.SysexError) as e:
            debug_log.get_logger().error(f"couldn't read backup {path}", exc_info=True)
            QMessageBox.critical(self, "Restore", f"Couldn't read the file: {e}")
            return
        summary = saved.summary()
        if not any(have for have, _ in summary.values()):
            QMessageBox.information(self, "Restore", "That file holds no JV-1010 backup.")
            return
        dialog = RestoreDialog(summary, self)
        if dialog.exec() != RestoreDialog.DialogCode.Accepted:
            return
        sections = dialog.sections()
        if not self._offer_backup_first("restoring"):
            return
        self._start_progress("Restoring the unit...")
        self.worker.submit("restore", saved, sections)

    def _on_backup_done(self, path, size):
        self._long_job = False
        self._backed_up = True
        self.statusBar().showMessage(f"Backup saved: {Path(path).name} ({size // 1024} KB)", 8000)
        self._refresh_connection()

    def _on_restore_done(self, count):
        self._long_job = False
        self.statusBar().showMessage(f"Restored {count} blocks, each read back", 8000)
        self._refresh_connection()

    def _on_write_done(self, label, name, backup_path):
        if label == "temporary":
            self.statusBar().showMessage(f'"{name}" sent to the temporary patch and read back', 5000)
            # edits made while it was being sent are not on the unit: only a patch equal to what was sent counts as in step
            self._temp_synced = self._shown is not None and self._shown[1] == self._sent_snapshot
            self._update_edit_hint()
        else:
            number = int(label.split(":")[1])
            if self._shown is not None and self._shown[1].name == name:
                self._original = self._shown[1].copy()  # what is shown is now what USER:number holds
                self._update_patch_label()
            self.statusBar().showMessage(f'"{name}" written to USER:{number + 1:03d} and read back; the old patch is in {Path(backup_path).name}', 10000)
            if number < self.names_list.count():
                item = self.names_list.item(number)
                item.setText(f"{number + 1:03d}  {name}")
        self._refresh_connection()

    def _on_cancelled(self, label, message):
        self._long_job = False
        self.statusBar().showMessage(message, 8000)
        self._refresh_connection()

    def closeEvent(self, event):
        self.worker.cancel()
        self.worker.stop()
        self.worker.wait(3000)
        self.session.close()
        super().closeEvent(event)
