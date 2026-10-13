"""The patch editor: one tab for the patch common block and one per tone, built from the parameter table (`core/groups.py` says which card a
parameter is on). It edits a `Patch` IN PLACE (the caller's working copy) and never talks to the unit: it emits `param_committed` for each user edit
and the window decides what to do with it (the owner's rule: the UI is live, MIDI goes out on release; a spin box commits on a step or Enter).
"""

from functools import lru_cache

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from jv_studio.core import groups, params, patch
from jv_studio.ui.qt_helpers import FullWidthTabBar, build_editor_card, build_scroll_area


@lru_cache(maxsize=None)
def _text_to_value(param):
    """{displayed text, lower case: raw value} for a parameter whose range is small enough to list."""
    if param.max - param.min > 20000:
        return {}
    return {params.format_value(param, v).lower(): v for v in range(param.min, param.max + 1)}


class ValueSpinBox(QSpinBox):
    """Shows a raw value the way the unit's display does (a note name, +12, L30, OFF...) and accepts that text back. The mouse wheel only acts when
    the box has focus, so scrolling a page of them never changes a value by accident."""

    def __init__(self, param, parent=None):
        super().__init__(parent)
        self.param = param
        self.setRange(param.min, param.max)
        self.setKeyboardTracking(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)

    def textFromValue(self, value):
        return params.format_value(self.param, value)

    def _parse(self, text):
        return _text_to_value(self.param).get(text.strip().lower())

    def valueFromText(self, text):
        found = self._parse(text)
        return self.value() if found is None else found

    def validate(self, text, pos):
        state = QValidator.State.Acceptable if self._parse(text) is not None else QValidator.State.Intermediate
        return state, text, pos

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class ChoiceCombo(QComboBox):
    def __init__(self, param, parent=None):
        super().__init__(parent)
        self.param = param
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        if param.choices:
            for index, choice in enumerate(param.choices):
                if choice.jv1010:  # a JV-1080-family value the JV-1010 ignores is not offered
                    self.addItem(choice.label, param.min + index)
        else:
            for index, label in enumerate(param.labels):
                self.addItem(label, param.min + index)

    def set_raw(self, value):
        index = self.findData(value)
        if index < 0:  # the unit holds a value we don't offer (a JV-1080-only choice, or outside the table): show it, don't hide it
            self.addItem(f"{params.format_value(self.param, value)} (not offered)", value)
            index = self.count() - 1
        self.setCurrentIndex(index)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class PatchEditor(QWidget):
    #: block key, parameter key, tone (0-3, or -1 for the common block), the value now in the patch (an int, or the text of the name)
    param_committed = Signal(str, str, int, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._patch = None
        self._loading = False
        self._widgets = {}  # (block, tone or None, key) -> widget
        self.tabs = QTabWidget()
        self.tabs.setTabBar(FullWidthTabBar(self.tabs))
        # a tab's page is built when it is first shown: the five pages are ~600 widgets, which every window (and every test) would otherwise pay for
        self._holders = []
        self._built = set()
        for title in ["Common"] + [f"Tone {t + 1}" for t in range(patch.TONE_COUNT)]:
            holder = QWidget()
            QVBoxLayout(holder).setContentsMargins(0, 0, 0, 0)
            self._holders.append(holder)
            self.tabs.addTab(holder, title)
        self.tabs.currentChanged.connect(self._build_tab)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)
        self.setEnabled(False)

    # -- building --------------------------------------------------------------------------------------------------------

    def _build_tab(self, index):
        if index in self._built or index < 0:
            return
        self._built.add(index)
        tone = None if index == 0 else index - 1
        self._holders[index].layout().addWidget(self._page(patch.COMMON if tone is None else patch.TONE, tone))
        self.refresh()

    def _page(self, block_key, tone):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(6)
        scope = "patch_editor_common" if tone is None else "patch_editor_tone"
        for title, members in groups.groups(block_key):
            form = QFormLayout()
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
            for param in members:
                widget = self._make_widget(block_key, tone, param)
                self._widgets[(block_key, tone, param.key)] = widget
                form.addRow(param.name, widget)
            layout.addWidget(build_editor_card(scope, title, form, key=f"{title}"))
        layout.addStretch()
        return build_scroll_area(page)

    def _make_widget(self, block_key, tone, param):
        if param.string:
            widget = QLineEdit()
            widget.setMaxLength(param.size)
            widget.editingFinished.connect(lambda w=widget, p=param: self._name_edited(w, p))
        elif param.has_choices():
            widget = ChoiceCombo(param)
            widget.activated.connect(lambda _i, w=widget, b=block_key, t=tone, p=param: self._edited(b, t, p, w.currentData()))
        else:
            widget = ValueSpinBox(param)
            widget.valueChanged.connect(lambda v, b=block_key, t=tone, p=param: self._edited(b, t, p, v))
        note = params.load_table().block(block_key).footnotes.get(param.footnote) if param.footnote else None
        if note:
            widget.setToolTip(note)
        return widget

    # -- showing a patch -------------------------------------------------------------------------------------------------

    def set_patch(self, working):
        """Show `working` (a `Patch`, edited in place from now on), or nothing for None."""
        self._patch = working
        self.setEnabled(working is not None)
        if working is not None:
            self._build_tab(self.tabs.currentIndex())
            self.refresh()

    def refresh(self):
        """Show the patch's current values again (after something else changed it). Emits nothing."""
        if self._patch is None:
            return
        self._loading = True
        try:
            table = params.load_table()
            for (block_key, tone, key), widget in self._widgets.items():
                param = table.block(block_key).param(key)
                value = self._patch.get(block_key, key, tone=tone)
                if isinstance(widget, QLineEdit):
                    widget.setText(value)
                elif isinstance(widget, ChoiceCombo):
                    widget.set_raw(value)
                else:
                    widget.setValue(max(param.min, min(param.max, value)))
        finally:
            self._loading = False

    def widget_for(self, block_key, key, tone=None):
        """The control for a parameter (builds its tab if it hasn't been shown yet)."""
        self._build_tab(0 if tone is None else tone + 1)
        return self._widgets[(block_key, tone, key)]

    # -- user edits ------------------------------------------------------------------------------------------------------

    def _edited(self, block_key, tone, param, value):
        if self._loading or self._patch is None:
            return
        stored = self._patch.set(block_key, param.key, value, tone=tone)
        self.param_committed.emit(block_key, param.key, -1 if tone is None else tone, stored)

    def _name_edited(self, widget, param):
        if self._loading or self._patch is None:
            return
        before = self._patch.name
        stored = self._patch.set(patch.COMMON, param.key, widget.text())
        if widget.text() != stored:
            widget.setText(stored)  # show what the unit will hold (characters outside 32-125 become spaces)
        if stored != before:
            self.param_committed.emit(patch.COMMON, param.key, -1, stored)
