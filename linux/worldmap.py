"""A world map that shows where servers are: land drawn from world_land.json (Natural Earth, public domain), one dot per place, bigger for more servers."""
import json
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from theme import T

LAND_FILE = Path(__file__).with_name("world_land.json")
_land = None


def land():
    """[[(lon, lat), ...], ...]: the rings of the land (an empty list if the file cannot be read, so the dots still show)."""
    global _land
    if _land is None:
        _land = []
        try:
            d = json.loads(LAND_FILE.read_text(encoding="utf-8"))
            scale = d.get("scale") or 10
            for flat in d.get("rings", []):
                _land.append([(flat[i] / scale, flat[i + 1] / scale) for i in range(0, len(flat) - 1, 2)])
        except (OSError, ValueError, TypeError, AttributeError):
            _land = []
    return _land


def project(lat, lon, w, h):
    """Longitude and latitude -> a point on a w x h picture (every degree takes the same room, so the map is twice as wide as high)."""
    return (lon + 180.0) / 360.0 * w, (90.0 - lat) / 180.0 * h


def group_places(servers, places):
    """[(place, [server ids])]: the located servers, one entry per city. `places` is {server id: place dict}."""
    groups = {}
    for s in servers:
        p = places.get(s["id"])
        if p:
            groups.setdefault((p["lat"], p["lon"]), (p, []))[1].append(s["id"])
    return list(groups.values())


class WorldMap(QWidget):
    picked = Signal(list)           # the server ids at the dot that was pressed

    def __init__(self):
        super().__init__()
        self.dots = []              # {"lat", "lon", "label", "ids"}
        self.chosen = None
        self.setMouseTracking(True)
        self.setMinimumSize(320, 160)
        sp = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)
        self._path = None
        self._path_size = None

    def sizeHint(self):
        return QSize(720, 360)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return w // 2

    def set_dots(self, dots):
        self.dots = list(dots)
        self.chosen = None
        self.update()

    def _land_path(self):
        size = (self.width(), self.height())
        if self._path is None or self._path_size != size:
            path = QPainterPath()
            path.setFillRule(Qt.FillRule.OddEvenFill)
            for ring in land():
                pts = [QPointF(*project(lat, lon, *size)) for lon, lat in ring]
                path.addPolygon(QPolygonF(pts))
                path.closeSubpath()
            self._path, self._path_size = path, size
        return self._path

    def _radius(self, dot):
        return 5 + min(math.sqrt(len(dot["ids"])) * 1.5, 9)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(T["surface"]))
        p.setPen(QPen(QColor(T["surface3"]), 1))
        for lon in range(-150, 180, 30):                       # a faint grid
            x, _ = project(0, lon, self.width(), self.height())
            p.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        for lat in range(-60, 90, 30):
            _, y = project(lat, 0, self.width(), self.height())
            p.drawLine(QPointF(0, y), QPointF(self.width(), y))
        p.setPen(QPen(QColor("#3a4152"), 1))
        p.setBrush(QColor(T["surface3"]))
        p.drawPath(self._land_path())
        for i, d in enumerate(self.dots):
            x, y = project(d["lat"], d["lon"], self.width(), self.height())
            r = self._radius(d)
            on = i == self.chosen
            p.setPen(QPen(QColor("#ffffff") if on else QColor(T["bg"]), 2 if on else 1.2))
            p.setBrush(QColor(T["accent_hover"] if on else T["accent"]))
            p.drawEllipse(QPointF(x, y), r, r)
        p.end()

    def _dot_at(self, pos):
        best, best_d = None, 1e9
        for i, d in enumerate(self.dots):
            x, y = project(d["lat"], d["lon"], self.width(), self.height())
            dist = math.hypot(pos.x() - x, pos.y() - y)
            if dist <= self._radius(d) + 5 and dist < best_d:
                best, best_d = i, dist
        return best

    def mouseMoveEvent(self, e):
        i = self._dot_at(e.position())
        if i is None:
            QToolTip.hideText()
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        d = self.dots[i]
        n = len(d["ids"])
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        QToolTip.showText(e.globalPosition().toPoint(), f"{d['label']}: {n} server{'s' if n != 1 else ''}", self)

    def mousePressEvent(self, e):
        i = self._dot_at(e.position())
        if i is not None:
            self.chosen = i
            self.update()
            self.picked.emit(list(self.dots[i]["ids"]))
