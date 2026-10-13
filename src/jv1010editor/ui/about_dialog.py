from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from jv1010editor.ui._version import APP_VERSION


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About JV-1010 Editor")
        title = QLabel(f"<h2>JV-1010 Editor</h2>Version {APP_VERSION}")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body = QLabel(
            "A free, open-source patch editor for the Roland JV-1010.<br>"
            "Licensed under the GNU General Public License, version 3 or later.<br><br>"
            "The parameter table is generated from Roland's JV-1010 Owner's Manual.<br>"
            "Roland and JV-1010 are trademarks of Roland Corporation. This project is not affiliated with Roland."
        )
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setWordWrap(True)
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(body)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(420)
