"""Frame around the shared region: drag edges and corners to resize, drag the top bar to move.

The frame is made of four separate windows (top bar, left, right, bottom), so no window of
ours lies over the region itself and clicks there reach the apps behind it. The top bar
also holds the connection status and the buttons of the app.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .platform_support import (
    exclude_from_capture,
    forbid_native_resize,
    keep_on_top,
    overlay_flags,
)

EDGE = 10  # grab band left, right and below the region
BAR = 30  # top bar above the region
CORNER = 22  # corners catch a bit more than the edge band
MIN_WIDTH = 520  # room for the buttons in the top bar
NOTICE_MS = 1500  # how long a short confirmation stays in the top bar
MIN_HEIGHT = 120

ACCENT = QColor("#2E86FF")
GRAB = QColor(46, 134, 255, 40)
BAR_BACKGROUND = QColor(28, 28, 34, 230)
BUTTON_ACTIVE = QColor("#2E86FF")
BUTTON = QColor(255, 255, 255, 40)
CONNECTED = QColor("#3DDC84")
WAITING = QColor("#FFA726")

LEFT, TOP, RIGHT, BOTTOM, MOVE = 1, 2, 4, 8, 16

_CURSORS = {
    LEFT: Qt.CursorShape.SizeHorCursor,
    RIGHT: Qt.CursorShape.SizeHorCursor,
    TOP: Qt.CursorShape.SizeVerCursor,
    BOTTOM: Qt.CursorShape.SizeVerCursor,
    LEFT | TOP: Qt.CursorShape.SizeFDiagCursor,
    RIGHT | BOTTOM: Qt.CursorShape.SizeFDiagCursor,
    RIGHT | TOP: Qt.CursorShape.SizeBDiagCursor,
    LEFT | BOTTOM: Qt.CursorShape.SizeBDiagCursor,
    MOVE: Qt.CursorShape.SizeAllCursor,
}


class RegionFrame(QObject):
    """Owns the frame state. Works in "frame coordinates": (0, 0) is the top-left of the whole frame."""

    region_changed = Signal(QRect)  # global logical coordinates of the shared region
    viewer_toggled = Signal()
    quit_requested = Signal()
    background_requested = Signal(str)  # "none", "white" or "black"
    clear_requested = Signal()
    copy_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._region = QRect()
        self._drag = 0
        self._press_global = QPoint()
        self._press_region = QRect()
        self._connected = False
        self._status = "Warte auf Tablet …"
        self._viewer_visible = False
        self._background = "none"
        self._notice = ""
        self._pieces = [
            _FramePiece(self, side) for side in ("top", "left", "right", "bottom")
        ]

    def region(self) -> QRect:
        return QRect(self._region)

    def show(self) -> None:
        for piece in self._pieces:
            piece.show()

    def set_region(self, region: QRect) -> None:
        self._region = QRect(region)
        origin = self._outer().topLeft()
        for piece in self._pieces:
            piece.place(origin, self._piece_rect(piece.side))

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        self._repaint()

    def set_status(self, text: str) -> None:
        self._status = text
        self._repaint()

    def set_viewer_visible(self, visible: bool) -> None:
        self._viewer_visible = visible
        self._repaint()

    def set_background(self, mode: str) -> None:
        self._background = mode
        self._repaint()

    def show_notice(self, text: str) -> None:
        """Show a short confirmation in place of the status text."""
        self._notice = text
        self._repaint()
        QTimer.singleShot(NOTICE_MS, self._clear_notice)

    def _clear_notice(self) -> None:
        self._notice = ""
        self._repaint()

    def _repaint(self) -> None:
        for piece in self._pieces:
            piece.update()

    # Layout in frame coordinates

    def _outer(self) -> QRect:
        return self._region.adjusted(-EDGE, -BAR, EDGE, EDGE)

    def width(self) -> int:
        return self._outer().width()

    def height(self) -> int:
        return self._outer().height()

    def _piece_rect(self, side: str) -> QRect:
        width, height = self.width(), self.height()
        if side == "top":
            return QRect(0, 0, width, BAR)
        if side == "bottom":
            return QRect(0, height - EDGE, width, EDGE)
        if side == "left":
            return QRect(0, BAR, EDGE, height - BAR - EDGE)
        return QRect(width - EDGE, BAR, EDGE, height - BAR - EDGE)

    def _buttons(self) -> list[tuple[str, QRect, str, bool]]:
        """Buttons of the top bar from right to left: (key, rect, label, active)."""
        specs = [
            ("quit", "×", 26, False),
            ("share", "Teilen", 64, self._viewer_visible),
            ("black", "Schwarz", 70, self._background == "black"),
            ("white", "Weiß", 52, self._background == "white"),
            ("clear", "Löschen", 66, False),
            ("copy", "Kopieren", 74, False),
        ]
        buttons = []
        right = self.width() - EDGE - 2
        for key, label, width, active in specs:
            rect = QRect(right - width, 5, width, BAR - 10)
            buttons.append((key, rect, label, active))
            right = rect.left() - 6
        return buttons

    def _button_at(self, pos: QPoint) -> str | None:
        for key, rect, _label, _active in self._buttons():
            if rect.contains(pos):
                return key
        return None

    def _hit(self, pos: QPoint) -> int:
        if self._button_at(pos):
            return 0
        x, y, width, height = pos.x(), pos.y(), self.width(), self.height()
        left = x < EDGE
        right = x >= width - EDGE
        top = y < 6
        bottom = y >= height - EDGE
        if left or right:
            if y < BAR:
                top = True
            elif y >= height - CORNER:
                bottom = True
        if top or bottom:
            if x < CORNER:
                left = True
            elif x >= width - CORNER:
                right = True
        edges = (
            (LEFT if left else 0)
            | (RIGHT if right else 0)
            | (TOP if top else 0)
            | (BOTTOM if bottom else 0)
        )
        if edges:
            return edges
        return MOVE if y < BAR else 0

    def cursor_at(self, pos: QPoint) -> Qt.CursorShape:
        if self._button_at(pos):
            return Qt.CursorShape.PointingHandCursor
        return _CURSORS.get(self._hit(pos), Qt.CursorShape.ArrowCursor)

    # Mouse handling, called by the pieces with frame coordinates

    def press(self, pos: QPoint, global_pos: QPoint) -> None:
        button = self._button_at(pos)
        if button == "quit":
            self.quit_requested.emit()
        elif button == "share":
            self.viewer_toggled.emit()
        elif button == "clear":
            self.clear_requested.emit()
        elif button == "copy":
            self.copy_requested.emit()
        elif button in ("white", "black"):
            # Clicking the active background again goes back to the transparent view.
            self.background_requested.emit(
                "none" if self._background == button else button
            )
        if button:
            return
        self._drag = self._hit(pos)
        self._press_global = global_pos
        self._press_region = QRect(self._region)

    def drag(self, global_pos: QPoint) -> bool:
        """Returns True while a drag is in progress."""
        if not self._drag:
            return False
        delta = global_pos - self._press_global
        region = QRect(self._press_region)
        if self._drag == MOVE:
            region.translate(delta)
        else:
            if self._drag & LEFT:
                region.setLeft(
                    min(region.left() + delta.x(), region.right() - MIN_WIDTH)
                )
            if self._drag & RIGHT:
                region.setRight(
                    max(region.right() + delta.x(), region.left() + MIN_WIDTH)
                )
            if self._drag & TOP:
                region.setTop(
                    min(region.top() + delta.y(), region.bottom() - MIN_HEIGHT)
                )
            if self._drag & BOTTOM:
                region.setBottom(
                    max(region.bottom() + delta.y(), region.top() + MIN_HEIGHT)
                )
        # Keep the top bar on screen, otherwise the frame could not be grabbed again.
        top_limit = QGuiApplication.primaryScreen().virtualGeometry().top() + BAR
        if region.top() < top_limit:
            if self._drag == MOVE:
                region.moveTop(top_limit)
            else:
                region.setTop(top_limit)
        if region != self._region:
            self.set_region(region)
            self.region_changed.emit(QRect(region))
        return True

    def release(self) -> None:
        self._drag = 0

    # Painting in frame coordinates; each piece clips to its own part

    def paint(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        inner = QRectF(EDGE, BAR, width - 2 * EDGE, height - BAR - EDGE)

        painter.fillRect(QRectF(0, 0, width, height), GRAB)
        painter.setPen(QPen(ACCENT, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(inner.adjusted(-1, -1, 1, 1))

        bar = QRectF(EDGE, 2, width - 2 * EDGE, BAR - 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(BAR_BACKGROUND)
        painter.drawRoundedRect(bar, 6, 6)

        painter.setBrush(CONNECTED if self._connected else WAITING)
        painter.drawEllipse(QRectF(bar.left() + 10, bar.center().y() - 5, 10, 10))

        if self._notice:
            status = f"OfficeDraw · {self._notice}"
        elif self._connected:
            status = "OfficeDraw · Tablet verbunden"
        else:
            status = f"OfficeDraw · {self._status}"
        buttons = self._buttons()
        text_rect = QRectF(
            bar.left() + 28,
            bar.top(),
            buttons[-1][1].left() - bar.left() - 34,
            bar.height(),
        )
        painter.setPen(QColor("white"))
        elided = painter.fontMetrics().elidedText(
            status, Qt.TextElideMode.ElideRight, int(text_rect.width())
        )
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            elided,
        )

        for _key, rect, label, active in buttons:
            self._draw_button(painter, rect, label, active)

    @staticmethod
    def _draw_button(painter: QPainter, rect: QRect, label: str, active: bool) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(BUTTON_ACTIVE if active else BUTTON)
        painter.drawRoundedRect(QRectF(rect), 4, 4)
        painter.setPen(QColor("white"))
        painter.drawText(QRectF(rect), Qt.AlignmentFlag.AlignCenter, label)


class _FramePiece(QWidget):
    """One side of the frame as its own window. Draws and forwards input in frame coordinates."""

    def __init__(self, frame: RegionFrame, side: str) -> None:
        super().__init__(None, overlay_flags())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.side = side
        self._frame = frame
        self._offset = QPoint()  # top-left of this piece in frame coordinates

    def place(self, frame_origin: QPoint, rect: QRect) -> None:
        self._offset = rect.topLeft()
        self.setFixedSize(rect.size())
        self.move(frame_origin + rect.topLeft())
        if self.isVisible():
            forbid_native_resize(self)  # Qt may restore the style when the size changes
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        keep_on_top(self)
        forbid_native_resize(self)
        exclude_from_capture(self)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.translate(-self._offset)
        self._frame.paint(painter)

    def _frame_pos(self, event: QMouseEvent) -> QPoint:
        return event.position().toPoint() + self._offset

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._frame.press(self._frame_pos(event), event.globalPosition().toPoint())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._frame.drag(event.globalPosition().toPoint()):
            self.setCursor(self._frame.cursor_at(self._frame_pos(event)))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._frame.release()
