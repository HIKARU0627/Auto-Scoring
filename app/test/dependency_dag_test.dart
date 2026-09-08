import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/dependency_dag.dart';
import 'package:auto_scoring_app/core/design/app_status_tone.dart';

DependencyEdgeModel _edge(String from, String to) => DependencyEdgeModel(
  (b) => b
    ..fromQuestionId = from
    ..toQuestionId = to
    ..rationale = '前提'
    ..provides.replace(const <DependencyProvision>[]),
);

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

DagQuestion _question(
  String id, {
  String? label,
  DagNodeStatus status = DagNodeStatus.pending,
  String? blockedOnQuestionId,
}) => DagQuestion(
  id: id,
  label: label ?? id,
  status: status,
  blockedOnQuestionId: blockedOnQuestionId,
);

void main() {
  group('dependencyExecutionLayers', () {
    test('puts every independent question in the first layer', () {
      expect(dependencyExecutionLayers(['q1', 'q2', 'q3'], const []), [
        ['q1', 'q2', 'q3'],
      ]);
    });

    test('places a question after every prerequisite it has', () {
      // q1 -> q3, q2 -> q3: q3 must wait for both, so it cannot share their
      // layer even though q1/q2 are independent of each other.
      final layers = dependencyExecutionLayers(
        ['q1', 'q2', 'q3'],
        [_edge('q1', 'q3'), _edge('q2', 'q3')],
      );
      expect(layers, [
        ['q1', 'q2'],
        ['q3'],
      ]);
    });

    test('returns null for a cyclic edge set', () {
      expect(
        dependencyExecutionLayers(
          ['q1', 'q2'],
          [_edge('q1', 'q2'), _edge('q2', 'q1')],
        ),
        isNull,
      );
    });

    test('ignores an edge naming a question that is not in the set', () {
      // A graph fetched for the whole test can name a question this
      // submission's own question list no longer has.
      expect(dependencyExecutionLayers(['q1'], [_edge('q1', 'gone')]), [
        ['q1'],
      ]);
    });
  });

  group('deriveDagNodeStatus', () {
    test('has no job and no review: 未処理', () {
      expect(
        deriveDagNodeStatus(job: null, review: null),
        DagNodeStatus.pending,
      );
    });

    test('maps each queue state to its own node state', () {
      for (final (state, expected) in const [
        ('blocked', DagNodeStatus.blocked),
        ('queued', DagNodeStatus.queued),
        ('running', DagNodeStatus.running),
        ('failed', DagNodeStatus.failed),
        ('cancelled', DagNodeStatus.cancelled),
      ]) {
        expect(
          deriveDagNodeStatus(job: _job(state: state), review: null),
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
        deriveDagNodeStatus(
          job: _job(state: 'running'),
          review: _review(),
        ),
        DagNodeStatus.running,
      );
    });

    test('succeeded but not usable is 要確認, not レビュー待ち', () {
      // The queue itself judged the result untrustworthy and is holding
      // everything downstream (docs/job-queue.md) -- a stronger statement
      // than "nobody has reviewed it yet".
      expect(
        deriveDagNodeStatus(
          job: _job(state: 'succeeded', usable: false),
          review: null,
        ),
        DagNodeStatus.needsCheck,
      );
    });

    test('a succeeded job carries the human decision when there is one', () {
      for (final (action, expected) in const [
        (null, DagNodeStatus.graded),
        ('approved', DagNodeStatus.approved),
        ('modified', DagNodeStatus.approved),
        ('rejected', DagNodeStatus.rejected),
        ('regrade_requested', DagNodeStatus.regradeRequested),
        ('undone', DagNodeStatus.graded),
      ]) {
        expect(
          deriveDagNodeStatus(
            job: _job(state: 'succeeded', usable: true),
            review: action == null ? null : _review(action: action),
          ),
          expected,
          reason: '$action',
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
        deriveDagNodeStatus(
          job: _job(state: 'succeeded', usable: true, id: 'job-regrade'),
          review: review,
        ),
        DagNodeStatus.graded,
      );
      // Still outstanding while only the *superseded* attempt is known.
      expect(
        deriveDagNodeStatus(
          job: _job(state: 'succeeded', usable: true, id: 'job-original'),
          review: review,
        ),
        DagNodeStatus.regradeRequested,
      );
    });

    test('再判定待ち also ends for any job that ran after the request', () {
      // The replacement job is normally named by the review, but a job
      // created afterwards for another reason (a re-submission under a newer
      // graph version) did not produce the result the reviewer rejected
      // either.
      final review = _review(action: 'regrade_requested', createdAtSeconds: 10);
      expect(
        deriveDagNodeStatus(
          job: _job(state: 'succeeded', usable: true, createdAtSeconds: 20),
          review: review,
        ),
        DagNodeStatus.graded,
      );
      expect(
        deriveDagNodeStatus(
          job: _job(state: 'succeeded', usable: true, createdAtSeconds: 5),
          review: review,
        ),
        DagNodeStatus.regradeRequested,
      );
    });
  });

  group('releasesDependents', () {
    test('reads the persisted usable flag, not the job state', () {
      // A SUCCEEDED job can be not-usable (low Confidence), and a FAILED one
      // can be usable once a person unstuck it with mark_question_usable.
      expect(
        releasesDependents(_job(state: 'succeeded', usable: true)),
        isTrue,
      );
      expect(
        releasesDependents(_job(state: 'succeeded', usable: false)),
        isFalse,
      );
      expect(releasesDependents(_job(state: 'failed', usable: true)), isTrue);
      expect(releasesDependents(_job(state: 'succeeded')), isFalse);
      expect(releasesDependents(null), isFalse);
    });
  });

  group('DagNodeStatus presentation', () {
    test('every state has its own icon and label, not just a colour', () {
      // Issue #25's rule: colour only sharpens a distinction that already
      // survives without it.
      final labels = DagNodeStatus.values.map((s) => s.label).toSet();
      final icons = DagNodeStatus.values.map((s) => s.icon).toSet();
      expect(labels, hasLength(DagNodeStatus.values.length));
      expect(icons, hasLength(DagNodeStatus.values.length));
    });

    test('only 要確認 pulls the eye, and only a failure is danger', () {
      final attention = DagNodeStatus.values
          .where((s) => s.tone == AppStatusTone.attention)
          .toSet();
      final danger = DagNodeStatus.values
          .where((s) => s.tone == AppStatusTone.danger)
          .toSet();
      expect(attention, {DagNodeStatus.needsCheck});
      expect(danger, {DagNodeStatus.failed});
    });

    test('未処理 counts as 待機, never as 完了', () {
      // A submission whose per-question jobs have not been enqueued yet has
      // nothing finished; reporting every node as 完了 was the one lie a
      // collapsed panel left standing (review round 1, P2).
      expect(DagNodeStatus.pending.progress, DagNodeProgress.waiting);
      expect(
        DagNodeStatus.values
            .where((s) => s.progress == DagNodeProgress.settled)
            .toSet(),
        {
          DagNodeStatus.needsCheck,
          DagNodeStatus.failed,
          DagNodeStatus.cancelled,
          DagNodeStatus.graded,
          DagNodeStatus.rejected,
          DagNodeStatus.approved,
        },
      );
      expect(
        DagNodeStatus.values
            .where((s) => s.progress == DagNodeProgress.running)
            .toSet(),
        {DagNodeStatus.running},
      );
    });
  });

  group('buildDependencyDagLayout', () {
    const metrics = DagMetrics(
      nodeWidth: 100,
      nodeHeight: 40,
      columnGap: 20,
      rowGap: 10,
      padding: 5,
      laneGap: 10,
    );

    test('lays layers out along +x and layer members down +y', () {
      final layout = buildDependencyDagLayout(
        questions: [_question('q1'), _question('q2'), _question('q3')],
        edges: [_edge('q1', 'q3'), _edge('q2', 'q3')],
        releasedQuestionIds: const {},
        metrics: metrics,
      )!;
      Rect rectOf(String id) => layout.nodes.firstWhere((n) => n.id == id).rect;

      expect(rectOf('q1'), const Rect.fromLTWH(5, 5, 100, 40));
      expect(rectOf('q2'), const Rect.fromLTWH(5, 55, 100, 40));
      // Second layer: one column to the right, back at the first row.
      expect(rectOf('q3'), const Rect.fromLTWH(125, 5, 100, 40));
      expect(layout.nodes.firstWhere((n) => n.id == 'q3').layer, 1);
      // padding*2 + 2 columns + 1 gap;  padding*2 + 2 rows + 1 gap.
      expect(layout.size, const Size(230, 100));
    });

    test('rows within a layer follow the screen order, not the id order', () {
      // The rail beside the diagram lists questions by page then 設問番号;
      // the layer itself is id-sorted to match the backend, so the row order
      // has to be re-derived from the caller's list or the two disagree.
      final layout = buildDependencyDagLayout(
        questions: [
          _question('q9', label: '1'),
          _question('q1', label: '2'),
        ],
        edges: const [],
        releasedQuestionIds: const {},
        metrics: metrics,
      )!;
      expect(layout.nodes.map((n) => n.id), ['q9', 'q1']);
    });

    test('an edge that would run behind a node is routed into a free lane', () {
      // `A -> B`, `B -> C` *and* `A -> C` is an ordinary graph, and the three
      // land in the same row of three consecutive layers -- so A -> C runs
      // straight through B's opaque card unless it is moved (review round 1,
      // P2).
      final layout = buildDependencyDagLayout(
        questions: [_question('q1'), _question('q2'), _question('q3')],
        edges: [_edge('q1', 'q2'), _edge('q2', 'q3'), _edge('q1', 'q3')],
        releasedQuestionIds: const {},
        metrics: metrics,
      )!;
      DagEdgeLine lineFor(String from, String to) =>
          layout.edges.firstWhere((e) => e.key == '$from>$to');

      // Adjacent layers have nothing in between and stay direct.
      expect(lineFor('q1', 'q2').detourY, isNull);
      expect(lineFor('q2', 'q3').detourY, isNull);
      // The skipping edge travels below every node row: rows bottom is
      // padding(5) + 1 row(40) = 45, plus one laneGap(10).
      expect(lineFor('q1', 'q3').detourY, 55);
      // The canvas grows to hold the lane, so it is never simply clipped.
      expect(layout.size.height, 60);
    });

    test('a skipping edge with a clear diagonal keeps its direct line', () {
      // Only edges a node is actually standing in the way of pay for a lane;
      // routing every skipping edge below the diagram would send a perfectly
      // readable line on a detour and grow the panel for nothing.
      //
      // Layers here are {q1,q2} / {q3} / {q4,q5}. The skipping edge q2 -> q5
      // runs along the *second* row, and the only node in between (q3) is
      // alone in its layer and therefore in the first -- nothing is in the
      // way.
      final layout = buildDependencyDagLayout(
        questions: [
          _question('q1'),
          _question('q2'),
          _question('q3'),
          _question('q4'),
          _question('q5'),
        ],
        edges: [
          _edge('q2', 'q3'),
          _edge('q3', 'q4'),
          _edge('q3', 'q5'),
          _edge('q2', 'q5'),
        ],
        releasedQuestionIds: const {},
        metrics: metrics,
      )!;
      expect(layout.nodes.firstWhere((n) => n.id == 'q3').rect.top, 5);
      expect(layout.edges.firstWhere((e) => e.key == 'q2>q5').detourY, isNull);
      expect(layout.size.height, 100);
    });

    test('an edge is satisfied only when its prerequisite released it', () {
      final layout = buildDependencyDagLayout(
        questions: [_question('q1'), _question('q2'), _question('q3')],
        edges: [_edge('q1', 'q2'), _edge('q2', 'q3')],
        releasedQuestionIds: const {'q1'},
        metrics: metrics,
      )!;
      expect(layout.satisfiedEdgeKeys, {'q1>q2'});
    });

    test('an edge runs from the prerequisite\'s right to the dependent\'s '
        'left, so its direction is the layout\'s own', () {
      final layout = buildDependencyDagLayout(
        questions: [_question('q1'), _question('q2')],
        edges: [_edge('q1', 'q2')],
        releasedQuestionIds: const {},
        metrics: metrics,
      )!;
      final edge = layout.edges.single;
      expect(edge.start, const Offset(105, 25));
      expect(edge.end, const Offset(125, 25));
      expect(edge.key, 'q1>q2');
    });

    test('drops an edge whose endpoint is not on screen', () {
      final layout = buildDependencyDagLayout(
        questions: [_question('q1')],
        edges: [_edge('q1', 'gone')],
        releasedQuestionIds: const {},
        metrics: metrics,
      )!;
      expect(layout.edges, isEmpty);
      expect(layout.size, const Size(110, 50));
    });

    test('a blocked node names the question it is waiting on', () {
      final layout = buildDependencyDagLayout(
        questions: [
          _question('q1', label: '1'),
          _question(
            'q2',
            label: '2',
            status: DagNodeStatus.blocked,
            blockedOnQuestionId: 'q1',
          ),
        ],
        edges: [_edge('q1', 'q2')],
        releasedQuestionIds: const {},
        metrics: metrics,
      )!;
      final blocked = layout.nodes.firstWhere((n) => n.id == 'q2');
      expect(blocked.statusLabel, '問1 待ち');
      expect(blocked.semanticsLabel, '問2 問1 待ち');
    });

    test('a blocked node with no recorded prerequisite still says so', () {
      final layout = buildDependencyDagLayout(
        questions: [_question('q1', label: '1', status: DagNodeStatus.blocked)],
        edges: const [],
        releasedQuestionIds: const {},
        metrics: metrics,
      )!;
      expect(layout.nodes.single.statusLabel, '前提待ち');
    });

    test('returns null for a cyclic graph and for no questions', () {
      expect(
        buildDependencyDagLayout(
          questions: [_question('q1'), _question('q2')],
          edges: [_edge('q1', 'q2'), _edge('q2', 'q1')],
          releasedQuestionIds: const {},
        ),
        isNull,
      );
      expect(
        buildDependencyDagLayout(
          questions: const [],
          edges: const [],
          releasedQuestionIds: const {},
        ),
        isNull,
      );
    });

    test('counts the states the collapsed header summarises', () {
      final layout = buildDependencyDagLayout(
        questions: [
          _question('q1', status: DagNodeStatus.running),
          _question('q2', status: DagNodeStatus.blocked),
          _question('q3', status: DagNodeStatus.approved),
        ],
        edges: const [],
        releasedQuestionIds: const {},
        metrics: metrics,
      )!;
      expect(layout.countWhere((s) => s == DagNodeStatus.running), 1);
      expect(
        layout.countWhere((s) => s.progress == DagNodeProgress.waiting),
        1,
      );
      expect(
        layout.countWhere((s) => s.progress == DagNodeProgress.settled),
        1,
      );
      expect(layout.statusById, {
        'q1': DagNodeStatus.running,
        'q2': DagNodeStatus.blocked,
        'q3': DagNodeStatus.approved,
      });
    });
  });
}
