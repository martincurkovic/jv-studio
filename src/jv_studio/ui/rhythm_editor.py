"""The rhythm set editor: a mini keyboard of the 64 keys (35-98) that chooses the key to edit, the shown key's tone in cards built from the parameter table (`core/groups.py`), and the set's name.

A rhythm set is a drum kit: every key has its own wave, tuning, filter, envelopes, level, pan and effect sends. The editor edits a `RhythmSet` IN PLACE (the caller's working copy) and
never talks to the unit: it emits `param_committed(block, key, note, value)` for each user edit and `keys_changed` after a copy or swap, and the panel decides what to send. The controls
are built once and always show the CHOSEN key: every handler reads `self._key` when it runs, never a key captured at build time (a captured key would edit the first key forever).
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from jv_studio.core import groups, params, rhythm, waves
from jv_studio.ui.envelope_graph import GRAPH_FOR_CARD
from jv_studio.ui.keyboard import KeySelector
from jv_studio.ui.knob_control import KnobControl, origin_value
from jv_studio.ui.patch_editor import COMPACT_FROM, KNOBS_PER_ROW, ChoiceCombo, PatchEditor, SwitchBox
from jv_studio.ui.qt_helpers import FullWidthTabBar, build_editor_card, build_two_column_page
from jv_studio.ui.wave_picker import WavePickerDialog

DEFAULT_KEY = 36


def key_title(key):
    return f"{key} ({params.note_name(key)})"


class RhythmEditor(QWidget):
    #: block key, parameter key, the MIDI key (35-98, or -1 for the common block), the value now in the set
    param_committed = Signal(str, str, int, object)
    #: one gesture as [(block, key, note or -1, old, new)]: Undo reverses it whole
    edits_recorded = Signal(list)
    #: keys whose WHOLE tone changed at once (a copy or a swap), after the edits were recorded
    keys_changed = Signal(list)
    #: a key button was pressed and "Play on click" is on: the panel sounds it
    key_clicked = Signal(int)
    #: another key is now shown (a click or `choose_key`)
    key_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._set = None
        self._key = DEFAULT_KEY
        self._loading = False
        self._widgets = {}  # parameter key -> control
        self._graphs = []
        self._graph_of = {}  # parameter key -> graph
        self._wave_label = None
        self._gesture = None

        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(12)
        self.name_edit.setToolTip("The name of the rhythm set (12 characters).")
        self.name_edit.editingFinished.connect(self._name_edited)
        self.play_check = QCheckBox("Play on click")
        self.play_check.setChecked(True)
        self.play_check.setToolTip("Sound the key on the unit when you click it (a key that is clicked plays on the channel set above). Part 10 of a performance plays the rhythm set.")
        self.copy_button = QPushButton("Copy Key To...")
        self.copy_button.setToolTip("Give another key the shown key's whole tone.")
        self.copy_button.clicked.connect(self._copy_key)
        self.swap_button = QPushButton("Swap Key With...")
        self.swap_button.setToolTip("Exchange the shown key's tone with another key's.")
        self.swap_button.clicked.connect(self._swap_key)

        header = QHBoxLayout()
        header.addWidget(QLabel("Name"))
        header.addWidget(self.name_edit, 1)
        header.addSpacing(12)
        header.addWidget(self.play_check)
        header.addStretch()
        header.addWidget(self.copy_button)
        header.addWidget(self.swap_button)

        self.selector = KeySelector(rhythm.FIRST_KEY, rhythm.LAST_KEY)
        self.selector.set_selected(DEFAULT_KEY)
        self.selector.key_picked.connect(self._key_pressed)
        self.selector.set_tooltip_provider(self._key_tooltip)
        self.key_label = QLabel()
        self.key_label.setObjectName("sectionHeader")
        self.key_label.setWordWrap(True)

        self._holder = QWidget()  # the key's cards, built when a set first arrives (about 90 widgets)
        QVBoxLayout(self._holder).setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.setTabBar(FullWidthTabBar(self.tabs))
        key_page = QWidget()
        page_layout = QVBoxLayout(key_page)
        page_layout.setContentsMargins(0, 6, 0, 0)
        page_layout.addLayout(header)
        page_layout.addWidget(self.selector)
        page_layout.addWidget(self.key_label)
        page_layout.addWidget(self._holder, 1)
        self.tabs.addTab(key_page, "Key")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)
        self._built = False
        self.setEnabled(False)

    # -- building --------------------------------------------------------------------------------------------------------

    def add_extra_tab(self, widget, title):
        self.tabs.addTab(widget, title)

    def _ensure_page(self):
        if self._built:
            return
        self._built = True
        cards, weights = [], []
        for title, members in groups.groups(rhythm.NOTE):
            form = QFormLayout()
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            grid = QGridLayout()
            grid.setHorizontalSpacing(2)
            grid.setVerticalSpacing(6)
            compact = sum(1 for p in members if not p.string and not p.has_choices()) >= COMPACT_FROM
            knobs = 0
            header = []
            if title == "Wave":
                form.addRow("Wave", self._wave_row())
            for param in members:
                control, is_knob = self._make_control(param, compact)
                self._widgets[param.key] = control
                if param.key == "tone_switch":  # on/off in the card's heading, as on a patch's tones
                    header.append(control)
                    continue
                if is_knob:
                    grid.addWidget(control, knobs // KNOBS_PER_ROW, knobs % KNOBS_PER_ROW, Qt.AlignmentFlag.AlignTop)
                    knobs += 1
                else:
                    form.addRow(param.name.replace("&", "&&"), control)
                    form.labelForField(control).setToolTip(control.toolTip())
            rows = [layout_ for layout_, used in ((form, form.rowCount()), (grid, knobs)) if used]
            if title in GRAPH_FOR_CARD:
                rows.insert(0, self._graph_row(GRAPH_FOR_CARD[title]))
            cards.append(build_editor_card("rhythm_editor", title, *rows, header_widgets=header))
            weights.append(form.rowCount() + (2 if compact else 3) * -(-knobs // KNOBS_PER_ROW) + 2)
        self._holder.layout().addWidget(build_two_column_page(cards, weights))

    def _wave_row(self):
        self._wave_label = QLabel()
        self._wave_label.setWordWrap(True)
        self._wave_label.setMinimumWidth(120)
        button = QPushButton("Choose...")
        button.setToolTip("Pick the wave by name (the group type, group ID and wave number are set together).")
        button.clicked.connect(lambda _checked=False: self._choose_wave())
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self._wave_label, 1)
        row.addWidget(button)
        return holder

    def _graph_row(self, graph_class):
        graph = graph_class()
        graph.setToolTip("Drag a handle to change a stage's time (left and right) and level (up and down); the flat line is the sustain level. Shift: fine. Double-click a handle: reset. Esc: cancel the drag.")
        table = params.load_table().block(rhythm.NOTE)
        defaults = {}
        for name in graph.NAMES:
            origin = origin_value(table.param(name))
            defaults[name] = origin if origin is not None else table.param(name).min
        graph.set_defaults(defaults)
        graph.values_changed.connect(self._graph_moved)
        graph.edit_committed.connect(self._graph_committed)
        self._graphs.append(graph)
        for name in graph.NAMES:
            self._graph_of[name] = graph
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(graph)
        row.addStretch()
        return row

    def _make_control(self, param, compact):
        if param.key == "tone_switch":
            control = SwitchBox(param)
            control.clicked.connect(lambda checked, p=param: self._edited(p, 1 if checked else 0))
            control.setToolTip(PatchEditor._tooltip(rhythm.NOTE, param, False) + "\nOff: this key makes no sound (its wave and settings are kept).")
            return control, False
        if param.has_choices():
            control = ChoiceCombo(param)
            control.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            control.setMinimumContentsLength(7)
            control.activated.connect(lambda _i, w=control, p=param: self._edited(p, w.currentData()))
            is_knob = False
        else:
            control = KnobControl(param, compact=compact)
            control.committed.connect(lambda v, p=param: self._edited(p, v))
            is_knob = True
        control.setToolTip(PatchEditor._tooltip(rhythm.NOTE, param, is_knob))
        return control, is_knob

    # -- showing a set ---------------------------------------------------------------------------------------------------

    def set_rhythm(self, working):
        """Show `working` (a `RhythmSet`, edited in place from now on), or nothing for None."""
        self._set = working
        self.setEnabled(working is not None)
        if working is not None:
            self._ensure_page()
        self.refresh()

    def chosen_key(self):
        return self._key

    def choose_key(self, key):
        """Show `key` (35-98) in the cards without playing it."""
        if key in rhythm.KEYS:
            self._key = key
            self.selector.set_selected(key)
            self.refresh()
            self.key_changed.emit(key)

    def _key_pressed(self, key):
        self._key = key
        self.selector.set_selected(key)
        self.refresh()
        self.key_changed.emit(key)
        if self.play_check.isChecked():
            self.key_clicked.emit(key)

    def refresh(self):
        """Show the set's current values again. Emits nothing."""
        self._loading = True
        try:
            if self._set is None:
                self.name_edit.clear()
                self.key_label.setText("")
                self._sync_graphs()
                return
            self.name_edit.setText(self._set.name)
            for key, widget in self._widgets.items():
                value = self._set.get(rhythm.NOTE, key, key=self._key)
                if isinstance(widget, ChoiceCombo):
                    widget.set_raw(value)
                else:
                    widget.set_value(value)
            self._sync_graphs()
            self._update_wave_label()
            self._update_keys()
        finally:
            self._loading = False

    def _wave_text(self, key):
        args = [self._set.get(rhythm.NOTE, name, key=key) for name in ("wave_group_type", "wave_group_id", "wave_number")]
        return waves.describe(*args) or f"Group type {args[0]}, ID {args[1]}, wave {args[2] + 1:03d} (no name known)"

    def _update_wave_label(self):
        if self._set is None:
            return
        described = self._wave_text(self._key)
        on = self._set.get(rhythm.NOTE, "tone_switch", key=self._key)
        if self._wave_label is not None:
            self._wave_label.setText(described if on else "No wave (tone off)")
            self._wave_label.setToolTip("" if on else f"The tone is switched off. Its wave is still {described}.")
        self.key_label.setText(f"Key {key_title(self._key)} · {described if on else 'tone off'}")

    def _update_keys(self):
        """A key whose tone is off is drawn greyed on the keyboard."""
        if self._set is not None:
            self.selector.set_dimmed([key for key in rhythm.KEYS if not self._set.get(rhythm.NOTE, "tone_switch", key=key)])

    def _key_tooltip(self, key):
        """What the pointer is over: the key and its wave (or that its tone is off)."""
        if self._set is None or key not in rhythm.KEYS:
            return f"Key {key_title(key)}"
        on = self._set.get(rhythm.NOTE, "tone_switch", key=key)
        return f"Key {key_title(key)}: {self._wave_text(key) if on else 'tone off'}"

    def _sync_graphs(self):
        for graph in self._graphs:
            if self._set is None:
                graph.set_editable(False)
                continue
            graph.set_values({name: self._set.get(rhythm.NOTE, name, key=self._key) for name in graph.NAMES})
            graph.set_editable(True)

    def widget_for(self, key):
        self._ensure_page()
        return self._widgets[key]

    # -- user edits ------------------------------------------------------------------------------------------------------

    def _edited(self, param, value):
        if self._loading or self._set is None:
            return
        note = self._key
        old = self._set.get(rhythm.NOTE, param.key, key=note)
        stored = self._set.set(rhythm.NOTE, param.key, value, key=note)
        if param.key in ("tone_switch", "wave_group_type", "wave_group_id", "wave_number"):
            self._update_wave_label()
            self._update_keys()
        graph = self._graph_of.get(param.key)
        if graph is not None:
            graph.set_values({name: self._set.get(rhythm.NOTE, name, key=note) for name in graph.NAMES})
        self.param_committed.emit(rhythm.NOTE, param.key, note, stored)
        self._record([(rhythm.NOTE, param.key, note, old, stored)])

    def _record(self, edits):
        edits = [e for e in edits if e[3] != e[4]]
        if not edits:
            return
        if self._gesture is not None:
            self._gesture.extend(edits)
        else:
            self.edits_recorded.emit(edits)

    def _gestured(self, apply):
        """Run `apply` (which makes several edits) so that Undo reverses them together."""
        self._gesture = []
        try:
            apply()
        finally:
            gesture, self._gesture = self._gesture, None
        if gesture:
            self.edits_recorded.emit(gesture)

    def _graph_moved(self, changed):
        for key, value in changed.items():
            self._widgets[key].set_value(value)

    def _graph_committed(self, changed):
        table = params.load_table().block(rhythm.NOTE)
        self._gestured(lambda: [self._edited(table.param(key), value) for key, value in changed.items()])

    def _choose_wave(self):
        if self._set is None:
            return
        current = [self._set.get(rhythm.NOTE, name, key=self._key) for name in ("wave_group_type", "wave_group_id", "wave_number")]
        dialog = WavePickerDialog(*current, parent=self)
        if dialog.exec() != WavePickerDialog.DialogCode.Accepted:
            return
        table = params.load_table().block(rhythm.NOTE)

        def apply():
            if dialog.wants_off:
                self._edited(table.param("tone_switch"), 0)
                return
            for name, value in zip(("wave_group_type", "wave_group_id", "wave_number"), dialog.result_wave()):
                self._edited(table.param(name), value)
            if not self._set.get(rhythm.NOTE, "tone_switch", key=self._key):
                self._edited(table.param("tone_switch"), 1)  # choosing a wave for a silent key means you want to hear it

        self._gestured(apply)
        self.refresh()

    def _name_edited(self):
        if self._loading or self._set is None:
            return
        before = self._set.name
        stored = self._set.set(rhythm.COMMON, "rhythm_name", self.name_edit.text())
        if self.name_edit.text() != stored:
            self.name_edit.setText(stored)
        if stored != before:
            self.param_committed.emit(rhythm.COMMON, "rhythm_name", -1, stored)
            self._record([(rhythm.COMMON, "rhythm_name", -1, before, stored)])

    # -- copy and swap -----------------------------------------------------------------------------------------------------

    def _ask_key(self, title, text):
        names = [f"{key_title(k)}" for k in rhythm.KEYS if k != self._key]
        choice, ok = QInputDialog.getItem(self, title, text, names, 0, False)
        if not ok:
            return None
        return int(choice.split()[0])

    def _copy_key(self):
        if self._set is None:
            return
        target = self._ask_key("Copy Key", f"Copy key {key_title(self._key)} to:")
        if target is not None:
            self.copy_key_to(self._key, target)

    def _swap_key(self):
        if self._set is None:
            return
        other = self._ask_key("Swap Keys", f"Swap key {key_title(self._key)} with:")
        if other is not None:
            self.swap_keys(self._key, other)

    def _whole_note_edits(self, key, new_bytes):
        """[(block, name, key, old, new)] for every parameter of `key`'s tone that `new_bytes` would change (applied to a copy: the set is not touched)."""
        table = params.load_table().block(rhythm.NOTE)
        trial = bytearray(new_bytes)
        edits = []
        for param in table.param_list():
            old, new = params.read(self._set.notes[key], param), params.read(trial, param)
            if old != new:
                edits.append((rhythm.NOTE, param.key, key, old, new))
        return edits

    def copy_key_to(self, source, target):
        edits = self._whole_note_edits(target, self._set.notes[source])
        self._set.copy_note(source, target)
        self._finished_whole_key_change(edits, [target])

    def swap_keys(self, a, b):
        edits = self._whole_note_edits(a, self._set.notes[b]) + self._whole_note_edits(b, self._set.notes[a])
        self._set.swap_notes(a, b)
        self._finished_whole_key_change(edits, [a, b])

    def _finished_whole_key_change(self, edits, keys):
        self.refresh()
        self._record(edits)
        self.keys_changed.emit(keys)
