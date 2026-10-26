import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';

import 'protocol.dart';

enum BackgroundMode { none, white, black }

/// TCP connection to the desktop app. The desktop app listens on the PC and the
/// phone reaches it through `adb reverse tcp:PORT tcp:PORT` (USB cable).
class DesktopConnection extends ChangeNotifier {
  DesktopConnection({this.host = '127.0.0.1', this.port = defaultPort});

  static const int defaultPort = 47800;

  final String host;
  final int port;

  /// Called after every (re)connect so the desktop app gets the full drawing.
  VoidCallback? onConnected;

  /// Called when the desktop app asks to remove all strokes.
  VoidCallback? onClearRequested;

  Socket? _socket;
  MessageReader _reader = MessageReader();
  Timer? _retryTimer;
  bool _disposed = false;
  ui.Image? _frame;
  BackgroundMode _background = BackgroundMode.none;
  bool _decoding = false;
  Uint8List? _pendingJpeg;

  /// Latest decoded frame of the streamed screen region.
  ui.Image? get frame => _frame;
  bool get connected => _socket != null;

  /// Shared with the desktop app: the screen image, or a plain white/black board.
  BackgroundMode get background => _background;

  /// Frame aspect ratio, 16:9 until the first frame arrives.
  double get aspect {
    final image = _frame;
    return image == null ? 16 / 9 : image.width / image.height;
  }

  void start() => _connect();

  Future<void> _connect() async {
    if (_disposed || _socket != null) return;
    try {
      final socket = await Socket.connect(host, port, timeout: const Duration(seconds: 2));
      if (_disposed) {
        socket.destroy();
        return;
      }
      socket.setOption(SocketOption.tcpNoDelay, true);
      _socket = socket;
      _reader = MessageReader();
      notifyListeners();
      onConnected?.call();
      socket.listen(
        _onData,
        onDone: _onClosed,
        onError: (_) => _onClosed(),
        cancelOnError: true,
      );
    } catch (_) {
      _scheduleRetry();
    }
  }

  void _scheduleRetry() {
    if (_disposed) return;
    _retryTimer?.cancel();
    _retryTimer = Timer(const Duration(seconds: 1), _connect);
  }

  void _onClosed() {
    final socket = _socket;
    if (socket == null) return;
    socket.destroy();
    _socket = null;
    notifyListeners();
    _scheduleRetry();
  }

  void _onData(Uint8List data) {
    for (final (type, payload) in _reader.feed(data)) {
      if (type == typeFrame) {
        _showFrame(payload);
      } else if (type == typeJson) {
        _onJson(jsonDecode(utf8.decode(payload)) as Map<String, dynamic>);
      }
    }
  }

  void _onJson(Map<String, dynamic> message) {
    if (message['t'] == 'clear') {
      onClearRequested?.call();
    } else if (message['t'] == 'bg') {
      _background = BackgroundMode.values.asNameMap()[message['mode']] ?? BackgroundMode.none;
      notifyListeners();
    }
  }

  /// Changes the background on both sides.
  void setBackground(BackgroundMode mode) {
    _background = mode;
    send({'t': 'bg', 'mode': mode.name});
    notifyListeners();
  }

  /// Decodes frames one at a time. If frames arrive faster than they decode,
  /// only the newest one is kept.
  Future<void> _showFrame(Uint8List jpeg) async {
    if (_decoding) {
      _pendingJpeg = jpeg;
      return;
    }
    _decoding = true;
    Uint8List? next = jpeg;
    while (next != null) {
      final codec = await ui.instantiateImageCodec(next);
      final image = (await codec.getNextFrame()).image;
      codec.dispose();
      final old = _frame;
      _frame = image;
      if (old != null) {
        Future<void>.delayed(const Duration(milliseconds: 250), old.dispose);
      }
      notifyListeners();
      next = _pendingJpeg;
      _pendingJpeg = null;
    }
    _decoding = false;
  }

  void send(Map<String, dynamic> message) {
    final socket = _socket;
    if (socket == null) return;
    try {
      socket.add(packJson(message));
    } catch (_) {
      _onClosed();
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _retryTimer?.cancel();
    _socket?.destroy();
    _frame?.dispose();
    super.dispose();
  }
}
