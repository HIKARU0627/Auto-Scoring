import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/core/widgets/disabled_action_reason.dart';

import 'app_harness.dart';

/// 無効なボタンの横に、**何を満たせば有効になるかが実際に出ている**
/// (Issue #88 受入条件1)。
///
/// 条件の組み合わせそのものは `action_requirements_test.dart` が総当たりする。
/// ここが見るのは画面側の3点だけである。
///
/// * 無効なボタンのそばに理由が描かれている（ツールチップではなく `Text` として）。
/// * 条件を満たすと、その理由が消える。余白も残さない。
/// * 狭幅 700x720 でもキーボードだけでも破綻しない (受入条件4)。
///
/// 画面ごとの理由は、その画面のテストファイルにも足してある -- テスト設定画面の
/// 回答欄まわりは `test_settings_page_test.dart`、資料取込の提案確認は
/// `intake_page_test.dart`。ここに集めたのは、**出し方そのもの**を見る分である。
void main() {
  Finder reason(String id) => find.byKey(Key('disabled-reason-$id'));

  IntakeTemplateModel template() => IntakeTemplateModel(
    (builder) => builder
      ..id = 'serial-number-prefix'
      ..name = '連番の接頭辞 (既定)'
      ..splitChildDirectories = true
      ..rules.replace(const <IntakeRuleModel>[]),
  );

  AppDependencies intakeDeps({required bool anyTemplate}) => AppDependencies(
    listTests: () async => const [],
    listIntakeTemplates: () async => anyTemplate ? [template()] : const [],
    intakeCost: () async => null,
    classificationAvailability: () async =>
        ClassificationAvailabilityResponse((b) => b..available = true),
  );

  group('資料取込: フォルダを選ぶ', () {
    testWidgets('型が1つも無いとき、ボタンは無効で、理由がその場に出る', (tester) async {
      await pumpAppAt(
        tester,
        AppRoutes.intake,
        dependencies: intakeDeps(anyTemplate: false),
      );
      await tester.pumpAndSettle();

      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('intake-choose-folder')))
            .onPressed,
        isNull,
      );
      expect(reason('intake-template'), findsOneWidget);
      // ツールチップではなく、ツリーに居る文字である -- ポインタを当てなくても
      // 読めるので、キーボードだけの人にも届く (受入条件1)。
      expect(
        find.ancestor(
          of: reason('intake-template'),
          matching: find.byType(Tooltip),
        ),
        findsNothing,
      );
    });

    testWidgets('型が選ばれると、ボタンが有効になり理由が消える', (tester) async {
      await pumpAppAt(
        tester,
        AppRoutes.intake,
        dependencies: intakeDeps(anyTemplate: true),
      );
      await tester.pumpAndSettle();

      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('intake-choose-folder')))
            .onPressed,
        isNotNull,
      );
      expect(reason('intake-template'), findsNothing);
      // 消えるだけでなく、縦の場所も取らない (`SizedBox.shrink`)。幅は
      // `ListView` が横いっぱいに伸ばすので見ない。
      expect(find.byType(DisabledActionReason), findsOneWidget);
      expect(
        tester.getSize(find.byType(DisabledActionReason)).height,
        0,
        reason: '理由が消えたのに余白だけ残っている',
      );
    });

    testWidgets('狭幅 700x720 でも理由が画面内に収まる', (tester) async {
      tester.view.physicalSize = const Size(700, 720);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await pumpAppAt(
        tester,
        AppRoutes.intake,
        dependencies: intakeDeps(anyTemplate: false),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      final box = tester.getRect(reason('intake-template'));
      expect(box.width, greaterThan(0));
      expect(box.right, lessThanOrEqualTo(700));
    });
  });

  group('設定: API キー', () {
    ApiKeyStatusModel slot({required bool configured}) => ApiKeyStatusModel(
      (builder) => builder
        ..id = 'openrouter'
        ..label = 'OpenRouter'
        ..transport = 'openrouter'
        ..configured = configured
        ..keySource = configured
            ? ConfigurationSource.credentialStore
            : ConfigurationSource.none
        ..keyVariable = 'AUTO_SCORING_OPENROUTER_API_KEY'
        ..model = 'google/gemini-2.5-flash'
        ..modelVariable = 'AUTO_SCORING_OPENROUTER_MODEL'
        ..modelSource = ConfigurationSource.builtinDefault
        ..textSettings.replace(const [])
        ..authNote = ''
        ..consoleUrl = 'https://openrouter.ai/settings/keys',
    );

    AppDependencies apiKeyDeps({
      required bool configured,
      String? storeUnavailableReason,
    }) {
      final settings = ApiKeySettingsResponse(
        (builder) => builder
          ..storeUnavailableReason = storeUnavailableReason
          ..transportOrder = 'openrouter'
          ..transportSource = ConfigurationSource.builtinDefault
          ..transportOrderStored = false
          ..availableTransports.replace(const [
            'gemini',
            'codex_app_server',
            'openrouter',
            'openai',
          ])
          ..restartRequired = false
          ..keys.replace([slot(configured: configured)]),
      );
      return AppDependencies(
        listTests: () async => const [],
        listIntakeTemplates: () async => const [],
        intakeCost: () async => null,
        apiKeySettings: () async => settings,
      );
    }

    Future<void> openTab(
      WidgetTester tester,
      AppDependencies dependencies,
    ) async {
      await pumpAppAt(tester, AppRoutes.settings, dependencies: dependencies);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('settings-tab-api-key')));
      await tester.pumpAndSettle();
    }

    testWidgets('キーが無いとき、疎通の確認が無効で、理由が出る', (tester) async {
      await openTab(tester, apiKeyDeps(configured: false));

      expect(
        tester
            .widget<OutlinedButton>(
              find.byKey(const Key('settings-api-key-verify-openrouter')),
            )
            .onPressed,
        isNull,
      );
      expect(reason('api-key-not-configured'), findsOneWidget);
      // 保存は押せるので、そちらの理由は出ない。無効でないボタンの理由が出る形
      // だと、2つ並んだボタンのどちらが塞がっているのか読めなくなる。
      expect(reason('credential-store-unavailable'), findsNothing);
    });

    testWidgets('キーが入っていれば、疎通の理由は消える', (tester) async {
      await openTab(tester, apiKeyDeps(configured: true));

      expect(
        tester
            .widget<OutlinedButton>(
              find.byKey(const Key('settings-api-key-verify-openrouter')),
            )
            .onPressed,
        isNotNull,
      );
      expect(reason('api-key-not-configured'), findsNothing);
    });

    testWidgets('資格情報ストアが使えないとき、保存が無効で、代わりの手が出る', (tester) async {
      await openTab(
        tester,
        apiKeyDeps(
          configured: false,
          storeUnavailableReason: 'この PC には資格情報ストアがありません。',
        ),
      );

      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('settings-api-key-save-openrouter')),
            )
            .onPressed,
        isNull,
      );
      expect(reason('credential-store-unavailable'), findsOneWidget);
      // 同じことを入力欄の helperText にも書かない (Issue #88)。2か所に置くと、
      // 片方だけが古くなる。
      expect(find.text('この PC ではキーを保存できません。'), findsNothing);
    });

    testWidgets('キーボードだけで、理由の隣のボタンまで到達して押せる', (tester) async {
      // 理由は `Text` なのでフォーカスを取らない。つまり理由を足したことで
      // Tab の順番が壊れていないこと (受入条件4)。
      var verified = 0;
      final dependencies = AppDependencies(
        listTests: () async => const [],
        listIntakeTemplates: () async => const [],
        intakeCost: () async => null,
        apiKeySettings: () async => ApiKeySettingsResponse(
          (builder) => builder
            ..transportOrder = 'openrouter'
            ..transportSource = ConfigurationSource.builtinDefault
            ..transportOrderStored = false
            ..availableTransports.replace(const [
              'gemini',
              'codex_app_server',
              'openrouter',
              'openai',
            ])
            ..restartRequired = false
            ..keys.replace([slot(configured: true)]),
        ),
        verifyApiKey: (slotId) async {
          verified++;
          return VerifyApiKeyResponse(
            (builder) => builder
              ..result = 'ok'
              ..detail = '疎通しました'
              ..keySource = ConfigurationSource.credentialStore,
          );
        },
      );
      await openTab(tester, dependencies);

      final verify = find.byKey(
        const Key('settings-api-key-verify-openrouter'),
      );
      var reached = false;
      for (var i = 0; i < 60 && !reached; i++) {
        await tester.sendKeyEvent(LogicalKeyboardKey.tab);
        await tester.pumpAndSettle();
        final focused = primaryFocus?.context?.widget;
        reached =
            focused != null &&
            find
                .descendant(of: verify, matching: find.byWidget(focused))
                .evaluate()
                .isNotEmpty;
      }
      expect(reached, isTrue, reason: 'Tab で「疎通を確認する」に到達できない');

      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();

      expect(verified, 1);
    });
  });
}
