"""The audition bar under the editor: a keyboard to hear the unit, and a patch browser that chooses patches on it by Bank Select + Program Change.

Nothing here writes to the unit's memory. It only emits what to send (`midi_out`, one complete channel message at a time) and what was chosen (`patch_chosen`), and the
window decides whether it is safe to send (not during a backup or an update). Choosing a patch changes the unit's CURRENT patch: the window says so and stops treating the
shown patch as the one on the unit (core/audition.py).

While the bar is OPEN (and the unit is connected) it owns the computer keyboard, as Ableton's computer MIDI keyboard does: every key press that is not a shortcut (Ctrl/Cmd/Alt) or a
navigation key (Tab, arrows, Esc, Enter, F-keys) is routed to the piano, whatever has the focus, so nothing can be typed into a text box. It stands aside while another window is in front
(a dialog, the System Settings window) or a drop-down is open. Cmd+K closes the bar and gives the keys back. The bar always starts closed.
"""

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QLabel, QPushButton, QSlider, QToolButton, QVBoxLayout, QWidget

from jv_studio.core import audition, params, patch_groups, universal
from jv_studio.ui.keyboard import TYPING_KEYS, PianoKeyboard, ScrollableKeyboard

HELP = (
    "Play the unit from the keyboard below and choose its patches. Nothing here is stored on the unit.\n"
    "While it is open the computer keyboard plays it: A W S E D F T G Y H U J K O L P ; are the notes, Z and X change the octave, C and V the velocity, "
    ", and . the patch, [ and ] the bank. "
    "Shortcuts such as Cmd+K (show or hide) still work."
)

CATEGORY_PREFIX = "category:"  # in the bank box's data: "category:PIANO"

#: keys that keep working while the bar owns the keyboard: moving around, confirming, cancelling
_PASS_THROUGH = {
    Qt.Key.Key_Tab, Qt.Key.Key_Backtab, Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right,
    Qt.Key.Key_PageUp, Qt.Key.Key_PageDown, Qt.Key.Key_Home, Qt.Key.Key_End, Qt.Key.Key_Space,
}
_SHORTCUT_MODIFIERS = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier | Qt.KeyboardModifier.AltModifier  # (Control is Cmd on a Mac)


class AuditionBar(QWidget):
    midi_out = Signal(object)  # one complete channel message (bytes)
    patch_chosen = Signal(str, int)  # patch group key, number (0-based): Bank Select and Program Change were just emitted
    open_changed = Signal(bool)  # the bar was shown or hidden (the View menu item follows)
    master_volume_changed = Signal(int)  # the Master slider was moved (and let go): send the Master Volume message
    unit_settings_requested = Signal()  # "From unit": read the receive channel and mode from the System block

    def __init__(self, parent=None):
        super().__init__(parent)
        self._user_names = []
        self._sounding = {}  # note -> the channel it was started on (so a note-off follows its note-on even if the channel box changes)
        self._available = False
        self._info_note = ""  # what the unit's own settings said (show_system), shown instead of the hint
        self._demo = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(15, 4, 15, 8)
        outer.setSpacing(6)

        self.toggle = QToolButton()
        self.toggle.setObjectName("auditionToggle")
        self.toggle.setText("Audition")
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setAutoRaise(True)
        self.toggle.setToolTip(HELP)
        self.toggle.clicked.connect(lambda: self.set_open(not self.is_open()))
        self.note = QLabel("")
        self.note.setObjectName("mutedLabel")
        self.note.setWordWrap(True)
        head = QHBoxLayout()
        head.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignLeft)  # (left: with the note line hidden the button would otherwise be stretched across the row, its label in the middle)
        head.addWidget(self.note, 1)
        outer.addLayout(head)

        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(6)
        outer.addWidget(self.body)

        row = QHBoxLayout()
        self.channel_combo = QComboBox()
        for number in range(1, 17):
            self.channel_combo.addItem(str(number))
        self.channel_combo.setToolTip("The MIDI channel the unit receives on. In Patch mode that is its Patch Receive Channel (System): 1 unless you changed it.")
        self.unit_button = QPushButton("From Unit")
        self.unit_button.setToolTip("Read the unit's receive channel and mode (a read; nothing is written).")
        self.unit_button.clicked.connect(self.unit_settings_requested)
        self.velocity = QSlider(Qt.Orientation.Horizontal)
        self.velocity.setRange(1, 127)
        self.velocity.setValue(audition.DEFAULT_VELOCITY)
        self.velocity.setMaximumWidth(140)
        self.velocity_label = QLabel()
        self.velocity.valueChanged.connect(lambda v: self.velocity_label.setText(str(v)))
        self.velocity_label.setText(str(self.velocity.value()))
        self.velocity_label.setMinimumWidth(26)
        self.master = QSlider(Qt.Orientation.Horizontal)
        self.master.setRange(0, 127)
        self.master.setValue(universal.MASTER_VOLUME_FULL)
        self.master.setMaximumWidth(110)
        self.master.setToolTip(
            "The unit's master volume (a MIDI message; it is not stored). The unit can't say what it is now, so this starts at full, as the unit does after power-on: "
            "turn it down before you turn anything up. Not heard in GM mode."
        )
        self.master_label = QLabel(str(self.master.value()))
        self.master_label.setMinimumWidth(26)
        self.master.valueChanged.connect(self._master_moved)
        self.master.sliderReleased.connect(lambda: self.master_volume_changed.emit(self.master.value()))
        self.typing_label = QLabel()
        self.typing_label.setObjectName("mutedLabel")
        self.playing_label = QLabel()  # the notes held right now (mouse or computer keys)
        self.playing_label.setMinimumWidth(150)
        self.playing_label.setToolTip("The notes being played")
        self.panic_button = QPushButton("Panic")
        self.panic_button.setToolTip("Silence the channel: hold pedal up, All Sound Off, All Notes Off.")
        self.panic_button.clicked.connect(self.panic)
        for widget in (QLabel("Channel"), self.channel_combo, self.unit_button, QLabel("Velocity"), self.velocity, self.velocity_label):
            row.addWidget(widget)
        row.addSpacing(12)
        row.addWidget(self.typing_label)
        row.addSpacing(12)
        row.addWidget(self.playing_label)
        row.addStretch()
        row.addWidget(QLabel("Master"))
        row.addWidget(self.master)
        row.addWidget(self.master_label)
        row.addSpacing(8)
        row.addWidget(self.panic_button)
        body.addLayout(row)

        browse = QHBoxLayout()
        self.bank_combo = QComboBox()
        for group in patch_groups.GROUPS:
            self.bank_combo.addItem(group.title, group.key)
            self.bank_combo.setItemData(self.bank_combo.count() - 1, patch_groups.GROUP_HELP[group.key], Qt.ItemDataRole.ToolTipRole)
        self.bank_combo.insertSeparator(self.bank_combo.count())
        for key, title in patch_groups.CATEGORIES.items():
            self.bank_combo.addItem(f"{title} (category)", CATEGORY_PREFIX + key)
            self.bank_combo.setItemData(self.bank_combo.count() - 1, patch_groups.CATEGORY_HELP, Qt.ItemDataRole.ToolTipRole)
        self.patch_combo = QComboBox()
        self.patch_combo.setMinimumWidth(260)
        self.prev_button = QPushButton("◀")
        self.next_button = QPushButton("▶")
        for button, tip in ((self.prev_button, "The previous patch"), (self.next_button, "The next patch")):
            button.setToolTip(tip)
            button.setMaximumWidth(36)
        self.bank_combo.setToolTip("Choose a patch on the unit (Patch mode): the unit's current patch changes. Use Read Temporary Patch to edit what you hear.")
        self.bank_combo.activated.connect(lambda _i: self._bank_chosen())
        self.patch_combo.activated.connect(lambda _i: self._send_patch())
        self.prev_button.clicked.connect(lambda: self._step(-1))
        self.next_button.clicked.connect(lambda: self._step(1))
        browse.addWidget(QLabel("Patch"))
        browse.addWidget(self.bank_combo)
        browse.addWidget(self.patch_combo, 1)
        browse.addWidget(self.prev_button)
        browse.addWidget(self.next_button)
        body.addLayout(browse)

        self.keyboard = PianoKeyboard()
        self.keyboard.note_on.connect(self._note_on)
        self.keyboard.note_off.connect(self._note_off)
        self.keyboard.typing_base_changed.connect(lambda _n: self._show_typing())
        self.keyboard.held_changed.connect(self._show_playing)
        self.keyboard.velocity_step.connect(self.step_velocity)
        self.keyboard.patch_step.connect(self._step)
        self.keyboard.bank_step.connect(self._step_bank)
        self.keyboard_scroll = ScrollableKeyboard(self.keyboard)  # (scrolls sideways when the window is too narrow for the keys)
        body.addWidget(self.keyboard_scroll)
        self._show_typing()
        self._fill_patches()
        self.set_open(False)  # always starts closed: an open bar takes over the computer keyboard
        self.set_available(False)

    def _idle_note(self):
        return self._info_note or ("Demo: the simulated unit makes no sound." if self._demo else "")

    def _set_note(self, text):
        self.note.setText(text)
        self.note.setVisible(bool(text))  # (an empty line would still take up room)

    def set_demo(self, demo):
        self._demo = demo

    # -- open / closed ---------------------------------------------------------------------------------------------------

    def is_open(self):
        return not self.body.isHidden()

    def set_open(self, opened, *, focus=False):
        """Show or hide the keyboard. Hiding it lets go of every note and gives the computer keyboard back; `focus` (the shortcut) also gives the piano the focus."""
        changed = opened != self.is_open()
        self.body.setVisible(opened)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow)
        app = QApplication.instance()
        if opened:
            if app is not None:
                app.installEventFilter(self)
            if focus:
                self.keyboard.setFocus()
        else:
            if app is not None:
                app.removeEventFilter(self)
            self.keyboard.release_all()
        self._update_routing()
        if changed:
            self.open_changed.emit(opened)

    # -- owning the computer keyboard ------------------------------------------------------------------------------------

    def routing_keys(self):
        """True while the computer keyboard belongs to the piano: the bar is open and the unit is connected (a dead keyboard must not swallow typing)."""
        return self.is_open() and self._available

    def _update_routing(self):
        self.keyboard.set_live(self.routing_keys())

    def _window_in_front(self):
        return QApplication.activeWindow() is self.window()

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease) or watched is self.keyboard or not self.routing_keys():
            return False
        if QApplication.activePopupWidget() is not None or not self._window_in_front():
            return False  # a drop-down, a dialog or another window of the app: typing there works as usual
        key = event.key()
        if event.modifiers() & _SHORTCUT_MODIFIERS or key in _PASS_THROUGH or Qt.Key.Key_F1 <= key <= Qt.Key.Key_F35:
            return False
        if kind == QEvent.Type.KeyPress:
            self.keyboard.keyPressEvent(event)
        else:
            self.keyboard.keyReleaseEvent(event)
        return True  # every other key belongs to the piano, whether or not it plays a note

    def set_available(self, available, why=""):
        """Off while there is no connection or a long job runs: the keys let go of everything first."""
        self._available = available
        if not available:
            self.keyboard.release_all()
        self.body.setEnabled(available)
        self._update_routing()
        self._set_note(self._idle_note() if available else why or self.note.text())

    # -- the keyboard ----------------------------------------------------------------------------------------------------

    def channel(self):
        """0-15."""
        return self.channel_combo.currentIndex()

    def set_channel(self, channel_one_based):
        self.channel_combo.setCurrentIndex(max(1, min(16, channel_one_based)) - 1)

    def _show_typing(self):
        base = self.keyboard.typing_base
        self.typing_label.setText(f"Octave: {params.note_name(base)} to {params.note_name(base + len(TYPING_KEYS) - 1)}")

    def _master_moved(self, value):
        """The number follows the slider while it is dragged; the message goes out when it is let go (or at once for a key or wheel step)."""
        self.master_label.setText(str(value))
        if not self.master.isSliderDown():
            self.master_volume_changed.emit(value)

    def step_velocity(self, direction):
        """Louder (+) or quieter (-): the next multiple of 10, or 1 / 127 at the ends (the C and V keys); the new value is shown in the read-out."""
        self.velocity.setValue(audition.step_velocity(self.velocity.value(), direction))
        self.playing_label.setText(f"Velocity {self.velocity.value()}")

    def _show_playing(self, notes):
        self.playing_label.setText("   ".join(params.note_name(n) for n in notes) if notes else "")

    def _note_on(self, note):
        if not self._available:
            return
        self._sounding[note] = self.channel()
        self.midi_out.emit(audition.note_on(self._sounding[note], note, self.velocity.value()))

    def _note_off(self, note):
        channel = self._sounding.pop(note, None)
        if channel is not None:
            self.midi_out.emit(audition.note_off(channel, note))

    def panic(self):
        self.keyboard.release_all()
        for message in audition.panic(self.channel()):
            self.midi_out.emit(message)

    # -- choosing a patch ------------------------------------------------------------------------------------------------

    def set_user_names(self, names):
        """The USER patch names read from the unit (for the patch box)."""
        self._user_names = list(names)
        if self.bank_combo.currentData() == "USER":
            self._fill_patches(keep=self.patch_combo.currentIndex())

    def _category(self):
        """The category being browsed ("PIANO"...), or None when a bank is."""
        data = self.bank_combo.currentData() or ""
        return data[len(CATEGORY_PREFIX):] if data.startswith(CATEGORY_PREFIX) else None

    def _group(self):
        return next(g for g in patch_groups.GROUPS if g.key == self.bank_combo.currentData())

    def _fill_patches(self, keep=0):
        """The patch box: a bank's patches 001.., or a category's patches (the unit's own numbering for it), each remembering which bank patch it is."""
        self.patch_combo.clear()
        if (category := self._category()) is not None:
            for entry in patch_groups.category_entries(category):
                self.patch_combo.addItem(f"{entry.no:03d}  {entry.name}", (entry.group.key, entry.number))
                self.patch_combo.setItemData(self.patch_combo.count() - 1, f"{entry.group.title} {entry.number + 1:03d}", Qt.ItemDataRole.ToolTipRole)
            self.patch_combo.setCurrentIndex(max(0, min(keep, self.patch_combo.count() - 1)))
            return
        group = self._group()
        names = patch_groups.names_of(group, self._user_names) or []
        for number in range(group.count):
            name = names[number] if number < len(names) else ""
            self.patch_combo.addItem(f"{number + 1:03d}  {name}".rstrip(), (group.key, number))
        self.patch_combo.setCurrentIndex(max(0, min(keep, group.count - 1)))

    def _bank_chosen(self):
        self._fill_patches(keep=0)
        self._send_patch()

    def _step(self, direction):
        index = self.patch_combo.currentIndex() + direction
        if 0 <= index < self.patch_combo.count():
            self.patch_combo.setCurrentIndex(index)
            self._send_patch()

    def _step_bank(self, direction):
        """The previous / next entry of the bank box (the banks, then the categories; the separator between them is skipped), choosing its first patch on the unit."""
        index = self.bank_combo.currentIndex() + direction
        while 0 <= index < self.bank_combo.count() and self.bank_combo.itemData(index) is None:
            index += direction  # (the separator)
        if 0 <= index < self.bank_combo.count():
            self.bank_combo.setCurrentIndex(index)
            self._bank_chosen()

    def _send_patch(self):
        if self.patch_combo.currentData() is None:
            return
        key, number = self.patch_combo.currentData()  # (the bank the patch lives in: a category's entries point into the banks)
        self.keyboard.release_all()  # (the old patch's notes must not hang on after it changes)
        for message in audition.patch_select(self.channel(), key, number):
            self.midi_out.emit(message)
        self.patch_chosen.emit(key, number)

    def choose(self, group_key, number):
        """Show patch `number` of `group_key` in the boxes and choose it on the unit (the USER list's "Play on Unit")."""
        index = self.bank_combo.findData(group_key)
        if index < 0:
            return
        self.bank_combo.setCurrentIndex(index)
        self._fill_patches(keep=number)
        self._send_patch()

    def current_label(self):
        if (category := self._category()) is not None:
            return f"{category} {self.patch_combo.currentText()}".strip()
        return f"{self._group().key} {self.patch_combo.currentText()}".strip()

    # -- what the unit says about itself ---------------------------------------------------------------------------------

    def show_selected_patch(self, info):
        """Show the patch the unit has selected in the bank and patch boxes, WITHOUT sending anything (the unit is already there). Only in Patch mode, and only for a patch group
        the manual's table names (a Wave Expansion board's is left alone)."""
        group = patch_groups.group_for(info.group_type, info.group_id)
        if info.sound_mode != 1 or group is None or not 0 <= info.patch_number < group.count:
            return
        index = self.bank_combo.findData(group.key)
        self.bank_combo.setCurrentIndex(index)
        self._fill_patches(keep=info.patch_number)

    def show_system(self, info, announce=True):
        """Show the patch the unit has selected. With `announce` (the From Unit button) also use its Patch Receive Channel and say what would stop this working; without it (a refresh)
        the channel box is left as the user set it (it may be on 10 for the rhythm part) and the note line stays as it is."""
        self.show_selected_patch(info)
        if not announce:
            return
        self.set_channel(info.channel + 1)
        problems = info.problems()
        self._info_note = " ".join(problems) if problems else f"The unit is in {info.mode_name} mode and receives on channel {info.channel + 1}."
        self._set_note(self._info_note)
