"""
Holds the app's ASCII logo as a single raw string constant.

Sourced directly from the owner's appheader.txt (since removed from the repo),
byte-for-byte: do not hand-edit the block art below; if it ever needs to change,
replace it with the new art the same way.
"""

LOGO = r"""
     ██╗██╗   ██╗    ███████╗████████╗██╗   ██╗██████╗ ██╗ ██████╗ 
     ██║██║   ██║    ██╔════╝╚══██╔══╝██║   ██║██╔══██╗██║██╔═══██╗
     ██║██║   ██║    ███████╗   ██║   ██║   ██║██║  ██║██║██║   ██║
██   ██║╚██╗ ██╔╝    ╚════██║   ██║   ██║   ██║██║  ██║██║██║   ██║
╚█████╔╝ ╚████╔╝     ███████║   ██║   ╚██████╔╝██████╔╝██║╚██████╔╝
 ╚════╝   ╚═══╝      ╚══════╝   ╚═╝    ╚═════╝ ╚═════╝ ╚═╝ ╚═════╝ 
                                                                   
"""


def logo_font():
    """The font the logo is drawn in, everywhere (the main window and About). Menlo is what the art was designed in; a different fixed font changes its line spacing
    and the art looks squashed or stretched (the About window once used the system fixed font and looked different from the main window)."""
    from PySide6.QtGui import QFont

    font = QFont("Menlo")
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(8)
    return font
