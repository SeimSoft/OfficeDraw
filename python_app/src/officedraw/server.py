"""TCP server the Flutter app reaches over USB (through `adb reverse`)."""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Callable

from .adb import adb_reverse
from .protocol import TYPE_JSON, Reader, pack_frame, pack_json


class DrawServer:
    """Accepts one phone at a time. Frames go out, drawing messages come in.

    Callbacks run on background threads; the GUI must marshal them to its own thread.
    """

    def __init__(
        self,
        port: int,
        on_message: Callable[[dict], None],
        on_client_change: Callable[[bool], None],
        on_status: Callable[[str], None],
    ) -> None:
        self.port = port
        self._on_message = on_message
        self._on_client_change = on_client_change
        self._on_status = on_status
        self._lock = threading.Lock()
        self._client: socket.socket | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        threading.Thread(
            target=self._serve, name="officedraw-accept", daemon=True
        ).start()
        threading.Thread(
            target=self._keep_adb_reverse, name="officedraw-adb", daemon=True
        ).start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            client, self._client = self._client, None
        if client is not None:
            _close(client)

    def send_frame(self, jpeg: bytes) -> None:
        self._send(pack_frame(jpeg))

    def send_json(self, message: dict) -> None:
        self._send(pack_json(message))

    def _serve(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind(("127.0.0.1", self.port))
        except OSError as error:
            self._on_status(f"Port {self.port} belegt: {error}")
            return
        listener.listen(1)
        listener.settimeout(1.0)
        while not self._stop.is_set():
            try:
                conn, _ = listener.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            self._adopt(conn)
        listener.close()

    def _keep_adb_reverse(self) -> None:
        # The phone may be plugged in later or re-plugged, so retry until it is linked.
        while not self._stop.is_set():
            with self._lock:
                linked = self._client is not None
            if not linked:
                self._on_status(adb_reverse(self.port))
            self._stop.wait(5)

    def _adopt(self, conn: socket.socket) -> None:
        conn.settimeout(None)
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        with self._lock:
            previous, self._client = self._client, conn
        if previous is not None:
            _close(previous)
        self._on_client_change(True)
        threading.Thread(
            target=self._read, args=(conn,), name="officedraw-read", daemon=True
        ).start()

    def _read(self, conn: socket.socket) -> None:
        reader = Reader()
        try:
            while True:
                data = conn.recv(65536)
                if not data:
                    break
                for message_type, payload in reader.feed(data):
                    if message_type == TYPE_JSON:
                        self._on_message(json.loads(payload))
        except (OSError, ValueError):
            pass
        finally:
            with self._lock:
                was_current = self._client is conn
                if was_current:
                    self._client = None
            _close(conn)
            if was_current:
                self._on_client_change(False)

    def _send(self, data: bytes) -> None:
        with self._lock:
            conn = self._client
            if conn is None:
                return
            try:
                conn.sendall(data)
                return
            except OSError:
                pass
        # Closing unblocks the reader thread, which then reports the disconnect.
        _close(conn)


def _close(conn: socket.socket) -> None:
    try:
        conn.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    conn.close()
