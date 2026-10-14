"""Small Qt helpers shared by the windows and dialogs: section cards, scroll pages, form alignment."""

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QLabel,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from jv_studio.ui.section_card import SectionCard


class ClickableLabel(QLabel):
    """A label that can be clicked (the connection pill): `clicked` is emitted on a left click, and the pointer shows it."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class FullWidthTabBar(QTabBar):
    """A tab bar whose tabs share the whole width of their QTabWidget (QTabBar's own `expanding` only spreads them over their natural width).

    Install with `tab_widget.setTabBar(FullWidthTabBar(tab_widget))` BEFORE adding tabs. It watches the QTabWidget's resize events,
    because the widget sizes its bar only once when the tabs are first laid out."""

    def __init__(self, tab_widget):
        super().__init__(tab_widget)
        tab_widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize:
            self.resize(watched.width(), self.height())
        return super().eventFilter(watched, event)

    def tabSizeHint(self, index):
        size = super().tabSizeHint(index)
        parent = self.parentWidget()
        visible = [i for i in range(self.count()) if self.isTabVisible(i)]  # only visible tabs share the width
        if parent is not None and index in visible:
            count = len(visible)
            position = visible.index(index)
            base, remainder = divmod(parent.width(), count)
            size.setWidth(base + (1 if position >= count - remainder else 0))  # the leftover pixels go to the last tabs: the bar matches the pane exactly
        return size


def align_form_label_columns(*forms):
    """Give every label in every form the width of the widest one, so the fields of a page of cards start at one x. Call after the rows are added."""
    labels = []
    for form in forms:
        for row in range(form.rowCount()):
            item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            widget = item.widget() if item is not None else None
            if isinstance(widget, QLabel):
                labels.append(widget)
    if labels:
        width = max(label.sizeHint().width() for label in labels)
        for label in labels:
            label.setMinimumWidth(width)


def widen_popup_to_fit_items(combo):
    """A QComboBox's drop-down is only as wide as the closed box: make it fit its widest item."""
    metrics = QFontMetrics(combo.font())
    widest = max((metrics.horizontalAdvance(combo.itemText(i)) for i in range(combo.count())), default=0)
    combo.view().setMinimumWidth(widest + 40)


def build_section_card(title, *row_layouts, header_widgets=(), collapse_key=None):
    """Group rows into one card (QWidget#sectionCard in the stylesheet). With `collapse_key` it is a collapsible `SectionCard`."""
    if collapse_key:
        return SectionCard(title, row_layouts, header_widgets, collapse_key)
    header = QLabel(title)
    header.setObjectName("sectionHeader")
    layout = QVBoxLayout()
    layout.setContentsMargins(12, 10, 12, 12)
    layout.setSpacing(10)
    if header_widgets:
        header_row = QHBoxLayout()  # small controls right beside the title rather than a row of their own
        header_row.setSpacing(8)
        header_row.addWidget(header)
        for widget in header_widgets:
            header_row.addWidget(widget)
        header_row.addStretch()
        layout.addLayout(header_row)
    else:
        layout.addWidget(header)
    for row in row_layouts:
        layout.addLayout(row)
    layout.addStretch()  # a card shorter than its neighbour keeps its content at the top instead of spreading it
    card = QWidget()
    card.setObjectName("sectionCard")
    card.setLayout(layout)
    card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)  # pinned to its size hint: it must not grow with the page
    return card


def build_editor_card(scope, title, *row_layouts, header_widgets=(), collapsible=True, key=None):
    """`build_section_card` for the editor pages: collapsible, remembered under "<scope>/<key or title>". A title must be unique within its scope
    (pass `key` when two cards share one); `collapsible=False` for a card that must always be open."""
    return build_section_card(title, *row_layouts, header_widgets=header_widgets, collapse_key=f"{scope}/{key or title}" if collapsible else None)


def set_enabled_without_scrolling(widget, enabled):
    """`widget.setEnabled(enabled)`, but a focused widget gives its focus up BEFORE it is disabled.

    A disabled widget hands its focus to the next one in the tab order, and a QScrollArea scrolls to reveal whichever widget receives it: a
    button that disables ITSELF when clicked (Run Hardware Test while it runs) threw its page 100-200 px down."""
    if not enabled and widget.hasFocus():
        widget.clearFocus()
    widget.setEnabled(enabled)


def build_scroll_area(page):
    """Wrap a whole page in a scroll area: past the minimum size it scrolls instead of forcing its window to grow."""
    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll_area.setWidget(page)
    return scroll_area


#: a card column never gets narrower than this (a row of 4 knobs plus the card's padding)
COLUMN_MIN_WIDTH = 346


def build_two_column_page(cards, weights):
    """A scrolling page with `cards` (widgets) in two columns, each card going to the shorter column (by `weights`, one rough height per card) so the page stays balanced.

    The columns are EXACTLY half the page's width each: their size hints are ignored, so collapsing a card can never shift the split, and the vertical scroll bar is ALWAYS shown
    (a bar that appears and disappears as cards collapse changes the width the columns share, and the whole page shifts sideways)."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(10, 10, 14, 10)  # room between the cards and the tab pane's frame
    layout.setSpacing(6)
    columns, column_layouts = [QWidget(), QWidget()], []
    for column in columns:
        column.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        column.setMinimumWidth(COLUMN_MIN_WIDTH)
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(6)
        column_layouts.append(column_layout)
    heights = [0, 0]
    for card, weight in zip(cards, weights):
        side = 0 if heights[0] <= heights[1] else 1
        column_layouts[side].addWidget(card)
        heights[side] += weight
    row = QHBoxLayout()
    row.setSpacing(6)
    for column, column_layout in zip(columns, column_layouts):
        column_layout.addStretch()
        row.addWidget(column, 1)  # equal stretch + ignored hints = exactly half each
    layout.addLayout(row)
    layout.addStretch()
    area = build_scroll_area(page)
    area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
    return area


def item_heading(where, name, edited):
    """The line over an open patch or performance: 'Temporary patch · St.Concert', 'USER:005 · My Lead  ● edited'."""
    where = where.removeprefix("the ")
    return f"{where[:1].upper()}{where[1:]} · {name}" + ("  ● edited" if edited else "")


def set_style_property(widget, name, value):
    """Set a dynamic property a stylesheet rule keys on (`QPushButton[primary="true"]`) and restyle the widget, only when it changed."""
    if widget.property(name) != value:
        widget.setProperty(name, value)
        widget.style().unpolish(widget)
        widget.style().polish(widget)


def set_primary(button, on):
    """The accent colour for the one button that is the likely next step (Write to USER while there are unsent edits)."""
    set_style_property(button, "primary", "true" if on else "false")
