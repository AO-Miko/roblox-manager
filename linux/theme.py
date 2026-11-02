"""The look of the app: colours (a dark and a light theme, five accent colours), text size, the stylesheet, and the few small pictures it needs."""
from string import Template

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPalette, QPen, QPolygonF
from PySide6.QtWidgets import QStyleFactory

MODES = ("dark", "light", "system")

# Every colour the app uses has a name here, in both themes; nothing else in the app should spell a colour out.
# The look ("Ink and paper"): warm neutrals, flat surfaces separated by tone instead of outlines, small corners, one strong accent.
DARK = {
    "bg": "#0d0d0f", "surface": "#151518", "surface2": "#1d1d21", "surface3": "#28282d",
    "border": "#26262b", "border2": "#3a3a41",
    "text": "#f4f1ea", "muted": "#aaa69d", "faint": "#7d7a73",
    "success": "#5fd38d", "warn": "#f2b84b", "danger": "#ff7a70", "info": "#7cb8ff",
    "danger_dim": "#3a1d1c", "danger_hover": "#4d2422", "danger_border": "#6a2f2c",
    "zebra": "#121215", "hover": "#202024", "sidebar": "#09090b",
    "notice_bg": "#2e2410", "notice_border": "#6b5120", "on_dim": "#ffffff",
    "orange": "#f08a5d", "violet": "#b9a3ff", "badge": "#d6303c",
}
LIGHT = {
    "bg": "#f5f2ea", "surface": "#fbfaf6", "surface2": "#ece8dd", "surface3": "#ddd8ca",
    "border": "#e0dbcd", "border2": "#c4bead",
    "text": "#1a1814", "muted": "#5a564c", "faint": "#8c877a",
    "success": "#17733f", "warn": "#8a5100", "danger": "#b42318", "info": "#1a5cb8",
    "danger_dim": "#fbe3df", "danger_hover": "#f5cdc7", "danger_border": "#e5aaa2",
    "zebra": "#f0ede4", "hover": "#e7e3d7", "sidebar": "#ebe7db",
    "notice_bg": "#fff1cf", "notice_border": "#e0bd6c", "on_dim": "#1a1814",
    "orange": "#a03d0a", "violet": "#6a3dc9", "badge": "#c92835",
}
# name -> (fill in the dark theme, fill in the light theme). White text on a fill is always at least 4.5 : 1.
ACCENTS = {
    "ember": ("#c2410c", "#b93a08"), "teal": ("#0f766e", "#0d6e66"), "iris": ("#5b4bd8", "#5040c8"),
    "gold": ("#a16207", "#8f5706"), "rose": ("#be123c", "#b01036"),
}
DEFAULT_ACCENT = "ember"
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
QToolTip { background: $text; color: $bg; border: none; padding: 5px 8px; border-radius: 3px; }

/* tabs: a row of plain words with an underline under the open one (the page tabs are hidden; the top bar is the way around) */
QTabWidget::pane { border: none; background: $bg; top: 0; }
QTabBar { background: transparent; qproperty-drawBase: 0; }
QTabBar::tab { background: transparent; color: $muted; padding: 9px 4px; margin-right: 22px; border: none; border-bottom: 3px solid transparent; font-weight: 700; }
QTabBar::tab:hover { color: $text; }
QTabBar::tab:selected { color: $text; border-bottom: 3px solid $accent_fg; }
QTabBar::tab:disabled { color: $faint; }
QTabWidget[sub="true"] > QTabBar::tab { padding: 7px 2px; margin: 4px 18px 4px 0; border: none; border-bottom: 2px solid transparent; font-weight: 600; }
QTabWidget[sub="true"] > QTabBar::tab:hover { color: $text; background: transparent; }
QTabWidget[sub="true"] > QTabBar::tab:selected { background: transparent; color: $text; border: none; border-bottom: 2px solid $accent_fg; }

/* buttons: quiet by default, one loud kind for the main action */
QPushButton { background: $surface2; color: $text; border: none; border-radius: 4px; padding: 8px 14px; font-weight: 600; }
QPushButton:hover { background: $surface3; }
QPushButton:pressed { background: $border2; }
QPushButton:focus { border: 2px solid $accent_fg; padding: 6px 12px; }
QPushButton:checked { background: $text; color: $bg; }
QPushButton::menu-indicator { image: none; width: 0; }
QPushButton:disabled { color: $faint; background: $surface; }
QPushButton[primary="true"] { background: $accent; color: $on_accent; font-weight: 700; }
QPushButton[primary="true"]:hover { background: $accent_hover; }
QPushButton[primary="true"]:pressed { background: $accent_press; }
QPushButton[primary="true"]:disabled { background: $accent_off; color: $on_accent; }
QPushButton[danger="true"] { color: $danger; background: transparent; border: 1px solid $danger_border; padding: 7px 13px; }
QPushButton[danger="true"]:hover { background: $danger_dim; border-color: $danger; }
QPushButton[danger="true"]:disabled { color: $faint; background: transparent; border-color: $border; }
QPushButton[swatch="true"] { padding: 0; border-radius: 4px; border: 2px solid transparent; min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px; }
QPushButton[swatch="true"]:checked { border: 3px solid $text; }

/* inputs: a line under the field instead of a box */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDateEdit, QComboBox { background: $surface; color: $text; border: none; border-bottom: 2px solid $border2; border-radius: 3px; padding: 7px 10px;
    selection-background-color: $accent; selection-color: $on_accent; }
QLineEdit:hover, QSpinBox:hover, QDateEdit:hover, QComboBox:hover { border-bottom-color: $muted; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDateEdit:focus, QComboBox:focus { border-bottom: 2px solid $accent_fg; }
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled { color: $faint; border-bottom-color: $border; }
QSpinBox, QDateEdit { padding-right: 24px; }
QSpinBox::up-button, QDateEdit::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 22px; border: none; background: transparent; }
QSpinBox::down-button, QDateEdit::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 22px; border: none; background: transparent; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover, QDateEdit::up-button:hover, QDateEdit::down-button:hover { background: $surface3; }
QSpinBox::up-arrow, QDateEdit::up-arrow { image: url($arrow_up); width: 10px; height: 10px; }
QSpinBox::down-arrow, QDateEdit::down-arrow { image: url($arrow_down); width: 10px; height: 10px; }
QComboBox { padding-right: 26px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: center right; width: 24px; border: none; }
QComboBox::down-arrow { image: url($arrow_down); width: 10px; height: 10px; }
QComboBox QAbstractItemView { background: $surface2; border: 1px solid $border2; selection-background-color: $accent; selection-color: $on_accent; padding: 3px; outline: 0; }
QCalendarWidget QWidget { background: $surface; }
QCalendarWidget QAbstractItemView:enabled { selection-background-color: $accent; selection-color: $on_accent; color: $text; }

/* check boxes: square */
QCheckBox { spacing: 9px; background: transparent; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 2px; background: $surface; border: 2px solid $border2; }
QCheckBox::indicator:hover { border-color: $accent_fg; }
QCheckBox::indicator:checked { background: $accent; border: 2px solid $accent; image: url($check); }
QCheckBox::indicator:disabled { background: $surface; border-color: $border; }

/* lists and tables: no frame, rows separated by tone */
QTableWidget, QListWidget { background: $surface; alternate-background-color: $zebra; border: none; border-radius: 6px; gridline-color: transparent;
    selection-background-color: $accent; selection-color: $on_accent; }
QTableWidget::item { padding: 6px 8px; border: none; }
QTableWidget::item:selected, QListWidget::item:selected { background: $accent; color: $on_accent; }
QTableWidget::item:hover { background: $hover; }
QListWidget::item { padding: 8px 10px; }
QHeaderView { background: transparent; }
QHeaderView::section { background: $surface; color: $muted; padding: 10px 8px; border: none; border-bottom: 2px solid $border2; font-weight: 700; }
QHeaderView::section:hover { color: $text; }
QTableCornerButton::section { background: $surface; border: none; }

/* scroll bars: thin, square ends */
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: $border2; border-radius: 2px; min-height: 30px; margin: 2px 2px; }
QScrollBar::handle:vertical:hover { background: $faint; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: $border2; border-radius: 2px; min-width: 30px; margin: 2px 2px; }
QScrollBar::handle:horizontal:hover { background: $faint; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QScrollArea { background: transparent; border: none; }
QScrollArea[holder="true"] > QWidget > QWidget { background: $bg; }
QScrollArea > QWidget > QWidget { background: transparent; }

/* cards: flat blocks of tone; the heading sits on top as a small label */
QGroupBox { background: $surface; border: none; border-radius: 6px; margin-top: 0; padding: 40px 18px 16px 18px; }
QGroupBox::title { subcontrol-origin: padding; subcontrol-position: top left; left: 18px; top: 14px; padding: 0; color: $muted; font-weight: 800; font-size: ${fm2}px; }
QFrame[card="true"] { background: $surface; border: none; border-radius: 6px; }
QFrame[tile="true"] { background: $surface2; border: none; border-radius: 4px; }
QFrame[hero="true"] { background: $surface; border: none; border-left: 6px solid $accent; border-radius: 6px; }
QFrame[card="true"] QLabel, QFrame[tile="true"] QLabel, QFrame[hero="true"] QLabel { border: none; }
QLabel[role="hint"] { color: $muted; }
QLabel[role="title"] { font-size: ${f6}px; font-weight: 800; }
QLabel[role="display"] { font-size: ${f9}px; font-weight: 800; }
QLabel[role="tile-value"] { font-size: ${f6}px; font-weight: 800; }
QLabel[role="tile-caption"] { color: $muted; font-size: ${fm2}px; font-weight: 700; }
QLabel[role="warn"] { color: $warn; }
QLabel[role="card-title"] { font-weight: 800; font-size: ${f1}px; }
QLabel[role="unread-dot"] { color: $badge; }
QLabel[role="read-check"] { color: $success; font-weight: 700; }
QLabel[role="level"] { font-weight: 800; padding: 2px 8px; border-radius: 3px; }
QLabel[level="important"] { color: $on_accent; background: $accent; }
QLabel[level="warning"] { color: $warn; background: $notice_bg; }
QFrame[card="true"][unread="true"] { border-left: 5px solid $badge; border-radius: 6px; }
QLabel[role="notice"] { background: $notice_bg; border: none; border-left: 4px solid $warn; border-radius: 3px; padding: 10px 12px; }
QLabel[role="step"] { background: $accent; color: $on_accent; border-radius: 3px; font-weight: 800; min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px; qproperty-alignment: AlignCenter; }

/* navigation: the top bar, the page header, search */
QFrame[sidebar="true"] { background: $sidebar; border: none; border-bottom: 1px solid $border; }
QFrame[sidebar="true"] QLabel { background: transparent; }
QLabel[role="brand"] { font-size: ${f2}px; font-weight: 900; color: $text; padding: 0 14px 0 6px; }
QLabel[role="group"] { color: $muted; font-size: ${fm3}px; font-weight: 700; padding: 2px 8px; }
QWidget[header="true"] { background: $bg; }
QDialog[palette="true"] { background: $surface2; border: 2px solid $text; border-radius: 4px; }
QListWidget[palette_list="true"] { border: none; background: transparent; }
QListWidget[palette_list="true"]::item { padding: 8px 10px; border-radius: 3px; }

/* progress, splitters, menus, status bar */
QProgressBar { background: $surface2; border: none; border-radius: 3px; text-align: center; min-height: 16px; color: $text; font-weight: 700; }
QProgressBar::chunk { background: $accent; border-radius: 3px; }
QSplitter::handle { background: transparent; }
QSplitter::handle:vertical { height: 8px; }
QSplitter::handle:horizontal { width: 8px; }
QMenu { background: $surface2; border: 1px solid $border2; border-radius: 4px; padding: 4px; }
QMenu::item { padding: 7px 22px 7px 14px; border-radius: 3px; }
QMenu::item:selected { background: $accent; color: $on_accent; }
QMenu::separator { height: 1px; background: $border; margin: 4px 8px; }
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
        pass                  # (an older Qt has no colour-scheme signal: the theme is simply not followed live)


choose()
