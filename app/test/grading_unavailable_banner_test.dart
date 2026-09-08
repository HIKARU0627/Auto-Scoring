import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_theme.dart';
import 'package:auto_scoring_app/core/widgets/grading_unavailable_banner.dart';
import 'package:auto_scoring_app/main.dart';

/// Issue #97: 「この端末では採点できない」を画面で分かるようにする、という
/// 受入条件そのもののテスト。
///
/// 帯の**出さない**条件を厚く見ているのは意図的で、出しすぎる帯は
/// (「サイドカーが一度応えなかった」を「設定不備」と言い切る) 出ない帯より
/// 悪いため。
GradingAvailabilityResponse _availability({
  required bool available,
  String? reason,
}) => GradingAvailabilityResponse(
  (builder) => builder
    ..available = available
    ..reason = reason,
);

Future<void> _pumpBanner(
  WidgetTester tester,
  GradingAvailabilityResponse? availability,
) => tester.pumpWidget(
  MaterialApp(
    theme: AppTheme.light(),
    home: GradingUnavailableBanner(
      availability: availability,
      child: const Scaffold(body: Text('画面の中身')),
    ),
  ),
);

void main() {
  group('GradingUnavailableBanner', () {
    testWidgets('採点が使えないことと、他は使えることを出す', (tester) async {
      await _pumpBanner(
        tester,
        _availability(
          available: false,
          reason: 'AUTO_SCORING_AI_GRADING_TRANSPORT is required',
        ),
      );

      expect(find.byKey(const Key('grading-unavailable-headline')), findsOne);
      expect(find.textContaining('答案取込・添削レビュー・PDF出力'), findsOne);
      // 直せる人が読む唯一の手がかりなので、理由は落とさずそのまま出す。
      expect(
        find.text('AUTO_SCORING_AI_GRADING_TRANSPORT is required'),
        findsOne,
      );
      // 帯は画面を隠さない -- 下の中身はそのまま見えている。
      expect(find.text('画面の中身'), findsOne);
    });

    testWidgets('理由が無くても帯そのものは出す', (tester) async {
      await _pumpBanner(tester, _availability(available: false));

      expect(find.byKey(const Key('grading-unavailable-headline')), findsOne);
      expect(find.byKey(const Key('grading-unavailable-reason')), findsNothing);
    });

    testWidgets('採点が使えるときは何も出さない', (tester) async {
      await _pumpBanner(tester, _availability(available: true));

      expect(
        find.byKey(const Key('grading-unavailable-headline')),
        findsNothing,
      );
      expect(find.text('画面の中身'), findsOne);
    });

    testWidgets('まだ聞けていない (null) ときは何も出さない', (tester) async {
      await _pumpBanner(tester, null);

      expect(
        find.byKey(const Key('grading-unavailable-headline')),
        findsNothing,
      );
    });
  });

  group('AutoScoringApp', () {
    testWidgets('起動時にサイドカーへ問い合わせ、使えなければ画面の上に出す', (tester) async {
      await tester.pumpWidget(
        AutoScoringApp(
          dependencies: AppDependencies(
            gradingAvailability: () async => _availability(
              available: false,
              reason: 'AUTO_SCORING_OPENAI_API_KEY is not set',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('grading-unavailable-headline')), findsOne);
      // ホーム画面は開いたまま -- 採点以外は使える、という主張と実際が一致する。
      expect(find.text('Auto-Scoring'), findsWidgets);
      expect(tester.takeException(), isNull);
    });

    testWidgets('問い合わせに失敗しても帯は出さず、例外も投げない', (tester) async {
      await tester.pumpWidget(
        AutoScoringApp(
          dependencies: AppDependencies(
            gradingAvailability: () async => throw SidecarApiException(
              SidecarErrorKind.unavailable,
              'sidecar is not connected',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.byKey(const Key('grading-unavailable-headline')),
        findsNothing,
      );
      expect(tester.takeException(), isNull);
    });
  });
}
