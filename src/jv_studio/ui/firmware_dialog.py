"""Hardware > Update Firmware...: choose the folder of Roland's System Update files, see what was checked, tick the boxes, start.

UNVERIFIED ON A UNIT (core/firmware.py): the dialog says so in plain words, and Start stays disabled until the files pass every check and every box is ticked.
The dialog only chooses and confirms; `UnitWorker` plays the files.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from jv_studio.core import firmware

STEPS = (
    "Put the unit in update mode (Roland's README): power it off and connect your interface's MIDI OUT to the JV-1010's MIDI IN. Turn the PART dial to 14 and the CATEGORY dial to "
    "Guitar/Bass. Switch on while holding VOLUME and VALUE; after 3 seconds release both and press VOLUME. The display reads \"nid.\" Then start here, and leave the unit alone.\n"
    "When it is done: switch the unit off and on, then do a Factory Reset (it erases all user data, so restore your backup afterwards)."
)

CHECKS = (
    "I made a backup of the unit (File > Back Up Unit...) and kept the file. It can't be done once the unit is in update mode.",
    "The unit shows \"nid.\" and nothing else is on its MIDI IN: no DAW, no MIDI monitor, no loop.",
    f"My MIDI interface passes SysEx messages of {firmware.MAX_MESSAGE_BYTES} bytes. Some stop at 256 and would corrupt the update (the loopback test in Settings checks 265 data bytes).",
    "I understand this has never been tried on a real JV-1010 and I use it at my own risk.",
)

ICON = {"error": "Error", "warning": "Warning", "info": "OK"}


def duration_text(seconds):
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes} min {secs:02d} s"


class FirmwareDialog(QDialog):
    def __init__(self, parent=None, folder=None):
        super().__init__(parent)
        self.setWindowTitle("Update Firmware (unverified)")
        self.setMinimumWidth(640)
        self._set = None
        layout = QVBoxLayout(self)
        warning = QLabel(firmware.WARNING_TEXT)
        warning.setWordWrap(True)
        warning.setObjectName("warningLabel")
        layout.addWidget(warning)

        row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        self.folder_edit.setPlaceholderText("The folder with Roland's .mid files (_0000001.mid ...)")
        self.choose_button = QPushButton("Choose Folder...")
        self.choose_button.clicked.connect(self._choose)
        row.addWidget(self.folder_edit, 1)
        row.addWidget(self.choose_button)
        layout.addLayout(row)

        self.summary = QLabel("Choose the folder to check the files.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.findings = QListWidget()
        self.findings.setMaximumHeight(120)
        self.findings.setVisible(False)
        layout.addWidget(self.findings)

        steps = QLabel(STEPS)
        steps.setWordWrap(True)
        steps.setObjectName("mutedLabel")
        layout.addWidget(steps)

        self.checks = []
        for text in CHECKS:
            box = QCheckBox(text)
            box.toggled.connect(self._update_ok)
            self.checks.append(box)
            layout.addWidget(box)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.start_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.start_button.setText("Start Update")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._update_ok()
        if folder:
            self.load_folder(folder)

    def _choose(self):
        start = self.folder_edit.text() or str(Path.home() / "Downloads")
        chosen = QFileDialog.getExistingDirectory(self, "Roland's System Update files", start)
        if chosen:
            self.load_folder(chosen)

    def load_folder(self, folder):
        """Read and check the files (about a second) and show what was found."""
        self.folder_edit.setText(str(folder))
        self._set = firmware.load(folder)
        found = self._set
        self.findings.clear()
        for finding in found.findings:
            item = QListWidgetItem(f"{ICON[finding.level]}: {finding}")
            item.setToolTip(str(finding))
            self.findings.addItem(item)
        self.findings.setVisible(bool(found.findings))
        if found.ok:
            self.summary.setText(
                f"{len(found.blocks)} files, {found.total_frames:,} messages, about {duration_text(found.duration)} to play. "
                + ("Checked against Roland's release." if found.release else "Not a release this app knows: see the warning.")
            )
        else:
            self.summary.setText("These files can't be played: see the errors below.")
        self._update_ok()

    def _update_ok(self, *_):
        ready = self._set is not None and self._set.ok and all(box.isChecked() for box in self.checks)
        self.start_button.setEnabled(ready)

    def firmware(self):
        return self._set
