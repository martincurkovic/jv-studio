"""Choose the patch a performance part plays, by name: a group (USER, PR-A to PR-E, the Session board), a filter box and the list of its patches.
USER's names are the ones read from the unit (the list shows just numbers until they have been); the ROM groups' names are the manual's."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from jv_studio.core import patch_groups


class PatchPickerDialog(QDialog):
    def __init__(self, group_type, group_id, number, user_names=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose Patch")
        self.setMinimumSize(380, 480)
        self._user_names = user_names
        layout = QVBoxLayout(self)
        self.group_combo = QComboBox()
        for group in patch_groups.GROUPS:
            self.group_combo.addItem(group.title, group)
        current = patch_groups.group_for(group_type, group_id)
        if current is not None:
            self.group_combo.setCurrentIndex(self.group_combo.findData(current))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by name")
        self.filter_edit.setClearButtonEnabled(True)
        self.list = QListWidget()
        self.note = QLabel("")
        self.note.setObjectName("mutedLabel")
        self.note.setWordWrap(True)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        for widget in (self.group_combo, self.filter_edit, self.list, self.note, self.buttons):
            layout.addWidget(widget)
        self.group_combo.currentIndexChanged.connect(lambda _i: self._fill(None))
        self.filter_edit.textChanged.connect(lambda _t: self._fill(None))
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())
        self.list.currentItemChanged.connect(lambda *_: self._update_ok())
        self._fill(number if current is not None else None)

    def _fill(self, select_number):
        group = self.group_combo.currentData()
        names = patch_groups.names_of(group, self._user_names)
        needle = self.filter_edit.text().strip().lower()
        self.list.clear()
        chosen = None
        for number in range(group.count):
            name = names[number] if names and number < len(names) else ""
            if needle and needle not in name.lower() and needle not in f"{number + 1:03d}":
                continue
            item = QListWidgetItem(f"{number + 1:03d}  {name}".rstrip())  # the unit's display numbers patches from 001
            item.setData(Qt.ItemDataRole.UserRole, number)
            self.list.addItem(item)
            if number == select_number:
                chosen = item
        self.note.setText("" if names else "The USER patch names haven't been read from the unit yet (Read Patch Names), so only numbers are shown.")
        if chosen is not None:
            self.list.setCurrentItem(chosen)
            self.list.scrollToItem(chosen, QListWidget.ScrollHint.PositionAtCenter)
        self._update_ok()

    def _update_ok(self):
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.list.currentItem() is not None)

    def result_patch(self):
        """(Patch Group Type, Patch Group ID, Patch Number) of the chosen patch."""
        group, item = self.group_combo.currentData(), self.list.currentItem()
        return group.type, group.id, item.data(Qt.ItemDataRole.UserRole)
