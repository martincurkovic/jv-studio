"""Choose a tone's wave by name: a group (INT-A, INT-B, an expansion board), a filter box and the list of its waves."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from jv_studio.core import waves


class WavePickerDialog(QDialog):
    def __init__(self, group_type, group_id, number, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose Wave")
        self.setMinimumSize(380, 480)
        layout = QVBoxLayout(self)
        self.group_combo = QComboBox()
        for group in waves.selectable_groups():
            self.group_combo.addItem(group.title, group)
        current = waves.group_for(group_type, group_id)
        if current is not None:
            self.group_combo.setCurrentIndex(self.group_combo.findData(current))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by name")
        self.filter_edit.setClearButtonEnabled(True)
        self.list = QListWidget()
        self.note = QLabel("Only waves of the groups listed in the Owner's Manual are named here.")
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
        needle = self.filter_edit.text().strip().lower()
        self.list.clear()
        chosen = None
        for number, name in enumerate(group.names if group else ()):
            if needle and needle not in name.lower():
                continue
            item = QListWidgetItem(f"{number + 1:03d}  {name}")  # the unit's display numbers waves from 001
            item.setData(Qt.ItemDataRole.UserRole, number)
            self.list.addItem(item)
            if number == select_number:
                chosen = item
        if chosen is not None:
            self.list.setCurrentItem(chosen)
            self.list.scrollToItem(chosen, QListWidget.ScrollHint.PositionAtCenter)
        self._update_ok()

    def _update_ok(self):
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.list.currentItem() is not None)

    def result_wave(self):
        """(Wave Group Type, Wave Group ID, Wave Number) of the chosen wave."""
        group, item = self.group_combo.currentData(), self.list.currentItem()
        return group.type, group.id, item.data(Qt.ItemDataRole.UserRole)
