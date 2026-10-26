import 'dart:math' as math;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import 'connection.dart';
import 'drawing_model.dart';
import 'viewport.dart';

enum Tool { pen, eraser }

/// Shows the streamed frame and handles input.
///
/// - Stylus (digitizer) or mouse button: draw. Inverted stylus end erases.
/// - One finger: pan. Two fingers: pinch to zoom and pan.
/// - Touches are ignored while the pen is down, so a resting hand does not draw or pan.
/// - Mouse wheel zooms, which makes the app usable on a desktop for testing.
class DrawingCanvas extends StatefulWidget {
  const DrawingCanvas({
    super.key,
    required this.connection,
    required this.model,
    required this.transform,
    required this.tool,
    required this.color,
    required this.strokeWidth,
  });

  final DesktopConnection connection;
  final DrawingModel model;
  final ViewTransform transform;
  final Tool tool;
  final Color color;
  final double strokeWidth;

  @override
  State<DrawingCanvas> createState() => _DrawingCanvasState();
}

class _DrawingCanvasState extends State<DrawingCanvas> {
  static const double _eraserRadiusPx = 22;

  final Map<int, Offset> _touches = {};
  int? _penPointer;
  Stroke? _stroke;
  bool _erasing = false;
  double? _pinchDistance;
  Offset? _pinchCentroid;

  Size get _viewport => (context.findRenderObject() as RenderBox).size;

  Rect get _content => widget.transform.contentRect(_viewport, widget.connection.aspect);

  Offset _normalize(Offset local) {
    final content = _content;
    return Offset(
      (local.dx - content.left) / content.width,
      (local.dy - content.top) / content.height,
    );
  }

  double _pressure(PointerEvent event) {
    final pressure = event.pressure <= 0 ? 1.0 : event.pressure;
    return pressure.clamp(0.05, 1.0).toDouble();
  }

  bool _isPen(PointerEvent event) {
    switch (event.kind) {
      case PointerDeviceKind.stylus:
      case PointerDeviceKind.invertedStylus:
        return true;
      case PointerDeviceKind.mouse:
        return event.buttons & kPrimaryMouseButton != 0;
      default:
        return false;
    }
  }

  void _eraseAt(Offset normalized) {
    final content = _content;
    widget.model.eraseNear(
      normalized,
      Size(_eraserRadiusPx / content.width, _eraserRadiusPx / content.height),
    );
  }

  void _onDown(PointerDownEvent event) {
    if (_isPen(event)) {
      if (_penPointer != null) return;
      _penPointer = event.pointer;
      _touches.clear();
      _pinchDistance = null;
      _pinchCentroid = null;
      _erasing = widget.tool == Tool.eraser || event.kind == PointerDeviceKind.invertedStylus;
      final point = _normalize(event.localPosition);
      if (_erasing) {
        widget.model.beginErase();
        _eraseAt(point);
      } else {
        _stroke = widget.model.beginStroke(widget.color, widget.strokeWidth);
        widget.model.addPoint(_stroke!, StrokePoint(point.dx, point.dy, _pressure(event)));
      }
    } else if (event.kind == PointerDeviceKind.touch && _penPointer == null) {
      _touches[event.pointer] = event.localPosition;
      _pinchDistance = null;
      _pinchCentroid = null;
    }
  }

  void _onMove(PointerMoveEvent event) {
    if (event.pointer == _penPointer) {
      final point = _normalize(event.localPosition);
      if (_erasing) {
        _eraseAt(point);
      } else if (_stroke != null) {
        widget.model.addPoint(_stroke!, StrokePoint(point.dx, point.dy, _pressure(event)));
      }
      return;
    }
    if (!_touches.containsKey(event.pointer)) return;
    _touches[event.pointer] = event.localPosition;

    final viewport = _viewport;
    final aspect = widget.connection.aspect;
    if (_touches.length == 1) {
      widget.transform.panBy(event.delta, viewport, aspect);
    } else if (_touches.length == 2) {
      final points = _touches.values.toList();
      final centroid = Offset.lerp(points[0], points[1], 0.5)!;
      final distance = (points[0] - points[1]).distance;
      final previousDistance = _pinchDistance;
      final previousCentroid = _pinchCentroid;
      if (previousDistance != null && previousCentroid != null && previousDistance > 0) {
        widget.transform.zoomBy(distance / previousDistance, centroid, viewport, aspect);
        widget.transform.panBy(centroid - previousCentroid, viewport, aspect);
      }
      _pinchDistance = distance;
      _pinchCentroid = centroid;
    }
  }

  void _onUp(PointerEvent event) {
    if (event.pointer == _penPointer) {
      if (_erasing) {
        widget.model.endErase();
      } else if (_stroke != null) {
        widget.model.endStroke(_stroke!);
      }
      _stroke = null;
      _erasing = false;
      _penPointer = null;
      return;
    }
    _touches.remove(event.pointer);
    _pinchDistance = null;
    _pinchCentroid = null;
  }

  void _onSignal(PointerSignalEvent event) {
    if (event is PointerScrollEvent) {
      widget.transform.zoomBy(
        math.exp(-event.scrollDelta.dy / 300),
        event.localPosition,
        _viewport,
        widget.connection.aspect,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Listener(
      behavior: HitTestBehavior.opaque,
      onPointerDown: _onDown,
      onPointerMove: _onMove,
      onPointerUp: _onUp,
      onPointerCancel: _onUp,
      onPointerSignal: _onSignal,
      child: CustomPaint(
        size: Size.infinite,
        painter: _CanvasPainter(
          connection: widget.connection,
          model: widget.model,
          transform: widget.transform,
        ),
      ),
    );
  }
}

class _CanvasPainter extends CustomPainter {
  _CanvasPainter({required this.connection, required this.model, required this.transform})
      : super(repaint: Listenable.merge([connection, model, transform]));

  final DesktopConnection connection;
  final DrawingModel model;
  final ViewTransform transform;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = const Color(0xFF1B1B1F));
    final content = transform.contentRect(size, connection.aspect);

    final frame = connection.frame;
    if (connection.background != BackgroundMode.none) {
      final color = connection.background == BackgroundMode.white ? Colors.white : Colors.black;
      canvas.drawRect(content, Paint()..color = color);
    } else if (frame != null) {
      canvas.drawImageRect(
        frame,
        Rect.fromLTWH(0, 0, frame.width.toDouble(), frame.height.toDouble()),
        content,
        Paint()..filterQuality = FilterQuality.medium,
      );
    }
    for (final stroke in model.strokes) {
      _drawStroke(canvas, content, stroke);
    }
  }

  @override
  bool shouldRepaint(covariant _CanvasPainter oldDelegate) => false;
}

void _drawStroke(Canvas canvas, Rect content, Stroke stroke) {
  Offset toScreen(StrokePoint p) =>
      Offset(content.left + p.x * content.width, content.top + p.y * content.height);

  final baseWidth = stroke.width * content.width;
  final points = stroke.points;
  if (points.length == 1) {
    canvas.drawCircle(toScreen(points.first), baseWidth / 2, Paint()..color = stroke.color);
    return;
  }
  final paint = Paint()
    ..color = stroke.color
    ..strokeCap = StrokeCap.round
    ..style = PaintingStyle.stroke;
  for (var i = 1; i < points.length; i++) {
    paint.strokeWidth = math.max(1.0, baseWidth * (0.25 + 0.75 * points[i].pressure));
    canvas.drawLine(toScreen(points[i - 1]), toScreen(points[i]), paint);
  }
}
