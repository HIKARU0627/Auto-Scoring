/// 失敗したジョブから、画面に出してよい日本語を決める (Issue #86)。
///
/// ここが唯一 `Job.last_error` に触る場所なので、**生の診断文が返り値に
/// 混ざらないこと**もここで固定する。パネル側の検査
/// (`dependency_dag_panel_test.dart`) は画面に出ないことを見るが、
/// それは「出す側が黙っただけ」でも緑になる。両方から挟む。
library;

import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/core/dag_failure_guidance.dart';
import 'package:auto_scoring_app/core/grading_failure_reason.dart';

/// `jobs.grading_processor._failed` が実際に組み立てる形。provider 名・例外
/// クラス名・HTTPステータスが入っている (Issue #97 review round 4)。
const _realisticLastError =
    'gemini AI provider returned a malformed response '
    '[vertex-ai/gemini-2.5-pro SchemaViolation, https://aiplatform.googleapis.com 400]';

void main() {
  group('dagFailureGuidance', () {
    test('分類ごとに、次にできることが変わる', () {
      expect(
        dagFailureGuidance(errorCode: 'rate_limited'),
        DagFailureGuidance.rateLimited,
      );
      expect(
        dagFailureGuidance(errorCode: 'timeout'),
        DagFailureGuidance.temporary,
      );
      expect(
        dagFailureGuidance(errorCode: 'server_error'),
        DagFailureGuidance.temporary,
      );
      expect(
        dagFailureGuidance(errorCode: 'permanent'),
        DagFailureGuidance.permanent,
      );
    });

    test('分類が無い・知らない分類なら、両方の出口を出す', () {
      // 新しい sidecar が増やした分類を言い当てるより、再判定と手入力の
      // 両方を示すほうが正直である。
      expect(dagFailureGuidance(), DagFailureGuidance.unknown);
      expect(
        dagFailureGuidance(errorCode: 'quota_exhausted_v2'),
        DagFailureGuidance.unknown,
      );
      expect(
        DagFailureGuidance.unknown.nextStep,
        allOf(contains('再判定'), contains('点数を入力')),
      );
    });

    test('回答欄の取り違えは、permanent の一般的な出口より先に見る', () {
      // 再判定は同じ画像を同じモデルへ送り直すだけなので、「設定を見直す」
      // でも「もう一度AIに任せる」でもなく、回答欄の枠を直すのが復旧手段
      // である (Issue #136)。
      final guidance = dagFailureGuidance(
        errorCode: 'permanent',
        lastError:
            "gemini AI provider reported that the answer image is not this "
            "question's answer ($notTheAnswerCropReason)",
      );
      expect(guidance, DagFailureGuidance.answerAreaWrong);
      expect(guidance.nextStep, contains('回答欄'));
      // 「もう一度AIに任せる」を勧めない。勧めれば同じ結果を待たせることに
      // なる。
      expect(guidance.nextStep, isNot(contains('もう一度')));
    });

    test('返す文言に last_error の断片が入らない', () {
      // 分類のために読むが、載せはしない。provider 名・例外クラス名・URL・
      // HTTPステータスは画面に出す物ではない (AGENTS.md «Security»)。
      for (final code in [
        null,
        'timeout',
        'rate_limited',
        'server_error',
        'permanent',
      ]) {
        final guidance = dagFailureGuidance(
          errorCode: code,
          lastError: _realisticLastError,
        );
        final shown = '${guidance.cause}${guidance.nextStep}';
        for (final fragment in [
          'gemini',
          'vertex-ai',
          'SchemaViolation',
          'https://',
          '400',
        ]) {
          expect(
            shown,
            isNot(contains(fragment)),
            reason: '$code の文言に $fragment が漏れている',
          );
        }
      }
    });

    test('どの分類も、何が起きたかと次に何ができるかを両方言う', () {
      for (final guidance in DagFailureGuidance.values) {
        expect(guidance.cause, isNotEmpty);
        expect(guidance.nextStep, isNotEmpty);
        // 次の一手は必ず画面上の操作の名前で言う。「しばらくお待ちください」
        // のような、押す物の無い指示にしない。
        expect(
          guidance.nextStep,
          anyOf(
            contains('再判定'),
            contains('点数を入力'),
            contains('回答欄'),
            contains('設定'),
          ),
          reason: '${guidance.name} の次の一手が操作を名指していない',
        );
      }
    });
  });
}
