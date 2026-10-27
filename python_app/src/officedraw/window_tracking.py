"""Bounds of the window the user is currently working in, for the "Anheften" (attach) mode."""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QPoint, QRect

from .platform_support import to_logical

MIN_TRACKED_WIDTH = 100  # smaller windows are popups, tooltips and the like
MIN_TRACKED_HEIGHT = 80


def active_window_rect() -> QRect | None:
    """Global logical bounds of the front window of the active app.

    Returns None while one of our own windows is active, when nothing suitable is in
    front (desktop, minimized window), or on unsupported platforms.
    """
    try:
        if sys.platform == "darwin":
            return _active_window_macos()
        if sys.platform == "win32":
            return _active_window_windows()
    except Exception as error:
        print(f"Aktives Fenster nicht ermittelbar: {error}", file=sys.stderr)
    return None


def _active_window_macos() -> QRect | None:
    import Quartz
    from AppKit import NSRunningApplication, NSWorkspace

    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return None
    pid = app.processIdentifier()
    if pid == NSRunningApplication.currentApplication().processIdentifier():
        return None
    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly
        | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )
    # The list is ordered front to back, so the first normal window of the app is its front window.
    for info in windows or []:
        if (
            info.get(Quartz.kCGWindowOwnerPID) != pid
            or info.get(Quartz.kCGWindowLayer, 0) != 0
        ):
            continue
        if info.get(Quartz.kCGWindowAlpha, 1) == 0:
            continue
        bounds = info[Quartz.kCGWindowBounds]
        rect = QRect(
            int(bounds["X"]),
            int(bounds["Y"]),
            int(bounds["Width"]),
            int(bounds["Height"]),
        )
        if rect.width() >= MIN_TRACKED_WIDTH and rect.height() >= MIN_TRACKED_HEIGHT:
            return rect  # Quartz uses points with the origin top-left, like Qt on macOS
    return None


_IGNORED_WINDOW_CLASSES = {
    "Progman",
    "WorkerW",
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
}
_DWMWA_EXTENDED_FRAME_BOUNDS = 9  # visible bounds, without the invisible resize border


def _active_window_windows() -> QRect | None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd or user32.IsIconic(hwnd):
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == os.getpid():
        return None
    class_name = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, class_name, 256)
    if class_name.value in _IGNORED_WINDOW_CLASSES:
        return None  # desktop or taskbar
    rect = wintypes.RECT()
    found = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        hwnd, _DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)
    )
    if found != 0 and not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    physical = QRect(
        QPoint(rect.left, rect.top), QPoint(rect.right - 1, rect.bottom - 1)
    )
    if physical.width() < MIN_TRACKED_WIDTH or physical.height() < MIN_TRACKED_HEIGHT:
        return None
    return to_logical(physical)
