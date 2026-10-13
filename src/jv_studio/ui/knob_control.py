"""A numeric parameter as AKAISDS shows one: the name, a knob and a plain-label readout of the value (as the unit's display shows it).

The readout sits BELOW the knob (the roomy layout) or BESIDE it (`compact`: the name above, the knob and its value side by side, about half the height: for cards with
many knobs). Turn the knob by dragging (Shift: fine, double-click: default); click it once and type to enter an exact value, in the unit's own terms: `C#5`, `L30`,
`+12`, `OFF`, or a plain number (`parse_display_text`).

Owner's rule, live UI and MIDI on release: the readout follows the knob while it turns, `committed(value)` fires once when a drag ends, when a value is typed, or
shortly after the last wheel/arrow-key step. `set_value` moves everything silently (loading a patch, an undo, a graph drag) and emits nothing.
"""

from functools import lru_cache

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from jv_studio.core import params
from jv_studio.ui.knob import Knob

KNOB_SIZE = 38
COLUMN_WIDTH = 76
COMPACT_COLUMN_WIDTH = 80
COMMIT_DELAY_MS = 150  # a wheel or arrow-key step commits this long after the last one


@lru_cache(maxsize=None)
def _text_to_value(param):
    """{displayed text, lower case: raw value} for every value of a parameter."""
    table = {params.format_value(param, v).lower(): v for v in range(param.min, param.max + 1)}
    for shown, v in list(table.items()):
        table.setdefault(shown.removesuffix(" hz"), v)  # a tuning typed without its unit: 440.0
    return table


def parse_display_text(param, text):
    """The raw value for text typed the way the unit shows it (a note name, `L30`, `+12`, `OFF`), or None. A bare number is the DISPLAYED number (what the readout
    would show), so `30` on a -63..+63 pan means +30; where the display is the raw value that is the same thing."""
    table = _text_to_value(param)
    text = text.strip().lower()
    for candidate in (text, "+" + text, text.replace(" ", ""), text + ".0"):
        if candidate in table:
            return table[candidate]
    return None


class KnobControl(QWidget):
    committed = Signal(int)

    def __init__(self, param, *, compact=False, show_name=True, knob_size=KNOB_SIZE, parent=None):
        super().__init__(parent)
        self.param = param
        self.setObjectName("transparentContainer")  # the card's own colour, not the page's
        if show_name:
            self.setFixedWidth(COMPACT_COLUMN_WIDTH if compact else COLUMN_WIDTH)
        self._value = param.min
        self._silent = False
        self.name_label = QLabel(param.name)
        self.name_label.setObjectName("knobLabel")
        self.name_label.setWordWrap(True)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        self.name_label.setMinimumHeight(30)  # room for two lines, so a row of knobs lines up whether or not a name wraps
        self.knob = Knob()
        self.knob.setRange(param.min, param.max)
        self.knob.setFixedSize(knob_size, knob_size)
        self.knob.setNotchesVisible(False)
        origin = origin_value(param)
        self.knob.setOriginValue(origin)
        self.knob.setDefaultValue(origin if origin is not None else param.min)
        self.value_label = QLabel(params.format_value(param, param.min))
        self.value_label.setObjectName("knobValue")
        self.value_label.setMinimumWidth(36 if compact else 0)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(COMMIT_DELAY_MS)
        self.timer.timeout.connect(self._commit)
        self.knob.valueChanged.connect(self._knob_moved)
        self.knob.sliderReleased.connect(self._commit)
        self.knob.text_entered.connect(self._typed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        if show_name:
            layout.addWidget(self.name_label)
        else:
            self.name_label.hide()  # a knob in a row or a grid that carries its own headers (the performance's parts)
        if compact:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(4)
            row.addStretch()
            row.addWidget(self.knob)
            row.addWidget(self.value_label)
            row.addStretch()
            layout.addLayout(row)
            self.value_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        else:
            layout.addWidget(self.knob, alignment=Qt.AlignmentFlag.AlignHCenter)
            layout.addWidget(self.value_label)
            self.value_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)

    # -- reading and setting ---------------------------------------------------------------------------------------------------

    def value(self):
        """The parameter's value. (The knob may sit at the end of a narrower travel than the parameter's range, see `set_travel`.)"""
        return self._value

    def text(self):
        return self.value_label.text()

    def set_value(self, value):
        """Show `value` everywhere, silently."""
        self._value = max(self.param.min, min(self.param.max, int(value)))
        self.value_label.setText(params.format_value(self.param, self._value))
        self.knob.blockSignals(True)
        self.knob.setValue(max(self.knob.minimum(), min(self.knob.maximum(), self._value)))
        self.knob.blockSignals(False)

    def setValue(self, value):
        """Set a value as the user would (a typed entry): shown, and committed if it changed."""
        before = self._value
        self.set_value(value)
        if self._value != before:
            self.timer.stop()
            self.committed.emit(self._value)

    def set_name(self, text):
        self.name_label.setText(text)

    def set_travel(self, low, high):
        """Make the knob turn over low..high (a parameter that means something different, with a different range, for each effect type). The value, and the readout,
        stay the parameter's own: a value beyond the travel shows its true number and the knob just stops at its end."""
        self.knob.blockSignals(True)
        self.knob.setRange(low, high)
        self.knob.setValue(max(low, min(high, self._value)))
        self.knob.blockSignals(False)

    # -- the knob's signals ----------------------------------------------------------------------------------------------------

    def _knob_moved(self, value):
        self._value = value
        self.value_label.setText(params.format_value(self.param, value))
        if not self.knob.is_dragging():
            self.timer.start()  # a wheel or key step

    def _commit(self):
        self.timer.stop()
        self.committed.emit(self._value)

    def _typed(self, text):
        value = parse_display_text(self.param, text)
        if value is None:
            return  # not a value this parameter can show: leave everything as it was
        self.setValue(value)


def origin_value(param):
    """The raw value a knob's arc grows from: the centre of a parameter that is shown as negative-to-positive (a pan, a tune), else None (the minimum)."""
    text = param.display_text or ""
    if param.display_min is not None and param.display_max is not None and param.display_min < 0 < param.display_max and param.max != param.min:
        return round(param.min + (0 - param.display_min) * (param.max - param.min) / (param.display_max - param.display_min))
    if text in ("L64 - 63R", "L63 - 63R"):
        return 64
    if param.key == "master_tune":
        return 63  # A = 440.0 Hz
    return None
