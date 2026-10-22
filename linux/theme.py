"""The look of the app: colours, the stylesheet, and the few small pictures it needs (check mark, arrows)."""
from string import Template

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPalette, QPen, QPolygonF
from PySide6.QtWidgets import QStyleFactory

# One place for every colour. They follow the app icon's electric blue.
T = {
    "bg": "#13151a", "surface": "#1a1d24", "surface2": "#222630", "surface3": "#2b303c",
    "border": "#2a2f3a", "border2": "#3a4150",
    "text": "#e7eaf0", "muted": "#8d96a7",
    "accent": "#2f8cff", "accent_hover": "#4c9eff", "accent_press": "#2477dc", "accent_dim": "#1d3a63",
    "success": "#35c27a", "warn": "#f0a73a", "danger": "#ef5b5b", "danger_dim": "#3d2227", "danger_hover": "#52292f",
}

QSS = Template("""
* { outline: 0; }
QMainWindow, QDialog, QMessageBox { background: $bg; }
QWidget { color: $text; font-size: 13px; }
QLabel { background: transparent; }
QToolTip { background: $surface3; color: $text; border: 1px solid $border2; padding: 6px 8px; border-radius: 6px; }

/* tabs */
QTabWidget::pane { border: none; border-top: 1px solid $border; background: $bg; top: -1px; }
QTabBar { background: transparent; qproperty-drawBase: 0; }
QTabBar::tab { background: transparent; color: $muted; padding: 10px 16px; margin-right: 2px; border: none; border-bottom: 2px solid transparent; font-weight: 600; }
QTabBar::tab:hover { color: $text; background: $surface; }
QTabBar::tab:selected { color: $text; border-bottom: 2px solid $accent; }
QTabBar::tab:disabled { color: $border2; }
QTabWidget[sub="true"] > QTabBar::tab { padding: 7px 13px; font-weight: 500; }

/* buttons */
QPushButton { background: $surface2; color: $text; border: 1px solid $border; border-radius: 8px; padding: 7px 14px; }
QPushButton:hover { background: $surface3; border-color: $border2; }
QPushButton:pressed { background: $surface; }
QPushButton:disabled { color: #5b6272; background: $surface; border-color: $border; }
QPushButton[primary="true"] { background: $accent; border: 1px solid $accent; color: white; font-weight: 600; }
QPushButton[primary="true"]:hover { background: $accent_hover; border-color: $accent_hover; }
QPushButton[primary="true"]:pressed { background: $accent_press; }
QPushButton[primary="true"]:disabled { background: $accent_dim; border-color: $accent_dim; color: #7f95b8; }
QPushButton[danger="true"] { color: $danger; border-color: #5a2d33; background: $danger_dim; }
QPushButton[danger="true"]:hover { background: $danger_hover; border-color: $danger; }
QPushButton[danger="true"]:disabled { color: #6b4146; background: $surface; border-color: $border; }

/* inputs */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDateEdit, QComboBox { background: $surface; color: $text; border: 1px solid $border; border-radius: 8px; padding: 6px 9px;
    selection-background-color: $accent_dim; selection-color: white; }
QLineEdit:hover, QSpinBox:hover, QDateEdit:hover, QComboBox:hover { border-color: $border2; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDateEdit:focus, QComboBox:focus { border: 1px solid $accent; }
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled { color: #5b6272; }
QSpinBox, QDateEdit { padding-right: 24px; }
QSpinBox::up-button, QDateEdit::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 22px; border: none; border-top-right-radius: 8px; background: transparent; }
QSpinBox::down-button, QDateEdit::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 22px; border: none; border-bottom-right-radius: 8px; background: transparent; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover, QDateEdit::up-button:hover, QDateEdit::down-button:hover { background: $surface3; }
QSpinBox::up-arrow, QDateEdit::up-arrow { image: url($arrow_up); width: 10px; height: 10px; }
QSpinBox::down-arrow, QDateEdit::down-arrow { image: url($arrow_down); width: 10px; height: 10px; }
QComboBox { padding-right: 26px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: center right; width: 24px; border: none; }
QComboBox::down-arrow { image: url($arrow_down); width: 10px; height: 10px; }
QComboBox QAbstractItemView { background: $surface; border: 1px solid $border2; selection-background-color: $accent_dim; selection-color: white; padding: 4px; outline: 0; }
QCalendarWidget QWidget { background: $surface; }
QCalendarWidget QAbstractItemView:enabled { selection-background-color: $accent; selection-color: white; color: $text; }

/* check boxes */
QCheckBox { spacing: 8px; background: transparent; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 5px; background: $surface; border: 1px solid $border2; }
QCheckBox::indicator:hover { border-color: $accent; }
QCheckBox::indicator:checked { background: $accent; border: 1px solid $accent; image: url($check); }
QCheckBox::indicator:disabled { background: $surface; border-color: $border; }

/* lists and tables */
QTableWidget, QListWidget { background: $surface; alternate-background-color: #1e222a; border: 1px solid $border; border-radius: 10px; gridline-color: transparent;
    selection-background-color: $accent_dim; selection-color: white; }
QTableWidget::item { padding: 4px 8px; border: none; }
QTableWidget::item:selected, QListWidget::item:selected { background: $accent_dim; color: white; }
QTableWidget::item:hover { background: #20242d; }
QListWidget::item { padding: 6px 8px; }
QHeaderView { background: transparent; }
QHeaderView::section { background: $surface; color: $muted; padding: 8px 10px; border: none; border-bottom: 1px solid $border; font-weight: 600; }
QHeaderView::section:hover { color: $text; background: $surface2; }
QTableCornerButton::section { background: $surface; border: none; }

/* scroll bars */
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: $surface3; border-radius: 4px; min-height: 28px; margin: 0 2px; }
QScrollBar::handle:vertical:hover { background: $border2; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal { background: $surface3; border-radius: 4px; min-width: 28px; margin: 2px 0; }
QScrollBar::handle:horizontal:hover { background: $border2; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QScrollArea { background: transparent; border: none; }
QScrollArea[holder="true"] > QWidget > QWidget { background: $bg; }
QScrollArea > QWidget > QWidget { background: transparent; }

/* cards */
QGroupBox { background: $surface; border: 1px solid $border; border-radius: 12px; margin-top: 0; padding: 36px 14px 12px 14px; }
QGroupBox::title { subcontrol-origin: padding; subcontrol-position: top left; left: 16px; top: 11px; padding: 0; color: $text; font-weight: 700; font-size: 14px; }
QFrame[card="true"] { background: $surface; border: 1px solid $border; border-radius: 12px; }
QFrame[tile="true"] { background: $surface2; border: 1px solid $border; border-radius: 10px; }
QFrame[card="true"] QLabel, QFrame[tile="true"] QLabel { border: none; }
QLabel[role="hint"] { color: $muted; }
QLabel[role="title"] { font-size: 18px; font-weight: 700; }
QLabel[role="tile-value"] { font-size: 19px; font-weight: 700; }
QLabel[role="tile-caption"] { color: $muted; font-size: 11px; }
QLabel[role="warn"] { color: $warn; }
QLabel[role="notice"] { background: #33280f; border: 1px solid #6b5120; border-radius: 10px; padding: 10px; }

/* navigation: side bar, page header, search */
QFrame[sidebar="true"] { background: #0f1115; border: none; border-right: 1px solid $border; }
QFrame[sidebar="true"] QLabel { background: transparent; }
QLabel[role="brand"] { font-size: 15px; font-weight: 800; color: $text; padding: 2px 6px; }
QLabel[role="group"] { color: $muted; font-size: 10px; font-weight: 700; padding: 2px 8px; }
QWidget[header="true"] { background: $bg; }
QDialog[palette="true"] { background: $surface; border: 1px solid $border2; border-radius: 12px; }
QListWidget[palette_list="true"] { border: none; background: transparent; }
QListWidget[palette_list="true"]::item { padding: 8px 10px; border-radius: 7px; }

/* progress, splitters, menus, status bar */
QProgressBar { background: $surface2; border: 1px solid $border; border-radius: 8px; text-align: center; min-height: 18px; color: $text; }
QProgressBar::chunk { background: $accent; border-radius: 7px; }
QSplitter::handle { background: transparent; }
QSplitter::handle:vertical { height: 8px; }
QSplitter::handle:horizontal { width: 8px; }
QMenu { background: $surface; border: 1px solid $border2; border-radius: 8px; padding: 5px; }
QMenu::item { padding: 6px 22px 6px 14px; border-radius: 5px; }
QMenu::item:selected { background: $accent_dim; color: white; }
QMenu::separator { height: 1px; background: $border; margin: 5px 8px; }
QStatusBar { background: #0f1115; color: $muted; border-top: 1px solid $border; }
QStatusBar::item { border: none; }
""")


def palette():
    p = QPalette()
    c = lambda k: QColor(T[k])
    for role, key in ((QPalette.ColorRole.Window, "bg"), (QPalette.ColorRole.WindowText, "text"), (QPalette.ColorRole.Base, "surface"),
                      (QPalette.ColorRole.AlternateBase, "surface2"), (QPalette.ColorRole.Text, "text"), (QPalette.ColorRole.Button, "surface2"),
                      (QPalette.ColorRole.ButtonText, "text"), (QPalette.ColorRole.ToolTipBase, "surface3"), (QPalette.ColorRole.ToolTipText, "text"),
                      (QPalette.ColorRole.Highlight, "accent"), (QPalette.ColorRole.Link, "accent_hover"), (QPalette.ColorRole.PlaceholderText, "muted")):
        p.setColor(role, c(key))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor("#5b6272"))
    return p


def ensure_assets(folder):
    """Draw the little pictures the stylesheet points at (check mark, arrows) once. Returns {name: path}."""
    folder.mkdir(parents=True, exist_ok=True)

    def make(name, draw, size=16):
        path = folder / f"{name}.png"
        img = QImage(size, size, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw(p, size)
        p.end()
        img.save(str(path))
        return str(path)

    def check(p, s):
        p.setPen(QPen(QColor("white"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPolyline(QPolygonF([QPointF(s * .24, s * .54), QPointF(s * .44, s * .72), QPointF(s * .78, s * .30)]))

    def chevron(up):
        def draw(p, s):
            p.setPen(QPen(QColor(T["muted"]), 1.9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            y1, y2 = (s * .62, s * .36) if up else (s * .38, s * .64)
            p.drawPolyline(QPolygonF([QPointF(s * .27, y1), QPointF(s * .5, y2), QPointF(s * .73, y1)]))
        return draw
    return {"check": make("check", check), "arrow_up": make("arrow_up", chevron(True)), "arrow_down": make("arrow_down", chevron(False))}


def stylesheet(assets):
    return QSS.substitute(**T, **{k: v.replace("\\", "/") for k, v in assets.items()})


def apply(app, folder):
    """Dress the application: a steady base style (so the stylesheet looks the same everywhere), the palette and the stylesheet."""
    if "Fusion" in QStyleFactory.keys():
        app.setStyle("Fusion")
    app.setPalette(palette())
    app.setStyleSheet(stylesheet(ensure_assets(folder)))
