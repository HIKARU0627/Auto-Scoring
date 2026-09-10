import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/app_router.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/core/widgets/back_or_home_button.dart';
import 'package:auto_scoring_app/features/home/home_page.dart';

import 'app_harness.dart';

/// **ナビゲーションスタックが空の状態で開かれた画面から、ホームへ戻れる**
/// (Issue #88 受入条件3)。
///
/// 画面を1つずつ並べたテストにはしていない。**ルート表そのものを列挙する。**
/// `createAppRouter()` が持っている `GoRoute` を全部取り出し、パスの
/// `:パラメータ` を埋めて `initialLocation` に渡すので、そこに積まれるのは
/// その画面1枚だけ -- つまり `Navigator.canPop()` が偽の状態であり、Issue が
/// 言っている「戻る矢印そのものが出ない」状態そのものである。
///
/// 画面ごとに書いたテストは「いまある画面」しか守らない。#160 のときに入口ごとの
/// テストが4つ目の入口について何も言わなかったのと同じ形で、8本目の画面を足した
/// 人は、自分の画面のテストを書き忘れたことに気づけない。**このテストは画面の数に
/// 依らないので、書き忘れたら落ちる。**
///
/// 除外は [_skipped] に、理由付きで1か所に集めてある。除外したルートが実在する
/// ことも検査するので、パスを書き換えたらそこで落ちる -- 黙って効かなくなる形に
/// はしていない。
void main() {
  /// 列挙から外すルートと、その理由。
  const skipped = <String, String>{
    AppRoutes.starting:
        '画面ではない。`SidecarStartupOverlay` がアプリ全体を覆っている間の置き場で、'
        'ルータがここに居るときに見えているものは `Scaffold()` ではない '
        '(`app_router.dart`、`startup_gate_test.dart`)。',
    AppRoutes.submissionQueuePattern:
        '答案キュー。Issue #145 が同じ波でこのファイルを触っているので #88 では '
        '手を付けない。follow-up: Issue #192。',
    AppRoutes.pdfReviewPattern:
        '添削レビュー。同上、Issue #145 の担当範囲。follow-up: Issue #192。',
  };

  /// 出口を検査するルート。[skipped] と合わせてルート表を覆う (下のテスト)。
  const covered = <String>{
    AppRoutes.intake,
    AppRoutes.settings,
    AppRoutes.testList,
    AppRoutes.testSettingsPattern,
    AppRoutes.submissionConfirmPattern,
  };

  /// パスの `:param` を、下のフェイクが答えられる id で埋める。
  String fill(String path) =>
      path.replaceAll(':testId', 'test-1').replaceAll(':submissionId', 'sub-1');

  /// `lib/app_router.dart` が宣言しているトップレベルのパス。
  ///
  /// ルータをその場で捨てるのは、`main()` の本体 (テストの外) からも呼ぶから
  /// である -- `addTearDown` はテストの中でしか使えない。
  List<String> declaredPaths() {
    final router = createAppRouter();
    try {
      return [
        for (final route in router.configuration.routes)
          if (route is GoRoute) route.path,
      ];
    } finally {
      router.dispose();
    }
  }

  TestResponse buildTest() => TestResponse(
    (b) => b
      ..id = 'test-1'
      ..name = '国語 第1回'
      ..status = 'draft'
      ..createdAt = DateTime.utc(2026, 1, 1),
  );

  Never notFound() => throw SidecarApiException(
    SidecarErrorKind.badResponse,
    'not found',
    statusCode: 404,
  );

  // 画面が最初の読み込みを終えるところまで。どの画面も「読めなかった」状態で
  // 構わない -- このテストが見ているのは出口だけで、**出口は画面が失敗して
  // いても在るべきもの**である。
  final dependencies = AppDependencies(
    listTests: () async => [
      TestSummary(
        (b) => b
          ..id = 'test-1'
          ..name = '国語 第1回',
      ),
    ],
    listTestRegistrations: () async => [buildTest()],
    getTest: (_) async => buildTest(),
    listSubmissions: (_) async => const [],
    getProfile: (_) async => notFound(),
    getDependencyGraph: (_) async => notFound(),
    getSubmission: (_) async => notFound(),
  );

  test('除外したルートは実在する', () {
    // 除外リストが黙って効かなくなるのを防ぐ。パスを書き換えた人は、ここで
    // 「その行も直せ」と言われる。
    expect(declaredPaths(), containsAll(skipped.keys));
  });

  test('ルート表の全ルートが、検査対象か除外のどちらかに入っている', () {
    // **このテストが、下の検査を画面の数に依らないものにしている。**
    //
    // [covered] を直接回すだけなら、8本目の画面を足した人がそこへ足し忘れても
    // 何も起きない。ここがルート表と突き合わせるので、足し忘れは「対象に入れるか、
    // 理由を書いて skipped へ」という失敗になる。
    //
    // ルータを `main()` の本体で作らずテストの中で作るのは、`GoRouter` が
    // `WidgetsBinding` を初期化してしまい、`testWidgets` のバインディングと
    // 衝突するからである。
    expect(declaredPaths(), isNotEmpty);
    expect(
      declaredPaths().where((path) => path != AppRoutes.home).toSet(),
      {...skipped.keys, ...covered},
      reason:
          '画面を足したなら、covered に入れるか、理由を書いて skipped へ。'
          '「ホームへ戻れない画面」を黙って増やさないための一覧である。',
    );
  });

  for (final path in covered) {
    final location = fill(path);

    testWidgets('$location: スタックが空でもホームへ戻れる', (tester) async {
      await pumpAppAt(tester, location, dependencies: dependencies);
      await tester.pumpAndSettle();

      // 前提の確認。これが真だと、この画面は既定の戻る矢印で戻れてしまい、
      // 以下は #88 が心配している状態を試していないことになる。
      expect(
        find.byType(BackButton),
        findsNothing,
        reason: 'スタックが空のはずなのに、Material の既定の戻る矢印が出ている',
      );

      final escape = find.byKey(BackOrHomeButton.widgetKey);
      expect(escape, findsOneWidget, reason: '$location に出口が無い');

      await tester.tap(escape);
      await tester.pumpAndSettle();

      expect(find.byType(HomePage), findsOneWidget);
    });

    testWidgets('$location: 狭幅 700x720 でも出口が押せる', (tester) async {
      // 受入条件4。狭い窓で AppBar の actions に押し出されて消えていないか。
      tester.view.physicalSize = const Size(700, 720);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await pumpAppAt(tester, location, dependencies: dependencies);
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(BackOrHomeButton.widgetKey));
      await tester.pumpAndSettle();

      expect(find.byType(HomePage), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('$location: キーボードだけでホームへ戻れる', (tester) async {
      // 受入条件4。ポインタを一度も使わない。Tab で出口まで行き、Enter で押す。
      await pumpAppAt(tester, location, dependencies: dependencies);
      await tester.pumpAndSettle();

      var reached = false;
      for (var i = 0; i < 40; i++) {
        await tester.sendKeyEvent(LogicalKeyboardKey.tab);
        await tester.pumpAndSettle();
        final focused = primaryFocus?.context?.widget;
        if (focused != null &&
            find
                .descendant(
                  of: find.byKey(BackOrHomeButton.widgetKey),
                  matching: find.byWidget(focused),
                )
                .evaluate()
                .isNotEmpty) {
          reached = true;
          break;
        }
      }
      expect(reached, isTrue, reason: '$location: Tab で出口に到達できない');

      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();

      expect(find.byType(HomePage), findsOneWidget);
    });
  }

  testWidgets('ホームでは出口を出さない', (tester) async {
    // ホームに「ホームへ戻る」を出すのは、押しても何も起きないボタンを1つ
    // 増やすだけである。
    await pumpAppAt(tester, AppRoutes.home, dependencies: dependencies);
    await tester.pumpAndSettle();

    expect(find.byKey(BackOrHomeButton.widgetKey), findsNothing);
  });

  testWidgets('積んで入った画面では、出口はひとつ前へ戻る', (tester) async {
    // 既定の振る舞いを置き換えたので、置き換えた先が既定と同じことを確かめる。
    // ここが壊れると、講師は画面を1枚めくるたびにホームへ飛ばされる。
    await pumpAppAt(tester, AppRoutes.home, dependencies: dependencies);
    await tester.pumpAndSettle();

    final context = tester.element(find.byType(HomePage));
    context.push(AppRoutes.testList);
    await tester.pumpAndSettle();
    context.push(AppRoutes.intake);
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(BackOrHomeButton.widgetKey));
    await tester.pumpAndSettle();

    // テスト一覧 -- ホームではない。
    expect(find.text('テスト一覧'), findsOneWidget);
    expect(find.byType(HomePage), findsNothing);
  });
}
