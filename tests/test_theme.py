"""Test of the look of the desktop app: dark and light themes, accent colours, text size, saved choices, and that no module spells a colour out.
Run: QT_QPA_PLATFORM=offscreen python3 tests/test_theme.py"""
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="theme-"))
os.environ.update({"ROBLOX_MANAGER_CONFIG": str(tmp / "cfg"), "ROBLOX_MANAGER_STATE": str(tmp / "state"), "ROBLOX_MANAGER_VAULT": "off",
                   "ROBLOX_MANAGER_APP_DIR": str(tmp / "app"), "ROBLOX_MANAGER_UPDATE_CACHE": str(tmp / "cache")})
(tmp / "app").mkdir()
(tmp / "app" / "VERSION").write_text("1.6.0\n")
sys.path.insert(0, str(ROOT / "linux"))
import browser_login  # noqa: F401
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
import rbx
import settings
import theme
from app import MainWindow

res = []


def check(n, ok, e=""):
    res.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + n + (("  " + str(e)[:300]) if e else ""))


def spin(s=0.1):
    end = time.time() + s
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


# ---------------------------------------------------------------- the palettes
SURFACES = ("bg", "surface", "surface2", "surface3")
TEXT_ON_SURFACE = ("text", "muted")
COLOURS_ON_BG_AND_SURFACE = ("success", "warn", "danger", "info", "orange", "violet", "accent_fg")
low = []
for dark in (True, False):
    for accent in theme.ACCENTS:
        p = theme.palette_for(dark, accent)
        label = ("dark " if dark else "light ") + accent
        for s in SURFACES:
            for t in TEXT_ON_SURFACE:
                if theme.contrast(p[t], p[s]) < 4.5:
                    low.append(f"{label}: {t} on {s} = {theme.contrast(p[t], p[s]):.1f}")
        for s in ("bg", "surface", "surface2"):
            for t in COLOURS_ON_BG_AND_SURFACE:
                if theme.contrast(p[t], p[s]) < 4.5:
                    low.append(f"{label}: {t} on {s} = {theme.contrast(p[t], p[s]):.1f}")
        for fill in ("accent", "accent_hover", "accent_press"):
            if theme.contrast(p["on_accent"], p[fill]) < 4.5:
                low.append(f"{label}: button text on {fill} = {theme.contrast(p['on_accent'], p[fill]):.1f}")
        if theme.contrast(p["on_dim"], p["accent_dim"]) < 7:
            low.append(f"{label}: selected text on accent_dim = {theme.contrast(p['on_dim'], p['accent_dim']):.1f}")
        if theme.contrast(p["danger"], p["danger_dim"]) < 4.5:
            low.append(f"{label}: danger text on its button = {theme.contrast(p['danger'], p['danger_dim']):.1f}")
        if theme.contrast(p["text"], p["notice_bg"]) < 7:
            low.append(f"{label}: text on the notice = {theme.contrast(p['text'], p['notice_bg']):.1f}")
check("every colour is readable (at least 4.5 : 1) in both themes and with every accent colour", not low, low[:6])
check("the dark and the light theme name the same colours", set(theme.DARK) == set(theme.LIGHT), set(theme.DARK) ^ set(theme.LIGHT))
check("there are five accent colours, each with a dark and a light fill", len(theme.ACCENTS) == 5 and all(len(v) == 2 for v in theme.ACCENTS.values()))
check("the dark and the light theme look different", theme.palette_for(True, "blue")["bg"] != theme.palette_for(False, "blue")["bg"])
check("contrast of black on white is 21", abs(theme.contrast("#000000", "#ffffff") - 21) < 0.01)

# ---------------------------------------------------------------- choosing
theme.choose("light", "green", 110)
check("T follows the choice (light, green, large): background and accent", theme.T["bg"] == theme.LIGHT["bg"] and theme.T["accent"] == theme.ACCENTS["green"][1], theme.T["accent"])
check("...and the state says so", theme.STATE["mode"] == "light" and not theme.STATE["dark"] and theme.STATE["size"] == 110)
check("font_px scales with the text size", theme.font_px() == round(13 * 1.10) and theme.font_px(5) == round(18 * 1.10), (theme.font_px(), theme.font_px(5)))
theme.choose("nonsense", "nonsense", 7)
check("unknown choices fall back to dark, blue and normal size", theme.STATE["mode"] == "dark" and theme.STATE["accent"] == "blue" and theme.STATE["size"] == 100)
theme.choose("system", "blue", 100)
check("'system' follows the desktop (dark or light, never an error)", theme.STATE["mode"] == "system" and theme.STATE["dark"] == theme.system_is_dark())
same = theme.T
theme.choose("light", "blue", 100)
check("T stays the same dict when the theme is switched (so 'from theme import T' keeps working)", theme.T is same and theme.T["bg"] == theme.LIGHT["bg"])
live = theme.Live({"a": "success", "b": "danger"})
theme.choose("dark", "blue", 100)
dark_success = live["a"]
theme.choose("light", "blue", 100)
check("a Live table of colours gives the colour of the theme in use", dark_success == theme.DARK["success"] and live["a"] == theme.LIGHT["success"] and live.get("zzz", "none") == "none" and "a" in live)

# ---------------------------------------------------------------- the stylesheet
assets = theme.ensure_assets(tmp / "assets")
for mode in ("dark", "light"):
    for size in theme.SIZES:
        theme.choose(mode, "purple", size)
        try:
            css = theme.stylesheet(theme.ensure_assets(tmp / "assets"))
            ok = "$" not in css and theme.T["accent"] in css
        except KeyError as e:
            ok, css = False, str(e)
        check(f"the stylesheet is complete in {mode} at {size} % (no name left unfilled)", ok, "" if ok else css[:80])
check("the drawn check mark and arrows exist for both themes", all(Path(v).exists() for v in assets.values()) and any("-light" in v for v in theme.ensure_assets(tmp / "assets").values()))

# ---------------------------------------------------------------- the choices in the settings
check("the settings know the theme, the accent colour and the text size", all(k in settings.DEFAULTS for k in ("ui.theme", "ui.accent", "ui.text_size")))
check("their defaults are the old look: dark, blue, 100 %", (settings.get("ui.theme"), settings.get("ui.accent"), settings.get("ui.text_size")) == ("dark", "blue", 100))
check("a theme that does not exist is refused", settings.set("ui.theme", "neon") == "dark")
check("an accent colour that does not exist is refused", settings.set("ui.accent", "beige") == "blue")
check("a text size is rounded to one the design has", settings.set("ui.text_size", 112) == 110 and settings.set("ui.text_size", 500) == 125 and settings.set("ui.text_size", 1) == 90)
settings.set("ui.text_size", 100)
check("a text that is not a number gives the default", settings.set("ui.text_size", "big") == 100)

# ---------------------------------------------------------------- the window
w = MainWindow(rbx.Client(), auto_login=False)
w.show()
spin(0.2)
check("the window starts dark", theme.STATE["dark"] and app.styleSheet().count(theme.DARK["bg"]) > 0)
tab = w.settings_tab
check("Settings > Looks has a button for each theme, five accent colours and a text size", len(tab.theme_buttons) == 3 and len(tab.accent_buttons) == 5 and tab.size_combo.count() == 4)
check("...showing the saved choices", tab.theme_buttons["dark"].isChecked() and tab.accent_buttons["blue"].isChecked() and tab.size_combo.currentData() == 100)
tab.theme_buttons["light"].click()
spin(0.2)
check("pressing Light dresses the open window at once", not theme.STATE["dark"] and theme.LIGHT["bg"] in app.styleSheet() and settings.get("ui.theme") == "light")
check("...the palette of the application changed too", app.palette().window().color().name() == theme.LIGHT["bg"], app.palette().window().color().name())
tab.accent_buttons["pink"].click()
spin(0.2)
check("pressing a colour changes the accent at once", theme.T["accent"] == theme.ACCENTS["pink"][1] and theme.T["accent"] in app.styleSheet() and settings.get("ui.accent") == "pink")
check("...and its swatch is the one marked", tab.accent_buttons["pink"].isChecked() and not tab.accent_buttons["blue"].isChecked())
tab.size_combo.setCurrentIndex(tab.size_combo.findData(125))
tab.size_combo.activated.emit(tab.size_combo.currentIndex())
spin(0.2)
check("choosing a text size changes the text at once", theme.STATE["size"] == 125 and f"font-size: {theme.font_px()}px" in app.styleSheet(), theme.font_px())
saved = json.loads((tmp / "cfg" / "settings.json").read_text())
check("the choices are saved in settings.json", saved.get("ui.theme") == "light" and saved.get("ui.accent") == "pink" and saved.get("ui.text_size") == 125, saved)
settings.reset()
spin(0.2)
check("Reset all settings brings the old look back", theme.STATE["dark"] and theme.STATE["accent"] == "blue" and theme.STATE["size"] == 100 and tab.theme_buttons["dark"].isChecked())

# ---------------------------------------------------------------- the welcome card of the Home page
acc = w.account
check("signed out, the Home page welcomes the person and offers Sign in", acc.welcome.isVisibleTo(acc) and acc.btn_welcome.isEnabled() and not acc.head.isVisibleTo(acc) and not acc.details.isVisibleTo(acc))

# ---------------------------------------------------------------- shortcut and search
w.toggle_theme()
spin(0.1)
check("Ctrl+Shift+L (toggle_theme) switches to the light theme and back", not theme.STATE["dark"] and settings.get("ui.theme") == "light")
w.toggle_theme()
spin(0.1)
check("...back to dark", theme.STATE["dark"] and settings.get("ui.theme") == "dark")
check("the shortcut is installed", any(sc.key().toString() == "Ctrl+Shift+L" for sc in w._shortcuts))
entries = {e[0]: e for e in w._search_entries()}
check("the search offers the three themes", all(k in entries for k in ("Dark theme", "Light theme", "Theme: match my desktop")), list(entries)[:12])
entries["Light theme"][3]()
spin(0.1)
check("...and picking one dresses the app", not theme.STATE["dark"])
settings.set("ui.theme", "dark")

# ---------------------------------------------------------------- the rule: colours are only spelled out in theme.py
offenders = []
for f in sorted((ROOT / "linux").glob("*.py")):
    if f.name == "theme.py":
        continue
    for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        if re.search(r"#[0-9a-fA-F]{6}\b|QColor\(\"#", line) and not line.strip().startswith("#"):
            offenders.append(f"{f.name}:{n}")
check("no module spells a colour out (they all use theme.T, so the light theme works everywhere)", not offenders, offenders[:8])

print(f"{sum(res)}/{len(res)} checks passed")
sys.exit(0 if all(res) else 1)
