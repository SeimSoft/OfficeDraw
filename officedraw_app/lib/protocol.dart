import 'dart:convert';
import 'dart:typed_data';

/// Wire format shared with the desktop app (python_app/src/officedraw/protocol.py).
///
/// Every message is: 1 byte type, 4 bytes big-endian payload length, payload.
const int protocolVersion = 1;
const int typeFrame = 1; // desktop -> phone: JPEG bytes of the screen region
const int typeJson = 2; // phone -> desktop: UTF-8 JSON object
const int headerSize = 5;

Uint8List packMessage(int type, Uint8List payload) {
  final header = ByteData(headerSize)
    ..setUint8(0, type)
    ..setUint32(1, payload.length, Endian.big);
  final builder = BytesBuilder(copy: false)
    ..add(header.buffer.asUint8List())
    ..add(payload);
  return builder.toBytes();
}

Uint8List packJson(Map<String, dynamic> message) =>
    packMessage(typeJson, Uint8List.fromList(utf8.encode(jsonEncode(message))));

/// Splits an incoming byte stream into complete (type, payload) messages.
class MessageReader {
  Uint8List _pending = Uint8List(0);

  List<(int, Uint8List)> feed(Uint8List chunk) {
    final bytes = _pending.isEmpty
        ? chunk
        : (BytesBuilder(copy: false)
              ..add(_pending)
              ..add(chunk))
            .toBytes();

    final messages = <(int, Uint8List)>[];
    var offset = 0;
    while (bytes.length - offset >= headerSize) {
      final header = ByteData.sublistView(bytes, offset, offset + headerSize);
      final type = header.getUint8(0);
      final length = header.getUint32(1, Endian.big);
      final start = offset + headerSize;
      if (bytes.length - start < length) break;
      messages.add((type, Uint8List.sublistView(bytes, start, start + length)));
      offset = start + length;
    }
    _pending = offset == bytes.length
        ? Uint8List(0)
        : Uint8List.sublistView(bytes, offset);
    return messages;
  }
}
