"""A rotary knob, adapted from AKAISDS's `Knob` (same owner, GPL-3.0): vertical drag to turn, Shift for fine control, double-click to reset, an arc that
grows from an ORIGIN (the minimum, or a bipolar parameter's centre).

Signals follow the owner's rule, live UI and MIDI on release: `valueChanged` fires on every step (show it), `sliderReleased` once when a drag ends
(send it). A change that is not a drag (wheel, arrow keys) is the caller's to commit: `is_dragging()` tells the two apart. There is no click-to-type
popup here: a knob is paired with a `ValueSpinBox` that takes typed text.
"""

import math
import sys

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QCursor, QPainter, QPen, QColor
from PySide6.QtWidgets import QApplication, QDial

from jv_studio.ui import theme

START_ANGLE_DEG = 240
SWEEP_DEG = 300
_RING_WIDTH = 4
_POINTER_WIDTH = 3
_DRAG_SENSITIVITY_PX = 150  # a drag this tall covers the whole range
_FINE_DRAG_DIVISOR = 8  # how much slower a Shift-held drag moves
_FINE_DRAG_DIVISOR_MACOS = 12  # macOS: no cursor warp (the OS fights it), a plainly larger divisor on the raw delta instead
_MACOS = sys.platform == "darwin"
VALUE_ARC_COLOR = "#3aa88a"


def arc_start_and_span(fraction, origin_fraction=0.0):
    """(start angle, span) in degrees of the value arc from `origin_fraction` to `fraction`; a clockwise span is negative."""
    return START_ANGLE_DEG - SWEEP_DEG * origin_fraction, -SWEEP_DEG * (fraction - origin_fraction)


class Knob(QDial):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._origin_value = None  # None: the arc grows from the minimum
        self._default_value = None
        self._drag_anchor_y = None
        self._drag_fraction = None  # a float accumulator carries the sub-step remainder between move events
        self._fine_active = False
        self._warp_anchor_global = None
        # if the whole application loses focus mid fine-drag no release arrives, and the blank override cursor would stay on the app-wide stack
        QApplication.instance().applicationStateChanged.connect(self._on_application_state_changed)

    # -- range, origin, default ------------------------------------------------------------------------------------------

    def setOriginValue(self, value):
        """The value the arc grows from (a pan's centre, a tune's zero). None: the minimum."""
        self._origin_value = value
        self.update()

    def setDefaultValue(self, value):
        self._default_value = value

    def defaultValue(self):
        return self._default_value if self._default_value is not None else self.minimum()

    def is_dragging(self):
        return self._drag_anchor_y is not None

    def _fraction(self, value):
        span = self.maximum() - self.minimum()
        return (value - self.minimum()) / span if span else 0.0

    def _value(self, fraction):
        return self.minimum() + fraction * (self.maximum() - self.minimum())

    # -- mouse -----------------------------------------------------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_anchor_y = event.position().y()
            self._drag_fraction = self._fraction(self.value())

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setValue(self.defaultValue())  # the release Qt sends right after does the commit

    def mouseMoveEvent(self, event):
        if self._drag_anchor_y is None:
            return
        fine = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if fine and not self._fine_active:
            self._enter_fine_drag()
        elif not fine and self._fine_active:
            self._exit_fine_drag()
        if self._fine_active and _MACOS:
            y = event.position().y()
            dy = (self._drag_anchor_y - y) / _FINE_DRAG_DIVISOR_MACOS
            self._drag_anchor_y = y
        elif self._fine_active:
            current, anchor = event.globalPosition(), self._warp_anchor_global
            if (round(current.x()), round(current.y())) == (round(anchor.x()), round(anchor.y())):
                return  # the synthetic move the warp itself generates
            dy = (anchor.y() - current.y()) / _FINE_DRAG_DIVISOR
            QCursor.setPos(anchor)
        else:
            y = event.position().y()
            dy = self._drag_anchor_y - y
            self._drag_anchor_y = y
        self._drag_fraction += dy / _DRAG_SENSITIVITY_PX
        wanted = int(round(self._value(self._drag_fraction)))
        clamped = max(self.minimum(), min(self.maximum(), wanted))
        if clamped != wanted:  # resync only when clamped, or a slow careful drag would lose its sub-step remainder every event
            self._drag_fraction = self._fraction(clamped)
        self.setValue(clamped)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._fine_active:
                self._exit_fine_drag()
            was_dragging = self._drag_anchor_y is not None
            self._drag_anchor_y = None
            self._drag_fraction = None
            if was_dragging:
                self.sliderReleased.emit()

    def _enter_fine_drag(self):
        self._fine_active = True
        if _MACOS:
            return
        self._warp_anchor_global = QCursor.pos()
        QApplication.setOverrideCursor(Qt.CursorShape.BlankCursor)

    def _exit_fine_drag(self):
        self._fine_active = False
        if _MACOS:
            return
        self._warp_anchor_global = None
        QApplication.restoreOverrideCursor()

    def hideEvent(self, event):
        if self._fine_active:  # hidden mid-drag (a tab switch): never leave the cursor invisible
            self._exit_fine_drag()
        self._drag_anchor_y = None
        super().hideEvent(event)

    def _on_application_state_changed(self, state):
        if state != Qt.ApplicationState.ApplicationActive and self._fine_active:
            self._exit_fine_drag()

    def wheelEvent(self, event):
        # only with focus (a scroll over a page of knobs must scroll the page), and then always accepted so the page doesn't move at the ends of the range
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)
        event.accept()

    # -- painting --------------------------------------------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(4, 4, -4, -4)
        palette = theme.current_palette()
        enabled = self.isEnabled()
        track = QPen(QColor(palette["border_hover"] if enabled else palette["border_disabled"]))
        track.setWidth(_RING_WIDTH)
        track.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(track)
        painter.drawArc(rect, START_ANGLE_DEG * 16, -SWEEP_DEG * 16)

        fraction = self._fraction(self.value())
        origin = self._fraction(self._origin_value) if self._origin_value is not None and self.minimum() < self._origin_value < self.maximum() else 0.0
        value_pen = QPen(QColor(VALUE_ARC_COLOR if enabled else palette["text_disabled"]))
        value_pen.setWidth(_RING_WIDTH)
        value_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(value_pen)
        start_deg, span_deg = arc_start_and_span(fraction, origin)
        painter.drawArc(rect, int(start_deg * 16), int(span_deg * 16))

        angle = math.radians(START_ANGLE_DEG - SWEEP_DEG * fraction)
        cx, cy, r = rect.center().x(), rect.center().y(), rect.width() / 2
        pointer = QPen(QColor(palette["text_bright"] if enabled else palette["text_disabled"]))
        pointer.setWidth(_POINTER_WIDTH)
        pointer.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pointer)
        outer_radius = r + _RING_WIDTH / 2  # the pointer ends on the ring's outer edge (a fraction of r left a gap that grew with the knob)
        painter.drawLine(
            QPointF(cx + r * 0.2 * math.cos(angle), cy - r * 0.2 * math.sin(angle)),
            QPointF(cx + outer_radius * math.cos(angle), cy - outer_radius * math.sin(angle)),
        )
