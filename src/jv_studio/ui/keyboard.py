"""A piano keyboard that scales to its width: click or drag with the mouse, or type on the computer keyboard while it has focus. It only reports notes
(`note_on`, `note_off`); whoever owns it decides what to send, and with what velocity.

Computer keys (QWERTY, the usual DAW layout), only while this widget has the focus so typing in a text box never plays a note: A W S E D F T G Y H U J K O L P ; are the notes
from `typing_base` (C, C#, D ... E an octave up); Z and X move that base down and up an octave, C and V ask for a quieter / louder note (`velocity_step`, -10 / +10). Every note that is held is released when the widget loses focus or is disabled.
"""

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from jv_studio.core import params
from jv_studio.ui import theme

FIRST_NOTE = 36  # C2
LAST_NOTE = 96  # C7: five octaves, 36 white keys (the unit's own range is wider; this is for auditioning)
TYPING_KEYS = "awsedftgyhujkolp;"  # semitones 0, 1, 2 ...
DEFAULT_TYPING_BASE = 60  # C4
BLACK = {1, 3, 6, 8, 10}


def _white_notes():
    return [n for n in range(FIRST_NOTE, LAST_NOTE + 1) if n % 12 not in BLACK]


class PianoKeyboard(QWidget):
    note_on = Signal(int)
    note_off = Signal(int)
    typing_base_changed = Signal(int)
    velocity_step = Signal(int)  # -10 or +10: the C and V keys
    held_changed = Signal(list)  # the notes held now, lowest first (for a live read-out)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(74)
        self.setMaximumHeight(74)
        self.setMouseTracking(False)
        self.typing_base = DEFAULT_TYPING_BASE
        self._whites = _white_notes()
        self._down = {}  # note -> how many sources hold it (mouse, typing key)
        self._mouse_note = None
        self._typed = {}  # Qt key -> the note it started

    # -- geometry --------------------------------------------------------------------------------------------------------

    def _white_width(self):
        return self.width() / len(self._whites)

    def _key_rect(self, note):
        white = self._white_width()
        if note % 12 not in BLACK:
            return QRectF(self._whites.index(note) * white, 0, white, self.height())
        before = self._whites.index(note - 1)  # the white key just below
        width = white * 0.6
        return QRectF((before + 1) * white - width / 2, 0, width, self.height() * 0.62)

    def note_at(self, x, y):
        """The note under a point: a black key wins where it overlaps a white one."""
        if not 0 <= x < self.width() or not 0 <= y < self.height():
            return None
        for note in range(FIRST_NOTE, LAST_NOTE + 1):
            if note % 12 in BLACK and self._key_rect(note).contains(x, y):
                return note
        index = int(x / self._white_width())
        return self._whites[min(index, len(self._whites) - 1)]

    # -- sounding --------------------------------------------------------------------------------------------------------

    def is_down(self, note):
        return note in self._down

    def _press(self, note):
        self._down[note] = self._down.get(note, 0) + 1
        if self._down[note] == 1:
            self.note_on.emit(note)
            self.held_changed.emit(sorted(self._down))
        self.update()

    def _release(self, note):
        count = self._down.get(note, 0)
        if count == 0:
            return
        if count == 1:
            del self._down[note]
            self.note_off.emit(note)
            self.held_changed.emit(sorted(self._down))
        else:
            self._down[note] = count - 1
        self.update()

    def release_all(self):
        """Let go of everything (focus lost, disabled, Panic)."""
        held = bool(self._down)
        for note in list(self._down):
            del self._down[note]
            self.note_off.emit(note)
        if held:
            self.held_changed.emit([])
        self._mouse_note = None
        self._typed.clear()
        self.update()

    def set_typing_base(self, note):
        note = max(FIRST_NOTE, min(LAST_NOTE - 12, note))
        if note != self.typing_base:
            self.typing_base = note
            self.typing_base_changed.emit(note)

    # -- mouse -----------------------------------------------------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus()
        self._mouse_note = self.note_at(event.position().x(), event.position().y())
        if self._mouse_note is not None:
            self._press(self._mouse_note)

    def mouseMoveEvent(self, event):
        if self._mouse_note is None:
            return
        note = self.note_at(event.position().x(), event.position().y())
        if note != self._mouse_note:  # a glissando: the old key up, the new one down
            self._release(self._mouse_note)
            self._mouse_note = note
            if note is not None:
                self._press(note)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._mouse_note is not None:
            self._release(self._mouse_note)
            self._mouse_note = None

    # -- computer keyboard -----------------------------------------------------------------------------------------------

    def keyPressEvent(self, event):
        if event.isAutoRepeat():
            return
        text = event.text().lower()
        if text == "z":
            self.set_typing_base(self.typing_base - 12)
        elif text == "x":
            self.set_typing_base(self.typing_base + 12)
        elif text == "c":
            self.velocity_step.emit(-10)
        elif text == "v":
            self.velocity_step.emit(10)
        elif len(text) == 1 and text in TYPING_KEYS and event.modifiers() in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier):
            note = self.typing_base + TYPING_KEYS.index(text)
            if FIRST_NOTE <= note <= LAST_NOTE and event.key() not in self._typed:
                self._typed[event.key()] = note
                self._press(note)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.isAutoRepeat():
            return
        note = self._typed.pop(event.key(), None)  # (released by key, so changing the octave while holding a key can't leave a note stuck)
        if note is not None:
            self._release(note)
        else:
            super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        self.release_all()
        super().focusOutEvent(event)
        self.update()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.update()

    def changeEvent(self, event):
        if not self.isEnabled():
            self.release_all()
        super().changeEvent(event)

    # -- painting --------------------------------------------------------------------------------------------------------

    def paintEvent(self, _event):
        palette = theme.current_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        edge = QPen(QColor(palette["key_edge"]))
        accent = QColor(palette["accent"])
        enabled = self.isEnabled()
        painter.setPen(edge)
        font = QFont(self.font())
        font.setPixelSize(9)
        painter.setFont(font)
        for note in self._whites:
            rect = self._key_rect(note)
            colour = accent if self.is_down(note) else QColor(palette["key_white"])
            if not enabled:
                colour = QColor(palette["bg_disabled"])
            painter.setBrush(colour)
            painter.drawRect(rect)
            if note % 12 == 0:  # the C of each octave carries its name
                painter.setPen(QColor(palette["key_black"] if not self.is_down(note) else palette["text_on_accent"]))
                painter.drawText(rect.adjusted(2, 0, 0, -3), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft, params.note_name(note))
                painter.setPen(edge)
        for note in range(FIRST_NOTE, LAST_NOTE + 1):
            if note % 12 in BLACK:
                painter.setBrush(accent if self.is_down(note) else QColor(palette["key_black"] if enabled else palette["border_disabled"]))
                painter.drawRect(self._key_rect(note))
        if self.hasFocus():  # the computer keys are live: say which key plays which note
            painter.setFont(font)
            for index, letter in enumerate(TYPING_KEYS):
                note = self.typing_base + index
                if not FIRST_NOTE <= note <= LAST_NOTE:
                    continue
                rect = self._key_rect(note)
                if note % 12 in BLACK:
                    area, colour = rect.adjusted(0, rect.height() - 15, 0, -2), "key_white"
                else:
                    area, colour = QRectF(rect.left(), self.height() * 0.66, rect.width(), self.height() * 0.2), "key_black"
                painter.setPen(QColor(palette["text_on_accent"] if self.is_down(note) else palette[colour]))
                painter.drawText(area, Qt.AlignmentFlag.AlignCenter, letter.upper())
            # a thin accent frame
            painter.setPen(QPen(accent, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect().adjusted(1, 1, -1, -1))
        painter.end()
