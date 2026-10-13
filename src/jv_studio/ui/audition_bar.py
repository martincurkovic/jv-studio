"""The audition bar under the editor: a keyboard to hear the unit, and a patch browser that chooses patches on it by Bank Select + Program Change.

Nothing here writes to the unit's memory. It only emits what to send (`midi_out`, one complete channel message at a time) and what was chosen (`patch_chosen`), and the
window decides whether it is safe to send (not during a backup or an update). Choosing a patch changes the unit's CURRENT patch: the window says so and stops treating the
shown patch as the one on the unit (core/audition.py).
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QSlider, QSpinBox, QToolButton, QVBoxLayout, QWidget

from jv_studio.core import app_config, audition, params, patch_groups
from jv_studio.ui.keyboard import TYPING_KEYS, PianoKeyboard

HINT = "Click the keys, or click the keyboard and type: A W S E D F T G Y H U J K O L P ; play notes, Z and X change the octave, C and V the velocity (Cmd+K shows or hides this bar)."


class AuditionBar(QWidget):
    midi_out = Signal(object)  # one complete channel message (bytes)
    patch_chosen = Signal(str, int)  # patch group key, number (0-based): Bank Select and Program Change were just emitted
    open_changed = Signal(bool)  # the bar was shown or hidden (the View menu item follows)
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
        self.toggle.setText("Audition")
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setAutoRaise(True)
        self.toggle.setToolTip("Play the unit from the keyboard below and choose its patches. Nothing here is stored on the unit.")
        self.toggle.clicked.connect(lambda: self.set_open(not self.is_open()))
        self.note = QLabel("")
        self.note.setObjectName("mutedLabel")
        self.note.setWordWrap(True)
        head = QHBoxLayout()
        head.addWidget(self.toggle)
        head.addWidget(self.note, 1)
        outer.addLayout(head)

        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(6)
        outer.addWidget(self.body)

        row = QHBoxLayout()
        self.channel_spin = QSpinBox()
        self.channel_spin.setRange(1, 16)
        self.channel_spin.setToolTip("The MIDI channel the unit receives on. In Patch mode that is its Patch Receive Channel (System): 1 unless you changed it.")
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
        self.typing_label = QLabel()
        self.typing_label.setObjectName("mutedLabel")
        self.playing_label = QLabel()  # the notes held right now (mouse or computer keys)
        self.playing_label.setMinimumWidth(150)
        self.playing_label.setToolTip("The notes being played")
        self.panic_button = QPushButton("Panic")
        self.panic_button.setToolTip("Silence the channel: hold pedal up, All Sound Off, All Notes Off.")
        self.panic_button.clicked.connect(self.panic)
        for widget in (QLabel("Channel"), self.channel_spin, self.unit_button, QLabel("Velocity"), self.velocity, self.velocity_label):
            row.addWidget(widget)
        row.addSpacing(12)
        row.addWidget(self.typing_label)
        row.addSpacing(12)
        row.addWidget(self.playing_label)
        row.addStretch()
        row.addWidget(self.panic_button)
        body.addLayout(row)

        browse = QHBoxLayout()
        self.bank_combo = QComboBox()
        for group in patch_groups.GROUPS:
            self.bank_combo.addItem(group.title, group.key)
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
        body.addWidget(self.keyboard)
        self._show_typing()
        self._fill_patches()
        self.set_open(app_config.get_audition_open(), remember=False)
        self.set_available(False)

    def _idle_note(self):
        return self._info_note or (("Demo: the simulated unit makes no sound. " if self._demo else "") + HINT)

    def set_demo(self, demo):
        self._demo = demo

    # -- open / closed ---------------------------------------------------------------------------------------------------

    def is_open(self):
        return not self.body.isHidden()

    def set_open(self, opened, *, remember=True, focus=False):
        """Show or hide the keyboard. Hiding it lets go of every note; `focus` (the shortcut) gives the keys the focus so typing plays at once."""
        changed = opened != self.is_open()
        self.body.setVisible(opened)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow)
        if not opened:
            self.keyboard.release_all()
        elif focus:
            self.keyboard.setFocus()
        if remember:
            app_config.save_audition_open(opened)
        if changed:
            self.open_changed.emit(opened)

    def set_available(self, available, why=""):
        """Off while there is no connection or a long job runs: the keys let go of everything first."""
        self._available = available
        if not available:
            self.keyboard.release_all()
        self.body.setEnabled(available)
        self.note.setText(self._idle_note() if available else why or self.note.text())

    # -- the keyboard ----------------------------------------------------------------------------------------------------

    def channel(self):
        """0-15."""
        return self.channel_spin.value() - 1

    def set_channel(self, channel_one_based):
        self.channel_spin.setValue(channel_one_based)

    def _show_typing(self):
        base = self.keyboard.typing_base
        self.typing_label.setText(f"Keys {TYPING_KEYS[0].upper()}-{TYPING_KEYS[-1]}: {params.note_name(base)} to {params.note_name(base + len(TYPING_KEYS) - 1)}")

    def step_velocity(self, delta):
        """Louder or quieter by `delta` (the C and V keys: -10 / +10), within 1-127; the new value is shown in the read-out."""
        self.velocity.setValue(max(1, min(127, self.velocity.value() + delta)))
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

    def _group(self):
        return next(g for g in patch_groups.GROUPS if g.key == self.bank_combo.currentData())

    def _fill_patches(self, keep=0):
        group = self._group()
        names = patch_groups.names_of(group, self._user_names) or []
        self.patch_combo.clear()
        for number in range(group.count):
            name = names[number] if number < len(names) else ""
            self.patch_combo.addItem(f"{number + 1:03d}  {name}".rstrip(), number)
        self.patch_combo.setCurrentIndex(max(0, min(keep, group.count - 1)))

    def _bank_chosen(self):
        self._fill_patches(keep=0)
        self._send_patch()

    def _step(self, direction):
        index = self.patch_combo.currentIndex() + direction
        if 0 <= index < self.patch_combo.count():
            self.patch_combo.setCurrentIndex(index)
            self._send_patch()

    def _send_patch(self):
        key, number = self.bank_combo.currentData(), self.patch_combo.currentData()
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
        return f"{self._group().key} {self.patch_combo.currentText()}".strip()

    # -- what the unit says about itself ---------------------------------------------------------------------------------

    def show_system(self, info):
        """Use the unit's Patch Receive Channel and say what would stop this working."""
        self.set_channel(info.channel + 1)
        problems = info.problems()
        self._info_note = " ".join(problems) if problems else f"The unit is in {info.mode_name} mode and receives on channel {info.channel + 1}. {HINT}"
        self.note.setText(self._info_note)
