"""Command line entry point: `officedraw` starts the app, `officedraw install-app` installs the phone app."""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

from . import __version__

DEFAULT_PORT = 47800
DEFAULT_FPS = 6.0
BUNDLED_APK = Path(__file__).parent / "bundled" / "officedraw.apk"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="officedraw",
        description="Bildschirmausschnitt per USB an die OfficeDraw-Android-App streamen und live bemalen lassen.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="TCP-Port (Standard: %(default)s)",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=DEFAULT_FPS,
        help="Bilder pro Sekunde zum Tablet (Standard: %(default)s)",
    )
    parser.add_argument(
        "--version", action="version", version=f"officedraw {__version__}"
    )
    commands = parser.add_subparsers(dest="command")
    install = commands.add_parser(
        "install-app", help="OfficeDraw-APK per adb auf das Android-Gerät installieren"
    )
    install.add_argument(
        "apk", nargs="?", help="Pfad zur APK (Standard: die mitgelieferte APK)"
    )

    args = parser.parse_args(argv)
    if args.command == "install-app":
        return install_app(args.apk)
    return run_gui(args.port, args.fps)


def run_gui(port: int, fps: float) -> int:
    from PySide6.QtWidgets import QApplication

    from .app import OfficeDrawApp

    # Ctrl+C in the terminal quits; Qt would otherwise swallow it.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    qt = QApplication.instance() or QApplication(sys.argv[:1])
    qt.setApplicationName("OfficeDraw")
    # Quit only via the × in the frame (or Ctrl+C), not when the share window is closed.
    qt.setQuitOnLastWindowClosed(False)
    app = OfficeDrawApp(port, fps)
    qt.aboutToQuit.connect(app.shutdown)
    app.start()
    return qt.exec()


def install_app(apk: str | None) -> int:
    from .adb import adb_install

    path = Path(apk) if apk else BUNDLED_APK
    if not path.is_file():
        print(f"APK nicht gefunden: {path}", file=sys.stderr)
        return 1
    try:
        print(adb_install(str(path)))
    except RuntimeError as error:
        print(f"Installation fehlgeschlagen: {error}", file=sys.stderr)
        print(
            "Prüfen: USB-Debugging am Gerät aktiv, Gerät autorisiert (`adb devices`).",
            file=sys.stderr,
        )
        return 1
    print("Fertig – „OfficeDraw“ ist auf dem Gerät installiert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
