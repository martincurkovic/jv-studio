"""The envelope graphs: a drawing of an envelope's SHAPE (no calibrated timing) that the user can also edit by dragging its handles.

Adapted from AKAISDS's `envelope_graph.py` (same owner, GPL-3.0): the dragging machinery (`_EditableGraph`) is the same, the envelope is the JV-1010's.
Dragging is shared by every graph: each graph supplies its curve, which curve points are handles and what dragging one means (`jv_values_for_handle` and
`jv_values_for_sustain` below: pure, Qt-free, the inverse of the drawing maths). A graph never writes anything itself. It emits
- `values_changed({name: value})` live while dragging (and on a reset or a cancel), so the owner can move its knobs and readouts at once;
- `edit_committed({name: value})` once, on release (or a reset), with only the values that differ from before: the moment a window may send them to the unit;
- `edit_cancelled()` when Esc (or hiding the graph) abandoned a drag: the values are already back and nothing was committed.
A graph is INERT until its owner calls `set_editable(True)`. Shift slows a drag, a double-click on a handle resets what it controls to `set_defaults`, Esc
cancels. While a drag is in progress `set_values` is ignored: a reload must not fight the pointer.
"""

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from jv_studio.ui import theme

#: the size the patch editor gives its envelope graphs (big enough to grab a handle)
GRAPH_SIZE = (300, 110)

_BORDER_RADIUS = 4  # matches QWidget#sectionCard/#zoneCard's own radius
_INSET = 8  # room between the border and the curve, so a handle on the edge (attack 0, level 99) is whole and easy to grab
_HANDLE_RADIUS = 4.5
_HIT_RADIUS = 11  # how close the pointer must be to a handle to take it
_FINE_DIVISOR = 6  # how much slower a Shift-held drag moves
_OVERLAP_PX = 2.5  # handles this close to the nearest one are "on top of" it (a stage of rate 0, an instant attack...)
_DECIDE_PX = 3  # how far the pointer moves before a drag over overlapping handles picks one
_SEGMENT_HIT = 6  # how close the pointer must be to a draggable segment (the sustain line) to take it



def _draw_border(painter, w, h):
    # the envelope curve is drawn edge-to-edge (0,0 to w,h) with nothing
    # else in the widget, so at rest - or at an extreme (attack=0,
    # sustain=99, ...) - it was often just a bare line with no visible
    # boundary at all, making the graph's actual extent a guess. A plain
    # rect, not a fancier frame, since this is a size reference for the
    # curve above it, not a card of its own.
    pen = QPen(QColor(theme.current_palette()["border"]))
    pen.setWidth(1)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    # inset by half the pen width - drawn exactly on the edge, a 1px line
    # is split across the boundary by anti-aliasing and half of it is
    # clipped away, reading as thinner on the right/bottom than the top/left
    painter.drawRoundedRect(
        QRectF(0.5, 0.5, w - 1, h - 1), _BORDER_RADIUS, _BORDER_RADIUS
    )



def _clamp_int(value, low, high):
    return max(low, min(high, int(round(value))))



class _Drag:
    # one drag in progress: the handle, the values before it, and where the handle is (in the graph's inner coordinates)
    def __init__(self, index, start, offset, pos, candidates=None, press=None):
        self.index = index
        self.candidates = candidates  # several handles under the pointer: which one is chosen by the first move (see _choose)
        self.press = press
        self.start = start
        self.offset = offset  # pointer - handle, so the handle doesn't jump to the pointer
        self.pos = pos
        self.fine = False
        self.fine_pointer = None
        self.fine_pos = None


class _EditableGraph(QWidget):
    """What every envelope graph shares: the frame, the curve, the handles and the dragging. Subclasses give the values and the geometry."""

    #: live, while dragging (also a reset or a cancel): {name: value} of the values that just changed
    values_changed = Signal(dict)
    #: once, on release (or a reset): {name: value} of the values that differ from before the drag
    edit_committed = Signal(dict)
    #: Esc or hiding the graph abandoned a drag (the values are already back)
    edit_cancelled = Signal()

    NAMES = ()  # the value names, in the order of `_values`
    HANDLE_NAMES = ()  # per handle: the value names dragging it changes
    HANDLE_AXES = ()  # per handle: "x", "y" or "xy" - which way it moves (the pointer shape)
    CURVE_INDEX_OF_HANDLE = ()  # per handle: which point of the curve it sits on
    # Draggable SEGMENTS (the flat sustain line): (curve point, curve point) pairs. A segment is a target after the handles, so its names and axes are the
    # tail of HANDLE_NAMES / HANDLE_AXES and its index is len(CURVE_INDEX_OF_HANDLE) + its position here. It always moves up/down.
    SEGMENT_POINTS = ()

    def __init__(self, color, parent=None):
        super().__init__(parent)
        self._color = color
        self._values = tuple(0 for _ in self.NAMES)
        self._editable = False
        self._defaults = {}
        self._drag = None
        self._hover = -1
        self.setMouseTracking(True)

    # -- subclass hooks ----------------------------------------------------------------------------------

    def _curve_points(self, w, h):
        raise NotImplementedError

    def _values_for_handle(self, index, x, y, w, h):
        raise NotImplementedError

    def _paint_background(self, painter, w, h):
        pass

    # -- values --------------------------------------------------------------------------------------------

    def _store(self, values):
        self._values = tuple(values)

    def values(self):
        return dict(zip(self.NAMES, self._values))

    def is_dragging(self):
        return self._drag is not None

    def set_defaults(self, defaults):
        """{name: value} a double-click on a handle resets to (the knobs' own defaults)."""
        self._defaults = dict(defaults)

    def set_editable(self, editable):
        editable = bool(editable)
        if not editable and self._drag is not None:
            self._cancel_drag()
        if editable != self._editable:
            self._editable = editable
            self._hover = -1
            self.unsetCursor()
            self.update()

    def is_editable(self):
        return self._editable

    # -- geometry --------------------------------------------------------------------------------------------

    def _inner_size(self):
        return max(self.width() - 2 * _INSET, 1), max(self.height() - 2 * _INSET, 1)

    def handle_positions(self):
        """The handles' centres in WIDGET coordinates (what a mouse event reports)."""
        w, h = self._inner_size()
        points = self._curve_points(w, h)
        return [QPointF(points[i][0] + _INSET, points[i][1] + _INSET) for i in self.CURVE_INDEX_OF_HANDLE]

    def _handles_at(self, position):
        """The handle under `position` - or, when several sit on top of one another, all of them (earliest first). Empty if none is close enough."""
        centres = self.handle_positions()
        distances = [((c.x() - position.x()) ** 2 + (c.y() - position.y()) ** 2) ** 0.5 for c in centres]
        if not distances or min(distances) > _HIT_RADIUS:
            return []
        nearest = centres[distances.index(min(distances))]
        return [
            i for i, c in enumerate(centres) if ((c.x() - nearest.x()) ** 2 + (c.y() - nearest.y()) ** 2) ** 0.5 <= _OVERLAP_PX and distances[i] <= _HIT_RADIUS
        ]

    def _segment_at(self, position):
        """The index (as a drag target) of the draggable segment under `position`, or -1."""
        w, h = self._inner_size()
        points = self._curve_points(w, h)
        for k, (a, b) in enumerate(self.SEGMENT_POINTS):
            ax, ay = points[a][0] + _INSET, points[a][1] + _INSET
            bx, by = points[b][0] + _INSET, points[b][1] + _INSET
            dx, dy = bx - ax, by - ay
            length_sq = dx * dx + dy * dy
            t = 0 if length_sq == 0 else max(0.0, min(1.0, ((position.x() - ax) * dx + (position.y() - ay) * dy) / length_sq))
            nearest_x, nearest_y = ax + t * dx, ay + t * dy
            if ((position.x() - nearest_x) ** 2 + (position.y() - nearest_y) ** 2) ** 0.5 <= _SEGMENT_HIT:
                return len(self.CURVE_INDEX_OF_HANDLE) + k
        return -1

    def _targets_at(self, position):
        """What a press at `position` takes: the handle(s) under it, else the segment under it (handles win where they meet), else nothing."""
        handles = self._handles_at(position)
        if handles:
            return handles
        segment = self._segment_at(position)
        return [segment] if segment >= 0 else []

    def _is_segment(self, index):
        return index >= len(self.CURVE_INDEX_OF_HANDLE)

    def _target_position(self, index, pointer):
        """Where a drag target is, in WIDGET coordinates: a handle's centre; for a segment the point of it level with the pointer (it only moves up/down)."""
        if not self._is_segment(index):
            return self.handle_positions()[index]
        w, h = self._inner_size()
        a = self.SEGMENT_POINTS[index - len(self.CURVE_INDEX_OF_HANDLE)][0]
        return QPointF(pointer.x(), self._curve_points(w, h)[a][1] + _INSET)

    def _choose(self, candidates, dx, dy):
        """Which of several overlapping handles a drag means: a sideways move takes the first that can move sideways, an up/down move the first that can
        move up/down (a handle at x 0 and one at x 0 are the attack and the decay of an instant envelope: dragging right is the attack, down the sustain)."""
        wanted = "x" if abs(dx) >= abs(dy) else "y"
        for index in candidates:
            if wanted in self.HANDLE_AXES[index]:
                return index
        return candidates[0]

    def _interactive(self):
        return self._editable and self.isEnabled()

    # -- painting --------------------------------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, not theme.current_palette().get("hard_edges"))  # (the System 6 skin draws jagged, bitmap-like lines)
        _draw_border(painter, self.width(), self.height())
        w, h = self._inner_size()
        painter.translate(_INSET, _INSET)
        self._paint_background(painter, w, h)
        line_color = theme.current_palette().get("graph_line", self._color)  # (the System 6 theme draws every curve in one colour)
        pen = QPen(QColor(line_color))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawPolyline(QPolygonF([QPointF(x, y) for x, y in self._curve_points(w, h)]))
        if not self._interactive():
            return
        palette = theme.current_palette()
        points = self._curve_points(w, h)
        for k, (a, b) in enumerate(self.SEGMENT_POINTS):
            index = len(self.CURVE_INDEX_OF_HANDLE) + k
            if index == self._hover or (self._drag is not None and self._drag.index == index):
                # the line that is about to move (or is moving) shows it: thicker and brighter
                bright = QPen(QColor(line_color).lighter(135))
                bright.setWidth(4)
                bright.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(bright)
                painter.drawLine(QPointF(*points[a]), QPointF(*points[b]))
        for index, point_index in enumerate(self.CURVE_INDEX_OF_HANDLE):
            x, y = points[point_index]
            active = index == self._hover or (self._drag is not None and self._drag.index == index)
            radius = _HANDLE_RADIUS + (1.5 if active else 0)
            painter.setBrush(QColor(line_color))
            ring = QPen(QColor(palette["text_bright"] if active else palette["bg"]))
            ring.setWidthF(1.5)
            painter.setPen(ring)
            painter.drawEllipse(QPointF(x, y), radius, radius)

    # -- mouse -----------------------------------------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self._interactive():
            return super().mousePressEvent(event)
        candidates = self._targets_at(event.position())
        if not candidates:
            return super().mousePressEvent(event)
        index = candidates[0]
        centre = self._target_position(index, event.position())
        inner = QPointF(centre.x() - _INSET, centre.y() - _INSET)
        self._drag = _Drag(
            index, self._values, event.position() - centre, inner, candidates if len(candidates) > 1 else None, event.position()
        )
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            # Shift already held at the press: the whole drag is fine, not just what follows the first move
            self._drag.fine, self._drag.fine_pointer, self._drag.fine_pos = True, event.position(), inner
        self.grabKeyboard()  # Esc reaches this widget without taking focus (a focus change can scroll the page)
        self.update()
        event.accept()

    def mouseMoveEvent(self, event):
        drag = self._drag
        if drag is None:
            self._update_hover(event.position())
            return
        pointer = event.position()
        if drag.candidates:
            # several handles under the pointer: nothing moves until it has gone far enough to say which one is meant
            moved = pointer - drag.press
            if (moved.x() ** 2 + moved.y() ** 2) ** 0.5 < _DECIDE_PX:
                return
            drag.index = self._choose(drag.candidates, moved.x(), moved.y())
            drag.candidates = None
        fine = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if fine and not drag.fine:
            drag.fine, drag.fine_pointer, drag.fine_pos = True, pointer, drag.pos
        elif not fine and drag.fine:
            # leaving fine mode: the handle stays where it is and follows the pointer from there
            drag.fine = False
            drag.offset = pointer - (drag.pos + QPointF(_INSET, _INSET))
        if drag.fine:
            drag.pos = drag.fine_pos + (pointer - drag.fine_pointer) / _FINE_DIVISOR
        else:
            drag.pos = pointer - drag.offset - QPointF(_INSET, _INSET)
        w, h = self._inner_size()
        new = tuple(self._values_for_handle(drag.index, drag.pos.x(), drag.pos.y(), w, h))
        if new != self._values:
            changed = {name: v for name, v, old in zip(self.NAMES, new, self._values) if v != old}
            self._store(new)
            self.update()
            self.values_changed.emit(changed)
        event.accept()

    def mouseReleaseEvent(self, event):
        drag = self._drag
        if drag is None or event.button() != Qt.MouseButton.LeftButton:
            return super().mouseReleaseEvent(event)
        self._end_drag()  # before the signal: the owner's reaction may call set_values
        changed = {name: v for name, v, start in zip(self.NAMES, self._values, drag.start) if v != start}
        self._update_hover(event.position())
        if changed:
            self.edit_committed.emit(changed)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self._interactive():
            return super().mouseDoubleClickEvent(event)
        targets = self._targets_at(event.position())
        if not targets:
            return super().mouseDoubleClickEvent(event)
        index = targets[0]
        values = list(self._values)
        for name in self.HANDLE_NAMES[index]:
            if name in self._defaults:
                values[self.NAMES.index(name)] = self._defaults[name]
        changed = {name: v for name, v, old in zip(self.NAMES, values, self._values) if v != old}
        if changed:
            self._store(values)
            self.update()
            self.values_changed.emit(changed)
            self.edit_committed.emit(changed)
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self._drag is not None:
            self._cancel_drag()
            event.accept()
            return
        super().keyPressEvent(event)

    def leaveEvent(self, event):
        if self._drag is None and self._hover != -1:
            self._hover = -1
            self.update()
        super().leaveEvent(event)

    def hideEvent(self, event):
        # a drag whose release can never arrive (a tab switched by the keyboard, the window closing) must not leave the keyboard grabbed
        if self._drag is not None:
            self._cancel_drag()
        super().hideEvent(event)

    # -- drag bookkeeping ------------------------------------------------------------------------------------

    def _end_drag(self):
        self._drag = None
        self.releaseKeyboard()
        self.update()

    def _cancel_drag(self):
        drag = self._drag
        self._end_drag()
        changed = {name: v for name, v, start in zip(self.NAMES, drag.start, self._values) if v != start}
        self._store(drag.start)
        if changed:
            self.values_changed.emit(changed)
        self.edit_cancelled.emit()

    def _update_hover(self, position):
        targets = self._targets_at(position) if self._interactive() else []
        index = targets[0] if targets else -1
        if index != self._hover:
            self._hover = index
            if index < 0:
                self.unsetCursor()
            else:
                axes = self.HANDLE_AXES[index]
                self.setCursor(
                    Qt.CursorShape.SizeAllCursor if axes == "xy" else Qt.CursorShape.SizeHorCursor if axes == "x" else Qt.CursorShape.SizeVerCursor
                )
            self.update()




# -- the JV-1010's envelopes: four stages, level 3 held until the key is released ------------------------------------------------

TIME_MAX = 127
LEVEL_MAX = 127
HOLD_FRACTION = 0.12  # the sustain: level 3 is held until the key is released, which has no duration, so a flat segment of fixed width stands for it


def jv_points(times, levels, start_level, w, h):
    """The curve of a pitch / filter / level envelope as plain (x, y) tuples: the start, the ends of stages 1-3, the end of the hold (flat at level 3) and
    the end of stage 4. `times` are four 0-127 values, `levels` four 0-127 values (level 4 is where the release ends). Each stage's width depends ONLY on its
    own time, never on the others (the AKAISDS lesson: normalising against the other stages made moving one resize them all)."""
    stage_w = (1 - HOLD_FRACTION) * w / 4

    def y_for(level):
        return h - level / LEVEL_MAX * h

    x1 = times[0] / TIME_MAX * stage_w
    x2 = x1 + times[1] / TIME_MAX * stage_w
    x3 = x2 + times[2] / TIME_MAX * stage_w
    hold_end = x3 + HOLD_FRACTION * w
    x4 = hold_end + times[3] / TIME_MAX * stage_w
    return [(0, y_for(start_level)), (x1, y_for(levels[0])), (x2, y_for(levels[1])), (x3, y_for(levels[2])), (hold_end, y_for(levels[2])), (x4, y_for(levels[3]))]


def jv_values_for_handle(index, x, y, times, levels, w, h, free_last_level=True):
    """(times, levels) after handle `index` (0-3: the end of stage 1-4) is dragged to (x, y): the inverse of `jv_points`. A stage's x is measured from where
    the stage before it ends NOW. Dragging sideways changes that stage's time, up/down its level; `free_last_level=False` (the level envelope, which always
    ends at silence) leaves level 4 alone."""
    times, levels = list(times), list(levels)
    if w <= 0 or h <= 0:
        return tuple(times), tuple(levels)
    stage_w = (1 - HOLD_FRACTION) * w / 4
    level = _clamp_int((h - y) / h * LEVEL_MAX, 0, LEVEL_MAX)
    start = sum(times[:index]) / TIME_MAX * stage_w + (HOLD_FRACTION * w if index == 3 else 0)
    times[index] = _clamp_int((x - start) / stage_w * TIME_MAX, 0, TIME_MAX)
    if index < 3 or free_last_level:
        levels[index] = level
    return tuple(times), tuple(levels)


def jv_values_for_sustain(y, times, levels, h):
    """(times, levels) after the flat sustain line is dragged to height y: only level 3 changes."""
    levels = list(levels)
    if h > 0:
        levels[2] = _clamp_int((h - y) / h * LEVEL_MAX, 0, LEVEL_MAX)
    return tuple(times), tuple(levels)


class JVEnvelopeGraph(_EditableGraph):
    """One of the tone's three envelopes. Subclasses name the parameter keys it edits. The values are keyed by those parameter keys, so the owner can
    pass them straight to the patch."""

    TIME_KEYS = ()
    LEVEL_KEYS = ()  # three or four: a level envelope has no level 4 (it ends at silence)
    START_LEVEL = 0  # where the envelope starts: 0, or 63 (no pitch offset: the levels run 0-126 for -63..+63) for the pitch envelope
    CURVE_INDEX_OF_HANDLE = (1, 2, 3, 5)
    SEGMENT_POINTS = ((3, 4),)

    def __init__(self, color, parent=None):
        self.NAMES = tuple(self.TIME_KEYS) + tuple(self.LEVEL_KEYS)
        self.FREE_LAST_LEVEL = len(self.LEVEL_KEYS) == 4
        last = (self.TIME_KEYS[3], self.LEVEL_KEYS[3]) if self.FREE_LAST_LEVEL else (self.TIME_KEYS[3],)
        self.HANDLE_NAMES = tuple((self.TIME_KEYS[i], self.LEVEL_KEYS[i]) for i in range(3)) + (last, (self.LEVEL_KEYS[2],))
        self.HANDLE_AXES = ("xy", "xy", "xy", "xy" if self.FREE_LAST_LEVEL else "x", "y")
        super().__init__(color, parent)
        self.setFixedSize(*GRAPH_SIZE)

    def set_values(self, values):
        """Show `{key: value}` (the patch's envelope values). Ignored while a drag is in progress."""
        if self._drag is not None:
            return
        self._store([values.get(name, old) for name, old in zip(self.NAMES, self._values)])
        self.update()

    def _split(self):
        times, rest = self._values[:4], self._values[4:]
        levels = tuple(rest) if self.FREE_LAST_LEVEL else tuple(rest) + (0,)
        return times, levels

    def _curve_points(self, w, h):
        times, levels = self._split()
        return jv_points(times, levels, self.START_LEVEL, w, h)

    def _join(self, times, levels):
        return tuple(times) + (tuple(levels) if self.FREE_LAST_LEVEL else tuple(levels[:3]))

    def _values_for_handle(self, index, x, y, w, h):
        times, levels = self._split()
        if index == 4:  # the sustain line
            return self._join(*jv_values_for_sustain(y, times, levels, h))
        return self._join(*jv_values_for_handle(index, x, y, times, levels, w, h, self.FREE_LAST_LEVEL))

    def _paint_background(self, painter, w, h):
        # the zero line (and, for the pitch envelope, the line where the pitch is unchanged), faint, so a level reads against something
        line = QPen(QColor(theme.current_palette()["border"]))
        line.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(line)
        for level in {0, self.START_LEVEL}:
            y = h - level / LEVEL_MAX * h
            painter.drawLine(QPointF(0, y), QPointF(w, y))


class PitchEnvelopeGraph(JVEnvelopeGraph):
    TIME_KEYS = tuple(f"pitch_envelope_time_{n}" for n in range(1, 5))
    LEVEL_KEYS = tuple(f"pitch_envelope_level_{n}" for n in range(1, 5))
    START_LEVEL = 63  # raw 63 = no pitch change (the pitch envelope's levels run 0-126 for -63..+63)

    def __init__(self, parent=None):
        super().__init__("#d97757", parent)


class FilterEnvelopeGraph(JVEnvelopeGraph):
    TIME_KEYS = tuple(f"filter_envelope_time_{n}" for n in range(1, 5))
    LEVEL_KEYS = tuple(f"filter_envelope_level_{n}" for n in range(1, 5))

    def __init__(self, parent=None):
        super().__init__("#3aa88a", parent)


class LevelEnvelopeGraph(JVEnvelopeGraph):
    TIME_KEYS = tuple(f"level_envelope_time_{n}" for n in range(1, 5))
    LEVEL_KEYS = tuple(f"level_envelope_level_{n}" for n in range(1, 4))

    def __init__(self, parent=None):
        super().__init__("#5b8def", parent)


GRAPH_FOR_CARD = {"Pitch": PitchEnvelopeGraph, "Filter": FilterEnvelopeGraph, "Level": LevelEnvelopeGraph}
