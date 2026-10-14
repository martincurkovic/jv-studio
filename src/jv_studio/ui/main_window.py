import sys
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QBrush, QColor, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from jv_studio.core import app_config, backup, debug_log, midi, midi_diagnostics, params, patch, patch_collection, stock, sysex, unit, universal, validate
from jv_studio.ui import theme
from jv_studio.ui.about_dialog import AboutDialog
from jv_studio.ui.audition_bar import AuditionBar
from jv_studio.ui.ascii_logo import LOGO, logo_font
from jv_studio.ui.diagnostics_ui import add_open_log_folder_action
from jv_studio.ui.firmware_dialog import FirmwareDialog
from jv_studio.ui.midi_session import MidiSession
from jv_studio.ui.patch_editor import PatchEditor
from jv_studio.ui.performance_panel import PerformancePanel
from jv_studio.ui.patch_collection_dialog import PatchCollectionDialog
from jv_studio.ui.rhythm_panel import RhythmPanel
from jv_studio.ui.qt_helpers import item_heading, set_enabled_without_scrolling
from jv_studio.ui.segmented import SegmentedControl
from jv_studio.ui.settings_dialog import SettingsDialog
from jv_studio.ui.system_dialog import SystemDialog
from jv_studio.ui.unit_dialogs import RenameDialog, RestoreDialog, SlotDialog, WriteUserDialog
from jv_studio.ui.unit_worker import UnitWorker


STATUS_BAR_MARGIN = 12  # px: the status bar's text keeps this far from the window's sides (and so from its rounded corners)


class MainWindow(QMainWindow):
    """The application window: the connection, a hardware check, a look at the unit's patches, whole-unit backup and restore, and the only two places
    that write to the unit: Send to Temporary Patch and Write to USER (both read back; the second saves the slot's old patch first).
    The editor itself arrives in phase 3 (dev_docs/roadmap.md)."""

    def __init__(self, session=None, worker=None, start_worker=True, demo=False, autoload=False):
        super().__init__()
        self._autoload_enabled = autoload  # read the names and the temporary patch / performance as soon as ports are open (the app turns it on; tests call what they need)
        self._autoload_ports = None  # the (input, output) the last auto-load ran for: reopening the same ports after a diagnostic does not read again
        self._autoload_steps = []  # [(job label, function that submits it)]
        self._sound_mode = None  # the unit's sound mode (0 performance, 1 patch, 2 GM) as of the last System read; None until one
        self._audition_timer = QTimer(self)  # a patch chosen in the audition bar is read back this long after the LAST choice (scrubbing with , and . must not read every patch)
        self._audition_timer.setSingleShot(True)
        self._audition_timer.timeout.connect(self._after_audition_choice)
        self._pending_check = None  # label ("user:N") of the patch just opened that the unit was told to select: the next step is to check that it did
        self._open_to_play = None  # label of a USER patch being read because it was double-clicked: when it arrives the unit is told to select it too
        self._announce_system = True  # the next System read is the From Unit button's (it says what it found); a refresh's is quiet
        self._loaded_tabs = set()  # the Performances (1) / Rhythm Sets (2) tabs that have been read from this unit: Refresh All refreshes those too
        self._autoload_force = False  # Refresh All was confirmed: read even a patch, performance or rhythm set with unsent edits
        self._autoload_job = None  # the label of the auto-load job in flight: its failure is a status line, not a dialog (a silent unit at startup is not an alarm)
        self.demo = demo  # a simulated unit on a fake connection (`--demo`): no real ports are listed, chosen or opened
        self.setWindowTitle("JV Studio (demo)" if demo else "JV Studio")
        self.setMinimumSize(1100, 700)
        self.resize(1260, 880)  # wide enough that the editor's pages need no horizontal scroll bar
        app_config.ensure_defaults_saved()
        self.session = session if session is not None else MidiSession()
        self.worker = worker if worker is not None else UnitWorker(self.session)
        self.session.changed.connect(self._refresh_connection)
        self.session.changed.connect(self._maybe_autoload)
        self.worker.patch_read.connect(self._on_patch_read)
        self.worker.names_read.connect(self._on_names_read)
        self.worker.name_read.connect(self._on_name_read)
        self.worker.performance_name_read.connect(self._on_performance_name_read)
        self.worker.performance_read.connect(self._end_progress)  # (connected before the panels', which refresh the window's state after this)
        self.worker.rhythm_read.connect(self._end_progress)
        self.worker.performance_names_read.connect(self._on_performance_names_read)
        self.worker.rhythm_names_read.connect(self._on_rhythm_names_read)
        self.worker.backup_done.connect(self._on_backup_done)
        self.worker.restore_done.connect(self._on_restore_done)
        self.worker.firmware_done.connect(self._on_firmware_done)
        self.worker.system_midi_read.connect(self._on_system_midi)
        self.worker.firmware_status.connect(self.statusBar().showMessage)
        self.worker.write_done.connect(self._on_write_done)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.param_written.connect(self._on_param_written)
        self.worker.progress.connect(self._on_progress)
        self.worker.failed.connect(self._autoload_stop)
        self.worker.failed.connect(self._on_failed)
        self.worker.busy_changed.connect(self._refresh_connection)
        self.worker.busy_changed.connect(self._autoload_next)
        self._shown = None  # (label, working Patch, base address); the patch is the WORKING COPY the editor changes; label is "temporary", "user:N" or "file"
        self._original = None  # what was read or opened, for Revert and for the "edited" mark
        self._sized_library = False
        self._where = ""  # how the shown patch is described ("USER:005")
        self._temp_synced = False  # the unit's temporary patch holds the working copy as it was last sent/read: only then can edits be heard live
        self._sent_snapshot = None  # a copy of the patch at the moment Send to Temporary Patch was queued
        self._long_job = False  # a job with a progress bar is running (names, backup, restore)
        self._cancellable = True  # ...and whether its Cancel button does anything
        self._summaries = []  # unit.PatchSummary of the USER patches read so far
        self._backed_up = False  # a whole-unit backup was saved in this session
        self.system_dialog = None  # built the first time System Settings is opened
        self._firmware_running = False  # Roland's update files are being played to the unit: closing the window or cancelling mid-way needs a second thought
        self._writing_shown_to = None  # the USER slot the shown (edited) patch is being written to, so its write_done marks it as stored
        self._undo = []  # steps of the shown patch's edits, each [(block, key, tone, old, new)]; cleared when another patch is shown
        self._redo = []

        self._build_menus()
        self._build_central()
        self.statusBar()
        if demo:
            note = QLabel("Demo: a simulated JV-1010. Changes are forgotten when you quit.")
            note.setObjectName("mutedLabel")
            self.statusBar().addPermanentWidget(note)
        else:
            self._restore_saved_ports()
        self._refresh_connection()
        if start_worker:
            self.worker.start()
        self._maybe_autoload()  # (a demo session is open from the start; real ports were opened just above, before the worker existed to queue on)

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

        edit_menu = self.menuBar().addMenu("&Edit")
        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self.undo)
        edit_menu.addAction(self.undo_action)
        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.triggered.connect(self.redo)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        self.revert_action = QAction("Revert Edits", self)
        self.revert_action.triggered.connect(self.revert_edits)
        edit_menu.addAction(self.revert_action)

        hardware_menu = self.menuBar().addMenu("&Hardware")
        self.detect_action = QAction("Detect JV-1010", self)
        self.detect_action.setShortcut("Ctrl+D")
        self.detect_action.triggered.connect(self.detect_hardware)
        hardware_menu.addAction(self.detect_action)
        self.read_action = QAction("Read Temporary Patch", self)
        self.read_action.setShortcut("Ctrl+R")
        self.read_action.triggered.connect(self.read_temporary)
        hardware_menu.addAction(self.read_action)
        self.refresh_action = QAction("Refresh All from Unit", self)
        self.refresh_action.setShortcut("Ctrl+Shift+R")
        self.refresh_action.setToolTip("Read the temporary patch, performance and rhythm set and the USER names again: for after something was changed on the unit's front panel.")
        self.refresh_action.triggered.connect(self.refresh_all)
        hardware_menu.addAction(self.refresh_action)
        hardware_menu.addSeparator()
        self.send_action = QAction("Send to Temporary Patch", self)
        self.send_action.setShortcut("Ctrl+Return")
        self.send_action.triggered.connect(self.send_temporary)
        hardware_menu.addAction(self.send_action)
        self.write_action = QAction("Write to USER...", self)
        self.write_action.triggered.connect(self.write_user)
        hardware_menu.addAction(self.write_action)
        hardware_menu.addSeparator()
        self.system_action = QAction("System Settings...", self)
        self.system_action.setToolTip("The unit's global settings: master tune, MIDI receive, controller sources, effect switches.")
        self.system_action.triggered.connect(self.open_system_settings)
        hardware_menu.addAction(self.system_action)
        self.gm_on_action = QAction("GM System On...", self)
        self.gm_on_action.setToolTip("Put the unit in General MIDI mode (the standard Universal SysEx message). While it is in GM mode this app can't read or write it.")
        self.gm_on_action.triggered.connect(self.gm_system_on)
        hardware_menu.addAction(self.gm_on_action)
        self.gm_off_action = QAction("GM System Off", self)
        self.gm_off_action.setToolTip("Take the unit out of GM mode: it returns to Performance mode, and this app can read and write it again.")
        self.gm_off_action.triggered.connect(self.gm_system_off)
        hardware_menu.addAction(self.gm_off_action)
        hardware_menu.addSeparator()
        self.firmware_action = QAction("Update Firmware... (unverified)", self)
        self.firmware_action.setToolTip("Plays Roland's System Update files to a unit in update mode. Never tried on a real JV-1010: use at your own risk.")
        self.firmware_action.triggered.connect(self.update_firmware)
        hardware_menu.addAction(self.firmware_action)

        view_menu = self.menuBar().addMenu("&View")
        self.audition_action = QAction("Audition Keyboard", self)
        self.audition_action.setCheckable(True)
        self.audition_action.setShortcut("Ctrl+K")  # (Cmd+K on a Mac)
        self.audition_action.setToolTip("Show or hide the keyboard along the bottom. Hidden, it plays nothing.")
        self.audition_action.triggered.connect(lambda checked: self.audition.set_open(checked, focus=checked))
        view_menu.addAction(self.audition_action)

        help_menu = self.menuBar().addMenu("&Help")
        add_open_log_folder_action(help_menu, self)
        about_action = QAction("About JV Studio...", self)
        about_action.setMenuRole(QAction.MenuRole.AboutRole)
        about_action.triggered.connect(lambda: AboutDialog(self).exec())
        help_menu.addAction(about_action)

    def _build_central(self):
        # top bar: the logo on the left, the connection on the right
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(15, 12, 15, 6)
        self.lbl_logo = QLabel(LOGO.strip("\n"))
        self.lbl_logo.setFont(logo_font())
        self.lbl_logo.setTextFormat(Qt.TextFormat.PlainText)
        self.lbl_logo.setWordWrap(False)
        self.lbl_logo.setStyleSheet("background: transparent;")
        top_bar.addWidget(self.lbl_logo)
        top_bar.addStretch()
        connection = QVBoxLayout()
        connection.setSpacing(4)
        self.connection_label = QLabel()
        self.connection_label.setObjectName("mutedLabel")
        self.connection_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.detect_results_label = QLabel()
        self.detect_results_label.setObjectName("mutedLabel")
        self.detect_results_label.setWordWrap(True)
        self.detect_results_label.setMaximumWidth(380)
        self.detect_results_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.btn_detect = QPushButton("Detect JV-1010")
        self.btn_detect.setToolTip("Asks the unit who it is and reads the name of its temporary patch. Nothing is written.")
        self.btn_detect.clicked.connect(self.detect_hardware)
        self.btn_settings = QPushButton("Settings...")
        self.btn_settings.setToolTip("Choose the MIDI ports, the theme, and run the loopback and hardware tests.")
        self.btn_settings.clicked.connect(self.open_settings)
        buttons.addWidget(self.btn_detect)
        buttons.addWidget(self.btn_settings)
        connection.addWidget(self.connection_label)
        connection.addWidget(self.detect_results_label)
        connection.addLayout(buttons)
        top_bar.addLayout(connection)

        # left: the unit's USER patches. right: the patch being edited
        library = QWidget()
        library_layout = QVBoxLayout(library)
        library_layout.setContentsMargins(15, 0, 6, 8)
        self.library_header = QLabel("USER Patches")
        self.library_header.setObjectName("sectionHeader")
        self.library_header.setToolTip("The unit's 128 user patches. Double-click (or press Enter) to open one; right-click to rename, copy or swap.")
        self.btn_read_names = QPushButton("Read Patch Names")
        self.btn_read_names.setToolTip(
            "Reads the 128 USER patch names, one request each (read-only), and checks them against the factory list. Double-click a patch to open it."
        )
        self.btn_read_names.clicked.connect(self.read_names)
        self.names_list = QListWidget()
        self.names_list.itemDoubleClicked.connect(self._read_user_from_item)
        self.names_list.itemActivated.connect(self._read_user_from_item)
        self.names_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.names_list.customContextMenuRequested.connect(self._names_context_menu)
        self.rename_action = QAction("Rename...", self.names_list)
        self.rename_action.setShortcut("F2")
        self.rename_action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        self.rename_action.triggered.connect(lambda: self.rename_user())
        self.names_list.addAction(self.rename_action)
        self.perf_list = QListWidget()
        self.perf_list.itemDoubleClicked.connect(self._open_perf_from_item)
        self.perf_list.itemActivated.connect(self._open_perf_from_item)
        self.rhythm_list = QListWidget()
        self.rhythm_list.itemDoubleClicked.connect(self._open_rhythm_from_item)
        self.rhythm_list.itemActivated.connect(self._open_rhythm_from_item)
        self.rhythm_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.rhythm_list.customContextMenuRequested.connect(self._rhythm_context_menu)
        self.list_stack = QStackedWidget()  # the USER patches, performances or rhythm sets, by mode
        self.list_stack.addWidget(self.names_list)
        self.list_stack.addWidget(self.perf_list)
        self.list_stack.addWidget(self.rhythm_list)
        library_layout.addWidget(self.library_header)
        library_layout.addWidget(self.btn_read_names)
        library_layout.addWidget(self.list_stack, 1)
        self.library = library  # a fixed width, as wide as the Patches / Performances switch (set when first shown)

        patch_panel = QWidget()
        panel = QVBoxLayout(patch_panel)
        panel.setContentsMargins(6, 0, 15, 8)
        self.patch_label = QLabel("No patch open. Read the temporary patch, double-click a USER patch, or open a .syx file.")
        self.patch_label.setObjectName("sectionHeader")
        self.patch_label.setWordWrap(True)
        self.problems_label = QLabel()
        self.problems_label.setWordWrap(True)
        self.problems_label.setObjectName("mutedLabel")
        self.problems_label.setVisible(False)
        actions = QHBoxLayout()
        self.btn_read_temporary = QPushButton("Read Temporary Patch")
        self.btn_read_temporary.setToolTip("Reads the patch the unit is playing now (read-only: nothing is written).")
        self.btn_read_temporary.clicked.connect(self.read_temporary)
        self.btn_send = QPushButton("Send to Temporary Patch")
        self.btn_send.setToolTip("Plays the shown patch on the unit without storing it, then reads it back to check.")
        self.btn_send.clicked.connect(self.send_temporary)
        self.btn_write = QPushButton("Write to USER...")
        self.btn_write.setToolTip("Stores the shown patch in a USER slot. The slot's current patch is saved to a file first.")
        self.btn_write.clicked.connect(self.write_user)
        self.btn_revert = QPushButton("Revert Edits")
        self.btn_revert.setToolTip("Go back to the patch as it was read or opened.")
        self.btn_revert.clicked.connect(self.revert_edits)
        for button in (self.btn_read_temporary, self.btn_send, self.btn_write, self.btn_revert):
            actions.addWidget(button)
        actions.addStretch()
        self.live_check = QCheckBox("Live edits")
        self.live_check.setChecked(True)
        self.live_check.setToolTip(
            "Hear your edits on the unit as you make them: each one is sent to its temporary patch (not stored) when you finish it, and read back. "
            "Works once the shown patch is on the temporary patch: read it from there, or use Send to Temporary Patch. Otherwise edits stay in the editor."
        )
        actions.insertWidget(actions.count() - 1, self.live_check)  # on the button row, after Revert Edits (before the stretch)
        self.editor = PatchEditor()
        self.editor.param_committed.connect(self._on_param_committed)
        self.editor.edits_recorded.connect(self._on_edits_recorded)
        self.tree = QTreeWidget()  # the last tab of the editor: every value as the unit holds it
        self.tree.setHeaderLabels(["Parameter", "Value", "Raw"])
        self.editor.add_extra_tab(self.tree, "Raw Values")
        self.editor.tabs.currentChanged.connect(lambda _i: self._refresh_tree_if_shown())
        panel.addWidget(self.patch_label)
        panel.addWidget(self.problems_label)
        panel.addLayout(actions)
        panel.addWidget(self.editor, 1)

        self.performance_panel = PerformancePanel(self)
        self.performance_panel.slot_changed.connect(self._perf_slot_changed)
        self.rhythm_panel = RhythmPanel(self)
        self.rhythm_panel.slot_changed.connect(self._rhythm_slot_changed)
        self.right_stack = QStackedWidget()  # the patch, performance or rhythm set editor, by mode
        self.right_stack.addWidget(patch_panel)
        self.right_stack.addWidget(self.performance_panel)
        self.right_stack.addWidget(self.rhythm_panel)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(library)
        body.addWidget(self.right_stack, 1)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addLayout(top_bar)
        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(15, 0, 15, 6)
        self.mode_tabs = SegmentedControl(
            ["Patches", "Performances", "Rhythm Sets"],
            [
                "Edit single patches (the unit's Patch mode).",
                "Edit performances: 16 parts, each playing a patch (the unit's Performance mode).",
                "Edit the two USER rhythm sets: a drum kit with its own sound on each of 64 keys (played by Part 10).",
            ],
        )
        self.mode_tabs.currentChanged.connect(self._set_mode)
        mode_row.addWidget(self.mode_tabs)
        mode_row.addStretch()
        central_layout.addLayout(mode_row)
        central_layout.addLayout(body, 1)
        self.audition = AuditionBar()  # the keyboard and patch browser along the bottom
        self.audition.set_demo(self.demo)
        self.audition.midi_out.connect(self._send_midi)
        self.audition.patch_chosen.connect(self._on_audition_patch)
        self.audition.unit_settings_requested.connect(self._read_unit_midi_settings)
        self.audition.master_volume_changed.connect(self._on_master_volume)
        central_layout.addWidget(self.audition)
        self.audition_action.setChecked(self.audition.is_open())
        self.audition.open_changed.connect(self.audition_action.setChecked)
        self.setCentralWidget(central)

        # progress of a long job (names, backup, restore) lives in the status bar, where it is visible from any page
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setToolTip("Stop after the current step. A cancelled backup saves nothing; a cancelled restore leaves the unit part way through.")
        self.btn_cancel.clicked.connect(self._cancel_job)
        self.names_progress = QProgressBar()
        self.names_progress.setMaximumWidth(220)
        self.btn_cancel.setVisible(False)
        self.names_progress.setVisible(False)
        self.statusBar().setSizeGripEnabled(False)  # the square in the corner: macOS windows have no grip
        self.statusBar().setContentsMargins(STATUS_BAR_MARGIN, 0, STATUS_BAR_MARGIN, 0)  # (the window's rounded corners clip text set against the edge)
        self.statusBar().addPermanentWidget(self.names_progress)
        self.statusBar().addPermanentWidget(self.btn_cancel)

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
        # the ports themselves are shown in Settings; here only the prompt when there are none
        self.connection_label.setText("No MIDI ports are open. Choose the interface the JV-1010 is connected to in Settings.")
        self.connection_label.setVisible(not self.session.is_open)
        idle = self.worker.is_idle()
        ready = self.session.is_open and idle
        for control in (self.btn_detect, self.detect_action, self.btn_read_temporary, self.read_action, self.btn_read_names):
            control.setEnabled(ready)
        for control in (self.backup_action, self.restore_action):
            control.setEnabled(ready)
        for control in (self.gm_on_action, self.gm_off_action):
            control.setEnabled(ready)
        self.firmware_action.setEnabled(ready and not self.demo)  # (a simulated unit has no update mode)
        if self.system_dialog is not None:
            self.system_dialog.refresh_state(ready)
        for control in (self.btn_send, self.send_action, self.btn_write, self.write_action):
            control.setEnabled(ready and self._shown is not None)
        self.open_action.setEnabled(idle)
        self.btn_revert.setEnabled(self._shown is not None and self._is_dirty())
        self.performance_panel.refresh_state(ready)
        self.rhythm_panel.refresh_state(ready)
        panel = self._side_panel()  # the menu acts on whichever editor is showing
        shown = panel.has_shown() if panel else self._shown is not None
        for control in (self.send_action, self.write_action):
            control.setEnabled(ready and shown)
        self.read_action.setEnabled(ready)
        self.refresh_action.setEnabled(ready)
        self.revert_action.setEnabled(panel.is_dirty() if panel else self.btn_revert.isEnabled())
        self.undo_action.setEnabled(panel.can_undo() if panel else bool(self._undo))
        self.redo_action.setEnabled(panel.can_redo() if panel else bool(self._redo))
        for control in (self.btn_settings, self.settings_action):
            control.setEnabled(idle)  # Settings closes and reopens the connection: never under a running job
        self.audition.set_available(
            self.session.is_open and not self._long_job,
            "Open the MIDI ports in Settings to play the unit." if not self.session.is_open else "Busy: the keyboard is off until the job is done.",
        )
        self.btn_cancel.setVisible(self._long_job and self._cancellable and not idle)
        self.names_progress.setVisible(self._long_job)
        self.save_action.setEnabled(shown)

    # -- the two modes -----------------------------------------------------------------------------------------------------

    def _performance_mode(self):
        return self.mode_tabs.currentIndex() == 1

    def _side_panel(self):
        """The performance or rhythm set panel when one is showing (the menu and the buttons act on it), None in Patches mode."""
        return {1: self.performance_panel, 2: self.rhythm_panel}.get(self.mode_tabs.currentIndex())

    _MODES = {
        0: ("USER Patches", "The unit's 128 user patches. Double-click (or press Enter) to open one; right-click to rename, copy or swap.",
            "Read Patch Names", "Reads the 128 USER patch names, one request each (read-only), and checks them against the factory list. Double-click a patch to open it.", "Patch"),
        1: ("USER Performances", "The unit's 32 user performances. Double-click (or press Enter) to open one.",
            "Read Performance Names", "Reads the 32 USER performance names, one request each (read-only). Double-click a performance to open it.", "Performance"),
        2: ("USER Rhythm Sets", "The unit's 2 user rhythm sets. Double-click (or press Enter) to open one; right-click to choose it on the unit.",
            "Read Rhythm Set Names", "Reads the 2 USER rhythm set names (read-only). Double-click a set to open it.", "Rhythm Set"),
    }

    def _set_mode(self, index):
        """Patches, Performances or Rhythm Sets: swap the list and the editor, and say what the menu and buttons now act on."""
        header, header_tip, button, button_tip, noun = self._MODES[index]
        self.list_stack.setCurrentIndex(index)
        self.right_stack.setCurrentIndex(index)
        self.library_header.setText(header)
        self.library_header.setToolTip(header_tip)
        self.btn_read_names.setText(button)
        self.btn_read_names.setToolTip(button_tip)
        self.open_action.setText(f"Open {noun} .syx...")
        self.save_action.setText(f"Save {noun} as .syx...")
        self.read_action.setText(f"Read Temporary {noun}")
        self.send_action.setText(f"Send to Temporary {noun}")
        self._refresh_connection()
        self._load_tab(index)

    def _open_rhythm_from_item(self, item):
        self.rhythm_panel.open_user(item.data(Qt.ItemDataRole.UserRole))

    def _rhythm_context_menu(self, pos):
        item = self.rhythm_list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        select = menu.addAction("Choose on Unit (Part 10)")
        select.setEnabled(self.session.is_open and not self._long_job)
        if menu.exec(self.rhythm_list.viewport().mapToGlobal(pos)) is select:
            self.rhythm_panel.select_on_unit(item.data(Qt.ItemDataRole.UserRole))

    def _on_rhythm_names_read(self, names):
        self.rhythm_list.clear()
        for number, name in enumerate(names):
            item = QListWidgetItem(f"{number + 1}  {name}")
            item.setData(Qt.ItemDataRole.UserRole, number)
            self.rhythm_list.addItem(item)
        self.rhythm_panel.set_names(names)
        self.statusBar().showMessage(f"Read {len(names)} USER rhythm set names", 5000)
        self._refresh_connection()

    def _rhythm_slot_changed(self, number, name):
        if number < self.rhythm_list.count():
            self.rhythm_list.item(number).setText(f"{number + 1}  {name}")

    def _open_perf_from_item(self, item):
        self.performance_panel.open_user(item.data(Qt.ItemDataRole.UserRole))

    def _on_performance_name_read(self, number, name):
        """One USER performance name arrived: it joins the list at once."""
        item = QListWidgetItem(f"{number + 1:02d}  {name}")
        item.setData(Qt.ItemDataRole.UserRole, number)
        self.perf_list.addItem(item)

    def _on_performance_names_read(self, names):
        self._long_job = False
        if self.perf_list.count() != len(names):  # (they were not shown as they came: show them now)
            self.perf_list.clear()
            for number, name in enumerate(names):
                item = QListWidgetItem(f"{number + 1:02d}  {name}")
                item.setData(Qt.ItemDataRole.UserRole, number)
                self.perf_list.addItem(item)
        self.performance_panel.set_names(names)
        self.statusBar().showMessage(f"Read {len(names)} USER performance names", 5000)
        self._refresh_connection()

    def _perf_slot_changed(self, number, name):
        if number < self.perf_list.count():
            self.perf_list.item(number).setText(f"{number + 1:02d}  {name}")

    def open_settings(self):
        if self.demo:
            QMessageBox.information(self, "Settings", "Demo mode uses a simulated JV-1010, so there are no MIDI ports to choose. Start JV Studio without --demo to use a real unit.")
            return
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
        if panel := self._side_panel():
            return panel.read_temporary()
        if not self._confirm_discard():
            return
        self.statusBar().showMessage("Reading the temporary patch...")
        self.worker.submit("temporary")

    def read_names(self):
        {0: self._read_patch_names, 1: self._read_performance_names, 2: self._read_rhythm_names}[self.mode_tabs.currentIndex()]()

    def _read_rhythm_names(self):
        self.rhythm_list.clear()
        self.statusBar().showMessage("Reading the USER rhythm set names...")
        self.worker.submit("rhythm_names")

    def _read_performance_names(self):
        self.perf_list.clear()
        self._start_progress("Reading the USER performance names...")
        self.worker.submit("perf_names")

    def _read_patch_names(self):
        self.names_list.clear()
        self._summaries = []
        self._start_progress("Reading the USER patch names...")
        self.worker.submit("names")

    # -- reading everything at startup -------------------------------------------------------------------------------------

    def _maybe_autoload(self, *_):
        """When ports are open (at startup, or newly chosen in Settings), read what is needed to start editing PATCHES: the temporary patch, which patch the unit has selected and the USER
        patch names, one job after another. The performance and rhythm set sides are read the first time their tab is opened (`_load_tab`), so a start-up is as short as it can be.
        Reads only; it stops at the first failure (a silent unit is not asked three more times)."""
        if not self._autoload_enabled or not self.session.is_open:
            return
        ports = (self.session.input_name, self.session.output_name)
        if ports == self._autoload_ports:
            return
        self._autoload_ports = ports
        self._loaded_tabs = set()  # a new connection: the other tabs have not been read from THIS unit yet
        self._autoload_steps = self._reload_plan()
        self._autoload_next()

    def _tab_steps(self, index):
        """What the Performances (1) or Rhythm Sets (2) tab needs read: its temporary performance / rhythm set first (to start editing), then the USER names."""
        return {
            1: [("perf_temporary", self._autoload_performance), ("perf_names", self._read_performance_names)],
            2: [("rhythm_temporary", self._autoload_rhythm), ("rhythm_names", self._read_rhythm_names)],
        }.get(index, [])

    def _reload_plan(self):
        """The patches, always, then every other tab that has been opened (or is open now): what Refresh All and a new connection read."""
        plan = [("temporary", self._autoload_patch), ("system_midi", self._autoload_selection), ("names", self._read_patch_names)]
        for index in sorted(self._loaded_tabs | {self.mode_tabs.currentIndex()}):
            plan += self._tab_steps(index)
            self._loaded_tabs.add(index)
        return plan

    def _load_tab(self, index):
        """The first time the Performances or Rhythm Sets tab is shown with a unit connected: read its side now (queued behind anything still running)."""
        if not self._autoload_enabled or not self.session.is_open or index in self._loaded_tabs or not self._tab_steps(index):
            return
        self._loaded_tabs.add(index)
        self._autoload_steps.extend(self._tab_steps(index))
        self._autoload_next()

    def refresh_all(self):
        """Read everything the start-up read again (the unit does not announce changes made on its front panel, so this is how the window catches up): the temporary patch, performance and
        rhythm set and the USER names. Edits that were never sent or written are asked about first (default No keeps them: only the names are then refreshed)."""
        if not self.session.is_open or not self.worker.is_idle() or self._firmware_running:
            return
        unsent = [what for what, dirty in (("patch", self._is_dirty()), ("performance", self.performance_panel.is_dirty()), ("rhythm set", self.rhythm_panel.is_dirty())) if dirty]
        self._autoload_force = False
        if unsent:
            answer = QMessageBox.question(
                self, "Refresh from the unit",
                f"The {' and '.join(unsent)} you are editing has changes that were not written to the unit. Discard them and read the unit's version?\n\nNo keeps your changes and only refreshes the rest.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
            )
            self._autoload_force = answer == QMessageBox.StandardButton.Yes
        else:
            self._autoload_force = True
        self.statusBar().showMessage("Reading the unit again...")
        self._autoload_steps = self._reload_plan()
        self._autoload_next()

    def _autoload_next(self, *_):
        """The worker went idle: start the next step (a step that doesn't apply is skipped)."""
        while self._autoload_steps and self.worker.is_idle():
            self._autoload_job, step = self._autoload_steps.pop(0)
            if step() is not False:
                return
        if not self._autoload_steps and self.worker.is_idle():
            self._autoload_job = None
            self._autoload_force = False

    def _autoload_stop(self, *_):
        self._autoload_steps.clear()
        self._autoload_force = False

    def _autoload_patch(self):
        if self._shown is not None and self._is_dirty() and not self._autoload_force:  # never over someone's edits
            return False
        self.statusBar().showMessage("Reading the temporary patch...")
        self.worker.submit("temporary")

    def _autoload_rhythm(self):
        if self.rhythm_panel.has_shown() and self.rhythm_panel.is_dirty() and not self._autoload_force:
            return False
        self._start_progress("Reading the temporary rhythm set...", cancellable=False)
        self.worker.submit("rhythm_temporary")

    def _autoload_performance(self):
        if self.performance_panel.has_shown() and self.performance_panel.is_dirty() and not self._autoload_force:
            return False
        self._start_progress("Reading the temporary performance...", cancellable=False)
        self.worker.submit("perf_temporary")

    def _start_progress(self, message, cancellable=True):
        """A read with a progress bar in the status bar. `cancellable` False for the whole-performance and whole-rhythm-set reads (a second or two, and not interruptible)."""
        self._long_job = True
        self._cancellable = cancellable
        self.names_progress.setRange(0, 100)
        self.names_progress.setValue(0)
        self.statusBar().showMessage(message)

    def _end_progress(self, *_):
        """A performance or a rhythm set arrived: the progress bar goes (the panel that asked shows it)."""
        self._long_job = False
        self._refresh_connection()

    def _read_user_from_item(self, item):
        number = item.data(Qt.ItemDataRole.UserRole)
        if number is not None and self.worker.is_idle() and self._confirm_discard():
            self.statusBar().showMessage(f"Reading USER:{number + 1:03d}...")
            self._open_to_play = f"user:{number}"  # (when it arrives the unit is told to play it too: see `_on_patch_read`)
            self.worker.submit("user", number)

    def _on_progress(self, done, total):
        self.names_progress.setRange(0, total)
        self.names_progress.setValue(done)

    def _on_name_read(self, number, summary):
        """One USER patch name arrived: it joins the list at once, so the list fills up while the rest is read."""
        if number == 0:
            self._summaries = []
        self._summaries.append(summary)
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, number)
        self.names_list.addItem(item)
        self._style_name_row(item, number)

    def _on_names_read(self, summaries):
        self._long_job = False
        self._summaries = list(summaries)
        self.performance_panel.set_user_patch_names([s.name for s in summaries])
        self.audition.set_user_names([s.name for s in summaries])
        if self.names_list.count() != len(summaries):  # (they were not shown as they came: show them now)
            self.names_list.clear()
            for number in range(len(summaries)):
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, number)
                self.names_list.addItem(item)
        for number in range(len(summaries)):
            self._style_name_row(self.names_list.item(number), number)
        differing = len(summaries) - stock.count_same(summaries)
        note = f"; {differing} differ from the factory list (highlighted)" if differing else "; all match the factory list"
        self.statusBar().showMessage(f"Read {len(summaries)} USER patch names{note}", 8000)
        self._refresh_connection()

    def _on_failed(self, label, message):
        self._long_job = False
        if label == "firmware":
            self._firmware_running = False
        if label in ("temporary_follow", "check_temporary"):  # started by the window, not by a click: a status line, not a dialog
            self._pending_check = None
            self.statusBar().showMessage(f"Couldn't read the patch the unit now plays: {message}", 10000)
            self._refresh_connection()
            return
        if label == "perf_write_param":
            self.performance_panel.on_live_failed(message)
            return
        if label in ("rhythm_write_param", "rhythm_write_note"):
            self.rhythm_panel.on_live_failed(message)
            return
        if label == "write_param":  # a live edit the unit didn't take: stop sending live (one message, not one per queued edit)
            if self.live_check.isChecked():
                self.live_check.setChecked(False)
                self._temp_synced = False
                debug_log.get_logger().warning(f"live edit failed, live sending switched off: {message}")
                QMessageBox.warning(self, "JV-1010", f"{message}\n\nLive sending is off. Send to Temporary Patch to try again.")
            self._refresh_connection()
            return
        if label == self._autoload_job:
            self._autoload_job = None
            debug_log.get_logger().warning(f"auto-load of {label} failed: {message}")
            self.statusBar().showMessage(f"Couldn't read the unit at startup: {message}", 12000)
            self._refresh_connection()
            return
        self.statusBar().showMessage(message)
        QMessageBox.warning(self, "JV-1010", message)
        self._refresh_connection()

    def _on_patch_read(self, label, read, problems):
        if label == "check":
            return self._on_follow_checked(read)
        base = patch.TEMPORARY_BASE if label == "temporary" else patch.user_base(int(label.split(":")[1]))
        where = "the temporary patch" if label == "temporary" else f"USER:{int(label.split(':')[1]) + 1:03d}"
        self._show_patch(label, read, base, problems, where)
        if label == self._open_to_play:
            self._open_to_play = None
            self._play_shown_on_unit(int(label.split(":")[1]))

    def _show_patch(self, label, read, base, problems, where):
        self._shown = (label, read, base)
        self._original = read.copy()
        self._where = where
        self._temp_synced = label == "temporary"
        self._undo.clear()
        self._redo.clear()
        self.editor.set_patch(read)
        self._update_patch_label()
        if problems:
            shown = "; ".join(str(p) for p in problems[:3])
            more = f" (and {len(problems) - 3} more)" if len(problems) > 3 else ""
            self.problems_label.setText(f"{len(problems)} value(s) outside the manual's ranges: {shown}{more}. Details are in the log.")
        else:
            self.problems_label.clear()
        self.problems_label.setVisible(bool(problems))
        if self.editor.tabs.currentWidget() is self.tree:
            self._fill_tree(read, problems)
        self.statusBar().showMessage(f"Read {where}", 5000)
        self._refresh_connection()

    # -- editing the shown patch (the working copy) -------------------------------------------------------------------------

    def _is_dirty(self):
        return self._shown is not None and self._original is not None and self._shown[1] != self._original

    def _update_patch_label(self):
        if self._shown is None:
            return
        self.patch_label.setText(item_heading(self._where, self._shown[1].name, self._is_dirty()))

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
        self._update_patch_label()
        debug_log.get_logger().info(f"edit: {self._where} {block}{'' if tone < 0 else f' tone {tone + 1}'} {key} = {value!r}")
        self._refresh_tree_if_shown()
        if self.live_check.isChecked() and self._temp_synced and self.session.is_open:
            self.worker.submit("write_param", block, key, None if tone < 0 else tone, value)
        self._refresh_connection()

    UNDO_LIMIT = 200

    def _on_edits_recorded(self, edits):
        self._undo.append(edits)
        del self._undo[: -self.UNDO_LIMIT]
        self._redo.clear()  # a new edit ends the redo line
        self._refresh_connection()

    def undo(self):
        if panel := self._side_panel():
            return panel.undo()
        self._step(self._undo, self._redo, reverse=True)

    def redo(self):
        if panel := self._side_panel():
            return panel.redo()
        self._step(self._redo, self._undo, reverse=False)

    def _step(self, take_from, put_on, reverse):
        """Undo or redo one gesture: put the old (or new) values back in the working copy, show them, and send them live like any edit."""
        if self._shown is None or not take_from:
            return
        edits = take_from.pop()
        working = self._shown[1]
        for block, key, tone, old, new in (reversed(edits) if reverse else edits):
            value = old if reverse else new
            working.set(block, key, value, tone=None if tone < 0 else tone)
            if self.live_check.isChecked() and self._temp_synced and self.session.is_open:
                self.worker.submit("write_param", block, key, None if tone < 0 else tone, value)
        put_on.append(edits)
        self.editor.refresh()
        self._update_patch_label()
        self._refresh_tree_if_shown()
        debug_log.get_logger().info(f"{'undo' if reverse else 'redo'}: {len(edits)} value(s) on {self._where}")
        self._refresh_connection()

    def _on_param_written(self, block, key, tone, value):
        self.statusBar().showMessage("Sent to the unit", 1500)

    def revert_edits(self):
        if panel := self._side_panel():
            return panel.revert_edits()
        if self._shown is None or not self._is_dirty():
            return
        label, _, base = self._shown
        self._shown = (label, self._original.copy(), base)
        self._undo.clear()
        self._redo.clear()
        self.editor.set_patch(self._shown[1])
        self._update_patch_label()
        self._refresh_tree_if_shown()
        if self.live_check.isChecked() and self._temp_synced and self.session.is_open:
            self.statusBar().showMessage("Reverted. Send to Temporary Patch to put it back on the unit.")
            self._temp_synced = False  # the unit's temporary patch still holds the edits
        self._refresh_connection()

    def _refresh_tree_if_shown(self):
        """The Raw Values tab is only rebuilt while it is showing (it is ~190 rows per edit otherwise)."""
        if self._shown is not None and self.editor.tabs.currentWidget() is self.tree:
            working = self._shown[1]
            self._fill_tree(working, validate.out_of_range(working))

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
        if panel := self._side_panel():
            return panel.save_syx()
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
        if panel := self._side_panel():
            return panel.open_syx()
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open patch .syx", str(Path.home()), "SysEx files (*.syx);;All files (*)")
        if not path:
            return
        try:
            found = patch_collection.parse(Path(path).read_bytes())
        except OSError as e:
            debug_log.get_logger().error(f"couldn't open {path}", exc_info=True)
            QMessageBox.critical(self, "Open", f"Couldn't read the file: {e}")
            return
        log = debug_log.get_logger()
        log.info(f"opened {path}: {len(found.entries)} patch(es), {found.repaired} with a wrong checksum used as they are, {found.damaged} damaged, {found.blank} blank, "
                 f"{found.incomplete} incomplete, {found.ignored} other message(s) ignored, {found.unusable} unusable")
        if not found.entries or not (found.offered(show_blank=True)):
            QMessageBox.information(self, "Open", "That file holds no JV-1010 patch." if not found.entries else "The patches in that file look damaged (wrong checksums and values outside the manual's ranges).")
            return
        if len(found.entries) == 1:
            entry = found.entries[0]
        else:
            dialog = PatchCollectionDialog(found, Path(path).name, self)
            if dialog.exec() != PatchCollectionDialog.DialogCode.Accepted:
                return
            entry = dialog.chosen()
        label = f"{Path(path).name} ({self._base_title(entry.base)})" if len(found.entries) == 1 else f"{Path(path).name} #{entry.index}"
        self._show_patch("file", entry.patch, entry.base, entry.problems, label)
        if entry.repaired:
            self.statusBar().showMessage(f'Opened "{entry.patch.name.strip()}": the file had wrong checksums on it ({entry.repaired} of 5 messages); the values are in range, so it was used as it is.', 12000)

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
        if panel := self._side_panel():
            return panel.send_temporary()
        if self._shown is None or not self.session.is_open or not self.worker.is_idle():
            return
        _, shown, _ = self._shown
        self.statusBar().showMessage(f'Sending "{shown.name}" to the temporary patch...')
        self._sent_snapshot = shown.copy()
        self.worker.submit("send_temporary", self._sent_snapshot)

    def write_user(self):
        if panel := self._side_panel():
            return panel.write_user()
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
        self._writing_shown_to = number
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

    def open_system_settings(self):
        if self.system_dialog is None:
            self.system_dialog = SystemDialog(self)
        self.system_dialog.show()
        self.system_dialog.raise_()
        self.system_dialog.activateWindow()
        self.system_dialog.refresh_state(self.session.is_open and self.worker.is_idle())
        if not self.system_dialog.has_shown() and self.session.is_open and self.worker.is_idle():
            self.system_dialog.read()  # (a read: the first look at what the unit holds)

    def update_firmware(self):
        if self.demo or not self.session.is_open or not self.worker.is_idle():
            return
        dialog = FirmwareDialog(self)
        if dialog.exec() != FirmwareDialog.DialogCode.Accepted:
            return
        update = dialog.firmware()
        if update is None or not update.ok:
            return
        debug_log.get_logger().warning(f"firmware update confirmed by the user: {update.release or 'unrecognised release'} from {update.folder}")
        self._firmware_running = True
        self._start_progress("Updating the firmware...")
        self.worker.submit("firmware", update)

    def _cancel_job(self):
        if self._firmware_running:
            answer = QMessageBox.warning(
                self,
                "Stop the firmware update?",
                "The unit is part-way through an update. Stopping now may leave it unable to start; you would have to play the update again from the first block.\n\nStop anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.worker.cancel()

    def _on_firmware_done(self, blocks, messages):
        self._long_job = False
        self._firmware_running = False
        self.statusBar().showMessage(f"Firmware sent: {blocks} files, {messages:,} messages", 10000)
        QMessageBox.information(
            self,
            "Firmware sent",
            f"All {blocks} files ({messages:,} messages) were sent. The unit sends no reply, so this app can't tell whether it was accepted.\n\n"
            "Switch the unit off and on. If it starts, do a Factory Reset (all user data is erased), then restore your backup. "
            "Record what happened in AGENTS.md: this has never been tried on a real unit.",
        )
        self._refresh_connection()

    def _on_restore_done(self, count):
        self._long_job = False
        self.statusBar().showMessage(f"Restored {count} blocks, each read back", 8000)
        self._refresh_connection()

    def _on_write_done(self, label, name, backup_path):
        if label.startswith(("perf:", "rhythm:")):
            return  # a performance or a rhythm set: its panel handles it
        if label == "temporary":
            self.statusBar().showMessage(f'"{name}" sent to the temporary patch and read back', 5000)
            # edits made while it was being sent are not on the unit: only a patch equal to what was sent counts as in step
            self._temp_synced = self._shown is not None and self._shown[1] == self._sent_snapshot
        else:
            number = int(label.split(":")[1])
            if self._writing_shown_to == number and self._shown is not None:
                self._original = self._shown[1].copy()  # what is shown is now what USER:number holds
                self._update_patch_label()
            elif self._shown is not None and self._shown[0] == label and not self._is_dirty():
                self.worker.submit("user", number)  # a rename, copy or swap changed the slot that is open: show what it holds now
            self._writing_shown_to = None
            self.statusBar().showMessage(f'USER:{number + 1:03d} is now "{name}" (read back); the old patch is in {Path(backup_path).name}', 10000)
            self._slot_changed(number, name)
        self._refresh_connection()

    def _slot_changed(self, number, name):
        """A USER slot now holds a patch called `name`: update the list row (its text and the factory comparison)."""
        if number < len(self._summaries):
            self._summaries[number] = unit.PatchSummary(name, self._summaries[number].key_assign)
            self.performance_panel.set_user_patch_names(self._names())
            self.audition.set_user_names(self._names())
        if number < self.names_list.count():
            self._style_name_row(self.names_list.item(number), number)

    def _style_name_row(self, item, number):
        summary = self._summaries[number] if number < len(self._summaries) else None
        if summary is None:
            return
        item.setText(f"{number + 1:03d}  {summary.name}")
        status, factory = stock.compare_one(number, summary)
        if status == stock.DIFFERENT:
            item.setForeground(QBrush(QColor(theme.current_palette()["warning"])))
            item.setToolTip(f'The factory patch here is "{factory.name}" ({factory.key_assign}).')
        else:
            item.setData(Qt.ItemDataRole.ForegroundRole, None)
            item.setToolTip("")

    # -- the USER list's own actions: rename, copy, swap ----------------------------------------------------------------------------

    def _names_context_menu(self, position):
        item = self.names_list.itemAt(position)
        if item is None:
            return
        number = item.data(Qt.ItemDataRole.UserRole)
        ready = self.session.is_open and self.worker.is_idle()
        menu = QMenu(self)
        menu.addAction("Open", lambda: self._read_user_from_item(item))
        play = menu.addAction("Play on Unit", lambda n=number: self.audition.choose("USER", n))
        play.setToolTip("Choose this patch on the unit (Bank Select + Program Change) so it can be played from the keyboard below. The unit's current patch changes.")
        play.setEnabled(self.session.is_open and not self._long_job)
        menu.addSeparator()
        for text, handler in (("Rename...", self.rename_user), ("Copy To...", self.copy_user), ("Swap With...", self.swap_user)):
            action = menu.addAction(text, lambda h=handler, n=number: h(n))
            action.setEnabled(ready)
        menu.exec(self.names_list.viewport().mapToGlobal(position))

    def _slot_for_action(self, number):
        if number is None:
            item = self.names_list.currentItem()
            number = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if number is None or not self.session.is_open or not self.worker.is_idle():
            return None
        return number

    def _slot_has_unsent_edits(self, number):
        if self._shown is not None and self._shown[0] == f"user:{number}" and self._is_dirty():
            QMessageBox.information(self, "USER Patches", f"USER:{number + 1:03d} is open with edits that aren't written. Write or revert them first.")
            return True
        return False

    def _names(self):
        return [s.name for s in self._summaries]

    def rename_user(self, number=None):
        number = self._slot_for_action(number)
        if number is None or self._slot_has_unsent_edits(number):
            return
        current = self._summaries[number].name if number < len(self._summaries) else ""
        dialog = RenameDialog(current, self)
        if dialog.exec() != RenameDialog.DialogCode.Accepted:
            return
        name = dialog.name().rstrip()
        if not name or name == current or not self._offer_backup_first(f"renaming USER:{number + 1:03d}"):
            return
        self.statusBar().showMessage(f"Renaming USER:{number + 1:03d}...")
        self.worker.submit("rename_user", number, name)

    def copy_user(self, number=None):
        number = self._slot_for_action(number)
        if number is None:
            return
        dialog = SlotDialog("Copy To", f"Copy USER:{number + 1:03d} to:", self._names(), min(number + 1, patch.USER_PATCH_COUNT - 1), "Overwrite",
                            "The target's current patch is saved to a file first, and the copy is read back to check it.", self)
        if dialog.exec() != SlotDialog.DialogCode.Accepted:
            return
        target = dialog.slot()
        if target == number or self._slot_has_unsent_edits(target) or not self._offer_backup_first(f"overwriting USER:{target + 1:03d}"):
            return
        self.statusBar().showMessage(f"Copying USER:{number + 1:03d} to USER:{target + 1:03d}...")
        self.worker.submit("copy_user", number, target)

    def swap_user(self, number=None):
        number = self._slot_for_action(number)
        if number is None or self._slot_has_unsent_edits(number):
            return
        dialog = SlotDialog("Swap With", f"Swap USER:{number + 1:03d} with:", self._names(), min(number + 1, patch.USER_PATCH_COUNT - 1), "Swap",
                            "Both patches are saved to files first, and each write is read back to check it.", self)
        if dialog.exec() != SlotDialog.DialogCode.Accepted:
            return
        other = dialog.slot()
        if other == number or self._slot_has_unsent_edits(other) or not self._offer_backup_first(f"swapping USER:{number + 1:03d} and USER:{other + 1:03d}"):
            return
        self.statusBar().showMessage(f"Swapping USER:{number + 1:03d} and USER:{other + 1:03d}...")
        self.worker.submit("swap_user", number, other)

    # -- the audition keyboard -------------------------------------------------------------------------------------------

    def _send_midi(self, message):
        """Notes and patch choices from the audition bar. Never during a firmware update: the unit is in update mode and only the update's own messages belong on the wire."""
        connection = self.session.connection
        if self._firmware_running or connection is None or not connection.is_open:
            return
        try:
            connection.send(message)
        except Exception:
            debug_log.get_logger().error("audition: couldn't send a MIDI message", exc_info=True)

    # -- Universal SysEx: master volume and GM mode ------------------------------------------------------------------------

    def _on_master_volume(self, level):
        self._send_midi(universal.master_volume(level))
        debug_log.get_logger().info(f"universal: master volume {level}")
        self.statusBar().showMessage(f"Master volume {level} sent", 3000)

    def _unit_state_changed(self):
        """The unit's own state changed under the editors (GM mode on or off): nothing the windows hold is known to be on the unit any more."""
        self._temp_synced = False
        self.performance_panel._temp_synced = False
        self.rhythm_panel._temp_synced = False

    def gm_system_on(self):
        if not self.session.is_open or not self.worker.is_idle() or self._firmware_running:
            return
        answer = QMessageBox.question(
            self, "GM System On",
            "Put the unit in General MIDI mode?\n\nIt resets the unit's current sound settings to the GM start state. While it is in GM mode JV Studio can't read or write it: "
            "use Hardware > GM System Off (or the unit's VALUE knob) to come back. Your stored patches are not touched.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._send_midi(universal.GM_SYSTEM_ON)
        self._unit_state_changed()
        debug_log.get_logger().warning("universal: GM System On sent")
        self.statusBar().showMessage("GM System On sent: the unit is in GM mode and ignores this app's reads and writes. Hardware > GM System Off brings it back.", 15000)

    def gm_system_off(self):
        if not self.session.is_open or not self.worker.is_idle() or self._firmware_running:
            return
        self._send_midi(universal.GM_SYSTEM_OFF)
        self._unit_state_changed()
        debug_log.get_logger().info("universal: GM System Off sent")
        self.statusBar().showMessage("GM System Off sent: the unit returns to Performance mode. Refresh All from Unit (Ctrl/Cmd+Shift+R) reads it again.", 15000)

    # -- the audition bar and the editor follow each other ------------------------------------------------------------------

    AUDITION_READ_DELAY_MS = 350  # the unit needs a moment to load a patch before its temporary patch can be read

    def _on_audition_patch(self, group, number):
        """A patch was chosen on the unit by Program Change: the unit's current patch is no longer what the editor last sent or read. A moment after the LAST choice the window reads
        the temporary patch into the editor (`_after_audition_choice`), unless that would replace edits that were never sent."""
        self._temp_synced = False
        if self._pending_check is None:
            self.statusBar().showMessage(f"Chose {self.audition.current_label()} on the unit...", 8000)
        self._audition_timer.start(self.AUDITION_READ_DELAY_MS)
        self._refresh_connection()

    def _after_audition_choice(self):
        if not self.session.is_open or self._firmware_running:
            self._pending_check = None
            return
        if not self.worker.is_idle():  # a job is running: try again shortly (the choice is not forgotten)
            self._audition_timer.start(200)
            return
        if self._sound_mode not in (None, 1):
            self._pending_check = None
            self.statusBar().showMessage("The unit is not in Patch mode: a patch chosen here goes to a part (Performance mode) or is ignored (GM mode), so there is no patch to load into the editor.", 10000)
            return
        if self._pending_check is not None:
            self.worker.submit("check_temporary")
        elif self._shown is not None and self._is_dirty():
            self.statusBar().showMessage(f"Chose {self.audition.current_label()} on the unit. Your unsent edits stay in the editor: Read Temporary Patch (Ctrl/Cmd+R) loads what you hear instead.", 12000)
        else:
            self.statusBar().showMessage(f"Chose {self.audition.current_label()}: reading it into the editor...")
            self.worker.submit("temporary_follow")

    def _play_shown_on_unit(self, number):
        """A USER patch was just opened by double-click: have the unit select it too (Bank Select + Program Change: a plain MIDI message, nothing is written) and check that it did."""
        if not self.session.is_open or self._sound_mode not in (None, 1):
            return
        self._pending_check = f"user:{number}"
        self.audition.choose("USER", number)

    def _on_follow_checked(self, unit_has):
        """The unit's temporary patch, read after it was told to select the patch the editor shows: if they are the same patch, live edits can start at once."""
        pending, self._pending_check = self._pending_check, None
        if pending is None or self._shown is None or self._shown[0] != pending:
            return  # something else was opened meanwhile
        where = self._where
        if unit_has == self._shown[1] and not self._is_dirty():
            self._temp_synced = True
            self.statusBar().showMessage(f"{where} is playing on the unit: your edits are heard as you make them.", 8000)
        else:
            self._temp_synced = False
            self.statusBar().showMessage(f"{where} is open, but the unit is not playing it (it needs Patch mode, Receive Program Change ON and the right channel). Send to Temporary Patch to hear it.", 12000)
        self._refresh_connection()

    def _on_system_midi(self, info):
        self._sound_mode = info.sound_mode
        announce, self._announce_system = self._announce_system, True
        self.audition.show_system(info, announce=announce)  # (a bound method, so the worker's signal is delivered on the GUI thread)

    def _read_unit_midi_settings(self):
        if not self.session.is_open or not self.worker.is_idle():
            self.statusBar().showMessage("Wait for the current job to finish first")
            return
        self._announce_system = True
        self.worker.submit("system_midi")

    def _autoload_selection(self):
        """A start-up or Refresh All step: which patch the unit has selected, shown in the audition bar's boxes (quietly: no note, the channel box untouched)."""
        self._announce_system = False
        self.worker.submit("system_midi")

    def _on_cancelled(self, label, message):
        self._long_job = False
        self.statusBar().showMessage(message, 8000)
        if label == "firmware":
            self._firmware_running = False
            QMessageBox.warning(self, "Firmware update stopped", message)
        self._refresh_connection()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._sized_library:  # once: the list is as wide as the Patches / Performances switch
            self._sized_library = True
            self.library.setFixedWidth(self.mode_tabs.sizeHint().width() + 21)  # the switch's left margin (15) less the list's (15), plus the list's right margin (6)

    def closeEvent(self, event):
        if self._firmware_running:
            answer = QMessageBox.warning(
                self,
                "Firmware update running",
                "The unit is part-way through a firmware update. Quitting now stops it and may leave the unit unable to start.\n\nQuit anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.worker.cancel()
        self.worker.stop()
        self.worker.wait(3000)
        self.session.close()
        super().closeEvent(event)
