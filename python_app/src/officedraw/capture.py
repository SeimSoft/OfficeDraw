"""Grabs a screen rectangle in a background thread, scales it and encodes it as JPEG."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import mss
from mss.exception import ScreenShotError
from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage

JPEG_QUALITY = 70


def grab_image(grabber: mss.base.MSSBase, rect: tuple[int, int, int, int]) -> QImage:
    """Grab a screen rectangle at full resolution."""
    left, top, width, height = rect
    shot = grabber.grab({"left": left, "top": top, "width": width, "height": height})
    return QImage(
        bytes(shot.raw),
        shot.width,
        shot.height,
        shot.width * 4,
        QImage.Format.Format_RGB32,  # mss delivers BGRA, which matches RGB32 on little endian
    ).copy()


class CaptureThread(threading.Thread):
    def __init__(
        self,
        rect: tuple[int, int, int, int],
        fps: float,
        max_width: int,
        on_frame: Callable[[QImage, bytes], None],
    ) -> None:
        super().__init__(name="officedraw-capture", daemon=True)
        self._rect = rect
        self.fps = fps
        self._max_width = max_width
        self._on_frame = on_frame
        self._stop = threading.Event()

    def set_rect(self, rect: tuple[int, int, int, int]) -> None:
        """Change the captured rectangle; takes effect with the next frame."""
        self._rect = rect

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        # mss keeps per-thread handles, so the grabber is created inside this thread.
        with mss.mss() as grabber:
            while not self._stop.is_set():
                started = time.monotonic()
                try:
                    image = grab_image(grabber, self._rect)
                except ScreenShotError:
                    self._stop.wait(1.0)
                    continue
                if image.width() > self._max_width:
                    height = round(image.height() * self._max_width / image.width())
                    image = image.scaled(
                        self._max_width,
                        height,
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                buffer = QBuffer()
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                image.save(buffer, "JPEG", JPEG_QUALITY)
                jpeg = bytes(buffer.data())
                buffer.close()
                self._on_frame(image, jpeg)
                elapsed = time.monotonic() - started
                self._stop.wait(max(0.0, 1.0 / self.fps - elapsed))
