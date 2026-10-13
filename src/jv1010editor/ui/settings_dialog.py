"""Settings: the MIDI ports and the theme, and the two troubleshooting tests (hardware detection, interface loopback)."""

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from jv1010editor.core import app_config, debug_log, midi, midi_diagnostics
from jv1010editor.ui import theme, tooltips
from jv1010editor.ui.loopback_results_dialog import LoopbackResultsDialog
from jv1010editor.ui.qt_helpers import (
    FullWidthTabBar,
    align_form_label_columns,
    build_scroll_area,
    build_section_card,
    set_enabled_without_scrolling,
    widen_popup_to_fit_items,
)

_DIAGRAM_DIR = os.path.join(os.path.dirname(__file__), "help", "diagrams")
_DIAGRAM_PIXEL_RATIO = 2.0  # the diagrams are drawn at 2x (tools/make_diagrams.py)
_MINIMUM_DIALOG_WIDTH = 560
_SCROLLBAR_WIDTH_ALLOWANCE = 32  # a page's own vertical scroll bar eats horizontal room


def _minimum_width_for_pages(pages, minimum=_MINIMUM_DIALOG_WIDTH):
    """The dialog width that shows the widest page without a horizontal scroll bar, never narrower than `minimum` (port names vary a lot)."""
    widest = max((page.sizeHint().width() for page in pages), default=0)
    return max(minimum, widest + _SCROLLBAR_WIDTH_ALLOWANCE)


class SettingsDialog(QDialog):
    """Two tabs, each a couple of cards: "Settings" (what you set up once) and "Troubleshooting" (what you reach for when something doesn't work)."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.session = session
        self.setMinimumHeight(520)
        outer = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.setTabBar(FullWidthTabBar(tabs))
        outer.addWidget(tabs)

        # measured BEFORE wrapping in a scroll area (a scroll area's own size hint says nothing about its page)
        settings_page = self._build_settings_page()
        troubleshooting_page = self._build_troubleshooting_page()
        tabs.addTab(build_scroll_area(settings_page), "Settings")
        tabs.addTab(build_scroll_area(troubleshooting_page), "Troubleshooting")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._apply_and_close)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        self.setMinimumWidth(_minimum_width_for_pages([settings_page, troubleshooting_page]))

    # -- Settings tab ----------------------------------------------------------------------------------------------------

    def _build_settings_page(self):
        midi_form = QFormLayout()
        self.combo_input = QComboBox()
        self.combo_output = QComboBox()
        for combo in (self.combo_input, self.combo_output):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_input.setToolTip(tooltips.MIDI_INPUT)
        self.combo_output.setToolTip(tooltips.MIDI_OUTPUT)
        self._populate_ports()
        midi_form.addRow(QLabel("MIDI Input:"), self.combo_input)
        midi_form.addRow(QLabel("MIDI Output:"), self.combo_output)
        midi_card = build_section_card("MIDI Input/Output", midi_form)

        # Appearance takes effect the moment an option is PICKED (not on OK), so the change is visible while the dialog is open and Cancel
        # doesn't undo it. `activated` fires only for a choice the USER makes, never for restoring the saved value below.
        appearance_form = QFormLayout()
        self.combo_theme = QComboBox()
        for label, value in theme.CHOICES:
            self.combo_theme.addItem(label, value)
        index = self.combo_theme.findData(app_config.get_saved_theme())
        self.combo_theme.setCurrentIndex(index if index >= 0 else 0)
        self.combo_theme.setToolTip(tooltips.THEME)
        self.combo_theme.activated.connect(self._on_theme_chosen)
        appearance_form.addRow(QLabel("Theme:"), self.combo_theme)
        appearance_card = build_section_card("Appearance", appearance_form)

        align_form_label_columns(midi_form, appearance_form)  # one label width, so the fields of both cards start at the same x
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(midi_card)
        layout.addWidget(appearance_card)
        layout.addStretch()
        return page

    def _populate_ports(self):
        self.combo_input.addItem("(None)", None)
        for name in midi.list_input_names():
            self.combo_input.addItem(name, name)
        self.combo_output.addItem("(None)", None)
        for name in midi.list_output_names():
            self.combo_output.addItem(name, name)
        for combo, current in ((self.combo_input, self.session.input_name), (self.combo_output, self.session.output_name)):
            index = combo.findData(current) if current else -1
            if index >= 0:
                combo.setCurrentIndex(index)
            widen_popup_to_fit_items(combo)

    def _on_theme_chosen(self, index):
        chosen = self.combo_theme.itemData(index)
        app_config.save_theme(chosen)
        theme.set_theme_preference(chosen)

    def _apply_and_close(self):
        input_name, output_name = self.combo_input.currentData(), self.combo_output.currentData()
        try:
            self.session.open(input_name, output_name)
        except Exception as e:
            # a port that vanished between listing and clicking, a driver error: say so rather than let it escape the slot unlogged
            debug_log.get_logger().error(f"settings: couldn't open the MIDI port(s) (input={input_name!r}, output={output_name!r})", exc_info=True)
            QMessageBox.critical(self, "Settings", f"Couldn't open the selected MIDI port(s): {e}")
            return
        debug_log.get_logger().info(f"settings: applied input={input_name!r} output={output_name!r}")
        app_config.save_ports(input_name, output_name)
        self.accept()

    # -- Troubleshooting tab ---------------------------------------------------------------------------------------------

    @staticmethod
    def _diagram_label(filename, description):
        """A centred cabling picture for a test card, or None if the file is missing (the card just has no picture)."""
        pixmap = QPixmap(os.path.join(_DIAGRAM_DIR, filename))
        if pixmap.isNull():
            return None
        pixmap.setDevicePixelRatio(_DIAGRAM_PIXEL_RATIO)
        label = QLabel()
        label.setPixmap(pixmap)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setAccessibleDescription(description)
        label.setToolTip(description)
        return label

    def _build_troubleshooting_page(self):
        hardware = QVBoxLayout()
        note = QLabel(
            "To check the JV-1010 is connected, cable the interface's MIDI OUT to the JV-1010's MIDI IN and the JV-1010's MIDI OUT to the "
            "interface's MIDI IN. Select the ports on the Settings tab, then run the test below. It only asks the unit who it is and "
            "reads its temporary patch's name: nothing is written."
        )
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop)
        hardware.addWidget(note)
        diagram = self._diagram_label("midi-jv1010-cable.png", "Interface MIDI OUT to JV-1010 MIDI IN, and JV-1010 MIDI OUT to interface MIDI IN")
        if diagram is not None:
            hardware.addWidget(diagram)
        self.hardware_results_label = QLabel()
        self.hardware_results_label.setWordWrap(True)
        hardware.addWidget(self.hardware_results_label)
        self.btn_hardware_test = QPushButton("Run Hardware Test")
        self.btn_hardware_test.setToolTip(tooltips.HARDWARE_TEST_BUTTON)
        self.btn_hardware_test.clicked.connect(self._run_hardware_test)
        hardware.addWidget(self.btn_hardware_test)
        self.hardware_progress = QProgressBar()
        self.hardware_progress.setRange(0, 0)
        self.hardware_progress.setVisible(False)
        hardware.addWidget(self.hardware_progress)
        hardware_card = build_section_card("Hardware Test", hardware)

        interface = QVBoxLayout()
        loopback_note = QLabel(
            "To test a MIDI interface's SysEx reliability, cable its MIDI OUT back into its own MIDI IN. Select the ports on the "
            "Settings tab, then run the test below (it may take 5-20 seconds)."
        )
        loopback_note.setWordWrap(True)
        loopback_note.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        interface.addWidget(loopback_note)
        loopback_diagram = self._diagram_label("midi-loopback-cable.png", "One MIDI cable from the interface's MIDI OUT to its own MIDI IN")
        if loopback_diagram is not None:
            interface.addWidget(loopback_diagram)
        self.btn_loopback_test = QPushButton("Run Loopback Test")
        self.btn_loopback_test.setToolTip(tooltips.LOOPBACK_TEST_BUTTON)
        self.btn_loopback_test.clicked.connect(self._run_loopback_test)
        interface.addWidget(self.btn_loopback_test)
        self.loopback_progress = QProgressBar()
        self.loopback_progress.setRange(0, 0)
        self.loopback_progress.setVisible(False)
        interface.addWidget(self.loopback_progress)
        interface_card = build_section_card("Interface Test", interface)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(hardware_card)
        layout.addWidget(interface_card)
        layout.addStretch()
        return page

    def _selected_ports(self, title):
        """(input, output) from the combos, or None after telling the user both are needed."""
        input_name, output_name = self.combo_input.currentData(), self.combo_output.currentData()
        if not input_name or not output_name:
            QMessageBox.warning(self, title, "Select both a MIDI Input and a MIDI Output on the Settings tab first.")
            return None
        return input_name, output_name

    def _run_test(self, title, button, progress, running_text, idle_text, work):
        """Shared by both tests: borrow the ports (the app's own connection is closed meanwhile), run `work(connection)`, always put things back."""
        ports = self._selected_ports(title)
        if ports is None:
            return None
        set_enabled_without_scrolling(button, False)  # (not setEnabled(False) directly: the focus would move on and the page scroll)
        button.setText(running_text)
        progress.setVisible(True)
        QApplication.processEvents()
        result = None
        try:
            with self.session.paused():
                connection = self.session.connection_factory(*ports)
                try:
                    result = work(connection)
                finally:
                    connection.close()
        except Exception as e:
            # this IS the built-in "diagnose my MIDI connection" tool, so a failure in the tool itself has to reach the log too
            debug_log.get_logger().error(f"settings: {title.lower()} failed (input={ports[0]!r}, output={ports[1]!r})", exc_info=True)
            QMessageBox.critical(self, title, f"Couldn't run the test: {e}")
        finally:
            button.setEnabled(True)
            button.setText(idle_text)
            progress.setVisible(False)
        return result

    def _run_hardware_test(self):
        result = self._run_test(
            "Hardware Test", self.btn_hardware_test, self.hardware_progress, "Testing...", "Run Hardware Test",
            lambda connection: midi_diagnostics.detect_hardware(connection, pump=QApplication.processEvents),
        )
        if result is None:
            return
        self.hardware_results_label.setText(result.message)
        log = debug_log.get_logger()
        log.info(f"hardware test: {result.status}")
        for line in result.log_lines:
            log.info(f"hardware test: {line}")

    def _run_loopback_test(self):
        results = self._run_test(
            "Loopback Test", self.btn_loopback_test, self.loopback_progress, "Testing...", "Run Loopback Test",
            lambda connection: midi_diagnostics.run_loopback(connection, pump=QApplication.processEvents),
        )
        if results is not None:
            self._show_loopback_results(results)

    def _show_loopback_results(self, results):
        failed = [size for size, passed, _ in results if not passed]
        debug_log.get_logger().info(
            f"loopback test: {len(results) - len(failed)}/{len(results)} sizes passed" + (f", first failure at {failed[0]} bytes" if failed else "")
        )
        LoopbackResultsDialog(results, self.combo_input.currentData(), self.combo_output.currentData(), self).exec()
