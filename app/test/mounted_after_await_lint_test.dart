import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Keeps `setState` on the 添削レビュー画面 behind its guarded wrapper.
///
/// 「`await` のあとに `mounted` を見る」という規律は、このコードベースで3回
/// 破られている -- Issue #66（破棄後の `ref.read` が `StateError`）、
/// Issue #64（画面離脱中の pending request、テスト名 "leaving the screen
/// mid-request" が残っている）、Issue #80（「AI採点を開始」の応答が、
/// レビュアーが画面を離れたあとに返る）。3回とも**未処理例外**になった。
///
/// 規律だけでは止まらなかったので、`_PdfReviewPageState` では
/// `setState` を直接呼ばず `_setStateIfMounted` を通す
/// （その docstring に「誰が中止の責任を持つか」の決定が書いてある）。
/// **その約束を守らせるのがこのテスト**である。`architecture_test.dart` や
/// `design_tokens_lint_test.dart` と同じ考え方で、規約は何かが検査して初めて
/// 実在する。
///
/// これは規律の代わりではなく後ろ盾である。`await` のあとで `mounted` を
/// 見る責任は、`await` した関数自身にある（`Timer` やコントローラ呼び出しは
/// この wrapper では守れない）。
void main() {
  test('添削レビュー画面が素の setState を呼んでいない', () {
    final file = File('lib/features/pdf_review/pdf_review_page.dart');
    expect(file.existsSync(), isTrue, reason: '${file.path} が見つからない');

    // `_setStateIfMounted` の中身の1回だけが正当な `setState` である。
    // 直前に `.` や識別子が来るもの（`_setStateIfMounted(`）は数えない。
    final bare = RegExp(r'(?<![\w.])setState\(');
    final offenders = <String>[];
    final lines = file.readAsLinesSync();
    for (var i = 0; i < lines.length; i++) {
      if (!bare.hasMatch(lines[i])) continue;
      // wrapper 本体。ここだけは素の呼び出しでよい。
      final isWrapperBody =
          i > 0 && lines[i - 1].contains('if (!mounted) return;');
      if (isWrapperBody) continue;
      offenders.add('${i + 1}: ${lines[i].trim()}');
    }

    expect(
      offenders,
      isEmpty,
      reason:
          '素の setState は破棄後に呼ばれると未処理例外になる。'
          '_setStateIfMounted を使うこと（同メソッドの docstring を読むこと）:\n'
          '${offenders.join('\n')}',
    );
  });
}
