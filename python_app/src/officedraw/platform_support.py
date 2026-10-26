"""Platform specifics: always-on-top windows, keeping our windows out of the capture, pixel coordinates."""

from __future__ import annotations

import sys

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QWidget

WDA_EXCLUDEFROMCAPTURE = 0x11  # Windows 10 2004+

# AppKit constants
NS_STATUS_WINDOW_LEVEL = 25  # above normal and floating windows
NS_CAN_JOIN_ALL_SPACES = 1 << 0
NS_STATIONARY = 1 << 4
NS_FULL_SCREEN_AUXILIARY = 1 << 8
NS_WINDOW_STYLE_MASK_RESIZABLE = 1 << 3


def overlay_flags() -> Qt.WindowType:
    """Window flags for frameless windows that float above everything."""
    flags = (
        Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowStaysOnTopHint
        | Qt.WindowType.WindowDoesNotAcceptFocus
    )
    # On Windows a tool window keeps the overlay out of the taskbar. On macOS tool
    # windows hide as soon as another app is active, so they are not used there.
    if sys.platform == "win32":
        flags |= Qt.WindowType.Tool
    return flags


def keep_on_top(widget: QWidget) -> None:
    """Keep a window above all other apps, also when our app is not the active one."""
    if sys.platform != "darwin":
        return  # WindowStaysOnTopHint is enough on Windows
    try:
        window = _ns_window(widget)
        window.setHidesOnDeactivate_(False)
        window.setLevel_(NS_STATUS_WINDOW_LEVEL)
        window.setCollectionBehavior_(
            NS_CAN_JOIN_ALL_SPACES | NS_STATIONARY | NS_FULL_SCREEN_AUXILIARY
        )
    except Exception as error:
        print(
            f"Fenster kann nicht dauerhaft im Vordergrund gehalten werden: {error}",
            file=sys.stderr,
        )


def forbid_native_resize(widget: QWidget) -> None:
    """Stop macOS from resizing a frameless window by itself when its edge is dragged.

    Qt marks frameless windows as resizable on macOS, so the system would resize the
    window behind our back instead of letting our own drag handling run.
    """
    if sys.platform != "darwin":
        return
    try:
        window = _ns_window(widget)
        mask = window.styleMask()
        if mask & NS_WINDOW_STYLE_MASK_RESIZABLE:
            window.setStyleMask_(mask & ~NS_WINDOW_STYLE_MASK_RESIZABLE)
    except Exception as error:
        print(f"Fenstergröße kann nicht fixiert werden: {error}", file=sys.stderr)


def exclude_from_capture(widget: QWidget) -> None:
    """Keep a window out of screen capture, so the streamed image does not contain our own frame."""
    try:
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.SetWindowDisplayAffinity(
                int(widget.winId()), WDA_EXCLUDEFROMCAPTURE
            )
        elif sys.platform == "darwin":
            _ns_window(widget).setSharingType_(0)  # NSWindowSharingNone
    except Exception as error:  # best effort, e.g. on Windows older than 2004
        print(
            f"Fenster kann nicht von der Aufnahme ausgeschlossen werden: {error}",
            file=sys.stderr,
        )


def capture_rect(rect: QRect, screen: QScreen) -> tuple[int, int, int, int]:
    """Convert a Qt rectangle (logical pixels) into the coordinates mss expects."""
    # On Windows mss works in physical pixels, on macOS in points.
    scale = screen.devicePixelRatio() if sys.platform == "win32" else 1.0
    return (
        round(rect.x() * scale),
        round(rect.y() * scale),
        round(rect.width() * scale),
        round(rect.height() * scale),
    )


def _ns_window(widget: QWidget):
    import objc

    # On macOS winId() is the NSView of the widget.
    return objc.objc_object(c_void_p=int(widget.winId())).window()
