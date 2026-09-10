/// 一括出力の「実際にファイルを置く」側 (Issue #142)。
///
/// `bulk_export.dart` から切ってあるのは、あちらを `dart:io` 無しで
/// テストできるようにするためである -- 40枚を流す最中の畳み方に本物の
/// フォルダは要らない。
library;

import 'dart:io';
import 'dart:typed_data';

import 'package:file_picker/file_picker.dart' as picker;
import 'package:path/path.dart' as p;

/// 出力先フォルダを1回だけ選ばせる。キャンセルされたら `null`。
Future<String?> chooseBulkExportDirectory() =>
    picker.FilePicker.getDirectoryPath();

/// [directory] へ [fileName] で書き、**実際に書いたパス**を返す。
///
/// 既にある名前は決して上書きしない。上書きは講師が既に受け取った添削PDFを
/// 黙って消すことで、業務ルール §2 (15)「過去の出力を上書きしない」に真っ向
/// から反する。サイドカーが `app-data/` の中でしているのと同じように、
/// `_2`, `_3` と番号を足して逃がす。
Future<String> writeBulkExportFile(
  String directory,
  String fileName,
  Uint8List bytes,
) async {
  final path = _freePath(directory, fileName);
  await File(path).writeAsBytes(bytes, flush: true);
  return path;
}

String _freePath(String directory, String fileName) {
  final stem = p.basenameWithoutExtension(fileName);
  final extension = p.extension(fileName);
  var candidate = p.join(directory, fileName);
  var counter = 2;
  while (File(candidate).existsSync()) {
    candidate = p.join(directory, '${stem}_$counter$extension');
    counter += 1;
  }
  return candidate;
}
