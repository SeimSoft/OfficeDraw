import 'dart:ui';

import 'package:flutter/foundation.dart';

/// Zoom and pan of the streamed frame.
///
/// The frame is first "fitted" into the viewport (zoom 1). Zoom and pan are
/// applied on top of that, and the frame is clamped so it never leaves the screen.
class ViewTransform extends ChangeNotifier {
  static const double minZoom = 1;
  static const double maxZoom = 12;

  double _zoom = 1;
  Offset _pan = Offset.zero; // content top-left relative to the fitted rect

  double get zoom => _zoom;

  static Rect fitRect(Size viewport, double aspect) {
    var width = viewport.width;
    var height = width / aspect;
    if (height > viewport.height) {
      height = viewport.height;
      width = height * aspect;
    }
    return Rect.fromLTWH(
      (viewport.width - width) / 2,
      (viewport.height - height) / 2,
      width,
      height,
    );
  }

  /// Where the frame is drawn, in viewport coordinates.
  Rect contentRect(Size viewport, double aspect) {
    final base = fitRect(viewport, aspect);
    final size = Size(base.width * _zoom, base.height * _zoom);
    return (base.topLeft + _pan) & size;
  }

  void zoomBy(double factor, Offset focal, Size viewport, double aspect) {
    final current = contentRect(viewport, aspect);
    final newZoom = (_zoom * factor).clamp(minZoom, maxZoom).toDouble();
    final ratio = newZoom / _zoom;
    // Keep the point under the focal point fixed on screen.
    final topLeft = focal - (focal - current.topLeft) * ratio;
    _apply(topLeft, viewport, aspect, newZoom);
  }

  void panBy(Offset delta, Size viewport, double aspect) {
    final current = contentRect(viewport, aspect);
    _apply(current.topLeft + delta, viewport, aspect, _zoom);
  }

  void reset() {
    _zoom = 1;
    _pan = Offset.zero;
    notifyListeners();
  }

  void _apply(Offset topLeft, Size viewport, double aspect, double zoom) {
    if (viewport.isEmpty) return;
    final base = fitRect(viewport, aspect);
    final size = Size(base.width * zoom, base.height * zoom);
    final clamped = Offset(
      _clampAxis(topLeft.dx, size.width, viewport.width),
      _clampAxis(topLeft.dy, size.height, viewport.height),
    );
    _zoom = zoom;
    _pan = clamped - base.topLeft;
    notifyListeners();
  }

  /// Centers small content, and keeps large content covering the viewport.
  static double _clampAxis(double position, double contentSize, double viewportSize) {
    if (contentSize <= viewportSize) return (viewportSize - contentSize) / 2;
    return position.clamp(viewportSize - contentSize, 0).toDouble();
  }
}
