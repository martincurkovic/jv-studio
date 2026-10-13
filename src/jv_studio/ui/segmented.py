"""A segmented control: a row of joined, mutually exclusive buttons (the mode switch). Same small API as a QTabBar (`currentIndex`, `setCurrentIndex`, `currentChanged`)
so it can stand in for one; the look comes from the stylesheet (checkable QPushButtons with a `segment` property of first, middle or last)."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget


class SegmentedControl(QWidget):
    currentChanged = Signal(int)

    def __init__(self, labels, tooltips=(), parent=None):
        super().__init__(parent)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)  # the buttons touch: one control, not two buttons
        for index, text in enumerate(labels):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setProperty("segment", "first" if index == 0 else "last" if index == len(labels) - 1 else "middle")
            if index < len(tooltips):
                button.setToolTip(tooltips[index])
            self._group.addButton(button, index)
            self._buttons.append(button)
            layout.addWidget(button)
        self._buttons[0].setChecked(True)
        self._group.idClicked.connect(self.currentChanged)

    def currentIndex(self):
        return self._group.checkedId()

    def setCurrentIndex(self, index):
        if index == self.currentIndex() or not 0 <= index < len(self._buttons):
            return
        self._buttons[index].setChecked(True)
        self.currentChanged.emit(index)  # (a click emits through the group; a call from code has to say so itself)
