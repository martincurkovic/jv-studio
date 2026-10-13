"""The performance editor: the parts as a mixer, one part in detail, the effects, and the setup (name, tempo, voice reserve). The sibling of `patch_editor.py`.

It edits a `Performance` IN PLACE (the caller's working copy) and never talks to the unit: it emits `param_committed(block, key, part, value)` for each user edit (part is -1 for the
common block) and `edits_recorded` once per gesture (choosing a part's patch sets three parameters, which Undo reverses together). The owner's rule applies: the UI is live, MIDI
goes out on release.

Tabs: Parts (a 16-row mixer: on, channel, patch by name, level, pan, output), Part (every setting of the chosen part), Effects (EFX, chorus, reverb) and Setup (name, tempo, voice
reserve). Which card a parameter is on comes from `core/groups.py`, as for patches; the JV-1080-only settings are not shown.
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

from jv_studio.core import groups, params, patch_groups, performance
from jv_studio.ui.efx import apply_efx_meanings
from jv_studio.ui.knob_control import KnobControl
from jv_studio.ui.patch_editor import COMPACT_FROM, KNOBS_PER_ROW, ChoiceCombo, PatchEditor
from jv_studio.ui.patch_picker import PatchPickerDialog
from jv_studio.ui.qt_helpers import FullWidthTabBar, build_editor_card, build_scroll_area, build_two_column_page

PARTS_TAB, PART_TAB, EFFECTS_TAB, SETUP_TAB = 0, 1, 2, 3
GRID_KNOB_SIZE = 28
DETAIL = "detail"  # the part a control belongs to when it edits "whichever part the Part tab shows"
TOTAL_VOICES = 64
EFFECT_CARDS = ("EFX", "Chorus", "Reverb & Delay")
SETUP_CARDS = ("Performance",)  # (the voice reserve is a column of the Parts mixer: one small knob per part, with a running total)
DETAIL_CARDS = ("Part", "Mix", "Keyboard")


class PerformanceEditor(QWidget):
    #: block key, parameter key, part (0-15, or -1 for the common block), the value now in the performance (an int, or the text of the name)
    param_committed = Signal(str, str, int, object)
    #: one user gesture as [(block, key, part or -1, old value, new value)]
    edits_recorded = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._perf = None
        self._loading = False
        self._gesture = None
        self._part = 0  # the part shown on the Part tab
        self._user_names = None
        self._common = {}  # key -> control (the Effects and Setup tabs)
        self._grid = {}  # (part, key) -> control (the Parts tab)
        self._detail = {}  # key -> control (the Part tab, for the chosen part)
        self._grid_patch = {}  # part -> the button that names its patch
        self._part_buttons = []
        self.tabs = QTabWidget()
        self.tabs.setTabBar(FullWidthTabBar(self.tabs))
        self.tabs.addTab(self._parts_page(), "Parts")
        self.tabs.addTab(self._part_page(), "Part")
        self.tabs.addTab(self._cards_page(performance.COMMON, EFFECT_CARDS, "performance_effects"), "Effects")
        self.tabs.addTab(self._setup_page(), "Setup")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)
        self.setEnabled(False)

    # -- building --------------------------------------------------------------------------------------------------------

    def _make_control(self, block_key, part, param, *, compact=False, show_name=True, knob_size=38):
        """(control, is_knob): a name is a line edit, a choice list a `ChoiceCombo`, a number a `KnobControl`."""
        if param.string:
            control = QLineEdit()
            control.setMaxLength(param.size)
            control.editingFinished.connect(lambda w=control, p=param: self._name_edited(w, p))
            is_knob = False
        elif param.has_choices():
            control = ChoiceCombo(param)
            control.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            control.setMinimumContentsLength(4 if param.key == "midi_channel" else 7)
            control.activated.connect(lambda _i, w=control, b=block_key, pt=part, p=param: self._edited(b, pt, p, w.currentData()))
            is_knob = False
        else:
            control = KnobControl(param, compact=compact, show_name=show_name, knob_size=knob_size)
            control.committed.connect(lambda v, b=block_key, pt=part, p=param: self._edited(b, pt, p, v))
            is_knob = True
        control.setToolTip(PatchEditor._tooltip(block_key, param, is_knob))
        return control, is_knob

    def _card(self, scope, title, block_key, part, members, register, extra_rows=()):
        """One card: the combos and name in a form, the numbers as knobs below it (the compact layout for a card with many)."""
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        grid = QGridLayout()
        grid.setHorizontalSpacing(2)
        grid.setVerticalSpacing(6)
        compact = sum(1 for p in members if not p.string and not p.has_choices()) >= COMPACT_FROM
        knobs = 0
        for param in members:
            control, is_knob = self._make_control(block_key, part, param, compact=compact)
            register[param.key] = control
            if is_knob:
                grid.addWidget(control, knobs // KNOBS_PER_ROW, knobs % KNOBS_PER_ROW, Qt.AlignmentFlag.AlignTop)
                knobs += 1
            else:
                form.addRow(param.name, control)
                form.labelForField(control).setToolTip(control.toolTip())
        rows = [layout_ for layout_, used in ((form, form.rowCount()), (grid, knobs)) if used] + list(extra_rows)
        weight = form.rowCount() + (2 if compact else 3) * -(-knobs // KNOBS_PER_ROW) + 2
        return build_editor_card(scope, title, *rows, key=title), weight

    def _cards_page(self, block_key, titles, scope, extra_rows=None):
        """The common block's cards named in `titles`, in two locked columns. `extra_rows` is {card title: [layouts]} to append to a card."""
        cards, weights = [], []
        for title, members in groups.groups(block_key):
            if title in titles:
                card, weight = self._card(scope, title, block_key, None, members, self._common, (extra_rows or {}).get(title, ()))
                cards.append(card)
                weights.append(weight)
        return build_two_column_page(cards, weights)

    def _setup_page(self):
        return self._cards_page(performance.COMMON, SETUP_CARDS, "performance_setup")

    def _part_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(10, 8, 10, 0)
        top = QHBoxLayout()
        self.part_combo = QComboBox()
        for part in range(performance.PART_COUNT):
            self.part_combo.addItem(f"Part {part + 1}", part)
        self.part_combo.setToolTip("Which part to edit.")
        self.part_combo.activated.connect(lambda _i: self.select_part(self.part_combo.currentData(), jump=False))
        self.detail_patch_label = QLabel()
        self.detail_patch_label.setWordWrap(True)
        choose = QPushButton("Choose Patch...")
        choose.setToolTip("Pick the patch this part plays, by name.")
        choose.clicked.connect(lambda _checked=False: self._choose_patch(self._part))
        top.addWidget(self.part_combo)
        top.addWidget(self.detail_patch_label, 1)
        top.addWidget(choose)
        outer.addLayout(top)
        cards, weights = [], []
        for title, members in groups.groups(performance.PART):
            card, weight = self._card("performance_part", title, performance.PART, DETAIL, members, self._detail)
            cards.append(card)
            weights.append(weight)
        outer.addWidget(build_two_column_page(cards, weights), 1)
        return page

    def _parts_page(self):
        """The mixer: one row per part."""
        table = params.load_table().block(performance.PART)
        common = params.load_table().block(performance.COMMON)
        page = QWidget()
        grid = QGridLayout(page)
        grid.setContentsMargins(12, 10, 16, 10)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        for column, (title, tip) in enumerate((("Part", ""), ("On", "Whether the part plays."), ("Ch", "The MIDI channel the part listens to."), ("Patch", "The patch the part plays. Click to choose another."),
                                               ("Level", "The part's level."), ("Pan", "The part's pan."),
                                               ("Voices", f"How many of the unit's {TOTAL_VOICES} voices are kept for the part (Voice Reserve), so other parts can't take them."), ("Output", "Where the part goes."))):
            header = QLabel(title)
            header.setObjectName("sectionHeader")
            header.setToolTip(tip)
            grid.addWidget(header, 0, column)
        for part in range(performance.PART_COUNT):
            row = part + 1
            button = QPushButton(str(part + 1))
            button.setFlat(True)
            button.setFixedWidth(42)
            button.setToolTip(f"Edit all of part {part + 1}'s settings.")
            button.clicked.connect(lambda _checked=False, p=part: self.select_part(p))
            self._part_buttons.append(button)
            grid.addWidget(button, row, 0)
            on = QCheckBox()
            on.setToolTip(PatchEditor._tooltip(performance.PART, table.param("receive_switch"), False))
            on.clicked.connect(lambda checked, p=part: self._edited(performance.PART, p, table.param("receive_switch"), 1 if checked else 0))
            self._grid[(part, "receive_switch")] = on
            grid.addWidget(on, row, 1, Qt.AlignmentFlag.AlignHCenter)
            for column, key in ((2, "midi_channel"),):
                control, _ = self._make_control(performance.PART, part, table.param(key))
                self._grid[(part, key)] = control
                grid.addWidget(control, row, column)
            patch_button = QPushButton()
            patch_button.setFlat(True)
            patch_button.setStyleSheet("text-align: left; padding-left: 4px;")
            patch_button.clicked.connect(lambda _checked=False, p=part: self._choose_patch(p))
            self._grid_patch[part] = patch_button
            grid.addWidget(patch_button, row, 3)
            for column, key in ((4, "part_level"), (5, "part_pan")):
                control, _ = self._make_control(performance.PART, part, table.param(key), compact=True, show_name=False, knob_size=GRID_KNOB_SIZE)
                self._grid[(part, key)] = control
                grid.addWidget(control, row, column)
            reserve_key = f"voice_reserve_{part + 1}"  # a common-block parameter, shown on the part's own row
            reserve, _ = self._make_control(performance.COMMON, None, common.param(reserve_key), compact=True, show_name=False, knob_size=GRID_KNOB_SIZE)
            self._common[reserve_key] = reserve
            grid.addWidget(reserve, row, 6)
            control, _ = self._make_control(performance.PART, part, table.param("output_assign"))
            self._grid[(part, "output_assign")] = control
            grid.addWidget(control, row, 7)
        grid.setColumnStretch(3, 1)
        grid.setRowStretch(performance.PART_COUNT + 1, 1)
        area = build_scroll_area(page)
        area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.reserve_label = QLabel()
        self.reserve_label.setObjectName("mutedLabel")
        self.reserve_label.setToolTip(f"The unit has {TOTAL_VOICES} voices. Voice Reserve keeps some of them for each part.")
        holder = QWidget()
        outer = QVBoxLayout(holder)
        outer.setContentsMargins(12, 6, 16, 0)
        outer.setSpacing(2)
        outer.addWidget(self.reserve_label)
        outer.addWidget(area, 1)
        return holder

    def add_extra_tab(self, widget, title):
        """Add a tab after the editor's own pages (the window's raw-values view)."""
        self.tabs.addTab(widget, title)

    # -- showing a performance -------------------------------------------------------------------------------------------

    def set_user_patch_names(self, names):
        """The USER patch names read from the unit (or None): the patch buttons and the picker use them."""
        self._user_names = list(names) if names else None
        self._update_patch_labels()

    def set_performance(self, working):
        """Show `working` (a `Performance`, edited in place from now on), or nothing for None."""
        self._perf = working
        self.setEnabled(working is not None)
        if working is not None:
            self.refresh()

    def refresh(self):
        """Show the performance's current values again (after something else changed it). Emits nothing."""
        if self._perf is None:
            return
        self._loading = True
        try:
            for key, control in self._common.items():
                self._show(control, performance.COMMON, key, None)
            for (part, key), control in self._grid.items():
                self._show(control, performance.PART, key, part)
            for key, control in self._detail.items():
                self._show(control, performance.PART, key, self._part)
        finally:
            self._loading = False
        self._apply_efx()
        self._update_patch_labels()
        self._update_reserve_total()

    def _show(self, control, block_key, key, part):
        value = self._perf.get(block_key, key, part=part)
        if isinstance(control, QLineEdit):
            control.setText(value)
        elif isinstance(control, ChoiceCombo):
            control.set_raw(value)
        elif isinstance(control, QCheckBox):
            control.setChecked(bool(value))
        else:
            control.set_value(value)

    def widget_for(self, block_key, key, part=None, grid=False):
        """The control for a parameter: a common one, a part's in the Parts grid (`grid=True`), or the Part tab's (for the part shown there)."""
        if block_key == performance.COMMON:
            return self._common[key]
        return self._grid[(part, key)] if grid else self._detail[key]

    def select_part(self, part, jump=True):
        self._part = part
        self.part_combo.setCurrentIndex(part)
        self.refresh()
        if jump:
            self.tabs.setCurrentIndex(PART_TAB)

    def _apply_efx(self):
        if self._perf is None or "efx_parameter_1" not in self._common:
            return
        apply_efx_meanings({n: self._common[f"efx_parameter_{n}"] for n in range(1, 13)}, self._perf.get(performance.COMMON, "efx_type"))

    def _update_reserve_total(self):
        if self._perf is None or not hasattr(self, "reserve_label"):
            return
        total = sum(self._perf.get(performance.COMMON, f"voice_reserve_{n}") for n in range(1, performance.PART_COUNT + 1))
        self.reserve_label.setText(f"Total reserved: {total} of {TOTAL_VOICES} voices")

    def _assignment(self, part):
        return [self._perf.get(performance.PART, key, part=part) for key in ("patch_group_type", "patch_group_id", "patch_number")]

    def _update_patch_labels(self):
        if self._perf is None:
            return
        for part, button in self._grid_patch.items():
            text = patch_groups.describe(*self._assignment(part), self._user_names)
            button.setText(text)
            button.setToolTip(f"Part {part + 1} plays {text}. Click to choose another patch.")
        self.detail_patch_label.setText(patch_groups.describe(*self._assignment(self._part), self._user_names))

    # -- user edits ------------------------------------------------------------------------------------------------------

    def _edited(self, block_key, part, param, value):
        if self._loading or self._perf is None:
            return
        if part == DETAIL:
            part = self._part
        old = self._perf.get(block_key, param.key, part=part)
        stored = self._perf.set(block_key, param.key, value, part=part)
        self._after_change(block_key, param.key, part)
        self.param_committed.emit(block_key, param.key, -1 if part is None else part, stored)
        self._record([(block_key, param.key, -1 if part is None else part, old, stored)])

    def _after_change(self, block_key, key, part):
        """Keep every view of the same value in step: the grid and the detail show a part's parameters twice."""
        if block_key == performance.COMMON:
            if key == "efx_type":
                self._apply_efx()
            if key.startswith("voice_reserve_"):
                self._update_reserve_total()
            return
        for control in (self._grid.get((part, key)), self._detail.get(key) if part == self._part else None):
            if control is not None:
                self._loading = True
                try:
                    self._show(control, performance.PART, key, part)
                finally:
                    self._loading = False
        if key.startswith("patch_"):
            self._update_patch_labels()

    def _name_edited(self, widget, param):
        if self._loading or self._perf is None:
            return
        before = self._perf.name
        stored = self._perf.set(performance.COMMON, param.key, widget.text())
        if widget.text() != stored:
            widget.setText(stored)  # show what the unit will hold (characters outside 32-125 become spaces)
        if stored != before:
            self.param_committed.emit(performance.COMMON, param.key, -1, stored)
            self._record([(performance.COMMON, param.key, -1, before, stored)])

    def _record(self, edits):
        edits = [e for e in edits if e[3] != e[4]]
        if not edits:
            return
        if self._gesture is not None:
            self._gesture.extend(edits)
        else:
            self.edits_recorded.emit(edits)

    def _choose_patch(self, part):
        if self._perf is None:
            return
        dialog = PatchPickerDialog(*self._assignment(part), user_names=self._user_names, parent=self)
        if dialog.exec() != PatchPickerDialog.DialogCode.Accepted:
            return
        table = params.load_table().block(performance.PART)
        self._gesture = []
        try:
            for key, value in zip(("patch_group_type", "patch_group_id", "patch_number"), dialog.result_patch()):
                self._edited(performance.PART, part, table.param(key), value)
        finally:
            gesture, self._gesture = self._gesture, None
        if gesture:
            self.edits_recorded.emit(gesture)
