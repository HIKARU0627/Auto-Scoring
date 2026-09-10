import 'dart:convert';
import 'dart:io';

import 'package:pdfrx/pdfrx.dart';

/// `flutter test` の下で本物の pdfium を使えるようにする。
///
/// `pdfium_dart` のローダは、**ビルド済みの** Flutter アプリの隣
/// (`<executable>/../lib/libpdfium.so`) か `.dart_tool/native_assets.yaml`
/// (これを書くのは `dart test` / `dart run` だけ) から pdfium を探す。Linux の
/// `flutter test` では実行ファイルが `flutter_tester` で native-assets ファイルも
/// 無いので、本物の PDF を描くテストが全部
/// 「Failed to load PDFium module」で落ちていた -- **テスト対象と何の関係も無い
/// 失敗**である (Issue #60)。Windows は素の `pdfium.dll` を OS の探索パスから
/// 解決するので CI では起きない。
///
/// ライブラリ自体はある。`flutter test` は `pdfium_dart` の build hook を走らせ、
/// hook が pdfium を落として `output.json` に記録している。その記録を読み直すのが
/// この関数で、**代用品ではなく本物の pdfium 経路のまま**テストを走らせられる。
///
/// Issue #145 で `pdf_review_page_test.dart` から出した -- 答案確定画面から
/// 添削レビュー画面へ入るテストも同じ下準備を要る。
void initializePdfiumForTests() {
  // pdfrxFlutterInitialize() は path_provider の getTemporaryDirectory() を
  // プラットフォームチャネル越しに呼ぶが、`flutter test` にその実装は無い
  // (MissingPluginException)。ここで先に入れておくとその呼び出しごと飛ばせる。
  // このサイズの fixture では書き込み可能なキャッシュは要らない。
  Pdfrx.cacheDirectoryPath = Directory.systemTemp.path;
  // ローダが自力で見つけられる環境では触らない (既定の解決に任せる)。
  final module = _hookBuiltPdfiumModule();
  if (module != null) Pdfrx.pdfiumModulePath = module;
}

/// `flutter test` がビルドしたが繋いでいない pdfium 共有ライブラリ。
/// この回り道が要らないプラットフォームでは `null`。
String? _hookBuiltPdfiumModule() {
  if (!Platform.isLinux) return null;
  final hookOutputs = Directory('.dart_tool/hooks_runner/pdfium_dart');
  if (!hookOutputs.existsSync()) return null;
  for (final run in hookOutputs.listSync().whereType<Directory>()) {
    final output = File('${run.path}/output.json');
    if (!output.existsSync()) continue;
    final decoded =
        jsonDecode(output.readAsStringSync()) as Map<String, dynamic>;
    for (final asset in decoded['assets'] as List<dynamic>? ?? const []) {
      final encoding =
          (asset as Map<String, dynamic>)['encoding'] as Map<String, dynamic>?;
      if (encoding?['id'] != 'package:pdfium_dart/libpdfium') continue;
      final file = encoding!['file'] as String?;
      if (file != null && File(file).existsSync()) return file;
    }
  }
  return null;
}
