import 'dart:async';
import 'dart:ui';

import 'package:flutter/foundation.dart';

/// A sampled pen position. x and y are normalized to the frame (0..1).
class StrokePoint {
  const StrokePoint(this.x, this.y, this.pressure);

  final double x;
  final double y;
  final double pressure;
}

class Stroke {
  Stroke({required this.id, required this.color, required this.width});

  final String id;
  final Color color;

  /// Stroke width relative to the frame width, so it scales with the image.
  final double width;
  final List<StrokePoint> points = [];

  String get colorHex => '#${color.toARGB32().toRadixString(16).padLeft(8, '0')}';

  Map<String, dynamic> toJson() => {
        'id': id,
        'color': colorHex,
        'w': width,
        'pts': [for (final p in points) [p.x, p.y, p.pressure]],
      };
}

/// One undoable step: strokes added, or strokes removed (erase / clear).
class _Action {
  _Action({this.added = const [], this.removed = const []});

  final List<Stroke> added;
  final List<Stroke> removed;
}

/// Holds all strokes and forwards every change to the desktop app.
class DrawingModel extends ChangeNotifier {
  DrawingModel({required this.send}) : _session = DateTime.now().microsecondsSinceEpoch.toRadixString(36);

  final void Function(Map<String, dynamic> message) send;
  final String _session;
  final Map<String, Stroke> _strokes = {};
  final List<_Action> _undoStack = [];
  final Map<String, List<StrokePoint>> _unsent = {};
  final List<Stroke> _erased = [];
  Timer? _flushTimer;
  int _counter = 0;

  Iterable<Stroke> get strokes => _strokes.values;
  bool get canUndo => _undoStack.isNotEmpty;
  bool get isEmpty => _strokes.isEmpty;

  Stroke beginStroke(Color color, double width) {
    final stroke = Stroke(id: '$_session-${_counter++}', color: color, width: width);
    _strokes[stroke.id] = stroke;
    send({'t': 'begin', 'id': stroke.id, 'color': stroke.colorHex, 'w': width});
    notifyListeners();
    return stroke;
  }

  void addPoint(Stroke stroke, StrokePoint point) {
    stroke.points.add(point);
    _unsent.putIfAbsent(stroke.id, () => []).add(point);
    _flushTimer ??= Timer(const Duration(milliseconds: 25), _flush);
    notifyListeners();
  }

  /// Sends buffered points in batches, so the desktop shows the stroke live.
  void _flush() {
    _flushTimer?.cancel();
    _flushTimer = null;
    for (final entry in _unsent.entries) {
      send({
        't': 'pts',
        'id': entry.key,
        'pts': [for (final p in entry.value) [p.x, p.y, p.pressure]],
      });
    }
    _unsent.clear();
  }

  void endStroke(Stroke stroke) {
    if (stroke.points.isEmpty) {
      _strokes.remove(stroke.id);
      notifyListeners();
      return;
    }
    _flush();
    send({'t': 'end', 'id': stroke.id});
    _undoStack.add(_Action(added: [stroke]));
    notifyListeners();
  }

  void beginErase() => _erased.clear();

  /// Removes every stroke that has a point inside the ellipse around [center].
  /// [radius] is normalized, so the caller can keep the eraser a fixed size on screen.
  void eraseNear(Offset center, Size radius) {
    final hit = [
      for (final stroke in _strokes.values)
        if (stroke.points.any((p) => _inside(p, center, radius))) stroke,
    ];
    if (hit.isEmpty) return;
    for (final stroke in hit) {
      _strokes.remove(stroke.id);
    }
    _erased.addAll(hit);
    send({'t': 'remove', 'ids': [for (final s in hit) s.id]});
    notifyListeners();
  }

  void endErase() {
    if (_erased.isEmpty) return;
    _undoStack.add(_Action(removed: List.of(_erased)));
    _erased.clear();
  }

  void undo() {
    if (_undoStack.isEmpty) return;
    final action = _undoStack.removeLast();
    if (action.added.isNotEmpty) {
      for (final stroke in action.added) {
        _strokes.remove(stroke.id);
      }
      send({'t': 'remove', 'ids': [for (final s in action.added) s.id]});
    }
    if (action.removed.isNotEmpty) {
      for (final stroke in action.removed) {
        _strokes[stroke.id] = stroke;
      }
      sendScene();
    }
    notifyListeners();
  }

  void clear() {
    if (_strokes.isEmpty) return;
    _undoStack.add(_Action(removed: List.of(_strokes.values)));
    _strokes.clear();
    sendScene();
    notifyListeners();
  }

  /// Sends the complete drawing. Used on connect and after bigger changes.
  void sendScene() {
    send({'t': 'scene', 'strokes': [for (final s in _strokes.values) s.toJson()]});
  }

  static bool _inside(StrokePoint p, Offset center, Size radius) {
    final dx = (p.x - center.dx) / radius.width;
    final dy = (p.y - center.dy) / radius.height;
    return dx * dx + dy * dy <= 1;
  }

  @override
  void dispose() {
    _flushTimer?.cancel();
    super.dispose();
  }
}
