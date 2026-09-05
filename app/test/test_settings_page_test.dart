import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/features/test_registration/test_settings_page.dart';
import 'package:built_collection/built_collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

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
}) {
  return ProfileResponse(
    (b) => b
      ..testId = 'test-1'
      ..status = status
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

Widget _wrap(Widget page) => MaterialApp(home: page);

/// Pumps [page] with a tall viewport so every section of the settings
/// screen (profile regions + dependency graph edges) is actually built and
/// findable, instead of sitting off-screen in the `ListView`'s lazy sliver.
Future<void> _pumpSettings(WidgetTester tester, Widget page) async {
  tester.view.physicalSize = const Size(1400, 3200);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(_wrap(page));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('loads and shows the profile and dependency graph state', (
    tester,
  ) async {
    final dependencies = AppDependencies(
      getTest: (testId) async => _test(),
      getProfile: (testId) async => _profile(),
      getDependencyGraph: (testId) async => _dependencyGraph(),
    );

    await _pumpSettings(
      tester,
      TestSettingsPage(dependencies: dependencies, testId: 'test-1'),
    );

    expect(find.text('テスト状態: 下書き'), findsOneWidget);
    expect(find.textContaining('問題文 ・ 設問1'), findsOneWidget);
    expect(find.textContaining('回答欄 ・ 設問1'), findsOneWidget);
    expect(find.textContaining('配点 ・ 設問1'), findsOneWidget);
  });

  testWidgets('analyzing profile candidates shows freshly generated regions', (
    tester,
  ) async {
    final dependencies = AppDependencies(
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

    await _pumpSettings(
      tester,
      TestSettingsPage(dependencies: dependencies, testId: 'test-1'),
    );

    expect(find.text('まだ解析されていません。「自動解析」を実行してください。'), findsOneWidget);

    await tester.tap(find.byKey(const Key('analyze-profile-button')));
    await tester.pumpAndSettle();

    expect(find.textContaining('問題文 ・ 設問1'), findsOneWidget);
  });

  testWidgets('confirming the profile locks region editing', (tester) async {
    final dependencies = AppDependencies(
      getTest: (testId) async => _test(),
      getProfile: (testId) async => _profile(),
      getDependencyGraph: (testId) async => _dependencyGraph(),
      // confirmProfile now saves the working copy first (Issue #16 review).
      updateProfile: (testId, regions) async => _profile(regions: regions),
      confirmProfile: (testId) async => _profile(
        status: 'confirmed',
        regions: [
          _region(kind: RegionKind.question, text: '問1', confirmed: true),
          _region(kind: RegionKind.answerArea, confirmed: true),
          _region(kind: RegionKind.score, text: '5点', confirmed: true),
        ],
      ),
    );

    await _pumpSettings(
      tester,
      TestSettingsPage(dependencies: dependencies, testId: 'test-1'),
    );

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
      getTest: (testId) async => _test(),
      getProfile: (testId) async => _profile(),
      getDependencyGraph: (testId) async => _dependencyGraph(),
      updateProfile: (testId, regions) async {
        savedRegions = regions;
        return _profile(regions: regions);
      },
    );

    await _pumpSettings(
      tester,
      TestSettingsPage(dependencies: dependencies, testId: 'test-1'),
    );

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

  testWidgets(
    'analyzing the dependency graph passes each confirmed QUESTION region '
    'as a prompt-text override',
    (tester) async {
      List<QuestionTextOverride>? capturedOverrides;
      final dependencies = AppDependencies(
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

      await _pumpSettings(
        tester,
        TestSettingsPage(dependencies: dependencies, testId: 'test-1'),
      );

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

      await _pumpSettings(
        tester,
        TestSettingsPage(dependencies: dependencies, testId: 'test-1'),
      );

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

      await _pumpSettings(
        tester,
        TestSettingsPage(dependencies: dependencies, testId: 'test-1'),
      );

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
      getTest: (testId) async => _test(),
      getProfile: (testId) async => _profile(status: 'confirmed'),
      getDependencyGraph: (testId) async => _dependencyGraph(edges: [edge]),
    );

    await _pumpSettings(
      tester,
      TestSettingsPage(dependencies: dependencies, testId: 'test-1'),
    );

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
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(status: 'confirmed'),
        getDependencyGraph: (testId) async =>
            _dependencyGraph(status: 'confirmed'),
      );

      await _pumpSettings(
        tester,
        TestSettingsPage(dependencies: dependencies, testId: 'test-1'),
      );

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
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(status: 'confirmed'),
        getDependencyGraph: (testId) async => _dependencyGraph(),
      );

      await _pumpSettings(
        tester,
        TestSettingsPage(dependencies: dependencies, testId: 'test-1'),
      );

      expect(find.text('第1層: test-1:1, test-1:2'), findsOneWidget);
      expect(find.text('第2層: test-1:2'), findsNothing);
    },
  );

  testWidgets(
    'completing registration is only enabled once both are confirmed',
    (tester) async {
      final dependencies = AppDependencies(
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

      await _pumpSettings(
        tester,
        TestSettingsPage(dependencies: dependencies, testId: 'test-1'),
      );

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
        getTest: (testId) async => _test(),
        getProfile: (testId) async => _profile(), // still draft
        getDependencyGraph: (testId) async =>
            _dependencyGraph(status: 'confirmed'),
      );

      await _pumpSettings(
        tester,
        TestSettingsPage(dependencies: dependencies, testId: 'test-1'),
      );

      final completeButtonFinder = find.byKey(
        const Key('complete-registration-button'),
      );
      expect(
        tester.widget<FilledButton>(completeButtonFinder).onPressed,
        isNull,
      );
    },
  );
}
