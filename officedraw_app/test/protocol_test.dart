import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:officedraw_app/protocol.dart';

void main() {
  test('messages survive being split across chunks', () {
    final json = packJson({'t': 'end', 'id': 'abc'});
    final frame = packMessage(typeFrame, Uint8List.fromList([1, 2, 3]));
    final stream = Uint8List.fromList([...json, ...frame]);

    final reader = MessageReader();
    final messages = <(int, Uint8List)>[
      for (var i = 0; i < stream.length; i += 3)
        ...reader.feed(Uint8List.sublistView(stream, i, (i + 3).clamp(0, stream.length))),
    ];

    expect(messages.length, 2);
    expect(messages[0].$1, typeJson);
    expect(jsonDecode(utf8.decode(messages[0].$2)), {'t': 'end', 'id': 'abc'});
    expect(messages[1].$1, typeFrame);
    expect(messages[1].$2, [1, 2, 3]);
  });
}
