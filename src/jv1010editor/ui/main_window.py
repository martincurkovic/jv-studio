import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QBrush, QColor, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
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

from jv1010editor.core import app_config, debug_log, midi, midi_diagnostics, params, patch
from jv1010editor.ui import theme
from jv1010editor.ui.about_dialog import AboutDialog
from jv1010editor.ui.diagnostics_ui import add_open_log_folder_action
from jv1010editor.ui.midi_session import MidiSession
from jv1010editor.ui.qt_helpers import build_scroll_area, build_section_card, set_enabled_without_scrolling
from jv1010editor.ui.settings_dialog import SettingsDialog
from jv1010editor.ui.unit_worker import UnitWorker


class MainWindow(QMainWindow):
    """The application window. For now: the connection, a hardware check, and a READ-ONLY look at the unit's patches (nothing here writes to the unit).
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
        self.worker.progress.connect(self._on_progress)
        self.worker.failed.connect(self._on_failed)
        self.worker.busy_changed.connect(self._refresh_connection)
        self._shown = None  # (label, Patch) in the viewer
        self._reading_names = False

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
        self.save_action = QAction("Save Patch as .syx...", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self.save_shown_patch)
        file_menu.addAction(self.save_action)
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
        self.btn_save = QPushButton("Save as .syx...")
        self.btn_save.clicked.connect(self.save_shown_patch)
        row.addWidget(self.btn_read_temporary)
        row.addWidget(self.btn_save)
        row.addStretch()
        viewer.addLayout(row)
        self.patch_label = QLabel("Nothing read yet.")
        self.patch_label.setWordWrap(True)
        viewer.addWidget(self.patch_label)
        self.problems_label = QLabel()
        self.problems_label.setWordWrap(True)
        self.problems_label.setObjectName("mutedLabel")
        viewer.addWidget(self.problems_label)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Parameter", "Value", "Raw"])
        self.tree.setMinimumHeight(260)
        viewer.addWidget(self.tree)

        library = QVBoxLayout()
        lib_row = QHBoxLayout()
        self.btn_read_names = QPushButton("Read USER Patch Names")
        self.btn_read_names.setToolTip("Reads the 128 USER patch names, one request each (read-only). Double-click a name to read that patch.")
        self.btn_read_names.clicked.connect(self.read_names)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.worker.cancel)
        self.names_progress = QProgressBar()
        self.names_progress.setVisible(False)
        lib_row.addWidget(self.btn_read_names)
        lib_row.addWidget(self.btn_cancel)
        lib_row.addWidget(self.names_progress, 1)
        library.addLayout(lib_row)
        self.names_list = QListWidget()
        self.names_list.setMinimumHeight(180)
        self.names_list.itemDoubleClicked.connect(self._read_user_from_item)
        library.addWidget(self.names_list)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(build_section_card("Connection", connection))
        layout.addWidget(build_section_card("Temporary Patch", viewer))
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
        for control in (self.btn_settings, self.settings_action):
            control.setEnabled(idle)  # Settings closes and reopens the connection: never under a running job
        self.btn_cancel.setVisible(self._reading_names and not idle)
        self.names_progress.setVisible(self._reading_names)
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
        self.statusBar().showMessage("Reading the temporary patch...")
        self.worker.submit("temporary")

    def read_names(self):
        self.names_list.clear()
        self._reading_names = True
        self.names_progress.setRange(0, patch.USER_PATCH_COUNT)
        self.names_progress.setValue(0)
        self.statusBar().showMessage("Reading the USER patch names...")
        self.worker.submit("names")

    def _read_user_from_item(self, item):
        number = item.data(Qt.ItemDataRole.UserRole)
        if number is not None and self.worker.is_idle():
            self.statusBar().showMessage(f"Reading USER:{number + 1:03d}...")
            self.worker.submit("user", number)

    def _on_progress(self, done, total):
        self.names_progress.setRange(0, total)
        self.names_progress.setValue(done)

    def _on_names_read(self, names):
        self._reading_names = False
        self.names_list.clear()
        for number, name in enumerate(names):
            item = QListWidgetItem(f"{number + 1:03d}  {name}")
            item.setData(Qt.ItemDataRole.UserRole, number)
            self.names_list.addItem(item)
        self.statusBar().showMessage(f"Read {len(names)} USER patch names", 5000)
        self._refresh_connection()

    def _on_failed(self, label, message):
        self._reading_names = False
        self.statusBar().showMessage(message)
        QMessageBox.warning(self, "JV-1010", message)
        self._refresh_connection()

    def _on_patch_read(self, label, read, problems):
        self._shown = (label, read)
        where = "the temporary patch" if label == "temporary" else f"USER:{int(label.split(':')[1]) + 1:03d}"
        self.patch_label.setText(f'{where}: "{read.name}"')
        if problems:
            shown = "; ".join(str(p) for p in problems[:3])
            more = f" (and {len(problems) - 3} more)" if len(problems) > 3 else ""
            self.problems_label.setText(f"{len(problems)} value(s) outside the manual's ranges: {shown}{more}. Details are in the log.")
        else:
            self.problems_label.setText("Every value is inside the manual's ranges.")
        self._fill_tree(read, problems)
        self.statusBar().showMessage(f"Read {where}", 5000)
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
        label, read = self._shown
        base = patch.TEMPORARY_BASE if label == "temporary" else patch.user_base(int(label.split(":")[1]))
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

    def closeEvent(self, event):
        self.worker.cancel()
        self.worker.stop()
        self.worker.wait(3000)
        self.session.close()
        super().closeEvent(event)
