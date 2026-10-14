"""The controls for a parameter that is a list of named options, chosen by what the list is:

- **OFF / ON** (or OFF / something, like LFO External Sync's OFF / CLOCK): a `SwitchBox`, a check box. One click, and it says what it does.
- **Two named options** (Poly | Solo, Rate | Time, Last | Loudest): a `ToggleChoice`, two joined buttons: both options stay visible and it is one click.
- **Anything longer**: a `ChoiceCombo`, a drop-down.

All three have the same small interface so an editor treats them alike: `edited(raw value)` is emitted when the USER chooses (never when the editor shows a value), `set_raw(value)` shows
a value silently, and `current_raw()` reads it. `make_choice_control(param)` picks. A value the unit holds that is not offered (a JV-1080-family value) is shown, never hidden.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QCheckBox, QComboBox, QHBoxLayout, QPushButton, QWidget

from jv_studio.core import friendly, params

#: two named options whose labels together are longer than this stay a drop-down (two long buttons would be wider than a combo)
TOGGLE_MAX_CHARS = 24


def offered_options(param, hide=()):
    """[(raw value, the unit's label)] the JV-1010 has: a JV-1080-family choice (angle brackets in the manual) and a value in `hide` are left out."""
    if param.choices:
        options = [(param.min + index, choice.label) for index, choice in enumerate(param.choices) if choice.jv1010]
    else:
        options = [(param.min + index, label) for index, label in enumerate(param.labels)]
    return [(value, label) for value, label in options if value not in hide]


def short_name(name):
    """A check box's text: the card says it is a switch, so "Redamper Control Switch" reads "Redamper Control"."""
    return name[: -len(" Switch")] if name.endswith(" Switch") and len(name) > len(" Switch") else name


class ChoiceCombo(QComboBox):
    edited = Signal(int)  # the raw value the user chose

    def __init__(self, param, parent=None, hide=()):
        super().__init__(parent)
        self.param = param
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        for value, label in offered_options(param, hide):
            self._add(label, value)
        self.activated.connect(lambda _i: self.edited.emit(self.currentData()))

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

    set_value = set_raw

    def current_raw(self):
        return self.currentData()

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class SwitchBox(QCheckBox):
    """An ON/OFF parameter as a check box. Checked is the second option (ON, or CLOCK...), unchecked the first."""

    edited = Signal(int)

    def __init__(self, param, text=None, parent=None, hide=()):
        options = offered_options(param, hide)
        super().__init__(text if text is not None else short_name(param.name), parent)
        self.param = param
        self._off, self._on = options[0][0], options[1][0]
        self.on_label = friendly.label(param.key, options[1][1])
        self.clicked.connect(lambda _checked: self.edited.emit(self.current_raw()))

    def set_raw(self, value):
        """Show `value` without telling anyone (a value that is neither option counts as on: it is not the first)."""
        self.blockSignals(True)
        self.setChecked(value != self._off)
        self.blockSignals(False)

    set_value = set_raw

    def current_raw(self):
        return self._on if self.isChecked() else self._off

    value = current_raw


class ToggleChoice(QWidget):
    """Two named options as two joined buttons: both are visible, one click chooses."""

    edited = Signal(int)

    def __init__(self, param, parent=None, hide=()):
        super().__init__(parent)
        self.param = param
        self._values = []
        self._buttons = []
        group = QButtonGroup(self)
        group.setExclusive(False)  # (so that a value the unit holds that is neither option can leave both unchecked)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        options = offered_options(param, hide)
        for index, (value, label) in enumerate(options):
            button = QPushButton(friendly.label(param.key, label))
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setProperty("segment", "first" if index == 0 else "last")
            button.setProperty("compact", True)
            tip = friendly.description(param.key, label) or (f"On the unit: {label}" if friendly.label(param.key, label) != label else "")
            if tip:
                button.setToolTip(tip)
            button.clicked.connect(lambda _checked, v=value: self._chosen(v))
            group.addButton(button)
            layout.addWidget(button)
            self._values.append(value)
            self._buttons.append(button)
        layout.addStretch(1)

    def _chosen(self, value):
        self.set_raw(value)
        self.edited.emit(value)

    def set_raw(self, value):
        for button, own in zip(self._buttons, self._values):
            button.setChecked(own == value)

    set_value = set_raw

    def current_raw(self):
        return next((v for b, v in zip(self._buttons, self._values) if b.isChecked()), None)


def make_choice_control(param, hide=(), allow_toggle=True):
    """The control for a parameter with named options (see the module docstring)."""
    options = offered_options(param, hide)
    if len(options) == 2 and options[0][1].strip().upper() == "OFF":
        return SwitchBox(param, hide=hide)
    if allow_toggle and len(options) == 2 and sum(len(friendly.label(param.key, label)) for _, label in options) <= TOGGLE_MAX_CHARS:
        return ToggleChoice(param, hide=hide)
    return ChoiceCombo(param, hide=hide)


def check_grid(boxes, columns=2):
    """The check boxes of a card in a tidy grid (None when there are none), `columns` to a row."""
    if not boxes:
        return None
    from PySide6.QtWidgets import QGridLayout

    grid = QGridLayout()
    grid.setHorizontalSpacing(12)
    grid.setVerticalSpacing(4)
    for index, box in enumerate(boxes):
        grid.addWidget(box, index // columns, index % columns)
    return grid
