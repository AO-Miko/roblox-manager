#!/usr/bin/env python3
"""Draws the Android launcher icons from linux/icon.png (run again if the icon changes)."""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
src = Image.open(ROOT / "linux" / "icon.png").convert("RGBA")
res = ROOT / "android" / "app" / "src" / "main" / "res"

# legacy square icons
for folder, size in (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)):
    d = res / f"mipmap-{folder}"
    d.mkdir(parents=True, exist_ok=True)
    src.resize((size, size), Image.LANCZOS).save(d / "ic_launcher.png", optimize=True)

# adaptive icon: the picture sits inside the safe zone (about 66%) of a 108dp canvas, on a dark background
canvas = 432
fg = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
inner = int(canvas * 0.70)
fg.alpha_composite(src.resize((inner, inner), Image.LANCZOS), ((canvas - inner) // 2, (canvas - inner) // 2))
d = res / "mipmap-xxxhdpi"
fg.save(d / "ic_launcher_foreground.png", optimize=True)
any_dpi = res / "mipmap-anydpi-v26"
any_dpi.mkdir(parents=True, exist_ok=True)
(any_dpi / "ic_launcher.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/bg" />
    <foreground android:drawable="@mipmap/ic_launcher_foreground" />
    <monochrome android:drawable="@mipmap/ic_launcher_foreground" />
</adaptive-icon>
""")
print("icons written")
