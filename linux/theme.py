"""The look of the app: colours (a dark and a light theme, five accent colours), text size, the stylesheet, and the few small pictures it needs."""
from string import Template

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPalette, QPen, QPolygonF
from PySide6.QtWidgets import QStyleFactory

MODES = ("dark", "light", "system")

# Every colour the app uses has a name here, in both themes; nothing else in the app should spell a colour out.
DARK = {
    "bg": "#12141a", "surface": "#1a1d25", "surface2": "#222631", "surface3": "#2c313e",
    "border": "#2a2f3b", "border2": "#3b4252",
    "text": "#e8ebf1", "muted": "#98a1b2", "faint": "#6b7487",
    "success": "#3fcf86", "warn": "#f0b040", "danger": "#f26b6b", "info": "#62b4ff",
    "danger_dim": "#3d2227", "danger_hover": "#52292f", "danger_border": "#5a2d33",
    "zebra": "#1e222b", "hover": "#252a35", "sidebar": "#0e1015",
    "notice_bg": "#33280f", "notice_border": "#6b5120", "on_dim": "#ffffff",
    "orange": "#ef8a5b", "violet": "#b59bff", "badge": "#cf2a37",
}
LIGHT = {
    "bg": "#f3f5f9", "surface": "#ffffff", "surface2": "#eef1f6", "surface3": "#e1e6ee",
    "border": "#dbe0e9", "border2": "#c3cbd8",
    "text": "#171b24", "muted": "#566073", "faint": "#8d97a8",
    "success": "#157a45", "warn": "#91560a", "danger": "#c42b2b", "info": "#1a62c4",
    "danger_dim": "#fbe4e4", "danger_hover": "#f6cfcf", "danger_border": "#e8b4b4",
    "zebra": "#f7f9fc", "hover": "#eaeff6", "sidebar": "#e9edf4",
    "notice_bg": "#fff3d6", "notice_border": "#e3c27a", "on_dim": "#171b24",
    "orange": "#a8480f", "violet": "#6b3fd1", "badge": "#cf2a37",
}
# name -> (fill in the dark theme, fill in the light theme). White text on a fill is always at least 4.5 : 1.
ACCENTS = {
    "blue": ("#266fd8", "#1a64e0"), "green": ("#18814a", "#12834a"), "purple": ("#7650e6", "#6a4be0"),
    "orange": ("#b55808", "#b85a00"), "pink": ("#cb3779", "#c4287a"),
}
DEFAULT_ACCENT = "blue"
SIZES = (90, 100, 110, 125)            # text size, in percent of the normal size
FONT_BASE = 13                         # pixels, at 100 %

# The colours in use right now. It is one dict that is changed in place, so `from theme import T` keeps working when the theme is switched.
T = {}
STATE = {"mode": "dark", "dark": True, "accent": DEFAULT_ACCENT, "size": 100}


def mix(a, b, t):
    """The colour t of the way from a to b (hex strings)."""
    a, b = QColor(a), QColor(b)
    return QColor.fromRgbF(a.redF() * (1 - t) + b.redF() * t, a.greenF() * (1 - t) + b.greenF() * t, a.blueF() * (1 - t) + b.blueF() * t).name()


def luminance(colour):
    c = QColor(colour)
    f = lambda v: v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c.redF()) + 0.7152 * f(c.greenF()) + 0.0722 * f(c.blueF())


def contrast(a, b):
    """WCAG contrast ratio of two colours (1 to 21); text wants 4.5 or more."""
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def palette_for(dark, accent):
    """The full set of colours for a theme and an accent colour."""
    p = dict(DARK if dark else LIGHT)
    fill = ACCENTS.get(accent, ACCENTS[DEFAULT_ACCENT])[0 if dark else 1]
    p["accent"] = fill
    p["accent_hover"] = mix(fill, "#000000", 0.10)                           # (darker in both themes: white text keeps its contrast)
    p["accent_press"] = mix(fill, "#000000", 0.20)
    p["accent_dim"] = mix(fill, p["bg"], 0.72 if dark else 0.84)             # a selected row, the open page in the side bar
    p["accent_fg"] = mix(fill, "#ffffff", 0.38) if dark else mix(fill, "#000000", 0.10)           # the accent as a colour for icons and links on a surface
    p["on_accent"] = "#ffffff"
    p["accent_off"] = mix(fill, p["bg"], 0.55)                               # a primary button that cannot be pressed
    return p


def system_is_dark():
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
        return scheme != Qt.ColorScheme.Light
    except AttributeError:               # Qt older than 6.5 cannot tell: the app was dark before, so it stays dark
        return True


def choose(mode="dark", accent=DEFAULT_ACCENT, size=100):
    """Fill T with the colours for a mode ('dark', 'light' or 'system'), an accent colour and a text size. Returns True when anything changed."""
    mode = mode if mode in MODES else "dark"
    dark = system_is_dark() if mode == "system" else mode == "dark"
    accent = accent if accent in ACCENTS else DEFAULT_ACCENT
    size = size if size in SIZES else 100
    new = palette_for(dark, accent)
    changed = new != T or STATE["size"] != size
    T.clear()
    T.update(new)
    STATE.update(mode=mode, dark=dark, accent=accent, size=size)
    return changed


def font_px(delta=0):
    """A font size in pixels at the chosen text size; `delta` is the step from the normal size (title +5, caption -2)."""
    return max(9, round((FONT_BASE + delta) * STATE["size"] / 100))


class Live:
    """A dict of colour NAMES that hands out the colour currently in T, so a table of colours made at import time follows a theme switch."""

    def __init__(self, names):
        self.names = dict(names)

    def __getitem__(self, key):
        return T[self.names[key]]

    def get(self, key, default=None):
        return T[self.names[key]] if key in self.names else default

    def __contains__(self, key):
        return key in self.names

    def items(self):
        return [(k, T[v]) for k, v in self.names.items()]


QSS = Template("""
* { outline: 0; }
QMainWindow, QDialog, QMessageBox { background: $bg; }
QWidget { color: $text; font-size: ${f0}px; }
QLabel { background: transparent; }
QToolTip { background: $surface3; color: $text; border: 1px solid $border2; padding: 6px 8px; border-radius: 6px; }

/* tabs: the page tabs have an underline, the small ones inside a page are pills */
QTabWidget::pane { border: none; border-top: 1px solid $border; background: $bg; top: -1px; }
QTabBar { background: transparent; qproperty-drawBase: 0; }
QTabBar::tab { background: transparent; color: $muted; padding: 10px 16px; margin-right: 2px; border: none; border-bottom: 2px solid transparent; font-weight: 600; }
QTabBar::tab:hover { color: $text; background: $hover; }
QTabBar::tab:selected { color: $text; border-bottom: 2px solid $accent_fg; }
QTabBar::tab:disabled { color: $faint; }
QTabWidget[sub="true"] > QTabBar::tab { padding: 6px 14px; margin: 6px 4px 6px 0; border: 1px solid transparent; border-radius: 15px; font-weight: 500; }
QTabWidget[sub="true"] > QTabBar::tab:hover { background: $surface2; }
QTabWidget[sub="true"] > QTabBar::tab:selected { background: $accent_dim; color: $on_dim; border: 1px solid $accent; }

/* buttons */
QPushButton { background: $surface2; color: $text; border: 1px solid $border; border-radius: 9px; padding: 7px 15px; }
QPushButton:hover { background: $surface3; border-color: $border2; }
QPushButton:pressed { background: $surface; }
QPushButton:focus { border-color: $accent_fg; }
QPushButton:checked { background: $accent_dim; border-color: $accent; color: $on_dim; }
QPushButton:disabled { color: $faint; background: $surface; border-color: $border; }
QPushButton[primary="true"] { background: $accent; border: 1px solid $accent; color: $on_accent; font-weight: 600; }
QPushButton[primary="true"]:hover { background: $accent_hover; border-color: $accent_hover; }
QPushButton[primary="true"]:pressed { background: $accent_press; }
QPushButton[primary="true"]:disabled { background: $accent_off; border-color: $accent_off; color: $on_accent; }
QPushButton[danger="true"] { color: $danger; border-color: $danger_border; background: $danger_dim; }
QPushButton[danger="true"]:hover { background: $danger_hover; border-color: $danger; }
QPushButton[danger="true"]:disabled { color: $faint; background: $surface; border-color: $border; }
QPushButton[swatch="true"] { padding: 0; border-radius: 14px; border: 2px solid $border; min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; }
QPushButton[swatch="true"]:checked { border: 3px solid $text; }

/* inputs */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDateEdit, QComboBox { background: $surface; color: $text; border: 1px solid $border; border-radius: 9px; padding: 6px 10px;
    selection-background-color: $accent_dim; selection-color: $on_dim; }
QLineEdit:hover, QSpinBox:hover, QDateEdit:hover, QComboBox:hover { border-color: $border2; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDateEdit:focus, QComboBox:focus { border: 1px solid $accent_fg; }
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled { color: $faint; }
QSpinBox, QDateEdit { padding-right: 24px; }
QSpinBox::up-button, QDateEdit::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 22px; border: none; border-top-right-radius: 8px; background: transparent; }
QSpinBox::down-button, QDateEdit::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 22px; border: none; border-bottom-right-radius: 8px; background: transparent; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover, QDateEdit::up-button:hover, QDateEdit::down-button:hover { background: $surface3; }
QSpinBox::up-arrow, QDateEdit::up-arrow { image: url($arrow_up); width: 10px; height: 10px; }
QSpinBox::down-arrow, QDateEdit::down-arrow { image: url($arrow_down); width: 10px; height: 10px; }
QComboBox { padding-right: 26px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: center right; width: 24px; border: none; }
QComboBox::down-arrow { image: url($arrow_down); width: 10px; height: 10px; }
QComboBox QAbstractItemView { background: $surface; border: 1px solid $border2; selection-background-color: $accent_dim; selection-color: $on_dim; padding: 4px; outline: 0; }
QCalendarWidget QWidget { background: $surface; }
QCalendarWidget QAbstractItemView:enabled { selection-background-color: $accent; selection-color: $on_accent; color: $text; }

/* check boxes */
QCheckBox { spacing: 8px; background: transparent; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 5px; background: $surface; border: 1px solid $border2; }
QCheckBox::indicator:hover { border-color: $accent_fg; }
QCheckBox::indicator:checked { background: $accent; border: 1px solid $accent; image: url($check); }
QCheckBox::indicator:disabled { background: $surface; border-color: $border; }

/* lists and tables */
QTableWidget, QListWidget { background: $surface; alternate-background-color: $zebra; border: 1px solid $border; border-radius: 12px; gridline-color: transparent;
    selection-background-color: $accent_dim; selection-color: $on_dim; }
QTableWidget::item { padding: 5px 8px; border: none; }
QTableWidget::item:selected, QListWidget::item:selected { background: $accent_dim; color: $on_dim; }
QTableWidget::item:hover { background: $hover; }
QListWidget::item { padding: 7px 9px; }
QHeaderView { background: transparent; }
QHeaderView::section { background: $surface; color: $muted; padding: 9px 10px; border: none; border-bottom: 1px solid $border; font-weight: 600; }
QHeaderView::section:hover { color: $text; background: $surface2; }
QTableCornerButton::section { background: $surface; border: none; }

/* scroll bars */
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: $border2; border-radius: 4px; min-height: 28px; margin: 0 2px; }
QScrollBar::handle:vertical:hover { background: $faint; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal { background: $border2; border-radius: 4px; min-width: 28px; margin: 2px 0; }
QScrollBar::handle:horizontal:hover { background: $faint; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QScrollArea { background: transparent; border: none; }
QScrollArea[holder="true"] > QWidget > QWidget { background: $bg; }
QScrollArea > QWidget > QWidget { background: transparent; }

/* cards */
QGroupBox { background: $surface; border: 1px solid $border; border-radius: 14px; margin-top: 0; padding: 38px 16px 14px 16px; }
QGroupBox::title { subcontrol-origin: padding; subcontrol-position: top left; left: 18px; top: 12px; padding: 0; color: $text; font-weight: 700; font-size: ${f1}px; }
QFrame[card="true"] { background: $surface; border: 1px solid $border; border-radius: 14px; }
QFrame[tile="true"] { background: $surface2; border: 1px solid $border; border-radius: 11px; }
QFrame[hero="true"] { background: $surface; border: 1px solid $border; border-radius: 16px; }
QFrame[card="true"] QLabel, QFrame[tile="true"] QLabel, QFrame[hero="true"] QLabel { border: none; }
QLabel[role="hint"] { color: $muted; }
QLabel[role="title"] { font-size: ${f5}px; font-weight: 700; }
QLabel[role="display"] { font-size: ${f9}px; font-weight: 800; }
QLabel[role="tile-value"] { font-size: ${f6}px; font-weight: 700; }
QLabel[role="tile-caption"] { color: $muted; font-size: ${fm2}px; }
QLabel[role="warn"] { color: $warn; }
QLabel[role="card-title"] { font-weight: 700; font-size: ${f1}px; }
QLabel[role="unread-dot"] { color: $badge; }
QLabel[role="level"] { font-weight: 700; padding: 2px 9px; border-radius: 9px; }
QLabel[level="important"] { color: $on_dim; background: $accent_dim; border: 1px solid $accent; }
QLabel[level="warning"] { color: $warn; background: $notice_bg; border: 1px solid $notice_border; }
QFrame[card="true"][unread="true"] { border-left: 4px solid $badge; }
QLabel[role="notice"] { background: $notice_bg; border: 1px solid $notice_border; border-radius: 10px; padding: 10px; }
QLabel[role="step"] { background: $accent_dim; color: $on_dim; border-radius: 13px; font-weight: 700; min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px; qproperty-alignment: AlignCenter; }

/* navigation: side bar, page header, search */
QFrame[sidebar="true"] { background: $sidebar; border: none; border-right: 1px solid $border; }
QFrame[sidebar="true"] QLabel { background: transparent; }
QLabel[role="brand"] { font-size: ${f2}px; font-weight: 800; color: $text; padding: 2px 6px; }
QLabel[role="group"] { color: $muted; font-size: ${fm3}px; font-weight: 700; padding: 2px 8px; }
QWidget[header="true"] { background: $bg; }
QDialog[palette="true"] { background: $surface; border: 1px solid $border2; border-radius: 12px; }
QListWidget[palette_list="true"] { border: none; background: transparent; }
QListWidget[palette_list="true"]::item { padding: 8px 10px; border-radius: 7px; }

/* progress, splitters, menus, status bar */
QProgressBar { background: $surface2; border: 1px solid $border; border-radius: 9px; text-align: center; min-height: 18px; color: $text; }
QProgressBar::chunk { background: $accent; border-radius: 8px; }
QSplitter::handle { background: transparent; }
QSplitter::handle:vertical { height: 8px; }
QSplitter::handle:horizontal { width: 8px; }
QMenu { background: $surface; border: 1px solid $border2; border-radius: 9px; padding: 5px; }
QMenu::item { padding: 6px 22px 6px 14px; border-radius: 5px; }
QMenu::item:selected { background: $accent_dim; color: $on_dim; }
QMenu::separator { height: 1px; background: $border; margin: 5px 8px; }
QStatusBar { background: $sidebar; color: $muted; border-top: 1px solid $border; }
QStatusBar::item { border: none; }
""")


def palette():
    p = QPalette()
    c = lambda k: QColor(T[k])
    for role, key in ((QPalette.ColorRole.Window, "bg"), (QPalette.ColorRole.WindowText, "text"), (QPalette.ColorRole.Base, "surface"),
                      (QPalette.ColorRole.AlternateBase, "surface2"), (QPalette.ColorRole.Text, "text"), (QPalette.ColorRole.Button, "surface2"),
                      (QPalette.ColorRole.ButtonText, "text"), (QPalette.ColorRole.ToolTipBase, "surface3"), (QPalette.ColorRole.ToolTipText, "text"),
                      (QPalette.ColorRole.Highlight, "accent"), (QPalette.ColorRole.Link, "accent_fg"), (QPalette.ColorRole.PlaceholderText, "muted")):
        p.setColor(role, c(key))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(T["on_accent"]))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(T["faint"]))
    return p


def ensure_assets(folder):
    """Draw the little pictures the stylesheet points at (check mark, arrows) once per theme. Returns {name: path}."""
    folder.mkdir(parents=True, exist_ok=True)
    tag = "dark" if STATE["dark"] else "light"

    def make(name, draw, size=16):
        path = folder / f"{name}-{tag}.png"
        img = QImage(size, size, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw(p, size)
        p.end()
        img.save(str(path))
        return str(path)

    def check(p, s):
        p.setPen(QPen(QColor(T["on_accent"]), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPolyline(QPolygonF([QPointF(s * .24, s * .54), QPointF(s * .44, s * .72), QPointF(s * .78, s * .30)]))

    def chevron(up):
        def draw(p, s):
            p.setPen(QPen(QColor(T["muted"]), 1.9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            y1, y2 = (s * .62, s * .36) if up else (s * .38, s * .64)
            p.drawPolyline(QPolygonF([QPointF(s * .27, y1), QPointF(s * .5, y2), QPointF(s * .73, y1)]))
        return draw
    return {"check": make("check", check), "arrow_up": make("arrow_up", chevron(True)), "arrow_down": make("arrow_down", chevron(False))}


def stylesheet(assets):
    sizes = {f"f{n}".replace("-", "m"): font_px(n) for n in (-3, -2, 0, 1, 2, 5, 6, 9)}
    return QSS.substitute(**T, **sizes, **{k: v.replace("\\", "/") for k, v in assets.items()})



def apply(app, folder, mode=None, accent=None, size=None):
    """Dress the application: a steady base style (so the stylesheet looks the same everywhere), the palette and the stylesheet.
    Called again with other choices it re-dresses the running app. With no choices it keeps the last ones (the first time: dark, blue, normal size)."""
    choose(mode or STATE["mode"], accent or STATE["accent"], size or STATE["size"])
    if "Fusion" in QStyleFactory.keys():
        app.setStyle("Fusion")
    app.setPalette(palette())
    app.setStyleSheet(stylesheet(ensure_assets(folder)))
    for w in app.allWidgets():               # widgets that draw themselves read T when they are painted
        w.update()


def follow_system(app, folder, on_change=None):
    """When the mode is 'system', re-dress the app when the desktop switches between light and dark."""
    try:
        hints = QGuiApplication.styleHints()
        hints.colorSchemeChanged.connect(lambda *_: STATE["mode"] == "system" and (apply(app, folder), on_change and on_change()))
    except AttributeError:
        pass


choose()
