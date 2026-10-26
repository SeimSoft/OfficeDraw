"""USB link helpers. `adb reverse` forwards the PC port to the phone's localhost."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def find_adb() -> str | None:
    found = shutil.which("adb")
    if found:
        return found
    exe = "adb.exe" if os.name == "nt" else "adb"
    sdk_roots = [
        os.environ.get("ANDROID_HOME"),
        os.environ.get("ANDROID_SDK_ROOT"),
        str(Path.home() / "Library" / "Android" / "sdk"),
        str(Path.home() / "AppData" / "Local" / "Android" / "Sdk"),
    ]
    for root in sdk_roots:
        if root and (Path(root) / "platform-tools" / exe).is_file():
            return str(Path(root) / "platform-tools" / exe)
    return None


def _run(args: list[str], timeout: float = 10) -> subprocess.CompletedProcess[str]:
    # Hide the console window that adb would otherwise flash on Windows.
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=flags,
    )


def adb_reverse(port: int) -> str:
    """Forward phone's 127.0.0.1:port to the PC's port. Returns a status line."""
    adb = find_adb()
    if adb is None:
        return "adb nicht gefunden – Android SDK Platform-Tools installieren"
    try:
        result = _run([adb, "reverse", f"tcp:{port}", f"tcp:{port}"])
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"adb Fehler: {error}"
    if result.returncode == 0:
        return f"USB aktiv (Port {port})"
    return "Kein Android-Gerät per USB: " + (
        result.stderr.strip() or result.stdout.strip()
    )


def adb_install(apk: str) -> str:
    """Install (or update) an APK on the connected device."""
    adb = find_adb()
    if adb is None:
        raise RuntimeError(
            "adb nicht gefunden – Android SDK Platform-Tools installieren"
        )
    result = _run([adb, "install", "-r", apk], timeout=180)
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0 or "Success" not in output:
        raise RuntimeError(output or "adb install fehlgeschlagen")
    return output
