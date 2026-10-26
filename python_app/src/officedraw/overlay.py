"""Click-through window over the shared region. Strokes appear on top of the apps behind it."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from .platform_support import exclude_from_capture, keep_on_top, overlay_flags
from .strokes import BACKGROUNDS, StrokeScene, paint_strokes


class OverlayWindow(QWidget):
    def __init__(self, scene: StrokeScene) -> None:
        # Mouse clicks pass through to the app behind.
        super().__init__(
            None, overlay_flags() | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._scene = scene

    def showEvent(self, event) -> None:
        super().showEvent(event)
        keep_on_top(self)
        exclude_from_capture(self)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        background = BACKGROUNDS.get(self._scene.background)
        if background is not None:
            painter.fillRect(self.rect(), background)
        paint_strokes(painter, QRectF(self.rect()), self._scene.strokes.values())
