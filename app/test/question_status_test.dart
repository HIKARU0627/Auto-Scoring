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

void main() {
  group('deriveQuestionStatus', () {
    test('has no job and no review: 未処理', () {
      expect(
        deriveQuestionStatus(job: null, review: null),
        QuestionStatus.pending,
      );
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
          deriveQuestionStatus(job: _job(state: state), review: null),
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
        deriveQuestionStatus(
          job: _job(state: 'running'),
          review: _review(),
        ),
        QuestionStatus.running,
      );
    });

    test('succeeded but not usable is 要確認, not レビュー待ち', () {
      // The queue itself judged the result untrustworthy and is holding
      // everything downstream (docs/job-queue.md) -- a stronger statement
      // than "nobody has reviewed it yet".
      expect(
        deriveQuestionStatus(
          job: _job(state: 'succeeded', usable: false),
          review: null,
        ),
        QuestionStatus.needsCheck,
      );
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
          deriveQuestionStatus(
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
            deriveQuestionStatus(
              job: _job(state: state, usable: usable, createdAtSeconds: 1),
              review: _review(action: 'modified', createdAtSeconds: 2),
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
          deriveQuestionStatus(
            job: _job(state: state, usable: usable, createdAtSeconds: 2),
            review: _review(action: 'modified', createdAtSeconds: 1),
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
        deriveQuestionStatus(
          job: _job(state: 'succeeded', usable: true, id: 'job-regrade'),
          review: review,
        ),
        QuestionStatus.graded,
      );
      // Still outstanding while only the *superseded* attempt is known.
      expect(
        deriveQuestionStatus(
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
        deriveQuestionStatus(
          job: _job(state: 'succeeded', usable: true, createdAtSeconds: 20),
          review: review,
        ),
        QuestionStatus.graded,
      );
      expect(
        deriveQuestionStatus(
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
