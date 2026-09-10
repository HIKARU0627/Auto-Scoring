import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'package:auto_scoring_app/core/app_routes.dart';

/// どの画面からも**必ず**出られるようにする `AppBar.leading` (Issue #88)。
///
/// これまで画面は `AppBar` の既定動作に任せていた。既定は「ひとつ前の画面が
/// スタックに残っていれば戻る矢印を出す」で、残っていなければ**何も出さない**。
/// ホームからたどって入るかぎりそれで戻れるが、スタックが空の状態で画面が
/// 開かれると出口が1つも無い画面になる。今の起動経路ではそうならない --
/// 通常の起動は必ずホームから始まる -- が、それは「その経路がまだ無いから」で
/// あって、直っているからではない。`lib/app_router.dart` のルート表は7本
/// フラットに並んでいるので、go_router 側にも親ルートという逃げ道は無い。
///
/// だから出口は既定動作ではなくこの widget が持つ:
///
/// * 戻れるなら、ひとつ前の画面へ (`pop`) -- 既定と同じ振る舞い。
/// * 戻れないなら、ホームへ (`replace`)。`push` ではないのは、行き止まりの
///   画面をスタックに残さないためである。
///
/// `go` は使わない。あれは積んであるスタックを丸ごと捨てるので、今度は着いた
/// 先が行き止まりになる (Issue #160、`test/navigation_stack_lint_test.dart`)。
///
/// `IconButton` なので Tab で到達でき、Enter / Space で押せる。ツールチップは
/// ポインタを使う人への補助で、**導線そのものはアイコンとラベルが持つ** --
/// ツールチップだけに意味を載せると、キーボードだけの人に届かない。
///
/// 検査は `test/home_escape_test.dart` が**ルート表を列挙して**行う。画面を
/// 1つ足してこれを置き忘れたら、そのテストが落ちる。
class BackOrHomeButton extends StatelessWidget {
  const BackOrHomeButton({super.key});

  /// ルート表を列挙するテストが探す `Key`。
  static const Key widgetKey = Key('app-back-or-home');

  @override
  Widget build(BuildContext context) {
    final canPop = Navigator.of(context).canPop();
    return IconButton(
      key: widgetKey,
      // 形が行き先を言う: 矢印は「ひとつ前」、家は「ホーム」。色は使わない。
      icon: Icon(canPop ? Icons.arrow_back : Icons.home_outlined),
      tooltip: canPop ? '前の画面へ戻る' : 'ホームへ戻る',
      onPressed: () {
        if (canPop) {
          Navigator.of(context).pop();
          return;
        }
        context.replace(AppRoutes.home);
      },
    );
  }
}
