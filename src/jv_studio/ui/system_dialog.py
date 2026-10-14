"""Hardware > System Settings...: the unit's global settings (master tune, MIDI receive, controller sources, effect switches, preview notes) in the editor's cards and knobs.

Two tabs: Settings (the System common block) and Scale Tune (12 notes in cents for Patch mode and each part). A modeless window with its own working copy. Nothing is sent while you edit; **Apply to Unit...** shows what will change (and what each change does), saves the current
System block to `~/.jv-studio/backups/SYSTEM-<time>.syx` first (nothing is written if that fails), sends ONLY the changed settings, then reads the block back and checks them.
The unit's mode is never switched to GM from here: the unit ignores SysEx in GM mode, so the app could neither check the change nor undo it.
"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from jv_studio.core import debug_log, groups, params, scale_tune, system
from jv_studio.ui.knob_control import KnobControl
from jv_studio.ui.patch_editor import COMPACT_FROM, KNOBS_PER_ROW, ChoiceCombo, PatchEditor
from jv_studio.ui.qt_helpers import build_editor_card, build_two_column_page
from jv_studio.ui.scale_tune_editor import ScaleTuneEditor

#: what a change does, shown in the confirmation (the settings that can make the unit behave differently, or go quiet)
CAUTION = {
    "sound_mode": "switches the unit between Performance and Patch mode",
    "patch_receive_channel": "in Patch mode the unit will only play notes sent on this channel",
    "control_channel": "this is the channel on which Program Change switches performances",
    "receive_program_change": "the unit stops or starts following Program Change messages",
    "receive_bank_select": "the unit stops or starts following Bank Select messages",
    "master_tune": "retunes the whole unit",
    "clock_source": "with MIDI, tempo-synced effects and LFOs follow incoming MIDI Clock (and have no tempo if none arrives)",
    "scale_tune_switch": "switches the per-note scale tuning on or off",
}

NOT_OFFERED = {"sound_mode": {system.GM_MODE}}  # (see the module docstring)


class SystemEditor(QWidget):
    """The System cards, built from the table (`core/groups.py`). Edits a `system.System` in place and emits `param_edited(key, value)`."""

    param_edited = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._system = None
        self._loading = False
        self._widgets = {}
        cards, weights = [], []
        for title, members in groups.groups(system.COMMON):
            form = QFormLayout()
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            grid = QGridLayout()
            grid.setHorizontalSpacing(2)
            grid.setVerticalSpacing(6)
            compact = sum(1 for p in members if not p.string and not p.has_choices()) >= COMPACT_FROM
            knobs = 0
            for param in members:
                if param.has_choices():
                    control = ChoiceCombo(param)
                    for value in NOT_OFFERED.get(param.key, ()):
                        control.removeItem(control.findData(value))
                    control.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                    control.setMinimumContentsLength(7)
                    control.activated.connect(lambda _i, w=control, p=param: self._edited(p, w.currentData()))
                    is_knob = False
                else:
                    control = KnobControl(param, compact=compact)
                    control.committed.connect(lambda v, p=param: self._edited(p, v))
                    is_knob = True
                control.setToolTip(PatchEditor._tooltip(system.COMMON, param, is_knob))
                self._widgets[param.key] = control
                if is_knob:
                    grid.addWidget(control, knobs // KNOBS_PER_ROW, knobs % KNOBS_PER_ROW, Qt.AlignmentFlag.AlignTop)
                    knobs += 1
                else:
                    form.addRow(param.name, control)
                    form.labelForField(control).setToolTip(control.toolTip())
            rows = [layout for layout, used in ((form, form.rowCount()), (grid, knobs)) if used]
            cards.append(build_editor_card("system_editor", title, *rows))
            weights.append(form.rowCount() + (2 if compact else 3) * -(-knobs // KNOBS_PER_ROW) + 2)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(build_two_column_page(cards, weights))
        self.setEnabled(False)

    def set_system(self, working):
        self._system = working
        self.setEnabled(working is not None)
        self.refresh()

    def refresh(self):
        if self._system is None:
            return
        self._loading = True
        try:
            for key, widget in self._widgets.items():
                value = self._system.get(key)
                if isinstance(widget, ChoiceCombo):
                    widget.set_raw(value)
                elif isinstance(widget, QLineEdit):
                    widget.setText(value)
                else:
                    widget.set_value(value)
        finally:
            self._loading = False

    def widget_for(self, key):
        return self._widgets[key]

    def _edited(self, param, value):
        if self._loading or self._system is None:
            return
        stored = self._system.set(param.key, value)
        self.param_edited.emit(param.key, stored)


class SystemDialog(QDialog):
    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.worker = host.worker
        self._working = None
        self._original = None
        self._working_scale = None
        self._original_scale = None
        self._just_applied = False  # the read that follows an apply must not hide the apply's message
        self.setWindowTitle("System Settings")
        self.setModal(False)
        self.resize(820, 600)
        layout = QVBoxLayout(self)
        self.heading = QLabel("The unit's global settings. Nothing is sent until you Apply.")
        self.heading.setObjectName("sectionHeader")
        self.heading.setWordWrap(True)
        self.selection_label = QLabel()
        self.selection_label.setObjectName("mutedLabel")
        self.problems_label = QLabel()
        self.problems_label.setObjectName("mutedLabel")
        self.problems_label.setWordWrap(True)
        self.problems_label.setVisible(False)
        buttons = QHBoxLayout()
        self.btn_read = QPushButton("Read from Unit")
        self.btn_read.setToolTip("Reads the unit's System settings (read-only: nothing is written).")
        self.btn_read.clicked.connect(self.read)
        self.btn_apply = QPushButton("Apply to Unit...")
        self.btn_apply.setToolTip("Shows what will change, saves the current settings to a file, sends only the changes and reads them back.")
        self.btn_apply.clicked.connect(self.apply)
        self.btn_revert = QPushButton("Revert Edits")
        self.btn_revert.setToolTip("Go back to the settings as they were read.")
        self.btn_revert.clicked.connect(self.revert)
        for button in (self.btn_read, self.btn_apply, self.btn_revert):
            buttons.addWidget(button)
        buttons.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        buttons.addWidget(close)
        self.editor = SystemEditor()
        self.editor.param_edited.connect(self._on_edited)
        self.scale_editor = ScaleTuneEditor()
        self.scale_editor.edited.connect(self._on_scale_edited)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.editor, "Settings")
        self.tabs.addTab(self.scale_editor, "Scale Tune")
        for widget in (self.heading, self.selection_label, self.problems_label):
            layout.addWidget(widget)
        layout.addLayout(buttons)
        layout.addWidget(self.tabs, 1)
        self.worker.system_read.connect(self._on_read)
        self.worker.scale_read.connect(self._on_scale_read)
        self.worker.system_applied.connect(self._on_applied)
        self.refresh_state(False)

    # -- state -----------------------------------------------------------------------------------------------------------

    def settings_dirty(self):
        return self._working is not None and self._working != self._original

    def scale_dirty(self):
        return self._working_scale is not None and self._working_scale != self._original_scale

    def is_dirty(self):
        return self.settings_dirty() or self.scale_dirty()

    def has_shown(self):
        return self._working is not None

    def refresh_state(self, ready):
        """`ready`: ports open and the worker idle."""
        self.btn_read.setEnabled(ready)
        self.btn_apply.setEnabled(ready and self.is_dirty())
        self.btn_revert.setEnabled(self.is_dirty())

    def _update_heading(self):
        names = self.host._names() if hasattr(self.host, "_names") else None
        if self._working is None:
            return
        self.selection_label.setText(f"The unit is in {self._working.selection_text(names)}" + ("   (edited)" if self.is_dirty() else ""))

    # -- reading ---------------------------------------------------------------------------------------------------------

    def read(self):
        if self.is_dirty():
            answer = QMessageBox.question(
                self, "Discard edits?", "The System settings have edits that were not applied. Discard them and read the unit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        if not self.host.session.is_open or not self.worker.is_idle():
            return
        self.host.statusBar().showMessage("Reading the System settings and scale tunes...")
        self.worker.submit("system_read")

    def _on_read(self, read, problems):
        self._working = read
        self._original = read.copy()
        self.editor.set_system(self._working)
        if problems:
            shown = "; ".join(str(p) for p in problems[:3])
            more = f" (and {len(problems) - 3} more)" if len(problems) > 3 else ""
            self.problems_label.setText(f"{len(problems)} value(s) outside the manual's ranges: {shown}{more}. Details are in the log.")
        self.problems_label.setVisible(bool(problems))
        self._update_heading()
        if not self._just_applied:
            self.host.statusBar().showMessage("Read the System settings", 5000)
        self._just_applied = False
        self.host._refresh_connection()

    def _on_scale_read(self, scales):
        self._working_scale = scales
        self._original_scale = scales.copy()
        self.scale_editor.set_scales(self._working_scale, self._original_scale)
        self._update_heading()
        self.host._refresh_connection()

    # -- editing and applying --------------------------------------------------------------------------------------------

    def _on_edited(self, key, value):
        debug_log.get_logger().info(f"edit: system {key} = {value!r}")
        self._update_heading()
        self.host._refresh_connection()

    def _on_scale_edited(self):
        debug_log.get_logger().info("edit: scale tune")
        self._update_heading()
        self.host._refresh_connection()

    def revert(self):
        if not self.is_dirty():
            return
        if self._working is not None:
            self._working = self._original.copy()
            self.editor.set_system(self._working)
        if self._working_scale is not None:
            self._working_scale = self._original_scale.copy()
            self.scale_editor.set_scales(self._working_scale, self._original_scale)
        self._update_heading()
        self.host._refresh_connection()

    def describe_changes(self):
        """The confirmation text: one line per change, then what the riskier ones do."""
        table = params.load_table().block(system.COMMON)
        lines, cautions = [], []
        for key, old, new in system.changes(self._original, self._working):
            param = table.param(key)
            lines.append(f"{param.name}: {params.format_value(param, old)}  →  {params.format_value(param, new)}")
            if key in CAUTION:
                cautions.append(f"• {param.name}: {CAUTION[key]}.")
        scale_param = params.load_table().block(scale_tune.BLOCK).param_list()
        for target in self._scale_changes():
            notes = self._working_scale.changed_notes(self._original_scale, target)
            shown = ", ".join(
                f"{scale_tune.NOTES[n]} {params.format_value(scale_param[n], self._original_scale.get(target, n))} → {params.format_value(scale_param[n], self._working_scale.get(target, n))}"
                for n in notes[:4]
            )
            lines.append(f"Scale tune, {scale_tune.target_name(target)}: {shown}" + (f" and {len(notes) - 4} more notes" if len(notes) > 4 else "") + " (cents)")
        if self._scale_changes() and self._working is not None and not self._working.get("scale_tune_switch"):
            cautions.append("• Scale Tune Switch is OFF, so scale tuning is not used until you switch it on (Settings > Tuning & Clock).")
        return lines, cautions

    def _scale_changes(self):
        return self._working_scale.changed_targets(self._original_scale) if self.scale_dirty() else []

    def apply(self):
        if not self.is_dirty() or not self.host.session.is_open or not self.worker.is_idle():
            return
        lines, cautions = self.describe_changes()
        text = "Change these settings on the unit?\n\n" + "\n".join(lines)
        if cautions:
            text += "\n\n" + "\n".join(cautions)
        text += "\n\nThe current settings are saved to a file first, and the changes are read back to check them."
        answer = QMessageBox.question(
            self, "Apply to the unit?", text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes or not self.host._offer_backup_first("changing the System settings"):
            return
        changes = [(key, new) for key, _, new in system.changes(self._original, self._working)] if self._working is not None else []
        blocks = {target: bytes(self._working_scale.blocks[target]) for target in self._scale_changes()}
        self.host.statusBar().showMessage("Applying the System settings...")
        self.worker.submit("system_apply", changes, blocks)

    def _on_applied(self, backup_path, count):
        self._just_applied = True
        self.host.statusBar().showMessage(f"{count} System setting(s) changed and read back; the old settings are in {Path(backup_path).name}", 10000)
        # (the worker then sends the read-back block as a system_read: it becomes what is shown and what Revert returns to)
