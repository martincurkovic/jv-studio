"""Choose the patch a performance part plays, by name: a bank (USER, Preset A to E, the Session board) or one of the unit's categories (Piano, Guitar / Bass...), a filter box
and the list of its patches. USER's names are the ones read from the unit (the list shows just numbers until they have been); the ROM names are the manual's.
A category lists patches of Preset A-E and Session under the unit's own numbers; what is stored is still the bank and number of the patch (the part's three parameters)."""

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
            self.group_combo.setItemData(self.group_combo.count() - 1, patch_groups.GROUP_HELP[group.key], Qt.ItemDataRole.ToolTipRole)
        self.group_combo.insertSeparator(self.group_combo.count())
        for key, title in patch_groups.CATEGORIES.items():
            self.group_combo.addItem(f"{title} (category)", key)  # (a str: the category; a PatchGroup: a bank)
            self.group_combo.setItemData(self.group_combo.count() - 1, patch_groups.CATEGORY_HELP, Qt.ItemDataRole.ToolTipRole)
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

    def _rows(self, data):
        """[(text shown, search number, name, bank, number from 0, tooltip)] for the chosen bank or category."""
        if isinstance(data, str):
            return [(f"{e.no:03d}  {e.name}", f"{e.no:03d}", e.name, e.group, e.number, f"{e.group.title} {e.number + 1:03d}") for e in patch_groups.category_entries(data)]
        names = patch_groups.names_of(data, self._user_names)
        rows = []
        for number in range(data.count):
            name = names[number] if names and number < len(names) else ""
            rows.append((f"{number + 1:03d}  {name}".rstrip(), f"{number + 1:03d}", name, data, number, ""))  # (the unit's display numbers patches from 001)
        return rows

    def _fill(self, select_number):
        data = self.group_combo.currentData()
        needle = self.filter_edit.text().strip().lower()
        self.list.clear()
        chosen = None
        for text, shown_number, name, bank, number, tip in self._rows(data):
            if needle and needle not in name.lower() and needle not in shown_number:
                continue
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, (bank, number))
            if tip:
                item.setToolTip(tip)
            self.list.addItem(item)
            if not isinstance(data, str) and number == select_number:
                chosen = item
        if isinstance(data, str):
            self.note.setText("Grouped by kind, like the unit's CATEGORY knob. Hover a patch to see which bank it is stored in.")
        else:
            names = patch_groups.names_of(data, self._user_names)
            self.note.setText("" if names else "The USER patch names haven't been read from the unit yet (Read Patch Names), so only numbers are shown.")
        if chosen is not None:
            self.list.setCurrentItem(chosen)
            self.list.scrollToItem(chosen, QListWidget.ScrollHint.PositionAtCenter)
        self._update_ok()

    def _update_ok(self):
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.list.currentItem() is not None)

    def result_patch(self):
        """(Patch Group Type, Patch Group ID, Patch Number) of the chosen patch."""
        group, number = self.list.currentItem().data(Qt.ItemDataRole.UserRole)  # (the bank the patch is stored in, even when browsing a category)
        return group.type, group.id, number
