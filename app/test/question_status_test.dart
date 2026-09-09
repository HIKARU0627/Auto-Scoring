import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/design/app_status_tone.dart';
import 'package:auto_scoring_app/core/question_status.dart';

JobResponse _job({
  String state = 'running',
  bool? usable,
  String? blockedOnQuestionId,
  String questionId = 'q1',
  String? id,
  int createdAtSeconds = 0,
}) => JobResponse(
  (b) => b
    ..id = id ?? 'job-$questionId'
    ..kind = 'grading'
    ..submissionId = 'sub-1'
    ..questionId = questionId
    ..state = state
    ..usable = usable
    ..blockedOnQuestionId = blockedOnQuestionId
    ..attempts = 1
    ..maxAttempts = 3
    ..createdAt = DateTime.utc(
      2026,
      1,
      1,
    ).add(Duration(seconds: createdAtSeconds))
    ..updatedAt = DateTime.utc(
      2026,
      1,
      1,
    ).add(Duration(seconds: createdAtSeconds)),
);

ReviewResponse _review({
  String action = 'approved',
  String? regradeJobId,
  int createdAtSeconds = 0,
}) => ReviewResponse(
  (b) => b
    ..id = 'review-1'
    ..submissionId = 'sub-1'
    ..questionId = 'q1'
    ..action = action
    ..version = 1
    ..aiGradeResultId = 'grade-1'
    ..regradeJobId = regradeJobId
    ..createdAt = DateTime.utc(
      2026,
      1,
      1,
    ).add(Duration(seconds: createdAtSeconds)),
);

/// [deriveQuestionStatus] with the common case of the new
/// `hasWaitingDependents` argument filled in.
///
/// `false` is the default here because it is the shape almost every case in
/// this file is about, and because it is what the real material looks like:
/// across the two 実機再検証 runs, 21 confirmed dependency graphs over 92
/// questions held **0 edges** between them, so no question had a dependent
/// that could be waiting (Issue #156). The cases that are about the flag pass
/// it explicitly.
QuestionStatus _derive({
  required JobResponse? job,
  required ReviewResponse? review,
  bool hasWaitingDependents = false,
}) => deriveQuestionStatus(
  job: job,
  review: review,
  hasWaitingDependents: hasWaitingDependents,
);

void main() {
  group('deriveQuestionStatus', () {
    test('has no job and no review: 未処理', () {
      expect(_derive(job: null, review: null), QuestionStatus.pending);
    });

    test('maps each queue state to its own node state', () {
      for (final (state, expected) in const [
        ('blocked', QuestionStatus.blocked),
        ('queued', QuestionStatus.queued),
        ('running', QuestionStatus.running),
        ('failed', QuestionStatus.failed),
        ('cancelled', QuestionStatus.cancelled),
      ]) {
        expect(
          _derive(job: _job(state: state), review: null),
          expected,
          reason: state,
        );
      }
    });

    test('a live job outranks an older review decision', () {
      // Re-submission under a newer graph version, or a 再判定 request,
      // creates a fresh job while the append-only review history still holds
      // the previous attempt's 承認 -- showing 承認済み over it would say the
      // opposite of what is happening.
      expect(
        _derive(
          job: _job(state: 'running'),
          review: _review(),
        ),
        QuestionStatus.running,
      );
    });

    test('succeeded but not usable, with a dependent stuck behind it: 要確認', () {
      // The queue judged the result not good enough to release what depends
      // on it (docs/job-queue.md) and something is actually waiting -- the
      // one reading of `usable == false` that is about this reviewer.
      expect(
        _derive(
          job: _job(state: 'succeeded', usable: false),
          review: null,
          hasWaitingDependents: true,
        ),
        QuestionStatus.needsCheck,
      );
    });

    test('succeeded but not usable, with nothing waiting: レビュー待ち', () {
      // Issue #156. `Job.usable` decides 「後続の依存設問へ進んでよいか」, not
      // 「この設問を人間が見なくてよいか」 (docs/ai-grading-pipeline.md). With
      // no dependent behind it the flag stops nothing, and reading it as 要確認
      // put an attention badge on 11 of the 12 graded questions of 実機再検証 #4
      // -- material whose dependency graphs held 0 edges, so not one of those 11
      // was holding anything back. The question is in the state every other
      // graded question is in: finished, waiting for a person.
      expect(
        _derive(job: _job(state: 'succeeded', usable: false), review: null),
        QuestionStatus.graded,
      );
    });

    test('with nothing waiting, usable does not change the reading', () {
      // The corollary, and the reason the branch falls through rather than
      // being weakened in place: a question a person already approved must
      // not read differently for having had a low-Confidence OCR pass behind
      // it. Same inputs, both values of `usable`, one answer.
      //
      // The 承認 deliberately *predates* the job here, which is where the two
      // readings come apart: `usable == false` used to outrank a decision
      // older than the attempt (Issue #118's other half), so leaving the
      // 要確認 branch in place and merely relabelling its fallback would
      // still have shown レビュー待ち for this question while the identical
      // one with `usable == true` showed 承認済み.
      for (final usable in const [true, false]) {
        expect(
          _derive(
            job: _job(state: 'succeeded', usable: usable, createdAtSeconds: 2),
            review: _review(action: 'approved', createdAtSeconds: 1),
          ),
          QuestionStatus.approved,
          reason: 'usable=$usable',
        );
      }
    });

    test('a succeeded job carries the human decision when there is one', () {
      for (final (action, expected) in const [
        (null, QuestionStatus.graded),
        ('approved', QuestionStatus.approved),
        ('modified', QuestionStatus.approved),
        ('rejected', QuestionStatus.rejected),
        ('regrade_requested', QuestionStatus.regradeRequested),
        ('undone', QuestionStatus.graded),
      ]) {
        expect(
          _derive(
            job: _job(state: 'succeeded', usable: true),
            review: action == null ? null : _review(action: action),
          ),
          expected,
          reason: '$action',
        );
      }
    });

    test(
      'a stopped job does not outrank a decision made since (Issue #118)',
      () {
        // A job that failed, was cancelled, or finished with an untrustworthy
        // result is not going to describe anything newer. A person who has
        // graded the question by hand since then is the newer fact, and the
        // answer sheet already counts that question as 確認済み server-side --
        // leaving 失敗 here would have the rail, the DAG and the Inspector all
        // contradicting the submission's own state.
        for (final (state, usable) in const [
          ('failed', false),
          ('cancelled', null),
          ('succeeded', false),
        ]) {
          expect(
            _derive(
              job: _job(state: state, usable: usable, createdAtSeconds: 1),
              review: _review(action: 'modified', createdAtSeconds: 2),
              // So the `succeeded` row exercises the 要確認 branch rather than
              // the plain one -- the rule under test is that a decision made
              // since outranks it (Issue #118), and with nothing waiting there
              // would be no 要確認 to outrank.
              hasWaitingDependents: true,
            ),
            QuestionStatus.approved,
            reason: state,
          );
        }
      },
    );

    test('a stopped job still outranks a decision that predates it', () {
      // The other half of the same rule: a re-submission creates a fresh job
      // after an old 承認, and that approval is about the previous attempt.
      for (final (state, usable, expected) in const [
        ('failed', false, QuestionStatus.failed),
        ('cancelled', null, QuestionStatus.cancelled),
        ('succeeded', false, QuestionStatus.needsCheck),
      ]) {
        expect(
          _derive(
            job: _job(state: state, usable: usable, createdAtSeconds: 2),
            review: _review(action: 'modified', createdAtSeconds: 1),
            hasWaitingDependents: true,
          ),
          expected,
          reason: state,
        );
      }
    });

    test('再判定待ち ends when the job the request created succeeds', () {
      // Nothing ever closes a `regrade_requested` row -- the replacement
      // grade lands as a new GradeResult, not a new Review -- so treating
      // the action as the state left the node stuck on 再判定待ち with a
      // fresh grade on screen unmentioned (review round 1, P2).
      final review = _review(
        action: 'regrade_requested',
        regradeJobId: 'job-regrade',
      );
      expect(
        _derive(
          job: _job(state: 'succeeded', usable: true, id: 'job-regrade'),
          review: review,
        ),
        QuestionStatus.graded,
      );
      // Still outstanding while only the *superseded* attempt is known.
      expect(
        _derive(
          job: _job(state: 'succeeded', usable: true, id: 'job-original'),
          review: review,
        ),
        QuestionStatus.regradeRequested,
      );
    });

    test('再判定待ち also ends for any job that ran after the request', () {
      // The replacement job is normally named by the review, but a job
      // created afterwards for another reason (a re-submission under a newer
      // graph version) did not produce the result the reviewer rejected
      // either.
      final review = _review(action: 'regrade_requested', createdAtSeconds: 10);
      expect(
        _derive(
          job: _job(state: 'succeeded', usable: true, createdAtSeconds: 20),
          review: review,
        ),
        QuestionStatus.graded,
      );
      expect(
        _derive(
          job: _job(state: 'succeeded', usable: true, createdAtSeconds: 5),
          review: review,
        ),
        QuestionStatus.regradeRequested,
      );
    });
  });

  group('QuestionStatus presentation', () {
    test('every state has its own icon and label, not just a colour', () {
      // Issue #25's rule: colour only sharpens a distinction that already
      // survives without it.
      final labels = QuestionStatus.values.map((s) => s.label).toSet();
      final icons = QuestionStatus.values.map((s) => s.icon).toSet();
      expect(labels, hasLength(QuestionStatus.values.length));
      expect(icons, hasLength(QuestionStatus.values.length));
    });

    test('only 要確認 pulls the eye, and only a failure is danger', () {
      final attention = QuestionStatus.values
          .where((s) => s.tone == AppStatusTone.attention)
          .toSet();
      final danger = QuestionStatus.values
          .where((s) => s.tone == AppStatusTone.danger)
          .toSet();
      expect(attention, {QuestionStatus.needsCheck});
      expect(danger, {QuestionStatus.failed});
    });
  });
}
