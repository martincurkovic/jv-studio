"""Choose which patch of a `.syx` file to open when the file holds several (a bank, or a collection made by someone else). See `core/patch_collection.py`."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem, QVBoxLayout

from jv_studio.core import params, patch


class PatchCollectionDialog(QDialog):
    def __init__(self, collection, file_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Open Patch")
        self.setMinimumSize(420, 460)
        self._collection = collection
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"{file_name} holds {len(collection.entries)} patches. Open:"))
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())
        self.list.currentItemChanged.connect(lambda *_: self._update_ok())
        layout.addWidget(self.list, 1)
        self.blank_check = QCheckBox(f"Show the {collection.blank} blank (INIT PATCH) slots")
        self.blank_check.setVisible(bool(collection.blank))
        self.blank_check.toggled.connect(lambda _on: self._fill())
        layout.addWidget(self.blank_check)
        self.note = QLabel(self._note())
        self.note.setObjectName("mutedLabel")
        self.note.setWordWrap(True)
        self.note.setVisible(bool(self.note.text()))
        layout.addWidget(self.note)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Open")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._fill()

    def _note(self):
        c, parts = self._collection, []
        if c.repaired:
            parts.append(f"{c.repaired} of the patches had wrong checksums (the file was made by a tool that got them wrong). Their values are all inside the manual's ranges, so they open normally; "
                         "sending or saving writes correct ones.")
        if c.damaged:
            parts.append(f"{c.damaged} patch(es) have a wrong checksum AND values outside the ranges, so they look damaged and are not listed.")
        if c.incomplete:
            parts.append(f"{c.incomplete} patch(es) were missing blocks and are not listed.")
        return " ".join(parts)

    def _fill(self):
        categories = params.load_table().block(patch.COMMON).param("patch_category")
        self.list.clear()
        for entry in self._collection.offered(self.blank_check.isChecked()):
            built = entry.patch
            tones = sum(built.get(patch.TONE, "tone_switch", tone=t) for t in range(patch.TONE_COUNT))
            category = params.format_value(categories, built.get(patch.COMMON, "patch_category")).title()
            item = QListWidgetItem(f"{entry.index:03d}  {built.name.strip()}    {tones} tone{'s' if tones != 1 else ''} · {category}" + ("  · checksum repaired" if entry.repaired else ""))
            item.setData(Qt.ItemDataRole.UserRole, entry)
            if entry.repaired:
                item.setToolTip("The file had a wrong checksum on this patch; its values are in range, so it was used as it is.")
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        self._update_ok()

    def _update_ok(self):
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.list.currentItem() is not None)

    def chosen(self):
        """The `FilePatch` that is selected."""
        return self.list.currentItem().data(Qt.ItemDataRole.UserRole)
