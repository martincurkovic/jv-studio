from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from jv_studio.ui.ascii_logo import LOGO, logo_font

from jv_studio.ui._version import APP_VERSION


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About JV Studio")
        logo = QLabel(LOGO.strip("\n"))
        logo.setTextFormat(Qt.TextFormat.PlainText)
        logo.setFont(logo_font())  # left-aligned inside the label: a centred QLabel centres every LINE on its own, and the art's lines differ in length
        title = QLabel(f"Version {APP_VERSION}")
        title.setObjectName("mutedLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body = QLabel(
            "A free, open-source editor and librarian for the Roland JV-1010.<br>"
            "Licensed under the GNU General Public License, version 3 or later.<br><br>"
            "The parameter table is generated from Roland's JV-1010 Owner's Manual.<br>"
            "Roland and JV-1010 are trademarks of Roland Corporation. This project is not affiliated with Roland."
        )
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setWordWrap(True)
        credits = QLabel(
            "Wave names: the waveform lists on "
            '<a href="https://gumielectronic.net/?p=2312">GumiElectronic</a>.<br>'
            'The knob and envelope widgets are adapted from <a href="https://github.com/martincurkovic/AKAISDS">AKAISDS</a>.<br>'
            'Protocol details were cross-checked against Lars Ahlzen\'s <a href="https://github.com/Ahlzen/jv1010tool">jv1010tool</a> (MIT).'
        )
        credits.setAlignment(Qt.AlignmentFlag.AlignCenter)
        credits.setWordWrap(True)
        credits.setTextFormat(Qt.TextFormat.RichText)
        credits.setOpenExternalLinks(True)
        credits.setObjectName("mutedLabel")
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addSpacing(12)
        layout.addWidget(logo, alignment=Qt.AlignmentFlag.AlignHCenter)  # the label is centred, not its lines
        layout.addWidget(title)
        layout.addWidget(body)
        layout.addWidget(credits)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(max(420, logo.sizeHint().width() + 48))  # wide enough for the logo in whatever fixed font the machine has
