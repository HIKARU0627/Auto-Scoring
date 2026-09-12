import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/core/sidecar_restart.dart';

import 'app_harness.dart';

/// 設定画面の「API キー」タブ (Issue #96).
///
/// The rule every test here defends: **a key goes in and does not come back
/// out.** The sidecar never sends one, so the screen has none to display --
/// but a screen that quietly kept the value in its text field, or built a
/// masked preview from it, would put it back on the glass. The two "not on
/// screen" tests fail if either happens.
void main() {
  const fakeKey = 'fake-openrouter-key-DO-NOT-USE-4c1f9a';

  ApiKeyStatusModel slot({
    bool configured = false,
    ConfigurationSource keySource = ConfigurationSource.none,
  }) => ApiKeyStatusModel(
    (builder) => builder
      ..id = 'openrouter'
      ..label = 'OpenRouter'
      ..transport = 'openrouter'
      ..configured = configured
      ..keySource = keySource
      ..keyVariable = 'AUTO_SCORING_OPENROUTER_API_KEY'
      ..model = 'google/gemini-2.5-flash'
      ..modelVariable = 'AUTO_SCORING_OPENROUTER_MODEL'
      ..modelSource = ConfigurationSource.builtinDefault
      ..textSettings.replace(const [])
      ..authNote = ''
      ..consoleUrl = 'https://openrouter.ai/settings/keys',
  );

  ApiKeySettingsResponse settings({
    ApiKeyStatusModel? key,
    String? storeUnavailableReason,
    String transportOrder = 'openrouter',
    ConfigurationSource transportSource = ConfigurationSource.builtinDefault,
    bool restartRequired = false,
  }) => ApiKeySettingsResponse(
    (builder) => builder
      ..storeUnavailableReason = storeUnavailableReason
      ..transportOrder = transportOrder
      ..transportSource = transportSource
      ..transportOrderStored = false
      ..availableTransports.replace(const [
        'gemini',
        'codex_app_server',
        'openrouter',
        'openai',
      ])
      ..restartRequired = restartRequired
      ..keys.replace([key ?? slot()]),
  );

  VerifyApiKeyResponse verification(String result, String detail) =>
      VerifyApiKeyResponse(
        (builder) => builder
          ..result = result
          ..detail = detail
          ..keySource = ConfigurationSource.credentialStore,
      );

  Future<void> openTab(
    WidgetTester tester, {
    required AppDependencies dependencies,
    RestartSidecar? restart,
  }) async {
    await pumpAppAt(
      tester,
      AppRoutes.settings,
      dependencies: dependencies,
      overrides: [restartSidecarProvider.overrideWithValue(restart)],
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('settings-tab-api-key')));
    await tester.pumpAndSettle();
  }

  AppDependencies deps({
    required ApiKeySettingsResponse initial,
    Future<ApiKeySettingsResponse> Function(String, String)? saveApiKey,
    Future<ApiKeySettingsResponse> Function(String)? deleteApiKey,
    Future<VerifyApiKeyResponse> Function(String)? verifyApiKey,
  }) => AppDependencies(
    listIntakeTemplates: () async => const [],
    intakeCost: () async => null,
    apiKeySettings: () async => initial,
    saveApiKey: saveApiKey ?? (slotId, value) async => initial,
    deleteApiKey: deleteApiKey ?? (slotId) async => initial,
    verifyApiKey: verifyApiKey ?? (slotId) async => verification('ok', 'ok'),
  );

  testWidgets('キーが未設定なら「未設定」と出て、疎通ボタンは押せない', (tester) async {
    await openTab(tester, dependencies: deps(initial: settings()));

    expect(
      find.byKey(const Key('settings-api-key-status-openrouter')),
      findsOneWidget,
    );
    expect(
      tester
          .widget<Text>(
            find.byKey(const Key('settings-api-key-status-openrouter')),
          )
          .data,
      '未設定',
    );
    final verify = tester.widget<OutlinedButton>(
      find.byKey(const Key('settings-api-key-verify-openrouter')),
    );
    expect(verify.onPressed, isNull);
  });

  testWidgets('保存すると入力値が送られ、画面には残らない (受入条件: 値を再表示しない)', (tester) async {
    String? sentSlot;
    String? sentValue;
    await openTab(
      tester,
      dependencies: deps(
        initial: settings(),
        saveApiKey: (slotId, value) async {
          sentSlot = slotId;
          sentValue = value;
          return settings(
            key: slot(
              configured: true,
              keySource: ConfigurationSource.credentialStore,
            ),
            restartRequired: true,
          );
        },
      ),
    );

    await tester.enterText(
      find.byKey(const Key('settings-api-key-field-openrouter')),
      fakeKey,
    );
    await tester.tap(find.byKey(const Key('settings-api-key-save-openrouter')));
    await tester.pumpAndSettle();

    expect(sentSlot, 'openrouter');
    expect(sentValue, fakeKey);
    // The field is empty again, and nothing anywhere on the screen renders
    // the value -- not even a masked prefix of it.
    expect(find.text(fakeKey), findsNothing);
    expect(
      tester
          .widget<EditableText>(
            find.descendant(
              of: find.byKey(const Key('settings-api-key-field-openrouter')),
              matching: find.byType(EditableText),
            ),
          )
          .controller
          .text,
      isEmpty,
    );
  });

  testWidgets('保存済みのキーは、再読み込みしても値が出ない', (tester) async {
    await openTab(
      tester,
      dependencies: deps(
        initial: settings(
          key: slot(
            configured: true,
            keySource: ConfigurationSource.credentialStore,
          ),
        ),
      ),
    );

    expect(
      tester
          .widget<Text>(
            find.byKey(const Key('settings-api-key-status-openrouter')),
          )
          .data,
      '保存済み（この PC の資格情報ストア）',
    );
    expect(find.text(fakeKey), findsNothing);
  });

  testWidgets('環境変数から読んだキーは、そう表示される', (tester) async {
    await openTab(
      tester,
      dependencies: deps(
        initial: settings(
          key: slot(
            configured: true,
            keySource: ConfigurationSource.environment,
          ),
        ),
      ),
    );

    expect(
      tester
          .widget<Text>(
            find.byKey(const Key('settings-api-key-status-openrouter')),
          )
          .data,
      contains('環境変数'),
    );
    // Nothing to delete: this app did not store it, and it must not claim
    // it can remove someone's `.env.local`.
    expect(
      find.byKey(const Key('settings-api-key-delete-openrouter')),
      findsNothing,
    );
  });

  testWidgets('provider の優先順とその出どころが読める', (tester) async {
    await openTab(
      tester,
      dependencies: deps(
        initial: settings(
          transportOrder: 'gemini,codex_app_server,openrouter,openai',
          transportSource: ConfigurationSource.environment,
        ),
      ),
    );

    expect(
      tester
          .widget<Text>(
            find.byKey(const Key('settings-api-key-transport-order')),
          )
          .data,
      'gemini,codex_app_server,openrouter,openai',
    );
    expect(
      find.textContaining('環境変数 AUTO_SCORING_AI_GRADING_TRANSPORT'),
      findsOneWidget,
    );
  });

  testWidgets('疎通の結果は、成功・認証失敗・不通で別々に出る', (tester) async {
    for (final (result, detail) in [
      ('ok', '疎通しました。'),
      ('unauthorized', 'キーが受け付けられませんでした。'),
      ('unreachable', 'provider に接続できませんでした。'),
    ]) {
      await openTab(
        tester,
        dependencies: deps(
          initial: settings(
            key: slot(
              configured: true,
              keySource: ConfigurationSource.credentialStore,
            ),
          ),
          verifyApiKey: (slotId) async => verification(result, detail),
        ),
      );

      await tester.tap(
        find.byKey(const Key('settings-api-key-verify-openrouter')),
      );
      await tester.pumpAndSettle();

      expect(
        tester
            .widget<Text>(
              find.byKey(const Key('settings-api-key-verification-openrouter')),
            )
            .data,
        detail,
        reason: 'each outcome needs its own wording, not one shared banner',
      );
    }
  });

  testWidgets('資格情報ストアが無い環境では、保存できないことを言い、保存ボタンを閉じる', (tester) async {
    await openTab(
      tester,
      dependencies: deps(
        initial: settings(storeUnavailableReason: 'この環境では OS の資格情報ストアを利用できません'),
      ),
    );

    expect(
      find.byKey(const Key('settings-api-key-store-unavailable')),
      findsOneWidget,
    );
    expect(
      tester
          .widget<FilledButton>(
            find.byKey(const Key('settings-api-key-save-openrouter')),
          )
          .onPressed,
      isNull,
    );
  });

  testWidgets('保存しただけでは採点に効かないと言い、その場で再起動できる', (tester) async {
    var restarted = 0;
    await openTab(
      tester,
      dependencies: deps(initial: settings(restartRequired: true)),
      restart: () async => restarted++,
    );

    expect(
      find.byKey(const Key('settings-api-key-restart-required')),
      findsOneWidget,
    );
    await tester.tap(find.byKey(const Key('settings-api-key-restart')));
    await tester.pumpAndSettle();

    expect(restarted, 1);
  });

  testWidgets('再起動できない起動方法では、代わりに何をすればよいか書く', (tester) async {
    await openTab(
      tester,
      dependencies: deps(initial: settings(restartRequired: true)),
    );

    expect(find.byKey(const Key('settings-api-key-restart')), findsNothing);
    expect(find.textContaining('アプリを起動し直して'), findsOneWidget);
  });

  testWidgets('保存に失敗したら、失敗したと言う', (tester) async {
    await openTab(
      tester,
      dependencies: deps(
        initial: settings(),
        saveApiKey: (slotId, value) async => throw SidecarApiException(
          SidecarErrorKind.unavailable,
          'キーを保存できませんでした。',
        ),
      ),
    );

    await tester.enterText(
      find.byKey(const Key('settings-api-key-field-openrouter')),
      fakeKey,
    );
    await tester.tap(find.byKey(const Key('settings-api-key-save-openrouter')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('settings-api-key-error')), findsOneWidget);
    expect(find.text(fakeKey), findsNothing);
  });
}
