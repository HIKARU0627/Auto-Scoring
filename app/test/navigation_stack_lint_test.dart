import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// 画面から画面へは `push` / `replace` / `pop` で移る。**`go` は使わない。**
///
/// go_router の `go` は現在地を指すだけの API ではなく、**積んであるスタックを
/// 丸ごと捨てて組み直す**。ルート表は `app_router.dart` で7本フラットに並んで
/// いるので、`go` の行き先には親ルートが無く、着いた画面には戻る先が1つも
/// 残らない -- アプリバーの戻る矢印が出ず、Escape も Alt+Left も効かない。
///
/// Issue #160 はそれが実機で起きたものである。答案キュー画面には入口が3つ
/// あり、ホームのテストカードとテスト一覧は `push`、添削レビューの
/// スナックバー「答案キューへ」だけが `go` だった。**同じ画面が、入口によって
/// 行き止まりになったりならなかったりしていた**。3つ目から入った講師は、
/// アプリを再起動するまでホームへ戻れなかった。
///
/// 入口ごとのテスト (`submission_queue_page_test.dart`、
/// `pdf_review_page_test.dart`) は「いまある3つ」を守るだけで、4つ目が
/// 足されたときには何も言わない。**このテストは入口の数に依らない。**
/// `mounted_after_await_lint_test.dart` と同じ考え方で、規約は何かが検査して
/// 初めて実在する。
///
/// スタックを捨ててよいのはコンポジションルート (`lib/main.dart`) だけである。
/// サイドカーが落ちたときに講師が積んだ画面を全部落とすのは、まさに「捨てる」
/// のが正しい操作で、そこには理由が書いてある。決定は
/// `docs/review-queue.md` §8.2。
void main() {
  test('画面のコードが go_router の go を呼んでいない', () {
    final dir = Directory('lib/features');
    expect(dir.existsSync(), isTrue, reason: '${dir.path} が見つからない');

    // `context.go(` / `GoRouter.of(context).go(` / `goNamed(` のいずれも。
    final clearsStack = RegExp(r'\.go(Named)?\(');
    final offenders = <String>[];
    for (final file in dir.listSync(recursive: true).whereType<File>()) {
      if (!file.path.endsWith('.dart')) continue;
      final lines = file.readAsLinesSync();
      for (var i = 0; i < lines.length; i++) {
        if (clearsStack.hasMatch(lines[i])) {
          offenders.add('${file.path}:${i + 1}: ${lines[i].trim()}');
        }
      }
    }

    expect(
      offenders,
      isEmpty,
      reason:
          'go はスタックを捨てるので、着いた画面が行き止まりになる (Issue #160)。'
          '画面間の移動は push / replace / pop を使うこと:\n'
          '${offenders.join('\n')}',
    );
  });
}
