import 'dart:async';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:built_collection/built_collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'app_harness.dart';

TestResponse _test({String status = 'draft'}) {
  return TestResponse(
    (b) => b
      ..id = 'test-1'
      ..name = '国語 第1回'
      ..status = status
      ..createdAt = DateTime.utc(2026, 1, 1),
  );
}

RegionModel _region({
  String label = '1',
  RegionKind kind = RegionKind.question,
  bool confirmed = false,
  String? text,
}) {
  return RegionModel(
    (b) => b
      ..regionId = 'q-$label'
      ..kind = kind
      ..pageIndex = 0
      ..label = label
      ..confirmed = confirmed
      ..text = text
      ..bbox.x0 = 0.1
      ..bbox.y0 = 0.1
      ..bbox.x1 = 0.5
      ..bbox.y1 = 0.2,
  );
}

ProfileResponse _profile({
  String status = 'draft',
  List<RegionModel>? regions,
  int revision = 1,
}) {
  return ProfileResponse(
    (b) => b
      ..testId = 'test-1'
      ..status = status
      ..revision = revision
      ..pages.add(
        PageFormatModel(
          (p) => p
            ..widthPt = 595
            ..heightPt = 842,
        ),
      )
      ..regions.replace(
        regions ??
            [
              _region(kind: RegionKind.question, text: '問1'),
              _region(kind: RegionKind.answerArea),
              _region(kind: RegionKind.score, text: '5点'),
            ],
      ),
  );
}

DependencyGraphResponse _dependencyGraph({
  String status = 'draft',
  int version = 1,
  List<DependencyEdgeModel> edges = const [],
}) {
  return DependencyGraphResponse(
    (b) => b
      ..id = 'test-1:v$version'
      ..testId = 'test-1'
      ..version = version
      ..status = status
      ..questionIds.replace(['test-1:1', 'test-1:2'])
      ..edges.replace(edges)
      ..unresolved.replace(const [])
      ..layers.replace([
        BuiltList<String>(['test-1:1']),
        BuiltList<String>(['test-1:2']),
      ])
      ..createdAt = DateTime.utc(2026, 1, 1),
  );
}

/// Opens テスト設定画面 for `test-1` with a tall viewport, so every section of
/// the screen (profile regions + dependency graph edges) is actually built and
/// findable, instead of sitting off-screen in the `ListView`'s lazy sliver.
Future<void> _pumpSettings(
  WidgetTester tester,
  AppDependencies dependencies,
) async {
  tester.view.physicalSize = const Size(1400, 3200);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await pumpAppAt(
    tester,
    AppRoutes.testSettings('test-1'),
    dependencies: dependencies,
  );
  await tester.pumpAndSettle();
}

CriteriaQuestionModel _criteriaQuestion({
  String number = '問1',
  int? points = 5,
  String? modelAnswer = '模範解答',
  List<CriteriaItemModel> criteria = const [],
  List<int> sourcePages = const [1],
  String? note,
}) {
  return CriteriaQuestionModel(
    (b) => b
      ..number = number
      ..points = points
      ..modelAnswer = modelAnswer
      ..criteria.replace(criteria)
      ..sourcePages.replace(sourcePages)
      ..note = note,
  );
}

CriteriaResponse _criteria({
  String status = 'draft',
  int revision = 1,
  bool extracted = true,
  List<CriteriaQuestionModel>? questions,
  int? declaredTotalPoints,
  List<int> unreadablePages = const [],
  String? note,
}) {
  final rows =
      questions ??
      [
        _criteriaQuestion(),
        _criteriaQuestion(number: '問2', points: null, note: '配点の記載が読み取れませんでした'),
      ];
  var known = 0;
  var unknown = 0;
  for (final row in rows) {
    if (row.points == null) {
      unknown += 1;
    } else {
      known += row.points!;
    }
  }
  return CriteriaResponse(
    (b) => b
      ..testId = 'test-1'
      ..status = status == 'confirmed'
          ? CriteriaStatus.confirmed
          : CriteriaStatus.draft
      ..revision = revision
      ..extracted = extracted
      ..questions.replace(rows)
      ..declaredTotalPoints = declaredTotalPoints
      ..unreadablePages.replace(unreadablePages)
      ..note = note
      ..totals.knownPoints = known
      ..totals.unknownCount = unknown
      ..totals.declaredTotalPoints = declaredTotalPoints
      ..totals.declaredDifference = null
      ..totals.isComplete = unknown == 0,
  );
}

CriteriaEstimateResponse _estimate({
  int pageCount = 3,
  int maxPages = 30,
  double? unitCost,
  double? estimatedCost,
}) {
  return CriteriaEstimateResponse(
    (b) => b
      ..pageCount = pageCount
      ..maxPages = maxPages
      ..unitCost = unitCost
      ..estimatedCost = estimatedCost,
  );
}

SidecarApiException _notFound() => SidecarApiException(
  SidecarErrorKind.badResponse,
  'not found',
  statusCode: 404,
);

void main() {
  testWidgets('loads and shows the profile and dependency graph state', (
    tester,
  ) async {
    final dependencies = AppDependencies(
      getCriteria: (testId) async => throw _notFound(),

      getTest: (testId) async => _test(),
      getProfile: (testId) async => _profile(),
      getDependencyGraph: (testId) async => _dependencyGraph(),
    );

    await _pumpSettings(tester, dependencies);

    expect(find.text('テスト状態: 下書き'), findsOneWidget);
    expect(find.textContaining('問題文 ・ 設問1'), findsOneWidget);
    expect(find.textContaining('回答欄 ・ 設問1'), findsOneWidget);
    expect(find.textContaining('配点 ・ 設問1'), findsOneWidget);
  });

  testWidgets('analyzing profile candidates shows freshly generated regions', (
    tester,
  ) async {
    final dependencies = AppDependencies(
      getCriteria: (testId) async => throw _notFound(),

      getTest: (testId) async => _test(),
      getProfile: (testId) async {
        throw SidecarApiException(
          SidecarErrorKind.badResponse,
          'not found',
          statusCode: 404,
        );
      },
      getDependencyGraph: (testId) async {
        throw SidecarApiException(
          SidecarErrorKind.badResponse,
          'not found',
          statusCode: 404,
        );
      },
      analyzeProfile: (testId) async => _profile(),
    );

    await _pumpSettings(tester, dependencies);

    expect(find.text('まだ解析されていません。「自動解析」を実行してください。'), findsOneWidget);

    await tester.tap(find.byKey(const Key('analyze-profile-button')));
    await tester.pumpAndSettle();

    expect(find.textContaining('問題文 ・ 設問1'), findsOneWidget);
  });

  testWidgets('confirming the profile locks region editing', (tester) async {
    final dependencies = AppDependencies(
      getCriteria: (testId) async => throw _notFound(),

      getTest: (testId) async => _test(),
      getProfile: (testId) async => _profile(),
      getDependencyGraph: (testId) async => _dependencyGraph(),
      // confirmProfile now saves the working copy first (Issue #16 review).
      updateProfile: (testId, regions) async => _profile(regions: regions),
      confirmProfile: (testId, {required revision}) async => _profile(
        status: 'confirmed',
        regions: [
          _region(kind: RegionKind.question, text: '問1', confirmed: true),
          _region(kind: RegionKind.answerArea, confirmed: true),
          _region(kind: RegionKind.score, text: '5点', confirmed: true),
        ],
      ),
    );

    await _pumpSettings(tester, dependencies);

    await tester.tap(find.byKey(const Key('confirm-profile-button')));
    await tester.pumpAndSettle();

    expect(find.text('プロファイルを確定しました'), findsOneWidget);
    final analyzeButton = tester.widget<FilledButton>(
      find.byKey(const Key('analyze-profile-button')),
    );
    expect(analyzeButton.onPressed, isNull);
  });

  testWidgets('editing a region persists the new values on save', (
    tester,
  ) async {
    List<RegionModel>? savedRegions;
    final dependencies = AppDependencies(
      getCriteria: (testId) async => throw _notFound(),

      getTest: (testId) async => _test(),
      getProfile: (testId) async => _profile(),
      getDependencyGraph: (testId) async => _dependencyGraph(),
      updateProfile: (testId, regions) async {
        savedRegions = regions;
        return _profile(regions: regions);
      },
    );

    await _pumpSettings(tester, dependencies);

    await tester.tap(
      find.descendant(
        of: find.byKey(const Key('region-tile-0')),
        matching: find.byIcon(Icons.edit_outlined),
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(const Key('region-label-field')), '9');
    await tester.tap(find.byKey(const Key('region-save-button')));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('save-profile-button')));
    await tester.pumpAndSettle();

    expect(savedRegions, isNotNull);
    expect(savedRegions!.first.label, '9');
    expect(find.text('プロファイルを保存しました'), findsOneWidget);
  });

  testWidgets('the region dialog rejects a non-finite coordinate', (
    tester,
  ) async {
    final dependencies = AppDependencies(
      getCriteria: (testId) async => throw _notFound(),

      getTest: (testId) async => _test(),
      getProfile: (testId) async => _profile(),
      getDependencyGraph: (testId) async => _dependencyGraph(),
    );

    await _pumpSettings(tester, dependencies);

    await tester.tap(
      find.descendant(
        of: find.byKey(const Key('region-tile-0')),
        matching: find.byIcon(Icons.edit_outlined),
      ),
    );
    await tester.pumpAndSettle();

    // `double.tryParse('NaN')` returns the non-null value `double.nan`, not
    // `null` -- every range/ordering comparison against it is false, so
    // without an explicit finiteness check this would silently pass
    // validation (Issue #16 review round 5).
    await tester.enterText(find.byKey(const Key('region-x0-field')), 'NaN');
    await tester.tap(find.byKey(const Key('region-save-button')));
    await tester.pump();

    expect(find.text('座標は0〜1の範囲で、右下が左上より大きくなるように入力してください'), findsOneWidget);
    // The dialog is still open -- the save was rejected, not accepted.
    expect(find.byKey(const Key('region-save-button')), findsOneWidget);
  });

  testWidgets(
    'analyzing the dependency graph passes each confirmed QUESTION region '
    'as a prompt-text override',
    (tester) async {
      List<QuestionTextOverride>? capturedOverrides;
      final dependencies = AppDependencies(
        getCriteria: (testId) async => throw _notFound(),

        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(status: 'confirmed'),
        getDependencyGraph: (testId) async {
          throw SidecarApiException(
            SidecarErrorKind.badResponse,
            'not found',
            statusCode: 404,
          );
        },
        analyzeDependencyGraph: (testId, {overrides = const []}) async {
          capturedOverrides = overrides;
          return _dependencyGraph();
        },
      );

      await _pumpSettings(tester, dependencies);

      await tester.tap(
        find.byKey(const Key('analyze-dependency-graph-button')),
      );
      await tester.pumpAndSettle();

      expect(capturedOverrides, isNotNull);
      expect(capturedOverrides, hasLength(1));
      expect(capturedOverrides!.single.questionId, 'test-1:1');
      expect(capturedOverrides!.single.promptText, '問1');
    },
  );

  testWidgets(
    'confirming the dependency graph requires reviewing edges first',
    (tester) async {
      final edge = DependencyEdgeModel(
        (b) => b
          ..fromQuestionId = 'test-1:1'
          ..toQuestionId = 'test-1:2'
          ..rationale = '問1の結果を利用'
          ..provides.replace([DependencyProvision.recognizedText]),
      );
      final dependencies = AppDependencies(
        getCriteria: (testId) async => throw _notFound(),

        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(status: 'confirmed'),
        getDependencyGraph: (testId) async => _dependencyGraph(edges: [edge]),
        confirmDependencyGraph:
            (testId, {required version, required edges}) async =>
                _dependencyGraph(
                  status: 'confirmed',
                  version: version,
                  edges: edges,
                ),
      );

      await _pumpSettings(tester, dependencies);

      expect(find.textContaining('test-1:1 → test-1:2'), findsOneWidget);

      await tester.tap(
        find.byKey(const Key('confirm-dependency-graph-button')),
      );
      await tester.pumpAndSettle();

      expect(find.text('設問依存関係グラフを確定しました'), findsOneWidget);
    },
  );

  testWidgets(
    'editing a dependency edge lets a reviewer choose what it provides',
    (tester) async {
      final edge = DependencyEdgeModel(
        (b) => b
          ..fromQuestionId = 'test-1:1'
          ..toQuestionId = 'test-1:2'
          ..rationale = '問1の得点を利用'
          ..provides.replace([DependencyProvision.recognizedText]),
      );
      List<DependencyEdgeModel>? confirmedEdges;
      final dependencies = AppDependencies(
        getCriteria: (testId) async => throw _notFound(),

        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(status: 'confirmed'),
        getDependencyGraph: (testId) async => _dependencyGraph(edges: [edge]),
        confirmDependencyGraph:
            (testId, {required version, required edges}) async {
              confirmedEdges = edges;
              return _dependencyGraph(
                status: 'confirmed',
                version: version,
                edges: edges,
              );
            },
      );

      await _pumpSettings(tester, dependencies);

      await tester.tap(
        find.descendant(
          of: find.byKey(const Key('edge-tile-0')),
          matching: find.byIcon(Icons.edit_outlined),
        ),
      );
      await tester.pumpAndSettle();

      // Swap the default provision for a different one -- the dialog must
      // let both be expressed, not silently keep whatever `_addEdge` (or
      // the analyzer) originally set (Issue #16 review round 4).
      await tester.tap(find.byKey(const Key('edge-provision-recognizedText')));
      await tester.tap(find.byKey(const Key('edge-provision-score')));
      await tester.tap(find.byKey(const Key('edge-save-button')));
      await tester.pumpAndSettle();

      await tester.tap(
        find.byKey(const Key('confirm-dependency-graph-button')),
      );
      await tester.pumpAndSettle();

      expect(confirmedEdges, isNotNull);
      expect(confirmedEdges!.single.provides, [DependencyProvision.score]);
    },
  );

  testWidgets('the edge dialog rejects saving with no provision selected', (
    tester,
  ) async {
    final edge = DependencyEdgeModel(
      (b) => b
        ..fromQuestionId = 'test-1:1'
        ..toQuestionId = 'test-1:2'
        ..rationale = '問1の結果を利用'
        ..provides.replace([DependencyProvision.recognizedText]),
    );
    final dependencies = AppDependencies(
      getCriteria: (testId) async => throw _notFound(),

      getTest: (testId) async => _test(),
      getProfile: (testId) async => _profile(status: 'confirmed'),
      getDependencyGraph: (testId) async => _dependencyGraph(edges: [edge]),
    );

    await _pumpSettings(tester, dependencies);

    await tester.tap(
      find.descendant(
        of: find.byKey(const Key('edge-tile-0')),
        matching: find.byIcon(Icons.edit_outlined),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('edge-provision-recognizedText')));
    await tester.tap(find.byKey(const Key('edge-save-button')));
    await tester.pump();

    expect(find.text('依存先に渡す内容を少なくとも1つ選択してください'), findsOneWidget);
    // The dialog itself is still open (the save was rejected).
    expect(find.byKey(const Key('edge-save-button')), findsOneWidget);
  });

  testWidgets(
    'the dependency-graph analyze button stays enabled once confirmed, to '
    'start a new version',
    (tester) async {
      // A confirmed graph is immutable, but `/dependency-graph/analyze`
      // always starts a new, higher-versioned draft rather than touching it
      // -- a reviewer who spots a bad edge after confirming must still be
      // able to re-run analysis (Issue #16 review round 3).
      final dependencies = AppDependencies(
        getCriteria: (testId) async => throw _notFound(),

        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(status: 'confirmed'),
        getDependencyGraph: (testId) async =>
            _dependencyGraph(status: 'confirmed'),
      );

      await _pumpSettings(tester, dependencies);

      final analyzeButton = tester.widget<FilledButton>(
        find.byKey(const Key('analyze-dependency-graph-button')),
      );
      expect(analyzeButton.onPressed, isNotNull);
    },
  );

  testWidgets(
    'parallel-execution layers are recomputed from the working edge set, '
    'not the stale server snapshot',
    (tester) async {
      // The fixture's `layers` field always reports two separate layers
      // (test-1:1, then test-1:2) regardless of `edges` -- standing in for
      // a real server response that goes stale the moment a reviewer edits
      // an edge. With no edges, the two questions are independent and
      // belong in the same layer; the settings screen must show that
      // freshly-computed answer, not the stale two-layer snapshot.
      final dependencies = AppDependencies(
        getCriteria: (testId) async => throw _notFound(),

        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(status: 'confirmed'),
        getDependencyGraph: (testId) async => _dependencyGraph(),
      );

      await _pumpSettings(tester, dependencies);

      expect(find.text('第1層: test-1:1, test-1:2'), findsOneWidget);
      expect(find.text('第2層: test-1:2'), findsNothing);
    },
  );

  testWidgets(
    'completing registration is only enabled once both are confirmed',
    (tester) async {
      final dependencies = AppDependencies(
        getCriteria: (testId) async => throw _notFound(),

        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(status: 'confirmed'),
        getDependencyGraph: (testId) async =>
            _dependencyGraph(status: 'confirmed'),
        completeRegistration: (testId) async => CompleteRegistrationResponse(
          (b) => b
            ..test.replace(_test(status: 'ready'))
            ..profileConfirmed = true
            ..dependencyGraphConfirmed = true,
        ),
      );

      await _pumpSettings(tester, dependencies);

      final completeButtonFinder = find.byKey(
        const Key('complete-registration-button'),
      );
      expect(
        tester.widget<FilledButton>(completeButtonFinder).onPressed,
        isNotNull,
      );

      await tester.tap(completeButtonFinder);
      await tester.pumpAndSettle();

      expect(find.text('テスト状態: 登録完了'), findsOneWidget);
    },
  );

  testWidgets(
    'completing registration stays disabled until the profile is confirmed',
    (tester) async {
      final dependencies = AppDependencies(
        getCriteria: (testId) async => throw _notFound(),

        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(), // still draft
        getDependencyGraph: (testId) async =>
            _dependencyGraph(status: 'confirmed'),
      );

      await _pumpSettings(tester, dependencies);

      final completeButtonFinder = find.byKey(
        const Key('complete-registration-button'),
      );
      expect(
        tester.widget<FilledButton>(completeButtonFinder).onPressed,
        isNull,
      );
    },
  );

  // ------------------------------------------------------------------ //
  // Issue #25 acceptance: desktop standard / narrow width.
  // ------------------------------------------------------------------ //
  group('Issue #25: 受入 -- desktop標準幅と狭幅', () {
    /// `_pumpSettings` above deliberately uses an unrealistically tall
    /// viewport so the lazy `ListView` builds every section at once. These
    /// two are the real thing: the window sizes a reviewer actually has.
    const desktopStandard = Size(1440, 900);
    const desktopNarrow = Size(820, 720);

    for (final (name, size) in [
      ('desktop標準幅', desktopStandard),
      ('狭幅', desktopNarrow),
    ]) {
      testWidgets('$name でテスト設定画面のレイアウトが破綻しない', (tester) async {
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        final dependencies = AppDependencies(
          getCriteria: (testId) async => throw _notFound(),

          getTest: (testId) async => _test(),
          getProfile: (testId) async => _profile(),
          getDependencyGraph: (testId) async => _dependencyGraph(),
        );

        await pumpAppAt(
          tester,
          AppRoutes.testSettings('test-1'),
          dependencies: dependencies,
        );
        await tester.pumpAndSettle();

        // A RenderFlex overflow is reported as a framework exception;
        // surfacing it here names which width broke rather than leaving it
        // to teardown.
        expect(tester.takeException(), isNull);
        // Present *and* on screen at this width. `takeException` alone only
        // catches a RenderFlex overflow; a section pushed past the viewport
        // edge raises nothing (round 1 review).
        for (final finder in [
          find.text('テスト状態: 下書き'),
          find.textContaining('回答欄 ・ 設問1'),
        ]) {
          expect(finder, findsOneWidget);
          final rect = tester.getRect(finder);
          expect(rect.width, greaterThan(0));
          expect(rect.height, greaterThan(0));
          expect(rect.left, greaterThanOrEqualTo(0));
          expect(rect.right, lessThanOrEqualTo(size.width));
        }
      });
    }
  });

  // Issue #66 review (P2): `_loadAll` calls getTest -> getProfile ->
  // getDependencyGraph in sequence, with a single `mounted` check after all
  // three. Now that `AppDependencies` comes from a provider, resolving it
  // again after a dispose would throw a `StateError` from `ref` -- which is
  // not a `SidecarApiException`, so nothing here catches it and it surfaces
  // as an unhandled async error.
  testWidgets('leaving while the initial load is in flight does not throw', (
    tester,
  ) async {
    final profile = Completer<ProfileResponse>();
    final dependencies = AppDependencies(
      getCriteria: (testId) async => throw _notFound(),

      getTest: (testId) async => _test(),
      getProfile: (testId) => profile.future,
      getDependencyGraph: (testId) async => _dependencyGraph(),
    );

    await pumpAppAt(
      tester,
      AppRoutes.testSettings('test-1'),
      dependencies: dependencies,
    );
    await tester.pump();

    await tester.pumpWidget(const SizedBox());
    await tester.pumpAndSettle();

    profile.complete(_profile());
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
  });

  // ------------------------------------------------------------------ //
  // 配点と採点基準 (Issue #103)
  // ------------------------------------------------------------------ //

  group('配点と採点基準', () {
    testWidgets('抽出できなかった配点は「不明」として一覧に出る', (tester) async {
      final dependencies = AppDependencies(
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(),
        getDependencyGraph: (testId) async => _dependencyGraph(),
        getCriteria: (testId) async =>
            _criteria(declaredTotalPoints: 20, unreadablePages: [2]),
      );

      await _pumpSettings(tester, dependencies);

      // 黙って落とさない: 不明の設問も一覧に並ぶ。
      expect(find.textContaining('設問問1 ・ 配点 5 点'), findsOneWidget);
      expect(find.textContaining('設問問2 ・ 配点: 不明'), findsOneWidget);
      // 読めなかったページも隠さない。
      expect(
        find.byKey(const Key('criteria-unreadable-pages')),
        findsOneWidget,
      );
    });

    testWidgets('合計と不明件数を必ず並べて出す', (tester) async {
      // 不明を含む一覧の横に合計だけを置くと、それが満点だと読める。
      final dependencies = AppDependencies(
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(),
        getDependencyGraph: (testId) async => _dependencyGraph(),
        getCriteria: (testId) async => _criteria(),
      );

      await _pumpSettings(tester, dependencies);

      final label = tester.widget<Text>(
        find.byKey(const Key('criteria-totals-label')),
      );
      expect(label.data, contains('合計 5 点'));
      expect(label.data, contains('配点不明 1 問'));
    });

    testWidgets('総得点と合計が食い違えば差を示す', (tester) async {
      final dependencies = AppDependencies(
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(),
        getDependencyGraph: (testId) async => _dependencyGraph(),
        getCriteria: (testId) async => _criteria(
          questions: [_criteriaQuestion(points: 5)],
          declaredTotalPoints: 20,
        ),
      );

      await _pumpSettings(tester, dependencies);

      expect(find.byKey(const Key('criteria-total-mismatch')), findsOneWidget);
      expect(find.textContaining('差 15 点'), findsOneWidget);
    });

    testWidgets('配点が不明なままでは確定できず、理由が画面に出る', (tester) async {
      final dependencies = AppDependencies(
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(),
        getDependencyGraph: (testId) async => _dependencyGraph(),
        getCriteria: (testId) async => _criteria(),
      );

      await _pumpSettings(tester, dependencies);

      final confirm = tester.widget<FilledButton>(
        find.byKey(const Key('confirm-criteria-button')),
      );
      expect(confirm.onPressed, isNull);
      expect(
        tester
            .widget<Text>(find.byKey(const Key('criteria-blocking-reason')))
            .data,
        contains('1 件'),
      );
    });

    testWidgets('抽出を一度も実行していなくても手で追加して保存できる', (tester) async {
      // Issue #95 決定 8 の退避手段。抽出が無い状態が出発点。
      List<CriteriaQuestionModel>? saved;
      final dependencies = AppDependencies(
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(),
        getDependencyGraph: (testId) async => _dependencyGraph(),
        getCriteria: (testId) async => throw _notFound(),
        updateCriteria: (testId, questions, {declaredTotalPoints}) async {
          saved = questions;
          return _criteria(questions: questions, extracted: false);
        },
      );

      await _pumpSettings(tester, dependencies);

      expect(
        tester
            .widget<Text>(find.byKey(const Key('criteria-empty-message')))
            .data,
        contains('まだ抽出されていません'),
      );

      await tester.tap(find.byKey(const Key('add-criteria-question-button')));
      await tester.pumpAndSettle();
      // 新しい設問は配点 null（不明）で生まれる。仮の 0 や 1 を置かない。
      expect(find.textContaining('配点: 不明'), findsOneWidget);

      await tester.tap(find.byKey(const Key('save-criteria-button')));
      await tester.pumpAndSettle();

      expect(saved, hasLength(1));
      expect(saved!.single.points, isNull);
    });

    testWidgets('抽出は、送信ページ数と費用を見せてからでないと実行されない', (tester) async {
      // 押した瞬間に有料 provider へ全ページ送るのを止める。
      var extracted = 0;
      final dependencies = AppDependencies(
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(),
        getDependencyGraph: (testId) async => _dependencyGraph(),
        getCriteria: (testId) async => throw _notFound(),
        estimateCriteria: (testId) async => _estimate(pageCount: 8),
        extractCriteria: (testId) async {
          extracted += 1;
          return _criteria();
        },
      );

      await _pumpSettings(tester, dependencies);
      await tester.tap(find.byKey(const Key('extract-criteria-button')));
      await tester.pumpAndSettle();

      // まだ送っていない。
      expect(extracted, 0);
      expect(
        tester.widget<Text>(find.byKey(const Key('extract-page-count'))).data,
        contains('8 ページ'),
      );

      await tester.tap(find.byKey(const Key('extract-confirm-button')));
      await tester.pumpAndSettle();
      expect(extracted, 1);
    });

    testWidgets('キャンセルすれば1ページも送らない', (tester) async {
      var extracted = 0;
      final dependencies = AppDependencies(
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(),
        getDependencyGraph: (testId) async => _dependencyGraph(),
        getCriteria: (testId) async => throw _notFound(),
        estimateCriteria: (testId) async => _estimate(),
        extractCriteria: (testId) async {
          extracted += 1;
          return _criteria();
        },
      );

      await _pumpSettings(tester, dependencies);
      await tester.tap(find.byKey(const Key('extract-criteria-button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('extract-cancel-button')));
      await tester.pumpAndSettle();

      expect(extracted, 0);
    });

    testWidgets('単価が未設定なら 0 円ではなく「見積もれません」と出す', (tester) async {
      final dependencies = AppDependencies(
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(),
        getDependencyGraph: (testId) async => _dependencyGraph(),
        getCriteria: (testId) async => throw _notFound(),
        estimateCriteria: (testId) async => _estimate(),
      );

      await _pumpSettings(tester, dependencies);
      await tester.tap(find.byKey(const Key('extract-criteria-button')));
      await tester.pumpAndSettle();

      final cost = tester
          .widget<Text>(find.byKey(const Key('extract-cost')))
          .data;
      expect(cost, contains('見積もれません'));
      expect(cost, isNot(contains('0')));
    });

    testWidgets('単価が設定されていれば概算を出す', (tester) async {
      final dependencies = AppDependencies(
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(),
        getDependencyGraph: (testId) async => _dependencyGraph(),
        getCriteria: (testId) async => throw _notFound(),
        estimateCriteria: (testId) async =>
            _estimate(pageCount: 4, unitCost: 0.25, estimatedCost: 1.0),
      );

      await _pumpSettings(tester, dependencies);
      await tester.tap(find.byKey(const Key('extract-criteria-button')));
      await tester.pumpAndSettle();

      expect(
        tester.widget<Text>(find.byKey(const Key('extract-cost'))).data,
        contains('1.00'),
      );
    });

    testWidgets('ページ数が上限を超えていれば、実行させずに理由を出す', (tester) async {
      var extracted = 0;
      final dependencies = AppDependencies(
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(),
        getDependencyGraph: (testId) async => _dependencyGraph(),
        getCriteria: (testId) async => throw _notFound(),
        estimateCriteria: (testId) async =>
            _estimate(pageCount: 31, maxPages: 30),
        extractCriteria: (testId) async {
          extracted += 1;
          return _criteria();
        },
      );

      await _pumpSettings(tester, dependencies);
      await tester.tap(find.byKey(const Key('extract-criteria-button')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('extract-over-limit')), findsOneWidget);
      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('extract-confirm-button')),
            )
            .onPressed,
        isNull,
      );
      expect(extracted, 0);
    });

    testWidgets('抽出が 0 件だったことと、実行していないことを別の文言で示す', (tester) async {
      final dependencies = AppDependencies(
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(),
        getDependencyGraph: (testId) async => _dependencyGraph(),
        getCriteria: (testId) async =>
            _criteria(questions: const [], extracted: true),
      );

      await _pumpSettings(tester, dependencies);

      expect(
        tester
            .widget<Text>(find.byKey(const Key('criteria-empty-message')))
            .data,
        contains('抽出は実行しましたが'),
      );
    });

    testWidgets('抽出結果を編集すると、保存前でも合計が追随する', (tester) async {
      // サーバの totals をそのまま出していると、ここで合計が古いままになる。
      final dependencies = AppDependencies(
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(),
        getDependencyGraph: (testId) async => _dependencyGraph(),
        getCriteria: (testId) async => _criteria(),
      );

      await _pumpSettings(tester, dependencies);
      expect(
        tester
            .widget<Text>(find.byKey(const Key('criteria-totals-label')))
            .data,
        contains('配点不明 1 問'),
      );

      await tester.tap(find.byKey(const Key('edit-criteria-1')));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(const Key('criteria-points-field')),
        '15',
      );
      await tester.tap(find.byKey(const Key('criteria-save-button')));
      await tester.pumpAndSettle();

      final label = tester.widget<Text>(
        find.byKey(const Key('criteria-totals-label')),
      );
      expect(label.data, contains('合計 20 点'));
      expect(label.data, isNot(contains('不明')));
      // 埋まったので確定できる。
      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('confirm-criteria-button')),
            )
            .onPressed,
        isNotNull,
      );
    });

    testWidgets('確定は保存してから、その revision を指定して行う', (tester) async {
      var savedRevision = 0;
      int? confirmedWith;
      final dependencies = AppDependencies(
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(),
        getDependencyGraph: (testId) async => _dependencyGraph(),
        getCriteria: (testId) async =>
            _criteria(questions: [_criteriaQuestion()], revision: 1),
        updateCriteria: (testId, questions, {declaredTotalPoints}) async {
          savedRevision = 7;
          return _criteria(questions: questions, revision: savedRevision);
        },
        confirmCriteria: (testId, {required revision}) async {
          confirmedWith = revision;
          return _criteria(
            questions: [_criteriaQuestion()],
            revision: revision,
            status: 'confirmed',
          );
        },
      );

      await _pumpSettings(tester, dependencies);
      await tester.tap(find.byKey(const Key('confirm-criteria-button')));
      await tester.pumpAndSettle();

      expect(confirmedWith, savedRevision);
      expect(find.text('配点と採点基準を確定し、設問に反映しました'), findsOneWidget);
      // 確定後は編集できない。
      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('extract-criteria-button')),
            )
            .onPressed,
        isNull,
      );
    });

    testWidgets('配点を確定しても、なぜまだ採点が始まらないかを画面に出す', (tester) async {
      // #104 の取込完了画面と同じ規律: できないことをできるように見せない。
      final dependencies = AppDependencies(
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(),
        getDependencyGraph: (testId) async => _dependencyGraph(),
        getCriteria: (testId) async =>
            _criteria(questions: [_criteriaQuestion()], status: 'confirmed'),
      );

      await _pumpSettings(tester, dependencies);

      expect(find.textContaining('配点と採点基準が未確定です'), findsNothing);
      expect(find.textContaining('回答欄（テストプロファイル）が未確定です'), findsOneWidget);
      expect(
        find.byKey(const Key('criteria-confirmed-next-step')),
        findsOneWidget,
      );
      expect(
        find.textContaining('配点は確定しました。採点の開始には回答欄の設定が必要です'),
        findsOneWidget,
      );
    });

    testWidgets('旧来の配点領域を持つテストでは、配点未確定を残作業に挙げない', (tester) async {
      // `complete-registration` の関門はプロファイルと依存グラフだけ。
      // Issue #103 以前のテストは `SCORE` 領域から配点を読めるので、
      // そこで「配点が未確定です」と出すのは、止めていないものを
      // 止めているように見せることになる。
      final dependencies = AppDependencies(
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(status: 'confirmed'),
        getDependencyGraph: (testId) async => _dependencyGraph(),
        getCriteria: (testId) async => throw _notFound(),
      );

      await _pumpSettings(tester, dependencies);

      expect(find.textContaining('配点と採点基準が未確定です'), findsNothing);
      expect(find.textContaining('設問依存関係グラフが未確定です'), findsOneWidget);
    });

    testWidgets('配点領域が無ければ、配点未確定を残作業に挙げる', (tester) async {
      final dependencies = AppDependencies(
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(
          status: 'confirmed',
          regions: [_region(kind: RegionKind.question, text: '問1')],
        ),
        getDependencyGraph: (testId) async => _dependencyGraph(),
        getCriteria: (testId) async => throw _notFound(),
      );

      await _pumpSettings(tester, dependencies);

      expect(find.textContaining('配点と採点基準が未確定です'), findsOneWidget);
    });

    testWidgets('設問が変わったら、確定済みグラフでも「済み」と言わない', (tester) async {
      // 一度計算した値を、状態が変わったあとも使い続ける形の欠陥。
      // 確定済みグラフは不変だが設問はそうではなく、サーバは食い違いを
      // 「未確定」と同じに扱って 409 で断る。`status` だけを見ていると
      // 画面だけが「残っていることはありません」と言う。
      final dependencies = AppDependencies(
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(status: 'confirmed'),
        // グラフが知っているのは test-1:1 と test-1:2 の2件
        getDependencyGraph: (testId) async =>
            _dependencyGraph(status: 'confirmed'),
        // 確定済みの採点基準は3件目を持つ = グラフはもう説明できていない
        getCriteria: (testId) async => _criteria(
          status: 'confirmed',
          questions: [
            _criteriaQuestion(number: '1'),
            _criteriaQuestion(number: '2'),
            _criteriaQuestion(number: '3'),
          ],
        ),
      );

      await _pumpSettings(tester, dependencies);

      expect(find.textContaining('設問が変わったため'), findsOneWidget);
      expect(find.textContaining('押すと断られます'), findsOneWidget);
      // **ボタンは塞がない。** 期待する設問集合は画面側の推定であり、
      // 外したときに正当な操作を止めるのは誤った「全部済み」より悪い。
      // 関門はサーバのまま。
      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('complete-registration-button')),
            )
            .onPressed,
        isNotNull,
      );
    });

    testWidgets('設問集合が一致していれば、確定済みグラフはそのまま済み扱い', (tester) async {
      final dependencies = AppDependencies(
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(status: 'confirmed'),
        getDependencyGraph: (testId) async =>
            _dependencyGraph(status: 'confirmed'),
        getCriteria: (testId) async => _criteria(
          status: 'confirmed',
          questions: [
            _criteriaQuestion(number: '1'),
            _criteriaQuestion(number: '2'),
          ],
        ),
      );

      await _pumpSettings(tester, dependencies);

      expect(find.textContaining('設問が変わったため'), findsNothing);
      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('complete-registration-button')),
            )
            .onPressed,
        isNotNull,
      );
    });

    testWidgets('領域の手動追加からは配点・採点基準・模範解答を選べない', (tester) async {
      // A案: 配点の入力口を「配点と採点基準」節ひとつに絞る。
      // fallback の経路はコードに残るが、画面からは作れない。
      final dependencies = AppDependencies(
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(
          regions: [_region(kind: RegionKind.question, text: '問1')],
        ),
        getDependencyGraph: (testId) async => _dependencyGraph(),
        getCriteria: (testId) async => throw _notFound(),
      );

      await _pumpSettings(tester, dependencies);

      await tester.tap(find.byKey(const Key('region-tile-0')));
      await tester.pumpAndSettle();
      await tester.tap(find.byIcon(Icons.edit_outlined).first);
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('region-kind-field')));
      await tester.pumpAndSettle();

      expect(find.text('回答欄').hitTestable(), findsWidgets);
      expect(find.text('配点'), findsNothing);
      expect(find.text('採点基準'), findsNothing);
      expect(find.text('模範解答'), findsNothing);
    });

    testWidgets('自動解析が作った旧来の配点領域は、開いても種類を保てる', (tester) async {
      // 選択肢から外しただけだと `DropdownButtonFormField` が
      // `initialValue` を候補に見つけられず、既存の領域を開けなくなる。
      final dependencies = AppDependencies(
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(
          regions: [_region(kind: RegionKind.score, text: '5点')],
        ),
        getDependencyGraph: (testId) async => _dependencyGraph(),
        getCriteria: (testId) async => throw _notFound(),
      );

      await _pumpSettings(tester, dependencies);

      await tester.tap(find.byIcon(Icons.edit_outlined).first);
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.byKey(const Key('region-kind-field')), findsOneWidget);
    });
  });
}
