"""The two questions asked before the unit's memory changes: which USER slot to overwrite, and which sections of a backup to restore."""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from jv_studio.core import memory, patch


class WriteUserDialog(QDialog):
    """Pick the USER slot a patch will replace. `names` are the slot names read from the unit (may be empty)."""

    def __init__(self, patch_name, names, default_slot, backups_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Write to USER")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f'Write "{patch_name}" to:'))
        self.slot_combo = QComboBox()
        for number in range(patch.USER_PATCH_COUNT):
            known = f"  {names[number]}" if number < len(names) else ""
            self.slot_combo.addItem(f"USER:{number + 1:03d}{known}", number)
        self.slot_combo.setCurrentIndex(max(0, min(default_slot, patch.USER_PATCH_COUNT - 1)))
        layout.addWidget(self.slot_combo)
        note = QLabel(f"The slot's current patch is saved to {backups_dir} first, and the write is read back to check it.")
        note.setWordWrap(True)
        note.setObjectName("mutedLabel")
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Overwrite")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def slot(self):
        return self.slot_combo.currentData()


class RestoreDialog(QDialog):
    """Choose what to restore from a backup. A section the backup doesn't fully hold is disabled; System settings start unchecked."""

    def __init__(self, summary, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Restore Unit")
        layout = QVBoxLayout(self)
        intro = QLabel("This overwrites the unit's memory with the backup, block by block, and reads each block back.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.checks = {}
        for section in memory.SECTIONS:
            have, total = summary[section]
            box = QCheckBox(f"{memory.SECTION_TITLES[section]} ({have} of {total} blocks in the backup)")
            box.setEnabled(have == total)
            box.setChecked(have == total and section != memory.SYSTEM)
            if section == memory.SYSTEM:
                box.setToolTip("Master tune, MIDI channels and other global settings. Leave this off unless you want those changed back too.")
            box.toggled.connect(self._update_ok)
            self.checks[section] = box
            layout.addWidget(box)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Restore")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._update_ok()

    def _update_ok(self, *_):
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.sections()))

    def sections(self):
        return [s for s in memory.SECTIONS if self.checks[s].isChecked()]


class SlotDialog(QDialog):
    """Pick a USER slot for Copy To... or Swap With...: a prompt, the 128 slots (with the names read from the unit, if any) and a note."""

    def __init__(self, title, prompt, names, default_slot, ok_text, note, parent=None, count=patch.USER_PATCH_COUNT, label="USER:{:03d}"):
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(prompt))
        self.slot_combo = QComboBox()
        for number in range(count):
            known = f"  {names[number]}" if number < len(names) else ""
            self.slot_combo.addItem(f"{label.format(number + 1)}{known}", number)
        self.slot_combo.setCurrentIndex(max(0, min(default_slot, count - 1)))
        layout.addWidget(self.slot_combo)
        muted = QLabel(note)
        muted.setWordWrap(True)
        muted.setObjectName("mutedLabel")
        layout.addWidget(muted)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(ok_text)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def slot(self):
        return self.slot_combo.currentData()


class RenameDialog(QDialog):
    """A patch name: at most 12 characters (the unit's limit); characters the unit can't show (outside 32-125) are replaced by spaces when it is stored."""

    def __init__(self, current, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rename USER Patch")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("New name (12 characters at most):"))
        self.edit = QLineEdit(current)
        self.edit.setMaxLength(12)
        self.edit.selectAll()
        layout.addWidget(self.edit)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.edit.textChanged.connect(lambda t: self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(t.strip())))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(current.strip()))

    def name(self):
        return self.edit.text()
