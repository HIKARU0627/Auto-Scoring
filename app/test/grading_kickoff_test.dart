import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/grading_kickoff.dart';

/// AI採点の起票が失敗したときの言い方 (Issue #80)。答案取込画面と添削レビュー
/// 画面が同じ関数を通るので、ここが2画面ぶんの文言の検証になる。
void main() {
  group('gradingKickoffErrorMessage', () {
    test('409 は確定DAG未確定と競合の両方の可能性を書き、どちらとも断定しない', () {
      // サイドカーはこの2つを同じ 409 で返し、`detail` は英語の内部
      // メッセージである。区別できないものを区別したふりをしない。
      final message = gradingKickoffErrorMessage(
        SidecarApiException(
          SidecarErrorKind.conflict,
          "test 'test-1' has no confirmed, up-to-date dependency graph",
          statusCode: 409,
        ),
      );

      expect(message, contains('設問依存関係が確定していない'));
      expect(message, contains('競合'));
      // サイドカーの英語メッセージをそのまま出さない。
      expect(message, isNot(contains('dependency graph')));
    });

    test('同時起票の競合も同じ文言になる', () {
      final message = gradingKickoffErrorMessage(
        SidecarApiException(
          SidecarErrorKind.conflict,
          'could not create jobs for submission ... please retry',
          statusCode: 409,
        ),
      );

      expect(
        message,
        gradingKickoffErrorMessage(
          SidecarApiException(
            SidecarErrorKind.conflict,
            'a different English detail',
            statusCode: 409,
          ),
        ),
      );
    });

    test('404 は答案が無いと言い、再試行を勧めない', () {
      final error = SidecarApiException(
        SidecarErrorKind.badResponse,
        'submission not found',
        statusCode: 404,
      );

      expect(gradingKickoffIsRetryable(error), isFalse);
      expect(gradingKickoffErrorMessage(error), contains('見つかりません'));
      expect(gradingKickoffErrorMessage(error), isNot(contains('お試し')));
    });

    test('通信できないときはサイドカーの理由を添えたうえで再試行できる', () {
      final error = SidecarApiException(
        SidecarErrorKind.unavailable,
        'sidecar is not reachable',
      );

      expect(gradingKickoffIsRetryable(error), isTrue);
      expect(
        gradingKickoffErrorMessage(error),
        'AI採点を開始できませんでした: sidecar is not reachable',
      );
    });
  });
}
