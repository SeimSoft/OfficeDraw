import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'connection.dart';
import 'drawing_canvas.dart';
import 'drawing_model.dart';
import 'viewport.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
  runApp(const OfficeDrawApp());
}

class OfficeDrawApp extends StatelessWidget {
  const OfficeDrawApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'OfficeDraw',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: Colors.indigo,
        brightness: Brightness.dark,
        useMaterial3: true,
      ),
      home: const DrawScreen(),
    );
  }
}

class DrawScreen extends StatefulWidget {
  const DrawScreen({super.key});

  @override
  State<DrawScreen> createState() => _DrawScreenState();
}

class _DrawScreenState extends State<DrawScreen> {
  static const _colors = [
    Color(0xFFE53935),
    Color(0xFF1E88E5),
    Color(0xFF43A047),
    Color(0xFFFDD835),
    Color(0xFF000000),
    Color(0xFFFFFFFF),
  ];
  static const _penChannel = MethodChannel('officedraw/pen');
  static const _widths = [0.003, 0.007, 0.016];
  static const _widthIconSizes = [8.0, 14.0, 22.0];

  late final DesktopConnection _connection = DesktopConnection();
  late final DrawingModel _model = DrawingModel(send: _connection.send);
  final ViewTransform _transform = ViewTransform();

  Tool _tool = Tool.pen;
  Color _color = _colors.first;
  double _width = _widths[1];

  @override
  void initState() {
    super.initState();
    _connection.onConnected = _model.sendScene;
    _connection.start();
    // Double tap on the pen (see MainActivity.kt) switches between pen and eraser.
    _penChannel.setMethodCallHandler((call) async {
      if (call.method == 'doubleTap') {
        setState(() => _tool = _tool == Tool.pen ? Tool.eraser : Tool.pen);
      }
    });
  }

  @override
  void dispose() {
    _penChannel.setMethodCallHandler(null);
    _connection.dispose();
    _model.dispose();
    _transform.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        // Without expand the Stack sizes itself to its non-positioned child, which
        // collapses to zero once the placeholder is replaced by the first frame.
        fit: StackFit.expand,
        children: [
          Positioned.fill(
            child: DrawingCanvas(
              connection: _connection,
              model: _model,
              transform: _transform,
              tool: _tool,
              color: _color,
              strokeWidth: _width,
            ),
          ),
          ListenableBuilder(
            listenable: _connection,
            builder: (context, _) => _connection.frame == null
                ? _Placeholder(connected: _connection.connected)
                : const SizedBox.shrink(),
          ),
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: SafeArea(
              bottom: false,
              child: Padding(
                padding: const EdgeInsets.all(8),
                child: _buildToolbar(),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildToolbar() {
    return Material(
      elevation: 4,
      borderRadius: BorderRadius.circular(16),
      color: Theme.of(context).colorScheme.surfaceContainerHigh,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        child: ListenableBuilder(
          listenable: Listenable.merge([_connection, _model]),
          builder: (context, _) => Wrap(
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: 4,
            children: [
              Tooltip(
                message: _connection.connected ? 'Verbunden' : 'Nicht verbunden',
                child: Icon(
                  _connection.connected ? Icons.usb : Icons.usb_off,
                  color: _connection.connected ? Colors.greenAccent : Colors.orangeAccent,
                ),
              ),
              IconButton(
                tooltip: 'Stift',
                isSelected: _tool == Tool.pen,
                icon: const Icon(Icons.edit),
                onPressed: () => setState(() => _tool = Tool.pen),
              ),
              IconButton(
                tooltip: 'Radierer',
                isSelected: _tool == Tool.eraser,
                icon: const Icon(Icons.backspace_outlined),
                onPressed: () => setState(() => _tool = Tool.eraser),
              ),
              for (final color in _colors)
                _ColorDot(
                  color: color,
                  selected: _color == color && _tool == Tool.pen,
                  onTap: () => setState(() {
                    _color = color;
                    _tool = Tool.pen;
                  }),
                ),
              for (var i = 0; i < _widths.length; i++)
                IconButton(
                  tooltip: 'Strichstärke',
                  isSelected: _width == _widths[i],
                  icon: Icon(Icons.circle, size: _widthIconSizes[i]),
                  onPressed: () => setState(() => _width = _widths[i]),
                ),
              IconButton(
                tooltip: 'Rückgängig',
                icon: const Icon(Icons.undo),
                onPressed: _model.canUndo ? _model.undo : null,
              ),
              IconButton(
                tooltip: 'Alles löschen',
                icon: const Icon(Icons.delete_sweep),
                onPressed: _model.isEmpty ? null : _model.clear,
              ),
              IconButton(
                tooltip: 'Ansicht zurücksetzen',
                icon: const Icon(Icons.fit_screen),
                onPressed: _transform.reset,
              ),
              const SizedBox(height: 28, child: VerticalDivider()),
              for (final mode in BackgroundMode.values)
                _BackgroundButton(
                  mode: mode,
                  selected: _connection.background == mode,
                  onTap: () => _connection.setBackground(mode),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ColorDot extends StatelessWidget {
  const _ColorDot({required this.color, required this.selected, required this.onTap});

  final Color color;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 28,
        height: 28,
        margin: const EdgeInsets.all(8),
        decoration: BoxDecoration(
          color: color,
          shape: BoxShape.circle,
          border: Border.all(
            color: selected ? Theme.of(context).colorScheme.primary : Colors.white24,
            width: selected ? 3 : 1,
          ),
        ),
      ),
    );
  }
}

/// Chooses what is behind the drawing: the PC screen, or a plain white/black board.
class _BackgroundButton extends StatelessWidget {
  const _BackgroundButton({required this.mode, required this.selected, required this.onTap});

  final BackgroundMode mode;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final (tooltip, fill) = switch (mode) {
      BackgroundMode.none => ('Bildschirm', Colors.transparent),
      BackgroundMode.white => ('Weißer Hintergrund', Colors.white),
      BackgroundMode.black => ('Schwarzer Hintergrund', Colors.black),
    };
    return Tooltip(
      message: tooltip,
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          width: 30,
          height: 30,
          margin: const EdgeInsets.all(7),
          decoration: BoxDecoration(
            color: fill,
            borderRadius: BorderRadius.circular(6),
            border: Border.all(
              color: selected ? Theme.of(context).colorScheme.primary : Colors.white38,
              width: selected ? 3 : 1,
            ),
          ),
          child: mode == BackgroundMode.none
              ? const Icon(Icons.desktop_windows_outlined, size: 18, color: Colors.white70)
              : null,
        ),
      ),
    );
  }
}

class _Placeholder extends StatelessWidget {
  const _Placeholder({required this.connected});

  final bool connected;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cable, size: 48, color: Colors.white38),
            const SizedBox(height: 12),
            Text(
              connected
                  ? 'Warte auf Bildausschnitt …'
                  : 'Verbinde mit der Desktop-App …\n'
                      'USB-Debugging aktiv? Python-App gestartet?',
              textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.white54),
            ),
          ],
        ),
      ),
    );
  }
}
