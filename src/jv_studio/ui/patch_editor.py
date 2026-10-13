"""The patch editor: one tab for the patch common block and one per tone, built from the parameter table (`core/groups.py` says which card a
parameter is on). It edits a `Patch` IN PLACE (the caller's working copy) and never talks to the unit: it emits `param_committed` for each user edit
and the window decides what to do with it (the owner's rule: the UI is live, MIDI goes out on release; a spin box commits on a step or Enter).
"""

from functools import lru_cache

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from jv_studio.core import groups, hints, params, patch, waves
from jv_studio.ui.envelope_graph import GRAPH_FOR_CARD
from jv_studio.ui.knob import Knob
from jv_studio.ui.wave_picker import WavePickerDialog
from jv_studio.ui.qt_helpers import FullWidthTabBar, build_editor_card, build_scroll_area


@lru_cache(maxsize=None)
def _text_to_value(param):
    """{displayed text, lower case: raw value} for a parameter whose range is small enough to list."""
    if param.max - param.min > 20000:
        return {}
    return {params.format_value(param, v).lower(): v for v in range(param.min, param.max + 1)}


#: a number with at most this many steps gets a knob over its box (a wave number's thousands of steps would be useless on one)
KNOB_MAX_STEPS = 255
KNOBS_PER_ROW = 4
KNOB_COLUMN_WIDTH = 78
KNOB_SIZE = 38
COMMIT_DELAY_MS = 150  # a wheel or arrow-key step on a knob commits this long after the last one


class ValueSpinBox(QSpinBox):
    """Shows a raw value the way the unit's display does (a note name, +12, L30, OFF...) and accepts that text back. The mouse wheel only acts when
    the box has focus, so scrolling a page of them never changes a value by accident."""

    def __init__(self, param, parent=None):
        super().__init__(parent)
        self.param = param
        self.setRange(param.min, param.max)
        self.setKeyboardTracking(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)  # the slider (or the arrow keys and wheel) moves it; the buttons only crowded the number
        self.setFixedWidth(60 if param.max - param.min < 1000 else 72)

    def textFromValue(self, value):
        return params.format_value(self.param, value)

    def _parse(self, text):
        return _text_to_value(self.param).get(text.strip().lower())

    def valueFromText(self, text):
        found = self._parse(text)
        return self.value() if found is None else found

    def validate(self, text, pos):
        state = QValidator.State.Acceptable if self._parse(text) is not None else QValidator.State.Intermediate
        return state, text, pos

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


def _origin_value(param):
    """The raw value a knob's arc grows from: the centre of a parameter that is shown as negative-to-positive (a pan, a tune), else None (the minimum)."""
    text = param.display_text or ""
    if param.display_min is not None and param.display_max is not None and param.display_min < 0 < param.display_max and param.max != param.min:
        return round(param.min + (0 - param.display_min) * (param.max - param.min) / (param.display_max - param.display_min))
    if text in ("L64 - 63R", "L63 - 63R"):
        return 64
    return None


class ChoiceCombo(QComboBox):
    def __init__(self, param, parent=None):
        super().__init__(parent)
        self.param = param
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        if param.choices:
            for index, choice in enumerate(param.choices):
                if choice.jv1010:  # a JV-1080-family value the JV-1010 ignores is not offered
                    self.addItem(choice.label, param.min + index)
        else:
            for index, label in enumerate(param.labels):
                self.addItem(label, param.min + index)

    def set_raw(self, value):
        index = self.findData(value)
        if index < 0:  # the unit holds a value we don't offer (a JV-1080-only choice, or outside the table): show it, don't hide it
            self.addItem(f"{params.format_value(self.param, value)} (not offered)", value)
            index = self.count() - 1
        self.setCurrentIndex(index)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


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
        self._knob_parts = {}  # (block, tone or None, key) -> (label, knob, column) of a number's knob column
        self._graphs = []  # (tone, the envelope graph)
        self._graph_of = {}  # (tone, parameter key) -> the graph that draws and edits it
        self._wave_labels = {}  # tone -> the label that names the tone's wave
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
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(6)
        scope = "patch_editor_common" if tone is None else "patch_editor_tone"
        # two columns of cards, each card going to the shorter column so the page stays balanced
        columns = [QVBoxLayout(), QVBoxLayout()]
        heights = [0, 0]
        for title, members in groups.groups(block_key):
            form = QFormLayout()
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            grid = QGridLayout()
            grid.setHorizontalSpacing(2)
            grid.setVerticalSpacing(6)
            knobs = 0
            if block_key == patch.TONE and title == "Wave":
                form.addRow("Wave", self._wave_row(tone))
            for param in members:
                widget, control, is_knob = self._make_widget(block_key, tone, param)
                self._widgets[(block_key, tone, param.key)] = control
                if is_knob:
                    grid.addWidget(widget, knobs // KNOBS_PER_ROW, knobs % KNOBS_PER_ROW, Qt.AlignmentFlag.AlignTop)
                    knobs += 1
                else:
                    form.addRow(param.name, widget)
                    form.labelForField(widget).setToolTip(widget.toolTip())
            rows = [layout_ for layout_, used in ((form, form.rowCount()), (grid, knobs)) if used]
            if block_key == patch.TONE and title in GRAPH_FOR_CARD:
                rows.insert(0, self._graph_row(tone, GRAPH_FOR_CARD[title]))
            side = 0 if heights[0] <= heights[1] else 1
            columns[side].addWidget(build_editor_card(scope, title, *rows, key=f"{title}"))
            heights[side] += form.rowCount() + 3 * -(-knobs // KNOBS_PER_ROW) + 2
        row = QHBoxLayout()
        row.setSpacing(6)
        for column in columns:
            column.setSpacing(6)
            column.addStretch()
            row.addLayout(column, 1)
        layout.addLayout(row)
        layout.addStretch()
        return build_scroll_area(page)

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
            label.setText(waves.describe(*args) or f"Group type {args[0]}, ID {args[1]}, wave {args[2] + 1:03d} (no name known)")

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
            for key, value in zip(("wave_group_type", "wave_group_id", "wave_number"), dialog.result_wave()):
                self._edited(patch.TONE, tone, table.param(key), value)
        finally:
            gesture, self._gesture = self._gesture, None
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
            origin = _origin_value(table.param(name))
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
        """Live while a graph handle moves (or a drag is cancelled): show the values in the knobs and boxes without touching the patch."""
        for key, value in changed.items():
            spin = self._widgets[(patch.TONE, tone, key)]
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
            parts = self._knob_parts.get((patch.TONE, tone, key))
            if parts:
                parts[1].blockSignals(True)
                parts[1].setValue(value)
                parts[1].blockSignals(False)

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

    def _make_widget(self, block_key, tone, param):
        """(widget to place, the control the editor reads and sets, is it a knob column). A number gets a knob column (label, knob, box); a name,
        a choice list or a huge range goes in a form row."""
        if param.string:
            control = QLineEdit()
            control.setMaxLength(param.size)
            control.editingFinished.connect(lambda w=control, p=param: self._name_edited(w, p))
            widget, is_knob = control, False
        elif param.has_choices():
            control = ChoiceCombo(param)
            # sized by a typical item, not the longest one: a few lists (patch categories, EFX types) have long names that would widen the whole page
            control.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            control.setMinimumContentsLength(7)
            control.activated.connect(lambda _i, w=control, b=block_key, t=tone, p=param: self._edited(b, t, p, w.currentData()))
            widget, is_knob = control, False
        else:
            control = ValueSpinBox(param)
            control.valueChanged.connect(lambda v, b=block_key, t=tone, p=param: self._edited(b, t, p, v))
            if param.max - param.min <= KNOB_MAX_STEPS:
                widget, is_knob = self._knob_column(block_key, tone, param, control), True
            else:
                widget, is_knob = control, False
        widget.setToolTip(self._tooltip(block_key, param, is_knob))
        return widget, control, is_knob

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
            parts.append("Drag to turn. Shift: fine. Double-click: reset.")
        return "\n".join(parts)

    def _knob_column(self, block_key, tone, param, spin):
        """Label over a knob over the value box. Turning the knob shows the value live in the box and commits when the drag is RELEASED; a wheel or
        arrow-key step commits shortly after the last one; typing in the box commits like any box edit (its own signal). The box moves the knob
        silently, the knob moves the box silently: one commit path each."""
        column = QWidget()
        column.setObjectName("transparentContainer")  # the card's own colour, not the page's
        column.setFixedWidth(KNOB_COLUMN_WIDTH)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        label = QLabel(param.name)
        label.setObjectName("knobLabel")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        label.setMinimumHeight(30)  # room for two lines, so a row of knobs lines up whether or not a name wraps
        knob = Knob()
        knob.setRange(param.min, param.max)
        knob.setFixedSize(KNOB_SIZE, KNOB_SIZE)
        knob.setNotchesVisible(False)
        origin = _origin_value(param)
        knob.setOriginValue(origin)
        knob.setDefaultValue(origin if origin is not None else param.min)
        knob.setValue(spin.value())
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        timer = QTimer(column)
        timer.setSingleShot(True)
        timer.setInterval(COMMIT_DELAY_MS)

        def set_silently(widget, value):
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)

        def commit():
            timer.stop()
            self._edited(block_key, tone, param, knob.value())

        def knob_moved(value):
            set_silently(spin, value)
            if not knob.is_dragging():
                timer.start()  # a wheel or key step

        timer.timeout.connect(commit)
        knob.valueChanged.connect(knob_moved)
        knob.sliderReleased.connect(commit)
        spin.valueChanged.connect(lambda v: set_silently(knob, v))
        layout.addWidget(label)
        layout.addWidget(knob, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(spin, alignment=Qt.AlignmentFlag.AlignHCenter)
        column.knob = knob
        self._knob_parts[(block_key, tone, param.key)] = (label, knob, column)
        return column

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
            table = params.load_table()
            for (block_key, tone, key), widget in self._widgets.items():
                param = table.block(block_key).param(key)
                value = self._patch.get(block_key, key, tone=tone)
                if isinstance(widget, QLineEdit):
                    widget.setText(value)
                elif isinstance(widget, ChoiceCombo):
                    widget.set_raw(value)
                else:
                    widget.setValue(max(param.min, min(param.max, value)))
        finally:
            self._loading = False
        self._apply_efx_labels()
        self._sync_graphs()
        self._update_wave_labels()

    def widget_for(self, block_key, key, tone=None):
        """The control for a parameter (builds its tab if it hasn't been shown yet)."""
        self._build_tab(0 if tone is None else tone + 1)
        return self._widgets[(block_key, tone, key)]

    # -- user edits ------------------------------------------------------------------------------------------------------

    def _apply_efx_labels(self):
        """EFX Parameter 1-12 mean different things for each of the 40 effect types: name their knobs after the chosen type and grey out the ones it
        doesn't use. Only labels, tooltips and the knob's travel change; the box keeps showing (and the patch keeps holding) the real value."""
        if self._patch is None or (patch.COMMON, None, "efx_parameter_1") not in self._knob_parts:
            return
        efx = params.load_table().efx_type(self._patch.get(patch.COMMON, "efx_type"))
        for n in range(1, 13):
            label, knob, column = self._knob_parts[(patch.COMMON, None, f"efx_parameter_{n}")]
            meaning = efx.param(n) if efx is not None else params.EfxParam(n, f"EFX Parameter {n}")
            used = meaning.name is not None
            label.setText(meaning.name if used else "(not used)")
            column.setEnabled(used)
            column.setToolTip(f"{meaning.name} ({efx.name}): {meaning.min} to {meaning.max}.\nDrag to turn. Shift: fine. Double-click: reset." if used and efx is not None else "")
            spin = self._widgets[(patch.COMMON, None, f"efx_parameter_{n}")]
            knob.blockSignals(True)
            knob.setRange(meaning.min, meaning.max)
            knob.setValue(max(meaning.min, min(meaning.max, spin.value())))
            knob.blockSignals(False)

    def _edited(self, block_key, tone, param, value):
        if self._loading or self._patch is None:
            return
        old = self._patch.get(block_key, param.key, tone=tone)
        stored = self._patch.set(block_key, param.key, value, tone=tone)
        if param.key == "efx_type":
            self._apply_efx_labels()
        if param.key in ("wave_group_type", "wave_group_id", "wave_number"):
            self._update_wave_labels()
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
