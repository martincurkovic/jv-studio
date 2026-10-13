"""The two questions asked before the unit's memory changes: which USER slot to overwrite, and which sections of a backup to restore."""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from jv1010editor.core import memory, patch


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
