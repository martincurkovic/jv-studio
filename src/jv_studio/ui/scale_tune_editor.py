"""The Scale Tune tab of System Settings: 12 knobs (C to B, in cents), for Patch mode or any of the 16 parts, with the manual's three example tunings.

It edits a `scale_tune.ScaleTunes` IN PLACE (the dialog's working copy) and only emits `edited`; the dialog owns reading, the confirmation and writing. Targets whose values
differ from what was read are marked with a dot in the target box.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from jv_studio.core import params, scale_tune
from jv_studio.ui.knob_control import KnobControl
from jv_studio.ui.qt_helpers import build_editor_card

KNOBS_PER_ROW = 6


class ScaleTuneEditor(QWidget):
    edited = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scales = None
        self._original = None
        self._loading = False
        table = params.load_table().block(scale_tune.BLOCK)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 14, 10)
        layout.setSpacing(8)

        pick = QHBoxLayout()
        self.target_combo = QComboBox()
        for target in (scale_tune.PATCH_MODE, *range(scale_tune.PART_COUNT)):
            self.target_combo.addItem(scale_tune.target_name(target), target)
        self.target_combo.setToolTip("Which tuning to edit. The unit keeps one for Patch mode and one for each of the 16 parts (Performance mode).")
        self.target_combo.activated.connect(lambda _i: self.refresh())
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(list(scale_tune.PRESETS))
        self.preset_combo.setToolTip("The manual's three example tunings.")
        self.tonic_combo = QComboBox()
        self.tonic_combo.addItems(scale_tune.NOTES)
        self.tonic_combo.setToolTip("The note the tuning is built on (its tonic): the pattern is moved to start there. The manual's examples are in C.")
        self.btn_set = QPushButton("Set")
        self.btn_set.setToolTip("Put the chosen tuning, on the chosen tonic, into the tuning shown.")
        self.btn_set.clicked.connect(self._set_preset)
        self.btn_all = QPushButton("Copy to All")
        self.btn_all.setToolTip("Make Patch mode and all 16 parts use the tuning shown.")
        self.btn_all.clicked.connect(self._copy_to_all)
        for widget in (QLabel("Tuning for"), self.target_combo):
            pick.addWidget(widget)
        pick.addSpacing(16)
        for widget in (QLabel("Preset"), self.preset_combo, QLabel("Tonic"), self.tonic_combo, self.btn_set):
            pick.addWidget(widget)
        pick.addStretch()
        pick.addWidget(self.btn_all)
        layout.addLayout(pick)

        grid = QGridLayout()
        grid.setHorizontalSpacing(2)
        grid.setVerticalSpacing(6)
        self._knobs = []
        for note, param in enumerate(table.param_list()):
            knob = KnobControl(param)
            knob.set_name(scale_tune.NOTES[note])
            knob.setToolTip(f"How many cents (hundredths of a semitone) {scale_tune.NOTES[note]} is tuned above or below equal temperament, in every octave.\nDrag to turn. Shift: fine. Double-click: reset. Click and type for an exact value.")
            knob.committed.connect(lambda value, n=note: self._knob_edited(n, value))
            grid.addWidget(knob, note // KNOBS_PER_ROW, note % KNOBS_PER_ROW, Qt.AlignmentFlag.AlignTop)
            self._knobs.append(knob)
        layout.addWidget(build_editor_card("scale_tune_editor", "Cents above or below equal temperament", grid, key="notes"))
        note = QLabel("Each note is tuned the same in every octave. The unit only uses scale tuning while Scale Tune Switch (Settings > Tuning & Clock) is on.")
        note.setObjectName("mutedLabel")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        self.setEnabled(False)

    # -- showing -------------------------------------------------------------------------------------------------------------

    def target(self):
        return self.target_combo.currentData()

    def set_scales(self, working, original=None):
        """Show `working` (edited in place from now on); `original` is what the unit held, for the dots."""
        self._scales, self._original = working, original
        self.setEnabled(working is not None)
        self.refresh()

    def refresh(self):
        """Show the values again (and the dots). Emits nothing."""
        if self._scales is None:
            return
        self._loading = True
        try:
            for note, knob in enumerate(self._knobs):
                knob.set_value(self._scales.get(self.target(), note))
        finally:
            self._loading = False
        self._update_marks()

    def _update_marks(self):
        changed = set(self._scales.changed_targets(self._original)) if self._scales is not None and self._original is not None else set()
        for index in range(self.target_combo.count()):
            target = self.target_combo.itemData(index)
            self.target_combo.setItemText(index, scale_tune.target_name(target) + ("  •" if target in changed else ""))

    # -- edits ---------------------------------------------------------------------------------------------------------------

    def _knob_edited(self, note, value):
        if self._loading or self._scales is None:
            return
        self._scales.set(self.target(), note, value)
        self._update_marks()
        self.edited.emit()

    def _set_preset(self):
        if self._scales is None:
            return
        self._scales.set_block_cents(self.target(), scale_tune.preset_cents(self.preset_combo.currentText(), self.tonic_combo.currentIndex()))
        self.refresh()
        self.edited.emit()

    def _copy_to_all(self):
        if self._scales is None:
            return
        source = bytes(self._scales.blocks[self.target()])
        for block in self._scales.blocks:
            block[:] = source
        self.refresh()
        self.edited.emit()
