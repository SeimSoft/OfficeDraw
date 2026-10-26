"""Stroke scene shared by the overlay and the viewer, plus the drawing code for both."""

from __future__ import annotations

import itertools
from collections.abc import Iterable
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen


BACKGROUNDS = {"white": QColor("white"), "black": QColor("black")}


@dataclass
class Stroke:
    color: str  # "#AARRGGBB", as sent by Flutter
    width: float  # relative to the frame width
    points: list[tuple[float, float, float]] = field(
        default_factory=list
    )  # x, y, pressure


class StrokeScene:
    """All strokes keyed by id, in drawing order. Coordinates are normalized to 0..1."""

    def __init__(self) -> None:
        self.strokes: dict[str, Stroke] = {}
        self.background = "none"  # "none" shows the screen, or a key of BACKGROUNDS

    def apply(self, message: dict) -> bool:
        """Apply one message from the Flutter app. Returns True if something visible changed."""
        kind = message.get("t")
        if kind == "begin":
            self.strokes[message["id"]] = Stroke(message["color"], float(message["w"]))
            return True
        if kind == "pts":
            stroke = self.strokes.get(message["id"])
            if stroke is None:
                return False
            stroke.points.extend(
                (float(x), float(y), float(p)) for x, y, p in message["pts"]
            )
            return True
        if kind == "remove":
            for stroke_id in message["ids"]:
                self.strokes.pop(stroke_id, None)
            return True
        if kind == "scene":
            self.strokes = {
                entry["id"]: Stroke(
                    entry["color"],
                    float(entry["w"]),
                    [(float(x), float(y), float(p)) for x, y, p in entry["pts"]],
                )
                for entry in message["strokes"]
            }
            return True
        return False  # "end" needs no redraw


def paint_strokes(painter: QPainter, target: QRectF, strokes: Iterable[Stroke]) -> None:
    """Draw strokes into [target], scaled from normalized coordinates."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen()
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    for stroke in strokes:
        pen.setColor(QColor(stroke.color))
        base_width = stroke.width * target.width()
        points = stroke.points
        segments = (
            [(points[0], points[0])] if len(points) == 1 else itertools.pairwise(points)
        )
        for start, end in segments:
            pen.setWidthF(max(1.0, base_width * (0.25 + 0.75 * end[2])))
            painter.setPen(pen)
            painter.drawLine(_to_point(start, target), _to_point(end, target))


def _to_point(point: tuple[float, float, float], target: QRectF) -> QPointF:
    return QPointF(
        target.left() + point[0] * target.width(),
        target.top() + point[1] * target.height(),
    )
