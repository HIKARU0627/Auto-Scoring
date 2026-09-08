import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/grading_kickoff.dart';

/// AI採点の起票が失敗したときの見せ方 (Issue #80)。答案取込画面と添削レビュー
/// 画面が同じ [GradingKickoffFailure] を通るので、ここが2画面ぶんの検証になる。
void main() {
  group('GradingKickoffFailure', () {
    test('409 は確定DAG未確定と競合の両方の可能性を書き、どちらとも断定しない', () {
      // サイドカーはこの2つを同じ 409 で返し、`detail` は英語の内部
      // メッセージである。区別できないものを区別したふりをしない。
      final failure = GradingKickoffFailure.of(
        SidecarApiException(
          SidecarErrorKind.conflict,
          "test 'test-1' has no confirmed, up-to-date dependency graph",
          statusCode: 409,
        ),
      );

      expect(failure.message, contains('設問依存関係が確定していない'));
      expect(failure.message, contains('競合'));
      // サイドカーの英語メッセージをそのまま出さない。
      expect(failure.message, isNot(contains('dependency graph')));
      expect(failure.retryable, isTrue);
    });

    test('同時起票の競合も同じ文言になる', () {
      String messageFor(String detail) => GradingKickoffFailure.of(
        SidecarApiException(SidecarErrorKind.conflict, detail, statusCode: 409),
      ).message;

      expect(
        messageFor('could not create jobs for submission ... please retry'),
        messageFor('a different English detail'),
      );
    });

    test('404 は答案が無いと言い、再試行できないものとして扱う', () {
      final failure = GradingKickoffFailure.of(
        SidecarApiException(
          SidecarErrorKind.badResponse,
          'submission not found',
          statusCode: 404,
        ),
      );

      expect(failure.retryable, isFalse);
      expect(failure.message, contains('見つかりません'));
      expect(failure.message, isNot(contains('お試し')));
    });

    test('通信できないときはサイドカーの理由を添えたうえで再試行できる', () {
      final failure = GradingKickoffFailure.of(
        SidecarApiException(
          SidecarErrorKind.unavailable,
          'sidecar is not reachable',
        ),
      );

      expect(failure.retryable, isTrue);
      expect(failure.message, 'AI採点を開始できませんでした: sidecar is not reachable');
    });

    test('文言と再試行可否は必ず一緒に決まる', () {
      // 別々の関数だった頃、添削レビュー画面が文言だけを使って再試行可否を
      // 握り潰した (review round 1, P2-2)。1つの値にしてあれば、片方だけを
      // 取り出すことができない。
      final failure = GradingKickoffFailure.of(
        SidecarApiException(
          SidecarErrorKind.badResponse,
          'submission not found',
          statusCode: 404,
        ),
      );

      expect(failure.message, isNotEmpty);
      expect(failure.retryable, isFalse);
    });
  });
}
