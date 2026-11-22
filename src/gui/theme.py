"""Dark astronomy-friendly theme for MountMonitor.

Uses dark backgrounds with muted colors to preserve night vision.
Red-shifted color palette typical of astronomy software.
"""

from PyQt6.QtGui import QPalette, QColor, QFont
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt


# Color palette
class Colors:
    """Color constants for the application."""
    # Backgrounds
    BG_DARK = QColor(20, 20, 25)         # Main background
    BG_MEDIUM = QColor(30, 30, 38)       # Panel background
    BG_LIGHT = QColor(45, 45, 55)        # Widget background
    BG_GRAPH = QColor(15, 15, 20)        # Graph background

    # Text
    TEXT_PRIMARY = QColor(200, 200, 210)   # Main text
    TEXT_SECONDARY = QColor(140, 140, 155) # Secondary text
    TEXT_MUTED = QColor(80, 80, 95)        # Muted/watermark text
    TEXT_HIGHLIGHT = QColor(255, 255, 255)  # Highlighted text

    # Accents
    ACCENT_BLUE = QColor(80, 130, 200)     # Primary accent
    ACCENT_RED = QColor(200, 80, 80)       # Error/warning
    ACCENT_GREEN = QColor(80, 180, 80)     # Success/tolerance

    # Graph data colors (matching original MountMonitor)
    GRAPH_RA = QColor(200, 100, 200)       # Magenta for RA
    GRAPH_DEC = QColor(200, 80, 80)        # Red for DEC
    GRAPH_SEISMIC = QColor(220, 220, 230)  # Bright for seismic (Java: black on white bg)
    GRAPH_STDEV = QColor(80, 130, 220)     # Blue for STDEV
    GRAPH_TOLERANCE = QColor(80, 180, 80)  # Green for tolerance
    GRAPH_MINMAX = QColor(200, 100, 200)   # Dashed lines
    GRAPH_TIME_FIX = QColor(100, 100, 110) # Gray for time fixes
    GRAPH_TIME_PC = QColor(80, 180, 80)    # Green for PC loop time
    GRAPH_TIME_MOUNT = QColor(200, 80, 80) # Red for mount loop time
    GRAPH_TIME_DIFF = QColor(230, 230, 235) # Bright white for PC-mount diff (Java: black on white bg)
    GRAPH_NTP = QColor(80, 130, 220)       # Blue for NTP
    GRAPH_SPEED_RAW = QColor(120, 120, 130) # Gray for raw speed
    GRAPH_SPEED_AVG = QColor(200, 200, 200) # White for averaged speed
    GRAPH_SPEED_REG = QColor(255, 255, 255) # Bright white for regression

    # Status colors
    STATUS_OK = QColor(80, 180, 80)
    STATUS_WARNING = QColor(220, 180, 50)
    STATUS_ERROR = QColor(200, 80, 80)
    STATUS_INACTIVE = QColor(100, 100, 110)

    # Borders
    BORDER = QColor(60, 60, 75)
    BORDER_FOCUS = QColor(80, 130, 200)


#: the colours of the frozen palette, by role (interface_kit.REPLIS)
COLOURS = {
    "fenetre": Colors.BG_DARK.name(), "texte": Colors.TEXT_PRIMARY.name(),
    "base": Colors.BG_LIGHT.name(), "base_alt": Colors.BG_MEDIUM.name(),
    "bouton": Colors.BG_LIGHT.name(), "texte_bouton": Colors.TEXT_PRIMARY.name(),
    "selection": Colors.ACCENT_BLUE.name(), "texte_selection": Colors.TEXT_HIGHLIGHT.name(),
    "lien": Colors.ACCENT_BLUE.name(), "infobulle": Colors.BG_MEDIUM.name(),
    "texte_infobulle": Colors.TEXT_PRIMARY.name(), "desactive": Colors.TEXT_MUTED.name(),
    "clair": Colors.BG_LIGHT.name(), "moyen": Colors.BG_MEDIUM.name(), "sombre": "#000000",
}


_CHECK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
    '<path d="M3.5 8.5l3 3 6-7" fill="none" stroke="#ffffff" stroke-width="2.2" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>')


_ARROW_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="9" height="9" viewBox="0 0 9 9">'
    '<path d="{d}" fill="#c8c8d2"/></svg>')


def _style_sheet() -> str:
    """The style sheet with its small images: a tick in checked boxes (a
    plain blue square was hard to tell from an empty one) and real arrows
    on the spin boxes (tiny dots on a 4K screen at 200 %)."""
    images = {"%CHECK%": ("mountmonitor_check.svg", _CHECK_SVG),
              "%UP%": ("mountmonitor_up.svg", _ARROW_SVG.format(d="M0.5 7 L4.5 2 L8.5 7 Z")),
              "%DOWN%": ("mountmonitor_down.svg", _ARROW_SVG.format(d="M0.5 2 L4.5 7 L8.5 2 Z"))}
    sheet = STYLESHEET
    try:
        import tempfile
        from pathlib import Path
        for key, (name, svg) in images.items():
            path = Path(tempfile.gettempdir()) / name
            if not path.exists() or path.read_text(encoding="utf-8") != svg:
                path.write_text(svg, encoding="utf-8")
            sheet = sheet.replace(key, path.as_posix())
        return sheet
    except Exception:
        import re
        return re.sub(r"\n\s*image: url\(%[A-Z]+%\);[^\n]*", "", sheet)


def apply_dark_theme(app: QApplication):
    """Apply the dark astronomy theme to the application."""
    palette = QPalette()

    palette.setColor(QPalette.ColorRole.Window, Colors.BG_DARK)
    palette.setColor(QPalette.ColorRole.WindowText, Colors.TEXT_PRIMARY)
    palette.setColor(QPalette.ColorRole.Base, Colors.BG_LIGHT)
    palette.setColor(QPalette.ColorRole.AlternateBase, Colors.BG_MEDIUM)
    palette.setColor(QPalette.ColorRole.ToolTipBase, Colors.BG_MEDIUM)
    palette.setColor(QPalette.ColorRole.ToolTipText, Colors.TEXT_PRIMARY)
    palette.setColor(QPalette.ColorRole.Text, Colors.TEXT_PRIMARY)
    palette.setColor(QPalette.ColorRole.Button, Colors.BG_LIGHT)
    palette.setColor(QPalette.ColorRole.ButtonText, Colors.TEXT_PRIMARY)
    palette.setColor(QPalette.ColorRole.BrightText, Colors.TEXT_HIGHLIGHT)
    palette.setColor(QPalette.ColorRole.Link, Colors.ACCENT_BLUE)
    palette.setColor(QPalette.ColorRole.Highlight, Colors.ACCENT_BLUE)
    palette.setColor(QPalette.ColorRole.HighlightedText, Colors.TEXT_HIGHLIGHT)
    palette.setColor(QPalette.ColorRole.PlaceholderText, Colors.TEXT_SECONDARY)
    palette.setColor(QPalette.ColorRole.Light, Colors.BG_LIGHT)
    palette.setColor(QPalette.ColorRole.Midlight, Colors.BG_MEDIUM)
    palette.setColor(QPalette.ColorRole.Dark, Colors.BG_DARK)
    palette.setColor(QPalette.ColorRole.Mid, Colors.BG_MEDIUM)
    palette.setColor(QPalette.ColorRole.Shadow, QColor(0, 0, 0))

    # Disabled colors
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, Colors.TEXT_MUTED)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, Colors.TEXT_MUTED)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, Colors.TEXT_MUTED)

    # FROZEN appearance (shared kit, interface_kit): Fusion style, COMPLETE
    # palette in all three groups, embedded font and style sheet; neither
    # the system light/dark theme nor its fonts get a say.
    try:
        import interface_kit
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent.parent
        interface_kit.appliquer_style(app, COLOURS, polices=root / "polices",
                                      famille="Source Sans 3", taille=10, feuille=_style_sheet())
    except Exception:
        app.setStyle("Fusion")
        app.setPalette(palette)
        app.setStyleSheet(_style_sheet())


#: application style sheet (fine-tuning on top of the palette)
STYLESHEET = """
        QMainWindow {
            background-color: #14141a;
        }
        QMenuBar {
            background-color: #1e1e26;
            color: #c8c8d2;
            border-bottom: 1px solid #3c3c4b;
        }
        QMenuBar::item:selected {
            background-color: #5082c8;
        }
        QMenu {
            background-color: #1e1e26;
            color: #c8c8d2;
            border: 1px solid #3c3c4b;
        }
        QMenu::item:selected {
            background-color: #5082c8;
        }
        QStatusBar {
            background-color: #1e1e26;
            color: #8c8c9b;
            border-top: 1px solid #3c3c4b;
        }
        QToolBar {
            background-color: #1e1e26;
            border: none;
            spacing: 4px;
            padding: 2px;
        }
        QPushButton {
            background-color: #2d2d37;
            color: #c8c8d2;
            border: 1px solid #3c3c4b;
            border-radius: 4px;
            padding: 5px 12px;
            min-height: 20px;
        }
        QPushButton:hover {
            background-color: #3c3c4b;
            border-color: #5082c8;
        }
        QPushButton:pressed {
            background-color: #5082c8;
        }
        QPushButton:disabled {
            background-color: #1e1e26;
            color: #50505f;
        }
        QComboBox {
            background-color: #2d2d37;
            color: #c8c8d2;
            border: 1px solid #3c3c4b;
            border-radius: 4px;
            padding: 4px 8px;
        }
        QComboBox:hover {
            border-color: #5082c8;
        }
        QComboBox QAbstractItemView {
            background-color: #1e1e26;
            color: #c8c8d2;
            selection-background-color: #5082c8;
        }
        QLineEdit, QSpinBox, QDoubleSpinBox {
            background-color: #2d2d37;
            color: #c8c8d2;
            border: 1px solid #3c3c4b;
            border-radius: 4px;
            padding: 4px 8px;
        }
        QSpinBox, QDoubleSpinBox {
            padding-right: 20px;
        }
        QSpinBox::up-button, QDoubleSpinBox::up-button {
            subcontrol-origin: border; subcontrol-position: top right;
            width: 18px; border-left: 1px solid #3c3c4b;
        }
        QSpinBox::down-button, QDoubleSpinBox::down-button {
            subcontrol-origin: border; subcontrol-position: bottom right;
            width: 18px; border-left: 1px solid #3c3c4b;
        }
        QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
        QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
            background-color: #3c3c4b;
        }
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
            image: url(%UP%); width: 9px; height: 9px;
        }
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
            image: url(%DOWN%); width: 9px; height: 9px;
        }
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
            border-color: #5082c8;
        }
        /* A disabled field must LOOK disabled: without these rules the
           colours above won over the palette and a greyed-out field looked
           editable until one clicked in it. */
        QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
        QComboBox:disabled {
            background-color: #1a1a20;
            color: #50505f;
            border-color: #26262f;
        }
        QLabel:disabled, QCheckBox:disabled, QRadioButton:disabled {
            color: #50505f;
        }
        QGroupBox {
            color: #c8c8d2;
            border: 1px solid #3c3c4b;
            border-radius: 6px;
            margin-top: 12px;
            padding-top: 14px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 6px;
        }
        QTabWidget::pane {
            border: 1px solid #3c3c4b;
            background-color: #1e1e26;
        }
        QTabBar::tab {
            background-color: #2d2d37;
            color: #8c8c9b;
            border: 1px solid #3c3c4b;
            padding: 6px 16px;
            margin-right: 2px;
        }
        QTabBar::tab:selected {
            background-color: #1e1e26;
            color: #c8c8d2;
            border-bottom-color: #1e1e26;
        }
        QTextEdit, QPlainTextEdit {
            background-color: #14141a;
            color: #c8c8d2;
            border: 1px solid #3c3c4b;
            font-family: 'Source Code Pro';
            font-size: 11px;
        }
        QScrollBar:vertical {
            background: #14141a;
            width: 10px;
            margin: 0;
        }
        QScrollBar::handle:vertical {
            background: #3c3c4b;
            border-radius: 5px;
            min-height: 20px;
        }
        QScrollBar::handle:vertical:hover {
            background: #5082c8;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0;
        }
        QCheckBox {
            color: #c8c8d2;
            spacing: 6px;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 1px solid #3c3c4b;
            border-radius: 3px;
            background-color: #2d2d37;
        }
        QCheckBox::indicator:checked {
            background-color: #5082c8;
            border-color: #5082c8;
            image: url(%CHECK%);
        }
        QLabel {
            color: #c8c8d2;
        }
        QSplitter::handle {
            background-color: #3c3c4b;
        }
        QSplitter::handle:hover {
            background-color: #5082c8;
        }
        QToolTip {
            background-color: #2d2d37;
            color: #c8c8d2;
            border: 1px solid #5082c8;
            padding: 4px;
        }
        QDialog {
            background-color: #14141a;
        }
"""

