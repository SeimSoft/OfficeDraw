"""Normal window with the live image and the drawing on top. This is the window to share in Teams."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QWidget

from .strokes import BACKGROUNDS, StrokeScene, paint_strokes

BACKGROUND = QColor("#1B1B1F")


class ViewerWindow(QWidget):
    visibility_changed = Signal(bool)

    def __init__(self, scene: StrokeScene) -> None:
        super().__init__()
        self.setWindowTitle("OfficeDraw – Ausschnitt")
        self.resize(960, 600)
        self._scene = scene
        self._image: QImage | None = None

    def set_image(self, image: QImage) -> None:
        self._image = image
        if self.isVisible():
            self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.visibility_changed.emit(True)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.visibility_changed.emit(False)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), BACKGROUND)
        if self._image is None:
            painter.setPen(QColor("#AAAAAA"))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "Warte auf Bildausschnitt …"
            )
            return
        target = _fit(QRectF(self.rect()), self._image.width() / self._image.height())
        background = BACKGROUNDS.get(self._scene.background)
        if background is None:
            painter.drawImage(target, self._image)
        else:
            painter.fillRect(target, background)
        paint_strokes(painter, target, self._scene.strokes.values())


def _fit(area: QRectF, aspect: float) -> QRectF:
    width = area.width()
    height = width / aspect
    if height > area.height():
        height = area.height()
        width = height * aspect
    center = area.center()
    return QRectF(center.x() - width / 2, center.y() - height / 2, width, height)
