"""The patch editor: one tab for the patch common block and one per tone, built from the parameter table (`core/groups.py` says which card a
parameter is on). It edits a `Patch` IN PLACE (the caller's working copy) and never talks to the unit: it emits `param_committed` for each user edit
and the window decides what to do with it (the owner's rule: the UI is live, MIDI goes out on release: a knob commits when a drag ends or a value is typed).
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from jv_studio.core import friendly, groups, hints, params, patch, waves
from jv_studio.ui.efx import apply_efx_meanings
from jv_studio.ui.envelope_graph import GRAPH_FOR_CARD
from jv_studio.ui.knob_control import KnobControl, origin_value
from jv_studio.ui.qt_helpers import FullWidthTabBar, build_editor_card, build_two_column_page
from jv_studio.ui.wave_picker import WavePickerDialog

#: how many knobs a card's grid holds per row
KNOBS_PER_ROW = 4
#: a card with at least this many knobs uses the COMPACT layout (the value beside the knob, about half the height): the roomy one for a handful, the compact one for the
#: envelope, LFO and controller cards
COMPACT_FROM = 8


class ChoiceCombo(QComboBox):
    def __init__(self, param, parent=None):
        super().__init__(parent)
        self.param = param
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        if param.choices:
            options = [(index, choice.label) for index, choice in enumerate(param.choices) if choice.jv1010]  # a JV-1080-family value the JV-1010 ignores is not offered
        else:
            options = list(enumerate(param.labels))
        for index, label in options:
            self._add(label, param.min + index)

    def _add(self, label, value):
        """An option under its readable name (core/friendly.py); the tooltip says what the unit's own display calls it."""
        name = friendly.label(self.param.key, label)
        self.addItem(name, value)
        if text := friendly.description(self.param.key, label):
            self.setItemData(self.count() - 1, text, Qt.ItemDataRole.ToolTipRole)
        elif name != label:
            self.setItemData(self.count() - 1, f"On the unit: {label}", Qt.ItemDataRole.ToolTipRole)

    def set_raw(self, value):
        index = self.findData(value)
        if index < 0:  # the unit holds a value we don't offer (a JV-1080-only choice, or outside the table): show it, don't hide it
            self.addItem(f"{friendly.label(self.param.key, params.format_value(self.param, value))} (not offered)", value)
            index = self.count() - 1
        self.setCurrentIndex(index)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class SwitchBox(QCheckBox):
    """An ON/OFF parameter as a check box (a tone's switch, in its card's heading): it says what it does, and it takes one click. Same small interface as the knobs (`set_value`, `value`)."""

    def __init__(self, param, text="On", parent=None):
        super().__init__(text, parent)
        self.param = param

    def set_value(self, value):
        """Show `value` (0 or 1) without telling anyone."""
        self.blockSignals(True)
        self.setChecked(bool(value))
        self.blockSignals(False)

    def value(self):
        return 1 if self.isChecked() else 0


class PatchEditor(QWidget):
    #: block key, parameter key, tone (0-3, or -1 for the common block), the value now in the patch (an int, or the text of the name)
    param_committed = Signal(str, str, int, object)
    #: one user gesture as [(block, key, tone or -1, old value, new value)]: a drag of an envelope handle changes two values at once, and Undo reverses them together
    edits_recorded = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._patch = None
        self._loading = False
        self._widgets = {}  # (block, tone or None, key) -> widget
        self._graphs = []  # (tone, the envelope graph)
        self._graph_of = {}  # (tone, parameter key) -> the graph that draws and edits it
        self._wave_labels = {}  # tone -> the label that names the tone's wave
        self._mixer = {}  # tone -> the Tone Mixer knob on the Common page (built with it)
        self._gesture = None  # while a graph commit applies several values: the edits so far, recorded together afterwards
        self.tabs = QTabWidget()
        self.tabs.setTabBar(FullWidthTabBar(self.tabs))
        # a tab's page is built when it is first shown: the five pages are ~600 widgets, which every window (and every test) would otherwise pay for
        self._holders = []
        self._built = set()
        for title in ["Common"] + [f"Tone {t + 1}" for t in range(patch.TONE_COUNT)]:
            holder = QWidget()
            QVBoxLayout(holder).setContentsMargins(0, 0, 0, 0)
            self._holders.append(holder)
            self.tabs.addTab(holder, title)
        self.tabs.currentChanged.connect(self._build_tab)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)
        self.setEnabled(False)

    # -- building --------------------------------------------------------------------------------------------------------

    def add_extra_tab(self, widget, title):
        """Add a tab after the parameter pages (the window's raw-values view)."""
        self.tabs.addTab(widget, title)

    def _build_tab(self, index):
        if index in self._built or not 0 <= index < len(self._holders):
            return
        self._built.add(index)
        tone = None if index == 0 else index - 1
        self._holders[index].layout().addWidget(self._page(patch.COMMON if tone is None else patch.TONE, tone))
        self.refresh()

    def _page(self, block_key, tone):
        scope = "patch_editor_common" if tone is None else "patch_editor_tone"
        cards, weights = [], []
        for title, members in groups.groups(block_key):
            form = QFormLayout()
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            grid = QGridLayout()
            grid.setHorizontalSpacing(2)
            grid.setVerticalSpacing(6)
            compact = sum(1 for p in members if not p.string and not p.has_choices()) >= COMPACT_FROM
            knobs = 0
            header = []  # small controls beside the card's title
            if block_key == patch.TONE and title == "Wave":
                form.addRow("Wave", self._wave_row(tone))
            for param in members:
                widget, control, is_knob = self._make_widget(block_key, tone, param, compact)
                self._widgets[(block_key, tone, param.key)] = control
                if param.key == "tone_switch":  # the tone's on/off sits in the Wave card's heading: "Wave [x] On"
                    header.append(control)
                    continue
                if is_knob:
                    grid.addWidget(widget, knobs // KNOBS_PER_ROW, knobs % KNOBS_PER_ROW, Qt.AlignmentFlag.AlignTop)
                    knobs += 1
                else:
                    form.addRow(param.name.replace("&", "&&"), widget)
                    form.labelForField(widget).setToolTip(widget.toolTip())
            rows = [layout_ for layout_, used in ((form, form.rowCount()), (grid, knobs)) if used]
            if block_key == patch.TONE and title in GRAPH_FOR_CARD:
                rows.insert(0, self._graph_row(tone, GRAPH_FOR_CARD[title]))
            cards.append(build_editor_card(scope, title, *rows, header_widgets=header, key=f"{title}"))
            weights.append(form.rowCount() + (2 if compact else 3) * -(-knobs // KNOBS_PER_ROW) + 2)
        if block_key == patch.COMMON:  # the four tones' levels side by side, next to the patch's own settings
            cards.insert(1, self._mixer_card())
            weights.insert(1, 7)
        return build_two_column_page(cards, weights)

    def _mixer_card(self):
        """"Tone Mixer": a knob for each tone's Tone Level (the same parameter as Tone Level on that tone's Level card), so the balance between the four tones is one glance."""
        param = params.load_table().block(patch.TONE).param("tone_level")
        grid = QGridLayout()
        grid.setHorizontalSpacing(2)
        for tone in range(patch.TONE_COUNT):
            knob = KnobControl(param)
            knob.name_label.setText(f"Tone {tone + 1}")
            knob.setToolTip(f"The level of tone {tone + 1}: the same as Tone Level on that tone's Level card.\n" + self._tooltip(patch.TONE, param, True))
            knob.committed.connect(lambda v, t=tone, p=param: self._edited(patch.TONE, t, p, v))
            grid.addWidget(knob, 0, tone, Qt.AlignmentFlag.AlignTop)
            self._mixer[tone] = knob
        return build_editor_card("patch_editor_common", "Tone Mixer", grid)

    def mixer_knob(self, tone):
        """The Tone Mixer knob of `tone` (builds the Common page if it has not been shown yet)."""
        self._build_tab(0)
        return self._mixer[tone]

    def _apply_mixer_states(self):
        """A tone that is switched off has its mixer knob greyed (its level is kept)."""
        if self._patch is None:
            return
        for tone, knob in self._mixer.items():
            on = bool(self._patch.get(patch.TONE, "tone_switch", tone=tone))
            knob.setEnabled(on)
            knob.setToolTip(knob.toolTip().split("\n(")[0] + ("" if on else f"\n(Tone {tone + 1} is switched off: its level is kept.)"))

    def _wave_row(self, tone):
        """The tone's wave by name, and a button to choose another."""
        label = QLabel()
        label.setWordWrap(True)
        label.setMinimumWidth(120)
        button = QPushButton("Choose...")
        button.setToolTip("Pick the wave by name (the group type, group ID and wave number are set together).")
        button.clicked.connect(lambda _checked=False, t=tone: self._choose_wave(t))
        self._wave_labels[tone] = label
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label, 1)
        layout.addWidget(button)
        return holder

    def _update_wave_labels(self):
        if self._patch is None:
            return
        for tone, label in self._wave_labels.items():
            args = [self._patch.get(patch.TONE, key, tone=tone) for key in ("wave_group_type", "wave_group_id", "wave_number")]
            described = waves.describe(*args) or f"Group type {args[0]}, ID {args[1]}, wave {args[2] + 1:03d} (no name known)"
            if self._patch.get(patch.TONE, "tone_switch", tone=tone):
                label.setText(described)
                label.setToolTip("")
            else:
                label.setText("No wave (tone off)")
                label.setToolTip(f"The tone is switched off. Its wave is still {described}.")

    def _choose_wave(self, tone):
        if self._patch is None:
            return
        current = [self._patch.get(patch.TONE, key, tone=tone) for key in ("wave_group_type", "wave_group_id", "wave_number")]
        dialog = WavePickerDialog(*current, parent=self)
        if dialog.exec() != WavePickerDialog.DialogCode.Accepted:
            return
        table = params.load_table().block(patch.TONE)
        self._gesture = []
        try:
            if dialog.wants_off:
                self._edited(patch.TONE, tone, table.param("tone_switch"), 0)
            else:
                for key, value in zip(("wave_group_type", "wave_group_id", "wave_number"), dialog.result_wave()):
                    self._edited(patch.TONE, tone, table.param(key), value)
                if not self._patch.get(patch.TONE, "tone_switch", tone=tone):
                    self._edited(patch.TONE, tone, table.param("tone_switch"), 1)  # choosing a wave for a silent tone means you want to hear it
        finally:
            gesture, self._gesture = self._gesture, None
        self.refresh()  # (the Tone Switch box follows)
        if gesture:
            self.edits_recorded.emit(gesture)

    def _graph_row(self, tone, graph_class):
        """An envelope graph for the top of a card. Dragging a handle moves the knobs and boxes LIVE; the patch (and so the unit) only changes when the drag
        is released, as for a knob. The knobs below stay for typing exact values."""
        graph = graph_class()
        graph.setToolTip("Drag a handle to change a stage's time (left and right) and level (up and down); the flat line is the sustain level. "
                         "Shift: fine. Double-click a handle: reset. Esc: cancel the drag.")
        table = params.load_table().block(patch.TONE)
        defaults = {}
        for name in graph.NAMES:
            origin = origin_value(table.param(name))
            defaults[name] = origin if origin is not None else table.param(name).min
        graph.set_defaults(defaults)
        graph.values_changed.connect(lambda changed, t=tone: self._graph_moved(t, changed))
        graph.edit_committed.connect(lambda changed, t=tone: self._graph_committed(t, changed))
        self._graphs.append((tone, graph))
        for name in graph.NAMES:
            self._graph_of[(tone, name)] = graph
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(graph)
        row.addStretch()
        return row

    def _graph_moved(self, tone, changed):
        """Live while a graph handle moves (or a drag is cancelled): show the values in the knobs without touching the patch."""
        for key, value in changed.items():
            self._widgets[(patch.TONE, tone, key)].set_value(value)

    def _graph_committed(self, tone, changed):
        table = params.load_table().block(patch.TONE)
        self._gesture = []
        try:
            for key, value in changed.items():
                self._edited(patch.TONE, tone, table.param(key), value)
        finally:
            gesture, self._gesture = self._gesture, None
        if gesture:
            self.edits_recorded.emit(gesture)

    def _sync_graphs(self, only=None):
        if self._patch is None:
            for _, graph in self._graphs:
                graph.set_editable(False)
            return
        for tone, graph in self._graphs:
            if only is not None and graph is not only:
                continue
            graph.set_values({name: self._patch.get(patch.TONE, name, tone=tone) for name in graph.NAMES})
            graph.set_editable(True)

    def _make_widget(self, block_key, tone, param, compact=False):
        """(widget to place, the control the editor reads and sets, is it a knob). A number is a `KnobControl` (name, knob, value readout: below the knob, or beside it when
        `compact`); a name or a choice list goes in a form row; a tone's switch is a check box (placed in its card's heading by `_page`)."""
        if param.key == "tone_switch":
            control = SwitchBox(param)
            control.clicked.connect(lambda checked, b=block_key, t=tone, p=param: self._edited(b, t, p, 1 if checked else 0))
            control.setToolTip(self._tooltip(block_key, param, False) + "\nOff: the tone makes no sound (its wave and settings are kept).")
            return control, control, False
        if param.string:
            control = QLineEdit()
            control.setMaxLength(param.size)
            control.editingFinished.connect(lambda w=control, p=param: self._name_edited(w, p))
            is_knob = False
        elif param.has_choices():
            control = ChoiceCombo(param)
            # sized by a typical item, not the longest one: a few lists (patch categories, EFX types) have long names that would widen the whole page
            control.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            control.setMinimumContentsLength(7)
            control.activated.connect(lambda _i, w=control, b=block_key, t=tone, p=param: self._edited(b, t, p, w.currentData()))
            is_knob = False
        else:
            control = KnobControl(param, compact=compact)
            control.committed.connect(lambda v, b=block_key, t=tone, p=param: self._edited(b, t, p, v))
            is_knob = True
        control.setToolTip(self._tooltip(block_key, param, is_knob))
        return control, control, is_knob

    @staticmethod
    def _tooltip(block_key, param, is_knob):
        """What the control is (a general explanation, see core/hints.py), its range as the unit shows it, and how to use a knob."""
        parts = []
        if text := hints.hint(block_key, param.key):
            parts.append(text)
        if not param.string and not param.has_choices():
            parts.append(f"Range: {params.format_value(param, param.min)} to {params.format_value(param, param.max)}")
            note = params.load_table().block(block_key).footnotes.get(param.footnote) if param.footnote else None
            if note:
                parts.append(f"({note})")
        if is_knob:
            parts.append("Drag to turn. Shift: fine. Double-click: reset. Click and type for an exact value.")
        return "\n".join(parts)

    # -- showing a patch -------------------------------------------------------------------------------------------------

    def set_patch(self, working):
        """Show `working` (a `Patch`, edited in place from now on), or nothing for None."""
        self._patch = working
        self.setEnabled(working is not None)
        if working is not None:
            self._build_tab(self.tabs.currentIndex())
            self.refresh()
        else:
            self._sync_graphs()

    def refresh(self):
        """Show the patch's current values again (after something else changed it). Emits nothing."""
        if self._patch is None:
            return
        self._loading = True
        try:
            for (block_key, tone, key), widget in self._widgets.items():
                value = self._patch.get(block_key, key, tone=tone)
                if isinstance(widget, QLineEdit):
                    widget.setText(value)
                elif isinstance(widget, ChoiceCombo):
                    widget.set_raw(value)
                else:
                    widget.set_value(value)
        finally:
            self._loading = False
        for tone, knob in self._mixer.items():
            knob.set_value(self._patch.get(patch.TONE, "tone_level", tone=tone))
        self._apply_mixer_states()
        self._apply_efx_labels()
        self._apply_structure_states()
        self._sync_graphs()
        self._update_wave_labels()

    def widget_for(self, block_key, key, tone=None):
        """The control for a parameter (builds its tab if it hasn't been shown yet)."""
        self._build_tab(0 if tone is None else tone + 1)
        return self._widgets[(block_key, tone, key)]

    # -- user edits ------------------------------------------------------------------------------------------------------

    def _apply_efx_labels(self):
        """EFX Parameter 1-12 mean different things for each of the 40 effect types: see `ui/efx.py`."""
        if self._patch is None or (patch.COMMON, None, "efx_parameter_1") not in self._widgets:
            return
        apply_efx_meanings({n: self._widgets[(patch.COMMON, None, f"efx_parameter_{n}")] for n in range(1, 13)}, self._patch.get(patch.COMMON, "efx_type"))

    #: the structure types that use the booster (the manual: "when the Structure Type is 03 or 04"), as raw values
    BOOSTER_TYPES = (2, 3)

    def _apply_structure_states(self):
        """The Booster only does anything for structure types 03 and 04: grey it out for the others (its value is kept)."""
        if self._patch is None or (patch.COMMON, None, "booster_1and2") not in self._widgets:
            return
        for structure, booster in (("structure_type_1and2", "booster_1and2"), ("structure_type_3and4", "booster_3and4")):
            used = self._patch.get(patch.COMMON, structure) in self.BOOSTER_TYPES
            control = self._widgets[(patch.COMMON, None, booster)]
            control.setEnabled(used)
            control.setToolTip(hints.hint(patch.COMMON, booster) if used else "Not used by this structure type: the booster only works with types 03 and 04.")

    def _edited(self, block_key, tone, param, value):
        if self._loading or self._patch is None:
            return
        old = self._patch.get(block_key, param.key, tone=tone)
        stored = self._patch.set(block_key, param.key, value, tone=tone)
        if param.key == "efx_type":
            self._apply_efx_labels()
        if param.key.startswith("structure_type"):
            self._apply_structure_states()
        if param.key in ("tone_switch", "wave_group_type", "wave_group_id", "wave_number"):
            self._update_wave_labels()
        if param.key == "tone_switch":
            self._apply_mixer_states()
        if block_key == patch.TONE and param.key == "tone_level":  # the mixer knob and the Level card's knob are one parameter: keep both showing it
            if tone in self._mixer:
                self._mixer[tone].set_value(stored)
            if (patch.TONE, tone, "tone_level") in self._widgets:
                self._widgets[(patch.TONE, tone, "tone_level")].set_value(stored)
        graph = self._graph_of.get((tone, param.key))
        if graph is not None:
            self._sync_graphs(only=graph)
        self.param_committed.emit(block_key, param.key, -1 if tone is None else tone, stored)
        self._record([(block_key, param.key, -1 if tone is None else tone, old, stored)])

    def _record(self, edits):
        edits = [e for e in edits if e[3] != e[4]]
        if not edits:
            return
        if self._gesture is not None:
            self._gesture.extend(edits)
        else:
            self.edits_recorded.emit(edits)

    def _name_edited(self, widget, param):
        if self._loading or self._patch is None:
            return
        before = self._patch.name
        stored = self._patch.set(patch.COMMON, param.key, widget.text())
        if widget.text() != stored:
            widget.setText(stored)  # show what the unit will hold (characters outside 32-125 become spaces)
        if stored != before:
            self.param_committed.emit(patch.COMMON, param.key, -1, stored)
            self._record([(patch.COMMON, param.key, -1, before, stored)])
