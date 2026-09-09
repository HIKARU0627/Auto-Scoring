import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/criteria_totals.dart';
import 'package:auto_scoring_app/core/dependency_dag.dart';
import 'package:auto_scoring_app/core/design/app_status_tone.dart';
import 'package:auto_scoring_app/core/design/app_theme_context.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';
import 'package:auto_scoring_app/core/pdf_file_picker.dart';
import 'package:auto_scoring_app/core/widgets/app_error_banner.dart';
import 'package:auto_scoring_app/features/test_registration/answer_area_editor.dart';

/// テスト設定画面 (simplified-design-specification.md §16.3, Issue #16).
///
/// Lets a reviewer confirm/correct what candidate generation produced before
/// a test can register:
///
/// * the profile's regions -- **座標だけ** (問題文/回答欄/添削記号領域, one list
///   per page, editable as plain fields rather than a PDF overlay -- see
///   docs/test-registration.md for why the PDF-overlay editor is out of
///   scope here). `Profile.status` moves `draft` -> `confirmed` only once
///   every region has been reviewed (`confirmProfile`).
/// * 配点と採点基準 (Issue #103): read out of the 採点基準PDF by an LLM, or
///   typed in from scratch, then edited and confirmed here. **配点の入力口は
///   この節ひとつだけ** -- Issue #103 acceptance criterion 7 ("手動入力と抽出
///   結果の編集が同じ画面"). `SCORE`/`RUBRIC`/`MODEL_ANSWER` regions still
///   exist and are still read by `build_questions_and_rubrics` as a
///   fallback for tests registered before Issue #103, but they can no longer
///   be created or switched to from the region editor: two places to type a
///   配点 is two places for it to be wrong, and neither the reviewer nor the
///   code could say which one won (`_selectableRegionKinds`).
/// * the question-dependency graph (Issue #26): candidate edges, their
///   rationale, and any question the analyzer could not resolve, plus the
///   parallel-execution layers a confirmed graph implies. A reviewer can
///   add/remove edges before confirming; `confirmDependencyGraph` rejects a
///   cyclic edge set (422) so a confirmed graph is always a DAG.
///
/// `completeRegistration` (登録完了) only succeeds once *both* are confirmed
/// -- the Issue #16 acceptance criterion "全必須項目確認後にだけ登録完了になる"
/// and the Issue #16 追加要件 "設問依存関係を...明示確認するまでテストをreadyに
/// しない".
class TestSettingsPage extends ConsumerStatefulWidget {
  const TestSettingsPage({super.key, required this.testId});

  final String testId;

  @override
  ConsumerState<TestSettingsPage> createState() => _TestSettingsPageState();
}

class _TestSettingsPageState extends ConsumerState<TestSettingsPage> {
  /// The sidecar operations this screen was opened against, captured once in
  /// [initState] -- never re-resolved from the provider mid-request. See
  /// [appDependenciesProvider] for why that rule exists.
  late final AppDependencies _dependencies;

  /// The native "choose a PDF" dialog, for picking the reference answer
  /// sheet (Issue #105). Captured in [initState] for the same reason as
  /// [_dependencies], and reached through a provider for the same reason
  /// `TestRegistrationPage` does: this screen is built from a route path.
  late final Future<PickedPdfFile?> Function() _pickPdfFile;

  TestResponse? _test;
  ProfileResponse? _profile;
  CriteriaResponse? _criteria;
  DependencyGraphResponse? _dependencyGraph;

  /// Working copy of the profile's regions, edited locally before `保存`
  /// (`updateProfile`) persists it. `null` until the profile has loaded once.
  List<RegionModel>? _editableRegions;

  /// Working copy of the 配点と採点基準, edited locally before `保存`
  /// (`updateCriteria`). Unlike the two below it, this is **not** `null`
  /// until something loads: a test with no draft at all is the normal
  /// starting point for hand entry (Issue #95 decision 8), so the list
  /// starts empty and editable.
  List<CriteriaQuestionModel> _editableCriteria = <CriteriaQuestionModel>[];

  /// The 総得点 the criteria PDF stated, editable because the model may have
  /// misread it -- or invented one from a footer page number, which Issue
  /// #95 decision 5 (案A) says to ignore.
  int? _editableDeclaredTotal;

  /// Working copy of the dependency graph's edges, edited locally before
  /// `確定` (`confirmDependencyGraph`). `null` until a graph has loaded once.
  List<DependencyEdgeModel>? _editableEdges;

  /// Whether a reference answer sheet is stored for this test and whether
  /// answer-area detection can run on this machine (Issue #105). `null` while
  /// the screen is still loading.
  AnswerLayoutResponse? _answerLayout;

  /// The stored answer sheet's bytes, for the overlay editor to draw on.
  /// `null` when none is stored, or when fetching it failed -- the two are
  /// told apart by [_answerLayoutPdfError].
  Uint8List? _answerLayoutPdf;

  /// Why the stored answer sheet could not be fetched. Non-null only when a
  /// sheet *is* recorded as stored, so "no sheet yet" and "the sheet is there
  /// but I cannot show it" stay different states with different fixes.
  String? _answerLayoutPdfError;

  /// This test's confirmed question numbers.
  ///
  /// Read from the questions themselves, **not** from the profile response.
  /// A test registered without a model-answer PDF has no profile until an
  /// answer sheet is uploaded, so sourcing the candidates from the profile
  /// made the very first action -- detecting, or drawing a box -- impossible
  /// on exactly the tests this Issue exists for (review round 1, P1).
  List<String> _questionNumbers = const [];

  bool _loading = true;
  bool _busy = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _dependencies = ref.read(appDependenciesProvider);
    _pickPdfFile = ref.read(pickPdfFileProvider);
    _loadAll();
  }

  Future<void> _loadAll() async {
    setState(() {
      _loading = true;
      _errorMessage = null;
    });
    try {
      final test = await _dependencies.getTest(widget.testId);
      ProfileResponse? profile;
      try {
        profile = await _dependencies.getProfile(widget.testId);
      } on SidecarApiException catch (error) {
        if (error.statusCode != 404) rethrow;
      }
      CriteriaResponse? criteria;
      try {
        criteria = await _dependencies.getCriteria(widget.testId);
      } on SidecarApiException catch (error) {
        // 404 is the ordinary state for a test nobody has extracted or
        // hand-entered criteria for yet -- not an error to show.
        if (error.statusCode != 404) rethrow;
      }
      DependencyGraphResponse? graph;
      try {
        graph = await _dependencies.getDependencyGraph(widget.testId);
      } on SidecarApiException catch (error) {
        if (error.statusCode != 404) rethrow;
      }
      final layout = await _dependencies.getAnswerLayout(widget.testId);
      final questions = await _dependencies.listQuestions(widget.testId);
      if (!mounted) return;
      setState(() {
        _test = test;
        _profile = profile;
        _editableRegions = profile?.regions.toList();
        _criteria = criteria;
        _editableCriteria =
            criteria?.questions.toList() ?? <CriteriaQuestionModel>[];
        _editableDeclaredTotal = criteria?.declaredTotalPoints;
        _dependencyGraph = graph;
        _editableEdges = graph?.edges.toList();
        _answerLayout = layout;
        _questionNumbers = [for (final q in questions) q.number];
      });
      await _loadAnswerLayoutPdf(layout);
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _runGuarded(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _errorMessage = null;
    });
    try {
      await action();
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _analyzeProfile() => _runGuarded(() async {
    final profile = await _dependencies.analyzeProfile(widget.testId);
    if (!mounted) return;
    setState(() {
      _profile = profile;
      _editableRegions = profile.regions.toList();
    });
  });

  /// Fetch the stored answer sheet into [_answerLayoutPdf], recording any
  /// failure in [_answerLayoutPdfError] instead of discarding it.
  ///
  /// This used to swallow the exception and fall back to blank page outlines.
  /// That produced the one outcome this whole screen exists to prevent: the
  /// AI's rectangles drawn on nothing, confirmable by someone who never saw
  /// the answer sheet (review round 1, P1 -- the same rule Issue #85 spent
  /// five rounds establishing, 見ていないものを確定させない).
  ///
  /// The failure does not fail the whole screen -- the dependency-graph
  /// section and everything else still work -- but it is shown, it is
  /// retryable, and while it stands the confirm is refused.
  Future<void> _loadAnswerLayoutPdf(AnswerLayoutResponse layout) async {
    if (layout.pageCount == null) {
      if (!mounted) return;
      setState(() {
        _answerLayoutPdf = null;
        _answerLayoutPdfError = null;
      });
      return;
    }
    try {
      final bytes = await _dependencies.getAnswerLayoutPdf(widget.testId);
      if (!mounted) return;
      setState(() {
        _answerLayoutPdf = bytes;
        _answerLayoutPdfError = null;
      });
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _answerLayoutPdf = null;
        _answerLayoutPdfError = error.message;
      });
    }
  }

  Future<void> _retryAnswerLayoutPdf() => _runGuarded(() async {
    final layout = _answerLayout;
    if (layout == null) return;
    await _loadAnswerLayoutPdf(layout);
  });

  Future<void> _uploadAnswerLayout() => _runGuarded(() async {
    final picked = await _pickPdfFile();
    if (picked == null) return;
    final layout = await _dependencies.uploadAnswerLayout(
      widget.testId,
      filePath: picked.path,
    );
    // The upload creates (or re-bases) the profile, so the working copy has
    // to be reloaded from it -- that is what makes 領域を手動追加 possible on
    // a test that never had a profile.
    final profile = await _dependencies.getProfile(widget.testId);
    if (!mounted) return;
    setState(() {
      _answerLayout = layout;
      _profile = profile;
      _editableRegions = profile.regions.toList();
    });
    await _loadAnswerLayoutPdf(layout);
    if (!mounted) return;
    final dropped = layout.droppedRegionCount;
    _showSnackBar(
      dropped == 0
          ? '答案を取り込みました。この答案の上で回答欄を決めます'
          : '答案を取り込みました。新しい答案に無いページの領域$dropped件は外しました',
    );
  });

  Future<void> _detectAnswerAreas() async {
    // Detection replaces every answer area, including ones drawn by hand --
    // the sidecar cannot tell them apart, and neither can this screen once
    // they are saved. Discarding somebody's work without saying so is the
    // same failure as merging two boxes nobody could attribute: the result
    // looks fine and the original is gone. So the count is named first,
    // exactly as Issue #101's delete flow names its blast radius.
    final existing = (_editableRegions ?? const <RegionModel>[])
        .where((region) => region.kind == RegionKind.answerArea)
        .length;
    if (existing > 0) {
      final proceed = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          key: const Key('redetect-confirm'),
          title: const Text('回答欄を検出し直しますか'),
          content: Text(
            'いまある回答欄$existing件を、検出結果で置き換えます。'
            '手で引いた回答欄も含めて置き換わり、元に戻せません。',
          ),
          actions: [
            TextButton(
              key: const Key('redetect-cancel'),
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text('やめる'),
            ),
            FilledButton(
              key: const Key('redetect-confirmed'),
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text('置き換える'),
            ),
          ],
        ),
      );
      if (proceed != true) return;
    }
    if (!mounted) return;
    return _runDetectAnswerAreas();
  }

  Future<void> _runDetectAnswerAreas() => _runGuarded(() async {
    final profile = await _dependencies.detectAnswerAreas(widget.testId);
    if (!mounted) return;
    setState(() {
      _profile = profile;
      _editableRegions = profile.regions.toList();
    });
    // Says what happened, not how well it went: the number of areas found is
    // a fact, the accuracy of them is not something this app has measured.
    // Counted from the regions just saved and this screen's own question
    // list, not from the response's snapshot -- one source, so the snackbar
    // and the panel below can never disagree.
    final undetected = _undetectedFrom(profile.regions.toList()).length;
    _showSnackBar(
      undetected == 0
          ? '回答欄を検出しました。答案の上で確認して直してください'
          : '回答欄を検出しました。見つからなかった設問が$undetected件あります',
    );
  });

  Future<void> _saveProfile() => _runGuarded(() async {
    final regions = _editableRegions;
    if (regions == null) return;
    final profile = await _dependencies.updateProfile(widget.testId, regions);
    if (!mounted) return;
    setState(() {
      _profile = profile;
      _editableRegions = profile.regions.toList();
    });
    _showSnackBar('プロファイルを保存しました');
  });

  Future<void> _confirmProfile() => _runGuarded(() async {
    final regions = _editableRegions;
    if (regions == null) return;
    // Persist whatever the reviewer edited/added/removed *before*
    // confirming: confirmProfile only ever sends the test id, so without
    // this an edit made after the last explicit "保存" tap (or never saved
    // at all) would be silently discarded and the server would confirm a
    // stale, previously-persisted region set instead (Issue #16 review).
    final saved = await _dependencies.updateProfile(widget.testId, regions);
    if (!mounted) return;
    setState(() {
      _profile = saved;
      _editableRegions = saved.regions.toList();
    });
    // Pinned to the revision this save just produced -- if another
    // client's edit lands on the server before this confirm call reaches
    // it, the server rejects it as stale instead of silently approving
    // regions this reviewer never saw (Issue #16 review round 8).
    final profile = await _dependencies.confirmProfile(
      widget.testId,
      revision: saved.revision,
    );
    // Confirming rebuilds the test's `Question` rows from the confirmed
    // regions, so the question set this screen was reading can change as a
    // *result* of this action. Re-read it rather than keep the list fetched
    // at load time -- otherwise the 未検出 notice below would be counted
    // against questions that no longer exist (review round 2).
    final questions = await _dependencies.listQuestions(widget.testId);
    if (!mounted) return;
    setState(() {
      _profile = profile;
      _editableRegions = profile.regions.toList();
      _questionNumbers = [for (final q in questions) q.number];
    });
    _showSnackBar('プロファイルを確定しました');
  });

  /// 抽出は**有料の provider に全ページを送る**。押した瞬間に送らず、
  /// 何ページ送るのか・いくらかかるのかを見せてから選んでもらう
  /// (Issue #103 コードレビュー P2-2)。再抽出でも同じだけかかる。
  Future<void> _extractCriteria() async {
    // 見積り取得 → 人に尋ねる → 抽出、の3段。**尋ねている間は `_busy` に
    // しない。** `_runGuarded` は進捗バーを出すが、アプリは待たされている
    // のではなく人の答えを待っているだけであり、進捗バーはそれを「処理中」
    // と偽って見せる（テストでも `pumpAndSettle` が止まらなくなる）。
    CriteriaEstimateResponse? estimate;
    await _runGuarded(() async {
      estimate = await _dependencies.estimateCriteria(widget.testId);
    });
    final confirmed = estimate;
    // 失敗していれば `_runGuarded` が既に画面へ理由を出している。
    if (confirmed == null || !mounted) return;
    final proceed = await showDialog<bool>(
      context: context,
      builder: (_) => _ExtractConfirmDialog(estimate: confirmed),
    );
    if (proceed != true || !mounted) return;
    await _runGuarded(_runExtraction);
  }

  Future<void> _runExtraction() async {
    final criteria = await _dependencies.extractCriteria(widget.testId);
    if (!mounted) return;
    setState(() {
      _criteria = criteria;
      _editableCriteria = criteria.questions.toList();
      _editableDeclaredTotal = criteria.declaredTotalPoints;
    });
    // Says what came back even when that is nothing. An extraction that
    // found no questions must not look like an extraction that did not run
    // (Issue #103 acceptance criterion 5: 黙って 0 件にしない).
    _showSnackBar('採点基準から ${criteria.questions.length} 件の設問を読み取りました');
  }

  Future<void> _saveCriteria() => _runGuarded(() async {
    final criteria = await _dependencies.updateCriteria(
      widget.testId,
      _editableCriteria,
      declaredTotalPoints: _editableDeclaredTotal,
    );
    if (!mounted) return;
    setState(() {
      _criteria = criteria;
      _editableCriteria = criteria.questions.toList();
      _editableDeclaredTotal = criteria.declaredTotalPoints;
    });
    _showSnackBar('配点と採点基準を保存しました');
  });

  Future<void> _confirmCriteria() => _runGuarded(() async {
    // Saved first, then confirmed against the revision that save produced --
    // the same two-step `_confirmProfile` uses, and for the same two
    // reasons: an edit made after the last explicit 保存 would otherwise be
    // discarded, and pinning the revision stops this confirm from approving
    // point values another client wrote in between.
    final saved = await _dependencies.updateCriteria(
      widget.testId,
      _editableCriteria,
      declaredTotalPoints: _editableDeclaredTotal,
    );
    if (!mounted) return;
    setState(() {
      _criteria = saved;
      _editableCriteria = saved.questions.toList();
      _editableDeclaredTotal = saved.declaredTotalPoints;
    });
    final confirmed = await _dependencies.confirmCriteria(
      widget.testId,
      revision: saved.revision,
    );
    if (!mounted) return;
    setState(() {
      _criteria = confirmed;
      _editableCriteria = confirmed.questions.toList();
      _editableDeclaredTotal = confirmed.declaredTotalPoints;
    });
    _showSnackBar('配点と採点基準を確定し、設問に反映しました');
  });

  Future<void> _analyzeDependencyGraph() => _runGuarded(() async {
    // The dependency analyzer only sees 問題文 (prompt text) via an
    // explicit override -- `Question` has no column for it yet, so unless
    // this is passed, a dependency stated only in a question's own prompt
    // (as opposed to the model answer or rubric, which the analyzer already
    // reads from the confirmed Question/Rubric rows) would be invisible and
    // the analyzer could wrongly conclude "no dependency" (Issue #16
    // review). QUESTION regions only exist once the profile has been
    // confirmed (that's also a prerequisite for this endpoint to find any
    // Question rows at all), so `_profile` here always holds the confirmed
    // set with real text.
    final overrides = [
      for (final region in _profile?.regions ?? const <RegionModel>[])
        if (region.kind == RegionKind.question)
          QuestionTextOverride(
            (b) => b
              ..questionId = '${widget.testId}:${region.label}'
              ..promptText = region.text,
          ),
    ];
    final graph = await _dependencies.analyzeDependencyGraph(
      widget.testId,
      overrides: overrides,
    );
    if (!mounted) return;
    setState(() {
      _dependencyGraph = graph;
      _editableEdges = graph.edges.toList();
    });
  });

  Future<void> _confirmDependencyGraph() => _runGuarded(() async {
    final graph = _dependencyGraph;
    final edges = _editableEdges;
    if (graph == null || edges == null) return;
    final confirmed = await _dependencies.confirmDependencyGraph(
      widget.testId,
      version: graph.version,
      edges: edges,
    );
    if (!mounted) return;
    setState(() {
      _dependencyGraph = confirmed;
      _editableEdges = confirmed.edges.toList();
    });
    _showSnackBar('設問依存関係グラフを確定しました');
  });

  Future<void> _completeRegistration() => _runGuarded(() async {
    final result = await _dependencies.completeRegistration(widget.testId);
    if (!mounted) return;
    setState(() => _test = result.test);
    _showSnackBar('テスト登録が完了しました');
  });

  void _showSnackBar(String message) {
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  bool get _profileConfirmed => _profile?.status == 'confirmed';
  bool get _isReady => _test?.status == 'ready';

  bool get _dependencyGraphConfirmed => _dependencyGraph?.status == 'confirmed';

  /// 確定済みグラフが、もういまの設問集合を説明していないか。
  ///
  /// 確定済みグラフは不変だが**テストの設問はそうではない。** サーバは
  /// その食い違いを「未確定」と同じに扱って `complete-registration` を
  /// 409 で断る（`domain.dependency_graph.can_start_submission_processing`）。
  /// 画面は `status` だけを見ていたので、**サーバが断る状態で「残っている
  /// ことはありません」と出していた。** 配点を確定すると設問行が作り直される
  /// ため、この経路は Issue #103 で新しく踏めるようになった。
  ///
  /// **警告するだけで、ボタンは塞がない。** 期待する設問集合は画面が持つ
  /// 情報から組み立てた**推定**であり、外したときに正当な操作を止めてしまう
  /// のは、誤った「全部済み」より悪い。関門はサーバのままにして、こちらは
  /// 「押す前に気づける」ことだけを担う。
  bool get _dependencyGraphIsStale {
    final graph = _dependencyGraph;
    if (graph == null || graph.status != 'confirmed') return false;
    return !dependencyGraphDescribesQuestions(
      testId: widget.testId,
      graphQuestionIds: graph.questionIds,
      // 未確定のドラフトは設問行になっていないので数に入れない
      // （サーバの `_confirmed_criteria` と同じ判断）。
      criteriaNumbers: _criteriaConfirmed
          ? _editableCriteria.map((question) => question.number)
          : const <String>[],
      questionRegionLabels: _profileConfirmed
          ? (_editableRegions ?? const <RegionModel>[])
                .where((region) => region.kind == RegionKind.question)
                .map((region) => region.label)
          : const <String>[],
    );
  }

  void _addRegion() {
    final regions = _editableRegions;
    if (regions == null) return;
    setState(() {
      regions.add(
        RegionModel(
          (b) => b
            ..regionId = 'manual-${regions.length + 1}'
            ..kind = RegionKind.question
            ..pageIndex = 0
            ..label = ''
            ..confirmed = false
            ..bbox.x0 = 0.1
            ..bbox.y0 = 0.1
            ..bbox.x1 = 0.3
            ..bbox.y1 = 0.2,
        ),
      );
    });
  }

  Future<void> _editRegion(int index) async {
    final regions = _editableRegions;
    if (regions == null) return;
    final updated = await showDialog<RegionModel>(
      context: context,
      builder: (_) => _RegionEditDialog(region: regions[index]),
    );
    if (updated == null) return;
    setState(() => regions[index] = updated);
  }

  bool get _criteriaConfirmed => _criteria?.status == CriteriaStatus.confirmed;

  /// このテストが、確定済みの「配点と採点基準」**なしでも**配点を持てるか。
  ///
  /// Issue #103 以前に登録されたテストは `SCORE` 領域のテキストから配点を
  /// 読む（`domain.test_registration` の後方互換 fallback）。そういうテストで
  /// 「配点と採点基準が未確定です」を残作業として並べると、**実際には
  /// 登録完了を止めていないもの**を止めているように見せることになる。
  /// `complete-registration` の関門はプロファイルと依存グラフだけである。
  bool get _hasFallbackScoreRegions =>
      (_editableRegions ?? const <RegionModel>[]).any(
        (region) => region.kind == RegionKind.score,
      );

  /// A new, entirely blank question. `points` is deliberately left `null`
  /// (不明) rather than seeded with 0 or 1: a placeholder number is a number
  /// somebody can confirm without ever having read the real one.
  void _addCriteriaQuestion() {
    setState(() {
      _editableCriteria = [
        ..._editableCriteria,
        CriteriaQuestionModel(
          (b) => b..number = '問${_editableCriteria.length + 1}',
        ),
      ];
    });
  }

  void _removeCriteriaQuestion(int index) {
    setState(() {
      _editableCriteria = [..._editableCriteria]..removeAt(index);
    });
  }

  Future<void> _editCriteriaQuestion(int index) async {
    final updated = await showDialog<CriteriaQuestionModel>(
      context: context,
      builder: (_) =>
          _CriteriaQuestionEditDialog(question: _editableCriteria[index]),
    );
    if (updated == null) return;
    setState(() {
      _editableCriteria = [..._editableCriteria]..[index] = updated;
    });
  }

  Future<void> _editDeclaredTotal() async {
    final updated = await showDialog<_DeclaredTotalResult>(
      context: context,
      builder: (_) => _DeclaredTotalDialog(value: _editableDeclaredTotal),
    );
    if (updated == null) return;
    setState(() => _editableDeclaredTotal = updated.value);
  }

  void _addEdge() {
    final questionIds = _dependencyGraph?.questionIds.toList() ?? const [];
    if (questionIds.length < 2) return;
    setState(() {
      _editableEdges?.add(
        DependencyEdgeModel(
          (b) => b
            ..fromQuestionId = questionIds[0]
            ..toQuestionId = questionIds[1]
            ..rationale = '人間が追加'
            ..provides.replace([DependencyProvision.recognizedText]),
        ),
      );
    });
  }

  void _removeEdge(int index) {
    setState(() => _editableEdges?.removeAt(index));
  }

  Future<void> _editEdge(int index) async {
    final edges = _editableEdges;
    final questionIds = _dependencyGraph?.questionIds.toList();
    if (edges == null || questionIds == null) return;
    final updated = await showDialog<DependencyEdgeModel>(
      context: context,
      builder: (_) =>
          _EdgeEditDialog(edge: edges[index], questionIds: questionIds),
    );
    if (updated == null) return;
    setState(() => edges[index] = updated);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_test?.name ?? 'テスト設定')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _loadAll,
              child: ListView(
                padding: AppSpacing.panel,
                children: [
                  _buildStatusBanner(),
                  if (_errorMessage != null) ...[
                    const SizedBox(height: AppSpacing.sm),
                    _buildErrorBanner(),
                  ],
                  if (_busy) ...[
                    const SizedBox(height: AppSpacing.sm),
                    const LinearProgressIndicator(),
                  ],
                  const SizedBox(height: AppSpacing.lg),
                  _buildProfileSection(),
                  const SizedBox(height: AppSpacing.xl),
                  _buildCriteriaSection(),
                  const SizedBox(height: AppSpacing.xl),
                  _buildDependencyGraphSection(),
                  const SizedBox(height: AppSpacing.xl),
                  _buildCompleteRegistrationButton(),
                ],
              ),
            ),
    );
  }

  Widget _buildStatusBanner() {
    final status = _test?.status ?? 'draft';
    return Card(
      child: Padding(
        padding: AppSpacing.banner,
        child: Row(
          children: [
            Icon(
              status == 'ready' ? Icons.verified : Icons.pending_actions,
              color:
                  (status == 'ready'
                          ? AppStatusTone.success
                          : AppStatusTone.neutral)
                      .color(context),
            ),
            const SizedBox(width: AppSpacing.sm),
            Text(
              status == 'ready' ? 'テスト状態: 登録完了' : 'テスト状態: 下書き',
              key: const Key('test-status-label'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildErrorBanner() {
    // `retryable: false`: this screen's failures always belong to one of its
    // explicit actions (自動解析, 保存, 確定, 登録完了), and the reviewer
    // re-presses that button -- a generic 再試行 could not know which.
    return AppErrorBanner(
      message: _errorMessage!,
      messageKey: const Key('settings-error-message'),
      retryable: false,
    );
  }

  /// Questions with no `ANSWER_AREA` in [regions].
  ///
  /// Computed from the working copy every time it is asked for, never taken
  /// from the last server response. A stored answer goes stale the moment the
  /// reviewer draws the missing box or reassigns one -- and that moment is
  /// exactly when it is being read (review round 1, P2).
  List<String> _undetectedFrom(List<RegionModel> regions) {
    final covered = {
      for (final region in regions)
        if (region.kind == RegionKind.answerArea) region.label,
    };
    return [
      for (final number in _questionNumbers)
        if (!covered.contains(number)) number,
    ];
  }

  /// Answer areas that name no confirmed question. These block the confirm --
  /// `build_questions_and_rubrics` ignores them without a word.
  List<RegionModel> _unassignedFrom(List<RegionModel> regions) {
    final known = _questionNumbers.toSet();
    return [
      for (final region in regions)
        if (region.kind == RegionKind.answerArea &&
            !known.contains(region.label))
          region,
    ];
  }

  /// Whether the answer sheet the regions are drawn on is actually on screen.
  ///
  /// Confirming answer-area coordinates is attesting to where they sit on a
  /// page. Doing that against blank outlines is confirming something nobody
  /// looked at, so it is refused while any answer area exists and the sheet
  /// is not displayed (review round 1, P1; Issue #85's rule).
  bool _mustSeeAnswerSheetFirst(List<RegionModel> regions) =>
      _answerLayoutPdf == null &&
      regions.any((region) => region.kind == RegionKind.answerArea);

  Widget _buildProfileSection() {
    final regions = _editableRegions;
    final working = regions ?? const <RegionModel>[];
    // All three are derived from the working copy, not from the last server
    // response: the reviewer assigns a question, draws a box, or deletes one,
    // and every one of these has to follow that click -- not the next 保存
    // round-trip.
    final unassigned = _unassignedFrom(working);
    final undetected = _undetectedFrom(working);
    final unseenSheet = _mustSeeAnswerSheetFirst(working);
    return Card(
      child: Padding(
        padding: AppSpacing.card,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    'テストプロファイル（設問・回答欄・添削記号領域の位置）',
                    style: context.texts.titleMedium,
                  ),
                ),
                if (_profileConfirmed)
                  const Chip(label: Text('確認済み'))
                else
                  const Chip(label: Text('未確認')),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            _buildAnswerLayoutControls(),
            const SizedBox(height: AppSpacing.md),
            if (regions == null)
              const Text(
                'まだ回答欄がありません。答案を取り込んで「回答欄を自動検出」するか、'
                '「領域を手動追加」で引いてください。',
              )
            else
              AnswerAreaEditor(
                key: const Key('answer-area-editor'),
                pages: _profile?.pages.toList() ?? const <PageFormatModel>[],
                regions: regions,
                questionNumbers: _questionNumbers,
                undetectedQuestionNumbers: undetected,
                pdfBytes: _answerLayoutPdf,
                readOnly: _busy || _profileConfirmed,
                onRegionsChanged: (next) =>
                    setState(() => _editableRegions = next),
                onEditNumerically: _editRegion,
              ),
            const SizedBox(height: AppSpacing.md),
            // Everything that stands between the reviewer and a confirm is
            // stated *here*, next to the button, not only up in the editor.
            // A reason that is only visible after scrolling back is a reason
            // nobody reads before pressing.
            if (unassigned.isNotEmpty)
              _buildConfirmBlocker(
                key: const Key('unassigned-region-warning'),
                message:
                    '設問が割り当てられていない回答欄が${unassigned.length}件あります。'
                    '設問を選ぶか削除するまで確定できません。',
              ),
            if (unseenSheet)
              _buildConfirmBlocker(
                key: const Key('unseen-answer-sheet-warning'),
                message: _answerLayout?.pageCount == null
                    ? '回答欄の位置は答案の上で確認します。'
                          '答案を取り込むまで確定できません。'
                    : '答案を表示できていません。'
                          '実際の答案を見ないまま確定はできません。上の再試行を押してください。',
              ),
            // Not a blocker: a question with no回答欄 still grades -- against
            // the whole page, marked 要確認, in front of a human. Shown at
            // the point of confirming all the same, so nobody confirms a
            // newly-created gap without being told (review round 1, P2).
            if (undetected.isNotEmpty)
              Padding(
                key: const Key('undetected-question-notice'),
                padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                child: Text(
                  '回答欄が決まっていない設問が${undetected.length}件あります'
                  '（${undetected.join("、")}）。'
                  'このまま確定もできますが、その設問は答案のページ全体を採点に送り、'
                  '要確認として人の目に回ります。',
                  style: context.texts.bodyMedium,
                ),
              ),
            Wrap(
              spacing: AppSpacing.sm,
              children: [
                OutlinedButton.icon(
                  key: const Key('save-profile-button'),
                  onPressed: (_busy || regions == null || _profileConfirmed)
                      ? null
                      : _saveProfile,
                  icon: const Icon(Icons.save_outlined),
                  label: const Text('修正内容を保存'),
                ),
                FilledButton.icon(
                  key: const Key('confirm-profile-button'),
                  onPressed:
                      (_busy ||
                          regions == null ||
                          regions.isEmpty ||
                          unassigned.isNotEmpty ||
                          unseenSheet ||
                          _profileConfirmed)
                      ? null
                      : _confirmProfile,
                  icon: const Icon(Icons.check_circle_outline),
                  label: const Text('プロファイルを確定'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  /// One reason the confirm is refused, in the attention tone, rendered
  /// immediately above the confirm button.
  Widget _buildConfirmBlocker({required Key key, required String message}) {
    return Padding(
      key: key,
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Text(
        message,
        style: context.texts.bodyMedium?.copyWith(
          color: AppStatusTone.attention.color(context),
        ),
      ),
    );
  }

  /// The 答案 / 自動検出 controls above the overlay.
  ///
  /// Every state here is spelled out rather than reduced to a disabled
  /// button: "no answer sheet uploaded" and "no image-capable provider on
  /// this machine" are different problems with different fixes, and in both
  /// cases the reviewer can still draw the boxes by hand -- which the copy
  /// has to say, or a blocked screen reads as a broken one.
  Widget _buildAnswerLayoutControls() {
    final layout = _answerLayout;
    final hasSheet = layout?.pageCount != null;
    final detectionAvailable = layout?.detectionAvailable ?? false;
    // From the questions themselves, not from the profile: a test that has
    // never had a profile still has confirmed questions, and this is the
    // gate on the very first detection (review round 1, P1).
    final hasQuestions = _questionNumbers.isNotEmpty;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.sm,
          children: [
            OutlinedButton.icon(
              key: const Key('upload-answer-layout-button'),
              onPressed: (_busy || _profileConfirmed)
                  ? null
                  : _uploadAnswerLayout,
              icon: const Icon(Icons.upload_file_outlined),
              label: Text(hasSheet ? '別の答案に差し替える' : '回答欄を決める答案を選ぶ'),
            ),
            FilledButton.icon(
              key: const Key('detect-answer-areas-button'),
              onPressed:
                  (_busy ||
                      _profileConfirmed ||
                      !hasSheet ||
                      !detectionAvailable ||
                      !hasQuestions)
                  ? null
                  : _detectAnswerAreas,
              icon: const Icon(Icons.auto_fix_high),
              label: const Text('回答欄を自動検出'),
            ),
            OutlinedButton.icon(
              key: const Key('add-region-button'),
              // Disabled rather than silently doing nothing: without a
              // profile there is no page format to place a region on, and
              // `_addRegion` used to return without a word in that state.
              onPressed:
                  (_busy || _profileConfirmed || _editableRegions == null)
                  ? null
                  : _addRegion,
              icon: const Icon(Icons.add_box_outlined),
              label: const Text('領域を手動追加'),
            ),
            // The pre-Issue-#105 path: derive regions from a registered
            // model-answer PDF's text. Kept for tests registered that way,
            // and deliberately not the primary action -- real material has no
            // model-answer PDF (Issue #95 decision 1), so for a test
            // registered from a 採点基準 alone this answers 409.
            TextButton.icon(
              key: const Key('analyze-profile-button'),
              onPressed: (_busy || _profileConfirmed) ? null : _analyzeProfile,
              icon: const Icon(Icons.description_outlined),
              label: const Text('模範解答PDFから解析（旧方式）'),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.sm),
        if (!hasSheet)
          Text(
            '回答欄は答案そのものの上で決めます。'
            'この様式の答案を1枚選んでください。'
            '確定した回答欄は、同じ様式の答案すべてに使われます。',
            key: const Key('answer-layout-missing'),
            style: context.texts.bodySmall,
          )
        else ...[
          Text(
            '${layout!.pageCount}ページの答案を取り込んでいます。'
            '自動検出はこの答案の全ページをAIに送ります（テストにつき1回）。'
            '採点のときに送るのは、切り出した回答欄の画像だけです。'
            'ページに印字・手書きされているものはそのまま送られます。'
            '手書きの氏名を確実に消す方法はありません。',
            key: const Key('answer-layout-present'),
            style: context.texts.bodySmall,
          ),
          // The count is exact; the money is not knowable here. Saying
          // "0円" would be a number this app has no basis for, so it says
          // it cannot estimate and why -- the same rule PR #104 and #107
          // applied to their own cost lines.
          Text(
            '実行するとAIを1回呼び、${layout.pageCount}ページ分の画像を送ります。'
            '費用の単価を設定していないため、金額は見積もれません。'
            '押し直すたびに同じだけ呼び出します。',
            key: const Key('answer-layout-cost'),
            style: context.texts.bodySmall,
          ),
        ],
        if (_answerLayoutPdfError != null)
          Padding(
            key: const Key('answer-layout-pdf-error'),
            padding: const EdgeInsets.only(top: AppSpacing.sm),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    // Never silently: without the sheet on screen the
                    // rectangles below are drawn on nothing, and confirming
                    // them is confirming something nobody looked at.
                    '答案を表示できませんでした（$_answerLayoutPdfError）。'
                    '実際の答案を見るまで確定はできません。',
                    style: context.texts.bodySmall?.copyWith(
                      color: AppStatusTone.attention.color(context),
                    ),
                  ),
                ),
                TextButton.icon(
                  key: const Key('retry-answer-layout-pdf-button'),
                  onPressed: _busy ? null : _retryAnswerLayoutPdf,
                  icon: const Icon(Icons.refresh),
                  label: const Text('再試行'),
                ),
              ],
            ),
          ),
        if (hasSheet && !hasQuestions)
          Text(
            '自動検出には設問一覧が必要です。先に配点と採点基準を確定してください。'
            'それまでは「領域を手動追加」で引けます。',
            key: const Key('answer-layout-needs-questions'),
            style: context.texts.bodySmall,
          ),
        if (!detectionAvailable && layout != null)
          Text(
            layout.detectionUnavailableReason ??
                '回答欄の自動検出は、このパソコンでは使えません。手動で引いてください。',
            key: const Key('answer-layout-detection-unavailable'),
            style: context.texts.bodySmall,
          ),
      ],
    );
  }

  Widget _buildCriteriaSection() {
    // Recomputed from the *editable* list every build, never read from
    // `_criteria!.totals`: the saved total describes the list as it was at
    // the last save, and showing it beside unsaved edits would report a sum
    // for rows that are no longer on screen. Same rule, same reason, as the
    // dependency graph's execution layers below.
    final totals = criteriaTotals(
      _editableCriteria,
      declaredTotalPoints: _editableDeclaredTotal,
    );
    final blockingReason = criteriaBlockingReason(_editableCriteria);
    final criteria = _criteria;
    return Card(
      child: Padding(
        padding: AppSpacing.card,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text('配点と採点基準', style: context.texts.titleMedium),
                ),
                if (_criteriaConfirmed)
                  const Chip(label: Text('確認済み'))
                else
                  const Chip(label: Text('未確認')),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            Wrap(
              spacing: AppSpacing.sm,
              children: [
                FilledButton.icon(
                  key: const Key('extract-criteria-button'),
                  onPressed: (_busy || _criteriaConfirmed)
                      ? null
                      : _extractCriteria,
                  icon: const Icon(Icons.auto_fix_high),
                  label: const Text('採点基準PDFから抽出'),
                ),
                // Deliberately not gated on an extraction having run or
                // succeeded: a subject whose criteria PDF the model cannot
                // read at all must still be enterable by hand, which is
                // exactly the case this button exists for (Issue #95
                // 決定 8).
                OutlinedButton.icon(
                  key: const Key('add-criteria-question-button'),
                  onPressed: (_busy || _criteriaConfirmed)
                      ? null
                      : _addCriteriaQuestion,
                  icon: const Icon(Icons.playlist_add),
                  label: const Text('設問を手で追加'),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.md),
            _buildCriteriaSummary(totals),
            if (criteria != null && criteria.unreadablePages.isNotEmpty) ...[
              const SizedBox(height: AppSpacing.xs),
              _buildCriteriaWarning(
                key: const Key('criteria-unreadable-pages'),
                message:
                    '${criteria.unreadablePages.join('・')} ページは読み取れませんでした。'
                    'そのページの設問は手で追加してください。',
              ),
            ],
            if (criteria?.note != null) ...[
              const SizedBox(height: AppSpacing.xs),
              _buildCriteriaWarning(
                key: const Key('criteria-note'),
                message: criteria!.note!,
              ),
            ],
            const SizedBox(height: AppSpacing.md),
            if (_editableCriteria.isEmpty)
              Text(
                criteria?.extracted == true
                    ? '抽出は実行しましたが、設問を1件も読み取れませんでした。'
                          '「設問を手で追加」で入力してください。'
                    : 'まだ抽出されていません。'
                          '「採点基準PDFから抽出」を実行するか、手で追加してください。',
                key: const Key('criteria-empty-message'),
              )
            else
              ..._editableCriteria.asMap().entries.map(
                (entry) => _buildCriteriaTile(entry.key, entry.value),
              ),
            const SizedBox(height: AppSpacing.md),
            if (blockingReason != null && !_criteriaConfirmed)
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                child: Text(
                  blockingReason,
                  key: const Key('criteria-blocking-reason'),
                  style: context.texts.bodySmall?.copyWith(
                    color: AppStatusTone.attention.color(context),
                  ),
                ),
              ),
            Wrap(
              spacing: AppSpacing.sm,
              children: [
                OutlinedButton.icon(
                  key: const Key('edit-declared-total-button'),
                  onPressed: (_busy || _criteriaConfirmed)
                      ? null
                      : _editDeclaredTotal,
                  icon: const Icon(Icons.functions),
                  label: const Text('総得点を修正'),
                ),
                OutlinedButton.icon(
                  key: const Key('save-criteria-button'),
                  onPressed: (_busy || _criteriaConfirmed)
                      ? null
                      : _saveCriteria,
                  icon: const Icon(Icons.save_outlined),
                  label: const Text('修正内容を保存'),
                ),
                FilledButton.icon(
                  key: const Key('confirm-criteria-button'),
                  onPressed:
                      (_busy || _criteriaConfirmed || blockingReason != null)
                      ? null
                      : _confirmCriteria,
                  icon: const Icon(Icons.check_circle_outline),
                  label: const Text('確定して設問に反映'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  /// 合計と不明件数を**必ず並べて**出す。不明を含む一覧の横に合計だけを置くと、
  /// それが満点だと読める (Issue #103 受入条件 4・5)。
  Widget _buildCriteriaSummary(CriteriaTotals totals) {
    final difference = totals.declaredDifference;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          totals.unknownCount == 0
              ? '配点の合計 ${totals.knownPoints} 点'
              : '配点の合計 ${totals.knownPoints} 点 ・ 配点不明 ${totals.unknownCount} 問',
          key: const Key('criteria-totals-label'),
          style: context.texts.titleSmall,
        ),
        if (totals.declaredTotalPoints != null)
          Text(
            '採点基準PDFの総得点: ${totals.declaredTotalPoints} 点',
            key: const Key('criteria-declared-total-label'),
            style: context.texts.bodySmall,
          ),
        if (difference != null) ...[
          const SizedBox(height: AppSpacing.xs),
          _buildCriteriaWarning(
            key: const Key('criteria-total-mismatch'),
            message:
                '採点基準PDFの総得点 ${totals.declaredTotalPoints} 点と一致しません'
                '（差 ${difference.abs()} 点）。抽出漏れの可能性があります。',
          ),
        ],
      ],
    );
  }

  Widget _buildCriteriaWarning({required Key key, required String message}) {
    return Row(
      key: key,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(
          Icons.warning_amber_outlined,
          size: AppIconSize.dense,
          color: AppStatusTone.attention.color(context),
        ),
        const SizedBox(width: AppSpacing.xs),
        Expanded(
          child: Text(
            message,
            style: context.texts.bodySmall?.copyWith(
              color: AppStatusTone.attention.color(context),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildCriteriaTile(int index, CriteriaQuestionModel question) {
    final unknown = question.points == null;
    final pages = question.sourcePages.isEmpty
        ? null
        : 'p.${question.sourcePages.join('・')}';
    final details = [
      '採点基準 ${question.criteria.length} 件',
      if (question.modelAnswer?.trim().isNotEmpty ?? false) '模範解答あり',
      ?pages,
      if (question.note?.trim().isNotEmpty ?? false) question.note!.trim(),
    ].join(' ・ ');
    return ListTile(
      key: Key('criteria-tile-$index'),
      // 不明だけが強調色を使う。この画面で色が意味を持つ唯一の箇所で、
      // 文言（「配点: 不明」）だけでも同じことが分かるようにしてある
      // (AGENTS.md「非色依存」)。
      leading: Icon(
        unknown ? Icons.help_outline : Icons.grade_outlined,
        color: unknown ? AppStatusTone.attention.color(context) : null,
      ),
      title: Text(
        unknown
            ? '設問${question.number} ・ 配点: 不明'
            : '設問${question.number} ・ 配点 ${question.points} 点',
      ),
      subtitle: Text(details),
      trailing: _criteriaConfirmed
          ? null
          : Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                  key: Key('edit-criteria-$index'),
                  icon: const Icon(Icons.edit_outlined),
                  tooltip: '編集',
                  onPressed: () => _editCriteriaQuestion(index),
                ),
                IconButton(
                  key: Key('remove-criteria-$index'),
                  icon: const Icon(Icons.delete_outline),
                  tooltip: '削除',
                  onPressed: () => _removeCriteriaQuestion(index),
                ),
              ],
            ),
    );
  }

  Widget _buildDependencyGraphSection() {
    final graph = _dependencyGraph;
    final edges = _editableEdges;
    // Not `graph.layers`: that is a snapshot from the last analyze/confirm
    // response, and goes stale the moment a reviewer adds, edits, or
    // removes an edge below -- showing it here would let a reviewer
    // confirm a hand-edited graph while still looking at the old
    // parallel-execution plan (Issue #16 review round 3).
    final layers = graph == null
        ? null
        : dependencyExecutionLayers(
            graph.questionIds.toList(),
            edges ?? const [],
          );
    return Card(
      child: Padding(
        padding: AppSpacing.card,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text('設問依存関係グラフ', style: context.texts.titleMedium),
                ),
                if (_dependencyGraphConfirmed)
                  const Chip(label: Text('確認済み'))
                else
                  const Chip(label: Text('未確認')),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            Wrap(
              spacing: AppSpacing.sm,
              children: [
                FilledButton.icon(
                  key: const Key('analyze-dependency-graph-button'),
                  // Gated on the *profile* being confirmed, not merely
                  // analyzed: Question rows (what the dependency-graph
                  // endpoint actually operates on) are only created by
                  // confirmProfile, so tapping this in the normal
                  // draft-profile interim would always hit the backend's
                  // 404 "no questions to analyze" (Issue #16 review).
                  //
                  // Not gated on `_dependencyGraphConfirmed`: a confirmed
                  // graph is immutable, but `/dependency-graph/analyze`
                  // always starts a new, higher-versioned DRAFT rather than
                  // touching it -- disabling this once confirmed left a
                  // reviewer who spots a bad edge before or after
                  // registration with no way back into the settings screen
                  // to fix it (Issue #16 review round 3).
                  onPressed: (_busy || !_profileConfirmed)
                      ? null
                      : _analyzeDependencyGraph,
                  icon: const Icon(Icons.auto_fix_high),
                  label: const Text('依存関係を分析（再実行）'),
                ),
                OutlinedButton.icon(
                  key: const Key('add-edge-button'),
                  onPressed:
                      (_busy ||
                          _dependencyGraphConfirmed ||
                          graph == null ||
                          graph.questionIds.length < 2)
                      ? null
                      : _addEdge,
                  icon: const Icon(Icons.add_link),
                  label: const Text('依存関係を手動追加'),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.md),
            if (graph == null)
              const Text('まだ分析されていません。「依存関係を分析」を実行してください。')
            else ...[
              if (edges == null || edges.isEmpty)
                const Text('依存関係はありません（すべて独立した設問）。')
              else
                ...edges.asMap().entries.map(
                  (entry) => _buildEdgeTile(entry.key, entry.value),
                ),
              if (graph.unresolved.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.sm),
                Text('要確認（AIが依存を判断できなかった設問）', style: context.texts.titleSmall),
                // Read against the *working* edge set, not the response these
                // entries came in. A reviewer who answers one of these does
                // so by adding an edge in the list above, and leaving the
                // entry untouched says their edit never happened -- the same
                // shape the `layers` note above already guards against
                // (review round 2). Nothing is hidden: the entry stays, so a
                // reviewer can still see what the analyzer could not decide.
                for (final unresolved in graph.unresolved)
                  Builder(
                    builder: (context) {
                      final answered = (edges ?? const <DependencyEdgeModel>[])
                          .any(
                            (edge) =>
                                edge.toQuestionId == unresolved.questionId,
                          );
                      return ListTile(
                        key: Key('unresolved-${unresolved.questionId}'),
                        // AIが判断できなかった設問は、人間が決めるまで先へ進めない
                        // -- この画面で強調色を使う唯一の箇所 (`AppStatusTone`)。
                        leading: Icon(
                          answered
                              ? Icons.check_circle_outline
                              : Icons.help_outline,
                          color: answered
                              ? AppStatusTone.success.color(context)
                              : AppStatusTone.attention.color(context),
                        ),
                        title: Text('設問 ${unresolved.questionId}'),
                        subtitle: Text(
                          answered
                              ? '${unresolved.reason}\n→ この設問への依存関係を追加済み'
                              : unresolved.reason,
                        ),
                        isThreeLine: answered,
                      );
                    },
                  ),
              ],
              const SizedBox(height: AppSpacing.sm),
              Text('並列実行可能な層', style: context.texts.titleSmall),
              if (layers == null)
                const Text('循環した依存関係があるため層を計算できません。確定前に解消してください。')
              else
                for (final (i, layer) in layers.indexed)
                  Text('第${i + 1}層: ${layer.join(', ')}'),
            ],
            const SizedBox(height: AppSpacing.md),
            FilledButton.icon(
              key: const Key('confirm-dependency-graph-button'),
              onPressed: (_busy || graph == null || _dependencyGraphConfirmed)
                  ? null
                  : _confirmDependencyGraph,
              icon: const Icon(Icons.check_circle_outline),
              label: const Text('依存関係グラフを確定'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEdgeTile(int index, DependencyEdgeModel edge) {
    return ListTile(
      key: Key('edge-tile-$index'),
      leading: const Icon(Icons.arrow_forward),
      title: Text('${edge.fromQuestionId} → ${edge.toQuestionId}'),
      subtitle: Text(edge.rationale),
      trailing: _dependencyGraphConfirmed
          ? null
          : Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                  icon: const Icon(Icons.edit_outlined),
                  tooltip: '編集',
                  onPressed: () => _editEdge(index),
                ),
                IconButton(
                  icon: const Icon(Icons.delete_outline),
                  tooltip: '削除',
                  onPressed: () => _removeEdge(index),
                ),
              ],
            ),
    );
  }

  Widget _buildCompleteRegistrationButton() {
    final canComplete =
        !_busy && !_isReady && _profileConfirmed && _dependencyGraphConfirmed;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        FilledButton.icon(
          key: const Key('complete-registration-button'),
          onPressed: canComplete ? _completeRegistration : null,
          icon: const Icon(Icons.task_alt),
          label: Text(_isReady ? '登録完了済み' : '登録完了'),
        ),
        const SizedBox(height: AppSpacing.sm),
        _buildRemainingWork(),
      ],
    );
  }

  /// なぜまだ採点が始まらないのかを、確定するたびに読める形で出す。
  ///
  /// 配点を確定しても、回答欄（テストプロファイル）と設問依存グラフが未確定
  /// なら `complete-registration` は 409 で止まる。それを押してから初めて
  /// 知るのでは遅い。#104 の取込完了画面と同じ規律で、**できないことを
  /// できるように見せない**。
  ///
  /// 回答欄については「別 Issue で対応中」とだけ書き、Issue 番号は書かない。
  /// この実装時点でその Issue はまだ起票されておらず、確かめていない番号を
  /// 画面に出すことになるため。
  Widget _buildRemainingWork() {
    if (_isReady) {
      return Text(
        '登録が完了しています。答案を取り込むと採点が始まります。',
        key: const Key('remaining-work-label'),
        style: context.texts.bodySmall,
      );
    }
    final remaining = <String>[
      if (!_criteriaConfirmed && !_hasFallbackScoreRegions) '配点と採点基準が未確定です',
      if (!_profileConfirmed) '回答欄（テストプロファイル）が未確定です',
      if (!_dependencyGraphConfirmed)
        '設問依存関係グラフが未確定です'
      else if (_dependencyGraphIsStale)
        '設問が変わったため、設問依存関係グラフを分析し直して確定してください'
            '（このまま「登録完了」を押すと断られます）',
    ];
    if (remaining.isEmpty) {
      return Text(
        '「登録完了」を押すと採点を開始できる状態になります。',
        key: const Key('remaining-work-label'),
        style: context.texts.bodySmall,
      );
    }
    return Column(
      key: const Key('remaining-work-label'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('採点を始めるには、まだ次が残っています:', style: context.texts.bodySmall),
        for (final item in remaining)
          Text('・$item', style: context.texts.bodySmall),
        if (_criteriaConfirmed && !_profileConfirmed) ...[
          const SizedBox(height: AppSpacing.xs),
          Text(
            // Issue #103 wrote this when 自動検出 did not exist yet. It does
            // now, so the copy points at it -- shipping a screen that calls a
            // shipped feature unimplemented is worse than the diff.
            '配点は確定しました。採点の開始には回答欄の設定が必要です。'
            '上の「回答欄を決める答案を選ぶ」で答案を1枚取り込み、'
            '「回答欄を自動検出」するか「領域を手動追加」で引いて確定してください。',
            key: const Key('criteria-confirmed-next-step'),
            style: context.texts.bodySmall,
          ),
        ],
      ],
    );
  }
}

/// 座標を引くための種類だけ。配点・採点基準・模範解答は「配点と採点基準」節で
/// 入力する (Issue #103 受入条件 7)。
const List<RegionKind> _coordinateRegionKinds = [
  RegionKind.question,
  RegionKind.answerArea,
  RegionKind.annotationArea,
];

/// 領域編集ダイアログの種類ドロップダウンに出す選択肢。
///
/// `current` が旧来の `SCORE`/`RUBRIC`/`MODEL_ANSWER`（Issue #103 以前に自動
/// 解析が作った領域）のときは、**その値だけ**を足す。取り除くと
/// `DropdownButtonFormField` の `initialValue` が候補に無い状態になって
/// アサーションで落ちるうえ、既存の領域を開けなくなる。新しく作ることは
/// できない、が正しい落としどころ。
List<RegionKind> _selectableRegionKinds(RegionKind current) =>
    _coordinateRegionKinds.contains(current)
    ? _coordinateRegionKinds
    : [..._coordinateRegionKinds, current];

String _regionKindLabel(RegionKind kind) => switch (kind) {
  RegionKind.question => '問題文',
  RegionKind.answerArea => '回答欄',
  RegionKind.annotationArea => '添削記号領域',
  RegionKind.score => '配点',
  RegionKind.rubric => '採点基準',
  RegionKind.modelAnswer => '模範解答',
  _ => kind.toString(),
};

String _provisionLabel(DependencyProvision provision) => switch (provision) {
  DependencyProvision.recognizedText => '認識テキスト',
  DependencyProvision.score => '得点',
  DependencyProvision.criterionResult => '採点基準の判定結果',
  _ => provision.toString(),
};

/// Edits one region's kind/page/label/bbox/text in place.
class _RegionEditDialog extends StatefulWidget {
  const _RegionEditDialog({required this.region});

  final RegionModel region;

  @override
  State<_RegionEditDialog> createState() => _RegionEditDialogState();
}

class _RegionEditDialogState extends State<_RegionEditDialog> {
  late RegionKind _kind;
  late final TextEditingController _labelController;
  late final TextEditingController _pageController;
  late final TextEditingController _x0Controller;
  late final TextEditingController _y0Controller;
  late final TextEditingController _x1Controller;
  late final TextEditingController _y1Controller;
  late final TextEditingController _textController;
  String? _validationError;

  @override
  void initState() {
    super.initState();
    final region = widget.region;
    _kind = region.kind;
    _labelController = TextEditingController(text: region.label);
    _pageController = TextEditingController(
      text: (region.pageIndex + 1).toString(),
    );
    _x0Controller = TextEditingController(text: region.bbox.x0.toString());
    _y0Controller = TextEditingController(text: region.bbox.y0.toString());
    _x1Controller = TextEditingController(text: region.bbox.x1.toString());
    _y1Controller = TextEditingController(text: region.bbox.y1.toString());
    _textController = TextEditingController(text: region.text ?? '');
  }

  @override
  void dispose() {
    _labelController.dispose();
    _pageController.dispose();
    _x0Controller.dispose();
    _y0Controller.dispose();
    _x1Controller.dispose();
    _y1Controller.dispose();
    _textController.dispose();
    super.dispose();
  }

  void _save() {
    final page = int.tryParse(_pageController.text);
    final x0 = double.tryParse(_x0Controller.text);
    final y0 = double.tryParse(_y0Controller.text);
    final x1 = double.tryParse(_x1Controller.text);
    final y1 = double.tryParse(_y1Controller.text);
    if (page == null || page < 1) {
      setState(() => _validationError = 'ページ番号は1以上の整数で入力してください');
      return;
    }
    // `double.tryParse('NaN')` returns non-null `double.nan`, not `null` --
    // every comparison below (`<`, `>`, `>=`) is false for NaN, so without
    // this check the range/ordering tests would all silently pass and the
    // invalid value would reach JSON serialization or the server instead of
    // this dialog's own validation (Issue #16 review round 5).
    if (x0 == null ||
        y0 == null ||
        x1 == null ||
        y1 == null ||
        !x0.isFinite ||
        !y0.isFinite ||
        !x1.isFinite ||
        !y1.isFinite ||
        x0 < 0 ||
        y0 < 0 ||
        x1 > 1 ||
        y1 > 1 ||
        x0 >= x1 ||
        y0 >= y1) {
      setState(() => _validationError = '座標は0〜1の範囲で、右下が左上より大きくなるように入力してください');
      return;
    }
    if (_labelController.text.trim().isEmpty) {
      setState(() => _validationError = '設問番号を入力してください');
      return;
    }
    final updated = widget.region.rebuild(
      (b) => b
        ..kind = _kind
        ..label = _labelController.text.trim()
        ..pageIndex = page - 1
        ..text = _textController.text.trim().isEmpty
            ? null
            : _textController.text.trim()
        ..bbox.x0 = x0
        ..bbox.y0 = y0
        ..bbox.x1 = x1
        ..bbox.y1 = y1,
    );
    Navigator.of(context).pop(updated);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('領域を編集'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            DropdownButtonFormField<RegionKind>(
              key: const Key('region-kind-field'),
              initialValue: _kind,
              decoration: const InputDecoration(labelText: '種類'),
              items: [
                for (final kind in _selectableRegionKinds(widget.region.kind))
                  DropdownMenuItem(
                    value: kind,
                    child: Text(_regionKindLabel(kind)),
                  ),
              ],
              onChanged: (value) {
                if (value != null) setState(() => _kind = value);
              },
            ),
            TextField(
              key: const Key('region-label-field'),
              controller: _labelController,
              decoration: const InputDecoration(labelText: '設問番号'),
            ),
            TextField(
              key: const Key('region-page-field'),
              controller: _pageController,
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: const InputDecoration(labelText: 'ページ（1始まり）'),
            ),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    key: const Key('region-x0-field'),
                    controller: _x0Controller,
                    decoration: const InputDecoration(labelText: 'x0'),
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: TextField(
                    key: const Key('region-y0-field'),
                    controller: _y0Controller,
                    decoration: const InputDecoration(labelText: 'y0'),
                  ),
                ),
              ],
            ),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    key: const Key('region-x1-field'),
                    controller: _x1Controller,
                    decoration: const InputDecoration(labelText: 'x1'),
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: TextField(
                    key: const Key('region-y1-field'),
                    controller: _y1Controller,
                    decoration: const InputDecoration(labelText: 'y1'),
                  ),
                ),
              ],
            ),
            TextField(
              key: const Key('region-text-field'),
              controller: _textController,
              maxLines: 3,
              decoration: const InputDecoration(
                labelText: 'テキスト（模範解答/採点基準/配点等）',
              ),
            ),
            if (_validationError != null) ...[
              const SizedBox(height: AppSpacing.sm),
              Text(
                _validationError!,
                style: context.texts.bodySmall?.copyWith(
                  color: context.colors.error,
                ),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('キャンセル'),
        ),
        FilledButton(
          key: const Key('region-save-button'),
          onPressed: _save,
          child: const Text('保存'),
        ),
      ],
    );
  }
}

/// Edits one dependency edge's endpoints/provisions/rationale in place.
class _EdgeEditDialog extends StatefulWidget {
  const _EdgeEditDialog({required this.edge, required this.questionIds});

  final DependencyEdgeModel edge;
  final List<String> questionIds;

  @override
  State<_EdgeEditDialog> createState() => _EdgeEditDialogState();
}

class _EdgeEditDialogState extends State<_EdgeEditDialog> {
  late String _from;
  late String _to;
  late final TextEditingController _rationaleController;
  // A `Set`, not a `List` -- `provides` has no meaningful order or
  // duplicates, and toggling membership per checkbox is simplest against a
  // set. Backend's `DependencyEdge.__post_init__` rejects an empty
  // `provides`, so an edge whose dependency is really "score" or
  // "criterion_result" (not just recognized text) must be expressible here,
  // not silently coerced to whatever `_addEdge` defaulted it to (Issue #16
  // review round 4).
  late Set<DependencyProvision> _provides;
  String? _validationError;

  @override
  void initState() {
    super.initState();
    _from = widget.edge.fromQuestionId;
    _to = widget.edge.toQuestionId;
    _rationaleController = TextEditingController(text: widget.edge.rationale);
    _provides = widget.edge.provides.toSet();
  }

  @override
  void dispose() {
    _rationaleController.dispose();
    super.dispose();
  }

  void _save() {
    if (_from == _to) {
      setState(() => _validationError = '依存元と依存先には異なる設問を選んでください');
      return;
    }
    if (_provides.isEmpty) {
      setState(() => _validationError = '依存先に渡す内容を少なくとも1つ選択してください');
      return;
    }
    if (_rationaleController.text.trim().isEmpty) {
      setState(() => _validationError = '根拠を入力してください');
      return;
    }
    final updated = widget.edge.rebuild(
      (b) => b
        ..fromQuestionId = _from
        ..toQuestionId = _to
        ..rationale = _rationaleController.text.trim()
        ..provides.replace(_provides),
    );
    Navigator.of(context).pop(updated);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('依存関係を編集'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            DropdownButtonFormField<String>(
              key: const Key('edge-from-field'),
              initialValue: _from,
              decoration: const InputDecoration(labelText: '依存元（先に処理する設問）'),
              items: [
                for (final id in widget.questionIds)
                  DropdownMenuItem(value: id, child: Text(id)),
              ],
              onChanged: (value) {
                if (value != null) setState(() => _from = value);
              },
            ),
            DropdownButtonFormField<String>(
              key: const Key('edge-to-field'),
              initialValue: _to,
              decoration: const InputDecoration(labelText: '依存先（後で処理する設問）'),
              items: [
                for (final id in widget.questionIds)
                  DropdownMenuItem(value: id, child: Text(id)),
              ],
              onChanged: (value) {
                if (value != null) setState(() => _to = value);
              },
            ),
            const SizedBox(height: AppSpacing.sm),
            const Text('依存先に渡す内容'),
            for (final provision in DependencyProvision.values)
              CheckboxListTile(
                key: Key('edge-provision-${provision.name}'),
                dense: true,
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                title: Text(_provisionLabel(provision)),
                value: _provides.contains(provision),
                onChanged: (checked) => setState(() {
                  if (checked ?? false) {
                    _provides.add(provision);
                  } else {
                    _provides.remove(provision);
                  }
                }),
              ),
            TextField(
              key: const Key('edge-rationale-field'),
              controller: _rationaleController,
              maxLines: 2,
              decoration: const InputDecoration(labelText: '根拠'),
            ),
            if (_validationError != null) ...[
              const SizedBox(height: AppSpacing.sm),
              Text(
                _validationError!,
                style: context.texts.bodySmall?.copyWith(
                  color: context.colors.error,
                ),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('キャンセル'),
        ),
        FilledButton(
          key: const Key('edge-save-button'),
          onPressed: _save,
          child: const Text('保存'),
        ),
      ],
    );
  }
}

/// 1 設問の番号・配点・模範解答・採点基準を編集する。
///
/// **配点は空欄にできる。** 空欄 = 不明であって 0 ではない。抽出できなかった
/// 設問を「とりあえず 0 点」で埋められるようにすると、確定の関門
/// (`criteriaBlockingReason` / サーバの `ensure_confirmable`) がまるごと
/// 意味を失う (Issue #103 受入条件 5)。
class _CriteriaQuestionEditDialog extends StatefulWidget {
  const _CriteriaQuestionEditDialog({required this.question});

  final CriteriaQuestionModel question;

  @override
  State<_CriteriaQuestionEditDialog> createState() =>
      _CriteriaQuestionEditDialogState();
}

class _CriteriaQuestionEditDialogState
    extends State<_CriteriaQuestionEditDialog> {
  late final TextEditingController _numberController;
  late final TextEditingController _pointsController;
  late final TextEditingController _modelAnswerController;
  late List<_EditableCriterion> _criteria;
  String? _validationError;

  @override
  void initState() {
    super.initState();
    final question = widget.question;
    _numberController = TextEditingController(text: question.number);
    _pointsController = TextEditingController(
      text: question.points?.toString() ?? '',
    );
    _modelAnswerController = TextEditingController(
      text: question.modelAnswer ?? '',
    );
    _criteria = [
      for (final item in question.criteria) _EditableCriterion.from(item),
    ];
  }

  @override
  void dispose() {
    _numberController.dispose();
    _pointsController.dispose();
    _modelAnswerController.dispose();
    for (final item in _criteria) {
      item.dispose();
    }
    super.dispose();
  }

  void _save() {
    final number = _numberController.text.trim();
    if (number.isEmpty) {
      setState(() => _validationError = '設問番号を入力してください');
      return;
    }
    final rawPoints = _pointsController.text.trim();
    int? points;
    if (rawPoints.isNotEmpty) {
      points = int.tryParse(rawPoints);
      if (points == null || points < 0) {
        setState(() => _validationError = '配点は0以上の整数か、空欄（不明）で入力してください');
        return;
      }
    }
    final criteria = <CriteriaItemModel>[];
    for (final item in _criteria) {
      final description = item.descriptionController.text.trim();
      if (description.isEmpty) {
        setState(() => _validationError = '採点基準の文言が空の行があります。入力するか削除してください');
        return;
      }
      final rawItemPoints = item.pointsController.text.trim();
      int? itemPoints;
      if (rawItemPoints.isNotEmpty) {
        itemPoints = int.tryParse(rawItemPoints);
        if (itemPoints == null || itemPoints < 0) {
          setState(() => _validationError = '採点基準の点数は0以上の整数か、空欄で入力してください');
          return;
        }
      }
      criteria.add(
        CriteriaItemModel(
          (b) => b
            ..description = description
            ..kind = item.kind
            ..points = itemPoints,
        ),
      );
    }
    final modelAnswer = _modelAnswerController.text.trim();
    Navigator.of(context).pop(
      widget.question.rebuild(
        (b) => b
          ..number = number
          ..points = points
          ..modelAnswer = modelAnswer.isEmpty ? null : modelAnswer
          ..criteria.replace(criteria),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('設問を編集'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              key: const Key('criteria-number-field'),
              controller: _numberController,
              decoration: const InputDecoration(labelText: '設問番号'),
            ),
            TextField(
              key: const Key('criteria-points-field'),
              controller: _pointsController,
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: const InputDecoration(
                labelText: '配点',
                helperText: '空欄のままにすると「不明」として扱われ、確定できません',
              ),
            ),
            TextField(
              key: const Key('criteria-model-answer-field'),
              controller: _modelAnswerController,
              maxLines: 4,
              minLines: 2,
              decoration: const InputDecoration(
                labelText: '模範解答',
                helperText: '空欄だと採点を開始できません（採点にはこの文が要ります）',
              ),
            ),
            const SizedBox(height: AppSpacing.md),
            Row(
              children: [
                Expanded(child: Text('採点基準', style: context.texts.titleSmall)),
                TextButton.icon(
                  key: const Key('add-criterion-button'),
                  onPressed: () => setState(
                    () =>
                        _criteria = [..._criteria, _EditableCriterion.empty()],
                  ),
                  icon: const Icon(Icons.add),
                  label: const Text('追加'),
                ),
              ],
            ),
            if (_criteria.isEmpty)
              const Text('採点基準がありません。追加してください。')
            else
              for (final (index, item) in _criteria.indexed)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      TextField(
                        key: Key('criterion-description-$index'),
                        controller: item.descriptionController,
                        maxLines: 3,
                        minLines: 1,
                        decoration: InputDecoration(
                          labelText: '基準${index + 1}',
                        ),
                      ),
                      Row(
                        children: [
                          Expanded(
                            child: DropdownButtonFormField<CriterionKind>(
                              key: Key('criterion-kind-$index'),
                              initialValue: item.kind,
                              decoration: const InputDecoration(
                                labelText: '方式',
                              ),
                              items: const [
                                DropdownMenuItem(
                                  value: CriterionKind.add,
                                  child: Text('加点'),
                                ),
                                DropdownMenuItem(
                                  value: CriterionKind.deduct,
                                  child: Text('減点'),
                                ),
                              ],
                              onChanged: (value) {
                                if (value != null) {
                                  setState(() => item.kind = value);
                                }
                              },
                            ),
                          ),
                          const SizedBox(width: AppSpacing.sm),
                          Expanded(
                            child: TextField(
                              key: Key('criterion-points-$index'),
                              controller: item.pointsController,
                              keyboardType: TextInputType.number,
                              inputFormatters: [
                                FilteringTextInputFormatter.digitsOnly,
                              ],
                              decoration: const InputDecoration(
                                labelText: '点数（空欄可）',
                              ),
                            ),
                          ),
                          IconButton(
                            key: Key('remove-criterion-$index'),
                            icon: const Icon(Icons.delete_outline),
                            tooltip: '削除',
                            onPressed: () => setState(() {
                              final removed = _criteria[index];
                              _criteria = [..._criteria]..removeAt(index);
                              removed.dispose();
                            }),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
            if (_validationError != null) ...[
              const SizedBox(height: AppSpacing.sm),
              Text(
                _validationError!,
                key: const Key('criteria-validation-error'),
                style: TextStyle(color: AppStatusTone.attention.color(context)),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('キャンセル'),
        ),
        FilledButton(
          key: const Key('criteria-save-button'),
          onPressed: _save,
          child: const Text('保存'),
        ),
      ],
    );
  }
}

/// ダイアログが開いている間だけ生きる、1 行ぶんの編集状態。
class _EditableCriterion {
  _EditableCriterion({
    required this.descriptionController,
    required this.pointsController,
    required this.kind,
  });

  factory _EditableCriterion.from(CriteriaItemModel item) => _EditableCriterion(
    descriptionController: TextEditingController(text: item.description),
    pointsController: TextEditingController(
      text: item.points?.toString() ?? '',
    ),
    kind: item.kind,
  );

  factory _EditableCriterion.empty() => _EditableCriterion(
    descriptionController: TextEditingController(),
    pointsController: TextEditingController(),
    kind: CriterionKind.add,
  );

  final TextEditingController descriptionController;
  final TextEditingController pointsController;
  CriterionKind kind;

  void dispose() {
    descriptionController.dispose();
    pointsController.dispose();
  }
}

/// 総得点の編集結果。`null` を「変更なし」と区別するために包んでいる
/// — 総得点を**消す**（PDFの数字がページ番号だった、など）のは正当な操作で、
/// ダイアログが `null` を返すキャンセルと同じにはできない。
class _DeclaredTotalResult {
  const _DeclaredTotalResult(this.value);

  final int? value;
}

/// 採点基準PDFに書かれていた総得点を直す。
class _DeclaredTotalDialog extends StatefulWidget {
  const _DeclaredTotalDialog({required this.value});

  final int? value;

  @override
  State<_DeclaredTotalDialog> createState() => _DeclaredTotalDialogState();
}

class _DeclaredTotalDialogState extends State<_DeclaredTotalDialog> {
  late final TextEditingController _controller;
  String? _validationError;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.value?.toString() ?? '');
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _save() {
    final raw = _controller.text.trim();
    if (raw.isEmpty) {
      Navigator.of(context).pop(const _DeclaredTotalResult(null));
      return;
    }
    final value = int.tryParse(raw);
    if (value == null || value < 0) {
      setState(() => _validationError = '総得点は0以上の整数か、空欄で入力してください');
      return;
    }
    Navigator.of(context).pop(_DeclaredTotalResult(value));
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('採点基準PDFの総得点'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextField(
            key: const Key('declared-total-field'),
            controller: _controller,
            keyboardType: TextInputType.number,
            inputFormatters: [FilteringTextInputFormatter.digitsOnly],
            decoration: const InputDecoration(
              labelText: '総得点（満点）',
              helperText: '空欄にすると照合しません。ページ番号を拾っていた場合は空欄に',
            ),
          ),
          if (_validationError != null) ...[
            const SizedBox(height: AppSpacing.sm),
            Text(
              _validationError!,
              key: const Key('declared-total-validation-error'),
              style: TextStyle(color: AppStatusTone.attention.color(context)),
            ),
          ],
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('キャンセル'),
        ),
        FilledButton(
          key: const Key('declared-total-save-button'),
          onPressed: _save,
          child: const Text('保存'),
        ),
      ],
    );
  }
}

/// 抽出を実行する前に、送信ページ数と概算費用を見せる。
///
/// **単価が未設定なら「未設定」と出す。0 円ではない。** 0 円は
/// 「利用者が無料だと言った」という意味であり、未設定は「このアプリが
/// 単価を知らない」という意味で、別のことである（#104 の取込画面が
/// 同じ区別をしている）。
class _ExtractConfirmDialog extends StatelessWidget {
  const _ExtractConfirmDialog({required this.estimate});

  final CriteriaEstimateResponse estimate;

  @override
  Widget build(BuildContext context) {
    final overLimit = estimate.pageCount > estimate.maxPages;
    final cost = estimate.estimatedCost;
    return AlertDialog(
      title: const Text('採点基準PDFから抽出'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${estimate.pageCount} ページを AI provider に送信します。',
            key: const Key('extract-page-count'),
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            // 文言は #101 の取込画面（`features/intake/intake_page.dart`）と
            // 揃えてある。**未設定は 0 円ではない。** 違うのは単位だけで、
            // あちらは1件あたり、こちらは1ページあたり。
            cost == null
                ? '概算費用: 1ページあたりの単価が未設定です（設定画面で入力できます）'
                : '概算費用: 約${cost.toStringAsFixed(2)}'
                      '（1ページあたり${estimate.unitCost?.toStringAsFixed(2)}）',
            key: const Key('extract-cost'),
          ),
          const SizedBox(height: AppSpacing.xs),
          Text('再実行すると同じだけかかります。', style: context.texts.bodySmall),
          if (overLimit) ...[
            const SizedBox(height: AppSpacing.sm),
            Text(
              '一度に読めるのは ${estimate.maxPages} ページまでです。'
              'このまま実行しても失敗します。ファイルを分割してください。',
              key: const Key('extract-over-limit'),
              style: TextStyle(color: AppStatusTone.attention.color(context)),
            ),
          ],
        ],
      ),
      actions: [
        TextButton(
          key: const Key('extract-cancel-button'),
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('キャンセル'),
        ),
        FilledButton(
          key: const Key('extract-confirm-button'),
          onPressed: overLimit ? null : () => Navigator.of(context).pop(true),
          child: const Text('実行'),
        ),
      ],
    );
  }
}
