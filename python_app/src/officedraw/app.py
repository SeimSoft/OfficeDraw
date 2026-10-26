"""Wires the USB server, screen capture, the region frame and the windows together."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRect, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QImage

from .capture import CaptureThread
from .frame import RegionFrame
from .overlay import OverlayWindow
from .platform_support import capture_rect
from .server import DrawServer
from .strokes import BACKGROUNDS, StrokeScene
from .viewer import ViewerWindow

MAX_WIDTH = 1280  # frames wider than this are scaled down before they are sent


class _Signals(QObject):
    """Moves callbacks from background threads onto the GUI thread."""

    message = Signal(object)
    client_changed = Signal(bool)
    link_status = Signal(str)
    frame = Signal(object)


class OfficeDrawApp(QObject):
    def __init__(self, port: int, fps: float) -> None:
        super().__init__()
        self._fps = fps
        self._signals = _Signals()
        self._scene = StrokeScene()
        self._server = DrawServer(
            port,
            on_message=self._signals.message.emit,
            on_client_change=self._signals.client_changed.emit,
            on_status=self._signals.link_status.emit,
        )
        self._overlay = OverlayWindow(self._scene)
        self._frame = RegionFrame()
        self._viewer = ViewerWindow(self._scene)
        self._capture: CaptureThread | None = None

        self._signals.message.connect(self._on_message)
        self._signals.client_changed.connect(self._on_client_changed)
        self._signals.link_status.connect(self._frame.set_status)
        self._signals.frame.connect(self._viewer.set_image)
        self._frame.region_changed.connect(self._set_region)
        self._frame.viewer_toggled.connect(self._toggle_viewer)
        self._frame.quit_requested.connect(self.quit)
        self._frame.background_requested.connect(self._set_background)
        self._viewer.visibility_changed.connect(self._frame.set_viewer_visible)

    def start(self) -> None:
        self._server.start()
        screen = (
            QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        )
        area = screen.availableGeometry()
        region = QRect(0, 0, area.width() // 2, area.height() // 2)
        region.moveCenter(area.center())
        self._frame.set_region(region)
        self._set_region(region)
        self._overlay.show()
        self._frame.show()

    def shutdown(self) -> None:
        if self._capture is not None:
            self._capture.stop()
        self._server.stop()

    def quit(self) -> None:
        self.shutdown()
        QGuiApplication.quit()

    def _set_region(self, region: QRect) -> None:
        self._overlay.setGeometry(region)
        screen = (
            QGuiApplication.screenAt(region.center()) or QGuiApplication.primaryScreen()
        )
        rect = capture_rect(region, screen)
        if self._capture is None:
            self._capture = CaptureThread(
                rect, fps=self._fps, max_width=MAX_WIDTH, on_frame=self._handle_frame
            )
            self._capture.start()
        else:
            self._capture.set_rect(rect)

    def _toggle_viewer(self) -> None:
        self._viewer.setVisible(not self._viewer.isVisible())
        if self._viewer.isVisible():
            self._viewer.raise_()

    def _handle_frame(self, image: QImage, jpeg: bytes) -> None:
        # Runs on the capture thread: send the frame, then hand the image to the viewer.
        self._server.send_frame(jpeg)
        self._signals.frame.emit(image)

    def _on_client_changed(self, connected: bool) -> None:
        self._frame.set_connected(connected)
        if connected:
            # A (re)connected tablet starts with the background that is active here.
            self._server.send_json({"t": "bg", "mode": self._scene.background})

    def _set_background(self, mode: str, notify_tablet: bool = True) -> None:
        if mode not in ("none", *BACKGROUNDS):
            return
        self._scene.background = mode
        self._frame.set_background(mode)
        self._overlay.update()
        self._viewer.update()
        if notify_tablet:
            self._server.send_json({"t": "bg", "mode": mode})

    def _on_message(self, message: object) -> None:
        if not isinstance(message, dict):
            return
        if message.get("t") == "bg":
            self._set_background(str(message.get("mode")), notify_tablet=False)
        elif self._scene.apply(message):
            self._overlay.update()
            self._viewer.update()
