import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/core/design/app_status_tone.dart';
import 'package:auto_scoring_app/core/design/app_theme_context.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';
import 'package:auto_scoring_app/core/material_read_ranges.dart';
import 'package:auto_scoring_app/core/question_order.dart';
import 'package:auto_scoring_app/core/question_status.dart';
import 'package:auto_scoring_app/core/review_queue.dart';
import 'package:auto_scoring_app/core/submission_confirmation.dart';
import 'package:auto_scoring_app/core/submission_review_reason.dart';
import 'package:auto_scoring_app/core/submission_status.dart';
import 'package:auto_scoring_app/core/widgets/app_error_banner.dart';
import 'package:auto_scoring_app/core/widgets/back_or_home_button.dart';
import 'package:auto_scoring_app/features/pdf_review/answer_crop_view.dart';
import 'package:auto_scoring_app/features/pdf_review/confidence_badge.dart';
import 'package:auto_scoring_app/features/pdf_review/pdf_review_page.dart'
    show QuestionReviewState;

/// 答案確定画面 -- その答案の**全設問を1画面に並べ、1回で確定する** (Issue #145)。
///
/// ## なぜ画面を分けたか
///
/// 添削レビュー画面は設問1件を見る画面である。40枚 × 5設問の現場では、それが
/// **200回の承認**になる。#113 が消したのはホームへの往復80回だけで、残る200回は
/// 導線ではなく**確定の単位**の問題なので、単位を答案1枚へ移すには「その答案の
/// 判断材料が全部そこにある画面」が要る。
///
/// ## 「1回で確定」は「見ないで確定」ではない
///
/// Issue #85 は、判断材料が画面外にあるまま承認ボタンだけが押せる状態を消した。
/// **まとめて確定する画面では、その危険が設問の数だけ増える。** だからここは
/// 設問ごとに到達を測り、**1つでも未到達が残っている間は確定ボタンを無効にし、
/// どれが未到達かを名指しで出す**。判定そのものは `core/submission_confirmation.dart`
/// にあり、ウィジェットを立てずに読める。
///
/// **確信度による自動承認は無い。** 簡易設計書 §25.2、および Issue #136
/// (確信度1.00の誤った0点が14件中7件)。確信度は画面に出るが、確定の可否には
/// 一切入らない。
///
/// ## 部分失敗を隠さない
///
/// OpenAPI schema は変えていないので、1回の確定は**設問ごとの確定APIをN回
/// 呼ぶ**。3問目で失敗すれば2問は確定済みで、答案は中途半端な状態で残る。
/// その事実を画面が言わなければ、「1回で確定」は失敗を隠す言い訳になる。
/// [SubmissionConfirmationOutcome] を受けて、どこまで確定したか・何が起きたか・
/// 残りが何問かを出し、そのまま残りを確定できるようにしてある。
class SubmissionConfirmPage extends ConsumerStatefulWidget {
  const SubmissionConfirmPage({
    super.key,
    required this.testId,
    required this.submissionId,
  });

  final String testId;
  final String submissionId;

  @override
  ConsumerState<SubmissionConfirmPage> createState() =>
      _SubmissionConfirmPageState();
}

/// 行の上端／下端に置く目印の、キーの接尾辞。
const String _rowTop = '#top';
const String _rowBottom = '#bottom';

/// 1画面ぶんの何割を「未到達へ送る」1回で進むか。1未満なので、連続する2画面が
/// 重なり、行が2画面のあいだに落ちることがない (Issue #85 と同じ規則)。
const double _pageOverlap = 0.9;

/// 行の高さがこれ以下なら、少しでも映った時点で読み切ったものとみなす。
const double _rowHeightEpsilon = 1;

class _SubmissionConfirmPageState extends ConsumerState<SubmissionConfirmPage> {
  /// この画面が開かれたときのサイドカー操作。**要求の途中で provider を
  /// 読み直さない** ([appDependenciesProvider] の docstring)。
  late final AppDependencies _dependencies;

  final ScrollController _scrollController = ScrollController();
  final GlobalKey _viewportKey = GlobalKey(debugLabel: 'confirm-viewport');
  final Map<String, GlobalKey> _rowKeys = {};

  bool _loading = true;
  String? _error;

  SubmissionResponse? _submission;
  List<QuestionResponse> _questions = const [];
  List<JobResponse> _jobs = const [];

  /// 設問ごとの判断材料。**導出は添削レビュー画面と同じ [QuestionReviewState]
  /// に任せている** -- 「いまどの点数が効いているか」(Undo・修正・再判定の
  /// 後始末) を2つ目の実装で決め直すと、同じ答案について2つの画面が違うことを
  /// 言い始める (Issue #84)。
  final Map<String, QuestionReviewState> _material = {};

  /// 設問ごとに、その行のどこまでが画面に出たか (0.0-1.0 の区間)。
  final Map<String, List<(double, double)>> _seen = {};

  /// 一度でも測ったか。**測る前の「どこも見ていない」は事実ではなく無知**なので、
  /// 未到達の告知はここが立つまで出さない。
  bool _measured = false;

  /// 最も近い未到達が上にあるか。ポーリングは無い画面だが、直しに行って戻って
  /// きたときに行が入れ替わるので、下とは限らない。
  bool _unreadIsAbove = false;

  bool _confirming = false;
  SubmissionConfirmationOutcome? _outcome;

  ReviewQueue? _queue;

  @override
  void initState() {
    super.initState();
    _dependencies = ref.read(appDependenciesProvider);
    unawaited(_load());
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void _setStateIfMounted(VoidCallback fn) {
    if (!mounted) return;
    setState(fn);
  }

  // ---------------------------------------------------------------- 読み込み

  Future<void> _load() async {
    _setStateIfMounted(() {
      _loading = true;
      _error = null;
      // **到達の記録も捨てる。** 読み直すと判断材料そのものが変わりうる (AI採点が
      // 終わった、誰かが直した)。到達は行の高さに対する割合で持っているので、
      // 中身が変わったあとの古い記録は**別のものについて**「見た」と言っている。
      //
      // 確定を流したあとの読み直し ([_loadMaterial]) はこれを消さない。あちらは
      // 同じ材料についての履歴が伸びただけで、部分失敗のあとに残り2問ぶんの
      // スクロールをやり直させる理由が無い。
      _seen.clear();
      _measured = false;
    });
    try {
      final submission = await _dependencies.getSubmission(widget.submissionId);
      final questions = sortQuestionsForReview(
        await _dependencies.listQuestions(widget.testId),
      );
      // ジョブは骨格ではない。引けなければ設問の状態が粗くなるだけで、判断材料も
      // 確定もそのまま成立する。
      var jobs = const <JobResponse>[];
      try {
        jobs = await _dependencies.listJobs(widget.submissionId);
      } on SidecarApiException {
        jobs = const [];
      }
      if (!mounted) return;
      _setStateIfMounted(() {
        _submission = submission;
        _questions = questions;
        _jobs = jobs;
      });
      await _loadMaterial(questions);
      if (!mounted) return;
      _setStateIfMounted(() => _loading = false);
      // 待たない。現在地と「次の答案」はこの画面の骨格ではない。
      unawaited(_loadQueue());
    } on SidecarApiException catch (error) {
      _setStateIfMounted(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  /// 全設問の判断材料を読む。
  ///
  /// **1設問ずつではなく全部読む。** 添削レビュー画面が開いている設問だけを
  /// 読むのは、そこが1設問の画面だからである。ここは答案1枚を1回で確定する
  /// 画面なので、**確定の対象になる設問の材料が全部揃っていなければ、そもそも
  /// 確定の可否を言えない**。
  ///
  /// 1設問でも落ちたら、その設問は「読み込めていない」として確定を止める
  /// ([SubmissionConfirmBlock.materialUnavailable])。取れなかったものについて
  /// 「見ましたか」と訊くことはできない。
  Future<void> _loadMaterial(List<QuestionResponse> questions) async {
    await Future.wait([
      for (final question in questions) _loadOneQuestion(question.id),
    ]);
  }

  Future<void> _loadOneQuestion(String questionId) async {
    final state = _material.putIfAbsent(questionId, QuestionReviewState.new);
    state.loading = true;
    state.error = null;
    try {
      final results = await Future.wait([
        _dependencies.listRecognitions(widget.submissionId, questionId),
        _dependencies.listGrades(widget.submissionId, questionId),
        _dependencies.listReviews(widget.submissionId, questionId),
      ]);
      state.recognitions = results[0] as List<RecognitionResponse>;
      state.grades = results[1] as List<GradeResultResponse>;
      state.reviews = results[2] as List<ReviewResponse>;
      // この画面はPDFの上に印を描かないので注釈は引かない。`hasLoaded` は
      // 4つ揃って初めて真になるので、空で埋めて「読めた」を成立させる。
      state.annotations = const <AnnotationResponse>[];
      state.error = null;
    } on SidecarApiException catch (error) {
      state.error = error.message;
    } finally {
      state.loading = false;
      _setStateIfMounted(() {});
    }
  }

  /// このテストの答案キュー -- 何枚目か、次はどれか (Issue #113)。
  /// **引けなくてもこの画面は成立する。** そのときは現在地が出ず、確定したあと
  /// 次の答案へは自動で進まない。
  Future<void> _loadQueue() async {
    try {
      final submissions = await _dependencies.listSubmissions(widget.testId);
      var progress = const <SubmissionReviewProgressResponse>[];
      try {
        progress = await _dependencies.listReviewProgress(widget.testId);
      } on SidecarApiException {
        progress = const [];
      }
      _setStateIfMounted(() {
        _queue = ReviewQueue.from(submissions: submissions, progress: progress);
      });
    } on SidecarApiException {
      // 現在地が出ないだけ。確定そのものは続けられる。
    }
  }

  // ------------------------------------------------------------ 到達したか

  /// いま画面に出ている行の、見えている部分を記録する。
  ///
  /// スクロール量ではなく**行そのものの位置**から測る。訊いているのは「この行が
  /// 映ったか」であって、「どれだけ動かしたか」ではない (Issue #85)。
  void _recordSeen() {
    final viewport = _viewportKey.currentContext?.findRenderObject();
    if (viewport is! RenderBox || !viewport.attached || !viewport.hasSize) {
      return;
    }
    final height = viewport.size.height;
    final updated = <String, List<(double, double)>>{};
    double? firstUnreadY;
    for (final question in _questions) {
      // 読み込み中・失敗中の行は判断材料ではない。それを「見た」に数えると、
      // 出てもいない中身について確定を開けてしまう。
      final material = _material[question.id];
      if (material == null || !material.hasLoaded || material.loading) continue;
      final top = _markerY(question.id, _rowTop, viewport);
      final bottom = _markerY(question.id, _rowBottom, viewport);
      if (top == null || bottom == null) continue;
      final rowHeight = bottom - top;
      final visibleTop = math.max(top, 0.0);
      final visibleBottom = math.min(bottom, height);
      final existing = updated[question.id] ?? _seen[question.id] ?? const [];
      if (visibleBottom > visibleTop) {
        final merged = rowHeight <= _rowHeightEpsilon
            ? const [(0.0, 1.0)]
            : mergeMaterialRange(
                existing,
                (visibleTop - top) / rowHeight,
                (visibleBottom - top) / rowHeight,
              );
        if (!sameMaterialRanges(existing, merged)) {
          updated[question.id] = merged;
        }
      }
      firstUnreadY ??= _firstGapY(
        updated[question.id] ?? existing,
        top,
        rowHeight,
      );
    }
    final unreadIsAbove = firstUnreadY != null && firstUnreadY < 0;
    if (updated.isEmpty && _measured && unreadIsAbove == _unreadIsAbove) return;
    _setStateIfMounted(() {
      _measured = true;
      _unreadIsAbove = unreadIsAbove;
      _seen.addAll(updated);
    });
  }

  double? _markerY(String questionId, String edge, RenderBox viewport) {
    final marker = _rowKeys['$questionId$edge']?.currentContext
        ?.findRenderObject();
    if (marker is! RenderBox || !marker.attached || !marker.hasSize) {
      return null;
    }
    return marker.localToGlobal(Offset.zero, ancestor: viewport).dy;
  }

  /// 行のうち、まだ映っていない先頭がビューポート座標のどこにあるか。
  /// 端から端まで映っていれば `null`。
  double? _firstGapY(
    List<(double, double)> ranges,
    double top,
    double rowHeight,
  ) {
    if (ranges.isNotEmpty &&
        ranges.first.$1 <= materialCoverEpsilon &&
        ranges.first.$2 >= 1 - materialCoverEpsilon) {
      return null;
    }
    final gapStart = ranges.isEmpty || ranges.first.$1 > materialCoverEpsilon
        ? 0.0
        : ranges.first.$2;
    return top + gapStart * rowHeight;
  }

  /// 目印。高さ0なので、**測っているものを自分で動かさない**。
  Widget _rowEdge(String questionId, String edge) => SizedBox.shrink(
    key: _rowKeys.putIfAbsent(
      '$questionId$edge',
      () => GlobalKey(debugLabel: 'confirm-row:$questionId$edge'),
    ),
  );

  /// 未到達の判断材料を1画面ぶん送る。
  ///
  /// **一気に飛ばさない。** 通り過ぎたところしか記録しないので、飛べば飛んだ
  /// ぶんが未到達のまま残り、「表示する」と書いてあるボタンが表示しないことに
  /// なる (Issue #85 レビュー4回目)。
  void _revealNext() {
    if (!_scrollController.hasClients) return;
    final position = _scrollController.position;
    final page = position.viewportDimension * _pageOverlap;
    unawaited(
      _scrollController.animateTo(
        _unreadIsAbove
            ? math.max(position.pixels - page, position.minScrollExtent)
            : math.min(position.pixels + page, position.maxScrollExtent),
        duration: AppMotion.emphasis,
        curve: AppMotion.standard,
      ),
    );
  }

  // --------------------------------------------------------------- 確定する

  SubmissionConfirmation get _confirmation => SubmissionConfirmation([
    for (final question in _questions)
      _confirmationFor(question, _material[question.id]),
  ]);

  QuestionConfirmation _confirmationFor(
    QuestionResponse question,
    QuestionReviewState? material,
  ) => QuestionConfirmation(
    questionId: question.id,
    number: question.number,
    materialLoaded:
        material != null &&
        material.hasLoaded &&
        !material.loading &&
        material.error == null,
    isConfirmed: material?.isConfirmed ?? false,
    aiGradeId: material?.latestAiGrade?.id,
    expectedVersion: material?.expectedVersion ?? 0,
    isReached: materialRowIsCovered(_seen[question.id]),
  );

  Future<void> _confirmSubmission() async {
    final confirmation = _confirmation;
    if (!confirmation.canConfirm || _confirming) return;
    _setStateIfMounted(() {
      _confirming = true;
      _outcome = null;
    });
    final outcome = await runSubmissionConfirmation(
      questions: confirmation.pending,
      approve: (question) => _dependencies.approveReview(
        widget.submissionId,
        question.questionId,
        expectedVersion: question.expectedVersion,
        expectedAiGradeId: question.aiGradeId,
      ),
    );
    if (!mounted) return;
    // 確定した設問の履歴は伸びている。読み直さないと、残りの再実行が古い
    // `expectedVersion` を送り、**直せる失敗が直せない失敗になる**。
    await _loadMaterial(_questions);
    if (!mounted) return;
    _setStateIfMounted(() {
      _confirming = false;
      _outcome = outcome;
    });
    if (!outcome.isComplete) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('${outcome.confirmed.length}問を確定しました')),
    );
    _goToNextSubmission();
  }

  /// この答案を終えたので、次の答案へ移る (Issue #113 と同じ規則)。
  ///
  /// `push` ではなく `replace`。40枚ぶんを戻るスタックに積んでも意味が無く、
  /// 戻る先は「入ってきた場所」(キュー、またはホーム) のままであるべきである。
  void _goToNextSubmission() {
    final next = _queue?.nextAfter(widget.submissionId);
    if (next == null) {
      // キューが引けていないのか、本当に残りが無いのか。**言い分ける。**
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            _queue == null ? '次の答案は取得できませんでした' : 'このテストの答案はすべて確認しました',
          ),
          action: _queue == null
              ? null
              : SnackBarAction(
                  // `go` ではなく `push`。`go` はスタックを捨てるので、着いた
                  // キューに戻る先が残らない (Issue #160)。
                  label: '答案キューへ',
                  onPressed: () =>
                      context.push(AppRoutes.submissionQueue(widget.testId)),
                ),
        ),
      );
      return;
    }
    context.replace(
      AppRoutes.submissionConfirm(testId: widget.testId, submissionId: next.id),
    );
  }

  /// 何も確定せず次の答案へ (`docs/review-queue.md` §10)。未了のままキューに
  /// 残り、また回ってくる。
  void _deferSubmission() {
    final next = _queue?.nextAfter(widget.submissionId);
    if (next == null) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('ほかに確認できる答案がありません')));
      return;
    }
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(const SnackBar(content: Text('後回しにしました。答案キューに残っています')));
    context.replace(
      AppRoutes.submissionConfirm(testId: widget.testId, submissionId: next.id),
    );
  }

  /// 1設問を添削レビュー画面で開く -- 直す・却下する・再判定する・点数を入れる
  /// はすべてあちらにある。**この画面が2つ目の修正UIを作らない。**
  ///
  /// 戻ってきたら、その設問だけ読み直し、**到達の記録は捨てる**。
  ///
  /// 捨てるのは、行の中身が入れ替わっているかもしれないからである。到達は行の
  /// 高さに対する割合で持っているので、点数が変わって行が伸び縮みすると、
  /// 前の記録は**別の中身について**「見た」と言っていることになる。
  ///
  /// **直した設問はこれで損をしない。** 修正はその場で確定する
  /// (`ReviewAction.MODIFIED`、`docs/review-edit-history.md` §3) ので、戻って
  /// きた時点で確定済みになり、確定済みの設問には到達を求めない。損をするのは
  /// 「開いて何もせずに戻った」場合だけで、そこは測り直すのが正しい。
  Future<void> _openQuestion(QuestionResponse question) async {
    await context.push(
      AppRoutes.pdfReview(
        testId: widget.testId,
        submissionId: widget.submissionId,
        questionId: question.id,
      ),
    );
    if (!mounted) return;
    _seen.remove(question.id);
    await _loadOneQuestion(question.id);
  }

  // ------------------------------------------------------------------- 描画

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: const BackOrHomeButton(),
        title: Text(_answerName()),
        actions: [
          if (_submission case final submission?)
            Padding(
              padding: AppSpacing.banner,
              child: _SubmissionStateChip(state: submission.state),
            ),
          // **この画面はポーリングしない。** 確定するために開く画面であって、
          // AI の進行を眺める画面ではない (それは添削レビュー画面の 進捗パネル)。
          // ただし採点がまだ動いている答案を開くことはあるので、**自分で読み直す
          // 手段は要る** -- 無ければ、AI が終わったことを知る方法が「一度閉じて
          // 開き直す」しかなくなる。
          IconButton(
            key: const Key('confirm-refresh-button'),
            onPressed: _confirming ? null : () => unawaited(_load()),
            icon: const Icon(Icons.refresh),
            tooltip: '再読み込み',
          ),
        ],
        bottom: _loading
            ? null
            : PreferredSize(
                preferredSize: const Size.fromHeight(AppLayout.appBarSubtitle),
                child: Padding(
                  padding: AppSpacing.banner,
                  child: Align(
                    alignment: AlignmentDirectional.centerStart,
                    child: Text(
                      _subtitle(),
                      key: const Key('confirm-subtitle'),
                      style: context.texts.bodySmall,
                    ),
                  ),
                ),
              ),
      ),
      body: _buildBody(),
    );
  }

  String _answerName() {
    final submission = _submission;
    if (submission == null) return '答案の確定';
    return submission.studentLabel ?? submission.originalFilename ?? '答案の確定';
  }

  /// 「12 / 40 件目 ・ 確定済み 3 / 5 問」。
  ///
  /// 設問粒度の数を出すのは、答案の `state` が動くのは全設問が確定したときだけ
  /// だからである (Issue #112) -- 3問まで確定した答案は手つかずの答案と `state`
  /// では区別がつかない。キューの行が同じ数を出しているのと同じ理由で、
  /// **中断して戻ってきた人に「どこまでやったか」が読める**必要がある。
  String _subtitle() {
    final confirmation = _confirmation;
    final progress =
        '確定済み ${confirmation.confirmedCount} / ${confirmation.total} 問';
    // **キューが引けていないときは何枚目かを書かない** -- 「1 / 1」と出せば
    // 残り1枚だと読まれる (Issue #113)。
    final position = _position();
    return position == null ? progress : '$position ・ $progress';
  }

  String? _position() {
    final queue = _queue;
    if (queue == null) return null;
    final position = queue.positionOf(widget.submissionId);
    if (position == 0) return null;
    return '$position / ${queue.total} 件目';
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(
        key: Key('confirm-loading'),
        child: CircularProgressIndicator(),
      );
    }
    final error = _error;
    if (error != null) {
      return Center(
        child: Padding(
          padding: AppSpacing.page,
          child: AppErrorBanner(
            message: '答案を読み込めませんでした: $error',
            messageKey: const Key('confirm-error'),
            onRetry: () => unawaited(_load()),
          ),
        ),
      );
    }
    if (_questions.isEmpty) {
      return Center(
        child: Padding(
          padding: AppSpacing.page,
          child: Text(
            'このテストには設問が登録されていません。',
            key: const Key('confirm-no-questions'),
            style: context.texts.bodyMedium,
          ),
        ),
      );
    }
    // Enter で確定 -- 未到達が残っているときは「未到達へ送る」になる。
    // キーボードだけの利用者にとって、これが判断材料へ届く唯一の手段である
    // (Issue #85 が Enter に同じ二役を持たせているのと同じ理由)。
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.enter): () {
          if (_confirmation.blocker == SubmissionConfirmBlock.unreached) {
            _revealNext();
            return;
          }
          unawaited(_confirmSubmission());
        },
      },
      child: Focus(
        autofocus: true,
        child: Column(
          children: [
            Expanded(child: _buildQuestionList()),
            const Divider(height: AppLayout.hairline),
            _buildActionBar(),
          ],
        ),
      ),
    );
  }

  Widget _buildQuestionList() {
    // 測り直す契機は2つ。指が動かしたとき (ScrollNotification) と、この画面が
    // build されたとき (直下の post-frame)。**2つとも要る** -- 内容が収まって
    // しまう画面はスクロール通知を1度も出さないので、通知だけに頼ると
    // 「下端外に何も無い画面で確定できない」形で固まる (Issue #85)。
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _recordSeen();
    });
    return NotificationListener<ScrollMetricsNotification>(
      onNotification: (_) {
        _recordSeen();
        return false;
      },
      child: NotificationListener<ScrollNotification>(
        onNotification: (_) {
          _recordSeen();
          return false;
        },
        child: KeyedSubtree(
          key: _viewportKey,
          child: ListView.separated(
            key: const Key('confirm-question-list'),
            controller: _scrollController,
            padding: AppSpacing.panel,
            itemCount: _questions.length,
            separatorBuilder: (_, _) => const SizedBox(height: AppSpacing.lg),
            itemBuilder: (context, index) {
              final question = _questions[index];
              final material = _material[question.id];
              return _QuestionCard(
                key: Key('confirm-question-${question.id}'),
                question: question,
                material: material,
                status: _statusOf(question),
                isReached: materialRowIsCovered(_seen[question.id]),
                submissionId: widget.submissionId,
                getAnswerImage: _dependencies.getAnswerImage,
                isNearlyBlankCrop: hasNearlyBlankCrop(
                  _submission?.reviewReason,
                  question.id,
                ),
                topEdge: _rowEdge(question.id, _rowTop),
                bottomEdge: _rowEdge(question.id, _rowBottom),
                onOpen: () => unawaited(_openQuestion(question)),
              );
            },
          ),
        ),
      ),
    );
  }

  /// 設問の状態。**添削レビュー画面と同じ [deriveQuestionStatus] を通す** --
  /// 一覧が「承認済み」と言い、開いた先が「要確認」と言うのが Issue #84 である。
  QuestionStatus _statusOf(QuestionResponse question) {
    final job = _latestJobFor(question.id);
    return deriveQuestionStatus(
      job: job,
      review: _material[question.id]?.effectiveReview,
      hasWaitingDependents: _jobs.any(
        (other) =>
            other.blockedOnQuestionId == question.id &&
            other.state == 'blocked',
      ),
    );
  }

  JobResponse? _latestJobFor(String questionId) {
    JobResponse? latest;
    for (final job in _jobs) {
      if (job.questionId != questionId) continue;
      if (latest == null || job.createdAt.isAfter(latest.createdAt)) {
        latest = job;
      }
    }
    return latest;
  }

  Widget _buildActionBar() {
    final confirmation = _confirmation;
    return Material(
      elevation: AppElevation.raised,
      child: Padding(
        padding: AppSpacing.actionBar,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (_outcome case final outcome?) ...[
              _OutcomeNotice(outcome: outcome),
              const SizedBox(height: AppSpacing.sm),
            ],
            _buildBlockerNotice(confirmation),
            const SizedBox(height: AppSpacing.sm),
            Wrap(
              alignment: WrapAlignment.end,
              spacing: AppSpacing.md,
              runSpacing: AppSpacing.sm,
              children: [
                _EnterActivates(
                  child: OutlinedButton.icon(
                    key: const Key('confirm-defer-button'),
                    onPressed: _confirming ? null : _deferSubmission,
                    icon: const Icon(Icons.low_priority),
                    label: const Text('後回し (S)'),
                  ),
                ),
                if (confirmation.blocker == SubmissionConfirmBlock.unreached)
                  OutlinedButton.icon(
                    key: const Key('confirm-reveal-button'),
                    onPressed: _revealNext,
                    icon: Icon(
                      _unreadIsAbove
                          ? Icons.arrow_upward
                          : Icons.arrow_downward,
                    ),
                    label: const Text('未到達の設問を表示'),
                  ),
                Tooltip(
                  message: _confirmTooltip(confirmation),
                  child: FilledButton.icon(
                    key: const Key('confirm-submission-button'),
                    onPressed: confirmation.canConfirm && !_confirming
                        ? () => unawaited(_confirmSubmission())
                        : null,
                    icon: const Icon(Icons.done_all),
                    label: Text(_confirmLabel(confirmation)),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  String _confirmLabel(SubmissionConfirmation confirmation) {
    final pending = confirmation.pending.length;
    if (pending == 0) return 'この答案を確定 (Enter)';
    // **残り何問かを数で出す。** 部分失敗のあとに押すのは「もう一度全部」では
    // なく「残り2問」であり、ボタンがそう言わなければ、どこまで済んだかを
    // 覚えているのは人の側になる。
    return '$pending問をまとめて確定 (Enter)';
  }

  String _confirmTooltip(SubmissionConfirmation confirmation) =>
      switch (confirmation.blocker) {
        null => 'この答案の全設問を確定します',
        SubmissionConfirmBlock.noQuestions => '設問がありません',
        SubmissionConfirmBlock.materialUnavailable => '判断材料を読み込めていない設問があります',
        SubmissionConfirmBlock.humanScoreRequired => '点数を入力していない設問があります',
        SubmissionConfirmBlock.unreached => '判断材料を最後まで表示すると確定できます',
        SubmissionConfirmBlock.nothingToConfirm => 'すべての設問が確定済みです',
      };

  /// **なぜ確定できないのか、どの設問なのか。**
  ///
  /// 「確定できません」だけでは、40枚を流している人は原因を探して画面を上下
  /// することになる。無効なボタンは、無効な理由を名指しで言う責任がある。
  Widget _buildBlockerNotice(SubmissionConfirmation confirmation) {
    final blocker = confirmation.blocker;
    if (blocker == null) {
      return _Notice(
        key: const Key('confirm-ready-notice'),
        icon: Icons.check_circle_outline,
        tone: AppStatusTone.success,
        message: '全設問の判断材料を表示しました。${confirmation.pending.length}問をまとめて確定できます。',
      );
    }
    return switch (blocker) {
      SubmissionConfirmBlock.noQuestions => _Notice(
        key: const Key('confirm-blocked-no-questions'),
        icon: Icons.help_outline,
        tone: AppStatusTone.neutral,
        message: 'このテストには設問が登録されていません。',
      ),
      SubmissionConfirmBlock.materialUnavailable => _Notice(
        key: const Key('confirm-blocked-unavailable'),
        icon: Icons.error_outline,
        tone: AppStatusTone.danger,
        message:
            '判断材料を読み込めていない設問があります'
            '（${_numbers(confirmation.unloaded)}）。再読み込みしてください。',
      ),
      SubmissionConfirmBlock.humanScoreRequired => _Notice(
        key: const Key('confirm-blocked-human-score'),
        icon: Icons.edit_note,
        tone: AppStatusTone.attention,
        message:
            'AIが採点できなかった設問があります'
            '（${_numbers(confirmation.needingHumanScore)}）。'
            'その設問を開いて点数を入力すると、まとめて確定できます。',
      ),
      // **どれが未到達かを出す。** これを出さずにボタンだけ無効にするのは、
      // 「どこかを見ていません」と言って画面を探させることである。
      SubmissionConfirmBlock.unreached => _Notice(
        key: const Key('confirm-blocked-unreached'),
        icon: _unreadIsAbove ? Icons.arrow_upward : Icons.arrow_downward,
        tone: AppStatusTone.attention,
        message:
            'まだ表示していない設問があります'
            '（${_numbers(confirmation.unreached)}）。'
            '最後まで表示すると確定できます。',
      ),
      SubmissionConfirmBlock.nothingToConfirm => _Notice(
        key: const Key('confirm-blocked-nothing'),
        icon: Icons.check_circle_outline,
        tone: AppStatusTone.success,
        message: 'この答案は全設問を確定済みです。',
      ),
    };
  }

  String _numbers(List<QuestionConfirmation> questions) =>
      questions.map((question) => '問${question.number}').join('・');
}

/// 設問1件の判断材料と、その設問について取れる操作。
///
/// **切り出し画像・AIの点数・根拠がここに揃っている**ことが「見た」の定義で
/// あり (Issue #145)、[topEdge]/[bottomEdge] のあいだが到達を測る範囲である。
class _QuestionCard extends StatelessWidget {
  const _QuestionCard({
    super.key,
    required this.question,
    required this.material,
    required this.status,
    required this.isReached,
    required this.submissionId,
    required this.getAnswerImage,
    required this.isNearlyBlankCrop,
    required this.topEdge,
    required this.bottomEdge,
    required this.onOpen,
  });

  final QuestionResponse question;
  final QuestionReviewState? material;
  final QuestionStatus status;
  final bool isReached;
  final String submissionId;
  final GetAnswerImage getAnswerImage;
  final bool isNearlyBlankCrop;
  final Widget topEdge;
  final Widget bottomEdge;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final material = this.material;
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: AppSpacing.card,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _buildHeader(context),
            const SizedBox(height: AppSpacing.sm),
            topEdge,
            if (material == null || material.loading)
              const Center(
                child: Padding(
                  padding: AppSpacing.panel,
                  child: CircularProgressIndicator(),
                ),
              )
            else if (material.error case final message?)
              Text(
                '判断材料を読み込めませんでした: $message',
                key: Key('confirm-question-error-${question.id}'),
                style: context.texts.bodySmall,
              )
            else
              _buildMaterial(context, material),
            bottomEdge,
            const SizedBox(height: AppSpacing.sm),
            Align(
              alignment: AlignmentDirectional.centerEnd,
              child: _EnterActivates(
                child: OutlinedButton.icon(
                  key: Key('confirm-open-${question.id}'),
                  onPressed: onOpen,
                  icon: const Icon(Icons.edit_outlined),
                  // AI が採点できなかった設問では、あちらで最初に押すのは
                  // 「点数を入力」である。ラベルを分けるのは、開いた先で何を
                  // するかが違うからである (Issue #118)。
                  label: Text(
                    material != null &&
                            material.hasLoaded &&
                            material.latestAiGrade == null &&
                            !material.isConfirmed
                        ? '点数を入力する'
                        : 'この設問を詳しく見る・直す',
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    final tone = status.tone.color(context);
    return Row(
      children: [
        Expanded(
          child: Text('問${question.number}', style: context.texts.titleMedium),
        ),
        Icon(status.icon, size: AppIconSize.dense, color: tone),
        const SizedBox(width: AppSpacing.xs),
        Text(status.label, style: context.textRoles.uiLabel),
        const SizedBox(width: AppSpacing.md),
        // **色だけで区別しない** (Issue #25)。形と語の両方を出す。
        _ReachBadge(
          key: Key('confirm-reach-${question.id}'),
          isReached: isReached,
        ),
      ],
    );
  }

  Widget _buildMaterial(BuildContext context, QuestionReviewState material) {
    final ocr = material.latestOcrRecognition;
    final aiGrade = material.latestAiGrade;
    final displayGrade = material.displayGrade;
    final humanGrade = displayGrade?.source_ == 'human' ? displayGrade : null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // 「AIが見た画像」が先。点数はそれが何の画像から出たかを言わない
        // (Issue #122 / #136)。
        //
        // **高さを固定して置く。** 画像は非同期に届くので、届いた拍子に行が
        // 伸びると、伸びたぶんは人が見ていないのに「見た」に数えられる。
        SizedBox(
          height: AppLayout.answerCropSlot,
          child: AnswerCropView(
            key: Key('confirm-crop-${question.id}'),
            submissionId: submissionId,
            questionId: question.id,
            getAnswerImage: getAnswerImage,
            isNearlyBlank: isNearlyBlankCrop,
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        Text('AI認識文字', style: context.texts.labelLarge),
        if (ocr == null)
          const Text('未認識')
        else ...[
          Text(
            ocr.text,
            key: Key('confirm-recognition-${question.id}'),
            style: context.textRoles.recognizedText,
          ),
          const SizedBox(height: AppSpacing.xs),
          ConfidenceBadge(
            label: 'OCR文字認識信頼度',
            confidence: ocr.confidence.toDouble(),
          ),
        ],
        const SizedBox(height: AppSpacing.sm),
        Text('採点', style: context.texts.labelLarge),
        if (aiGrade == null)
          Text(
            'AIの点数がありません。この設問は自分で点数を入力する必要があります。',
            key: Key('confirm-no-grade-${question.id}'),
            style: context.textRoles.gradingComment,
          )
        else ...[
          Text(
            '${aiGrade.score.awarded} / ${aiGrade.score.maximum} 点',
            key: Key('confirm-score-${question.id}'),
            style: context.textRoles.score,
          ),
          if (aiGrade.answerImageFinding == AnswerImageFinding.blank)
            Text(
              'AIは「解答欄に何も書かれていない」と報告しました。'
              '本当に無記入ならこの0点は正しく、切り出しがずれていても'
              '同じ0点になります。上の画像を確かめてください。',
              key: Key('confirm-answer-image-blank-${question.id}'),
              style: context.textRoles.gradingComment,
            ),
          const SizedBox(height: AppSpacing.xs),
          ConfidenceBadge(
            label: '採点信頼度',
            confidence: aiGrade.confidence.toDouble(),
          ),
          if (aiGrade.rationale case final rationale?
              when rationale.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.xs),
            Text('根拠', style: context.texts.labelLarge),
            Text(
              rationale,
              key: Key('confirm-rationale-${question.id}'),
              style: context.textRoles.gradingComment,
            ),
          ],
          if (aiGrade.comment case final comment? when comment.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.xs),
            Text('コメント', style: context.texts.labelLarge),
            Text(
              comment,
              key: Key('confirm-comment-${question.id}'),
              style: context.textRoles.gradingComment,
            ),
          ],
        ],
        if (humanGrade != null) ...[
          const SizedBox(height: AppSpacing.xs),
          Text('人による確定', style: context.texts.labelLarge),
          Text(
            '${humanGrade.score.awarded} / ${humanGrade.score.maximum} 点',
            key: Key('confirm-human-score-${question.id}'),
            style: context.textRoles.score,
          ),
        ],
        if (question.rubric.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.sm),
          Text('採点基準', style: context.texts.labelLarge),
          for (final criterion in question.rubric)
            Padding(
              key: Key('confirm-criterion-${question.id}-${criterion.id}'),
              padding: const EdgeInsets.only(top: AppSpacing.xs),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    _criterionIcon(_outcomeFor(criterion.id, displayGrade)),
                    size: AppIconSize.dense,
                  ),
                  const SizedBox(width: AppSpacing.xs),
                  Expanded(
                    child: Text(
                      '${criterion.description}（${criterion.maxPoints}点）',
                      style: context.textRoles.questionText,
                    ),
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Text(
                    _criterionLabel(_outcomeFor(criterion.id, displayGrade)),
                    style: context.texts.labelLarge,
                  ),
                ],
              ),
            ),
        ],
      ],
    );
  }
}

String? _outcomeFor(String criterionId, GradeResultResponse? grade) {
  if (grade == null) return null;
  for (final result in grade.criteria) {
    if (result.criterionId == criterionId) return result.outcome;
  }
  return null;
}

IconData _criterionIcon(String? outcome) => switch (outcome) {
  'pass' => Icons.check_circle_outline,
  'partial' => Icons.remove_circle_outline,
  'fail' => Icons.cancel_outlined,
  null => Icons.hourglass_empty,
  _ => Icons.help_outline,
};

String _criterionLabel(String? outcome) => switch (outcome) {
  'pass' => '合格',
  'partial' => '部分合格',
  'fail' => '不合格',
  null => '未評価',
  _ => outcome,
};

/// Enter を、**この子ウィジェットのためのものに戻す**。
///
/// この画面は Enter をページ全体で「確定（未到達が残っていれば未到達へ送る）」に
/// 束ねている。キー入力はフォーカスのある位置から上へ伝わるので、そのままだと
/// **後回しボタンにフォーカスして Enter を押した人が、答案を確定してしまう**。
/// フォーカスに近い位置で束ね直すと、そちらが先に処理して押した本人のボタンが
/// 動く（添削レビュー画面が「続きを表示」に同じことをしている）。
class _EnterActivates extends StatelessWidget {
  const _EnterActivates({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => Shortcuts(
    shortcuts: const <ShortcutActivator, Intent>{
      SingleActivator(LogicalKeyboardKey.enter): ActivateIntent(),
    },
    child: child,
  );
}

/// 「表示済み」/「未表示」。
///
/// **これが色だけの印だったら意味が無い** -- 未到達を告げる唯一の手掛かりが
/// 色になり、Issue #25 の禁じ手そのものになる。形・語・色の3つで出す。
class _ReachBadge extends StatelessWidget {
  const _ReachBadge({super.key, required this.isReached});

  final bool isReached;

  @override
  Widget build(BuildContext context) {
    final tone = isReached ? AppStatusTone.success : AppStatusTone.attention;
    final color = tone.color(context);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(
          isReached ? Icons.visibility : Icons.visibility_off_outlined,
          size: AppIconSize.dense,
          color: color,
        ),
        const SizedBox(width: AppSpacing.xs),
        Text(
          isReached ? '表示済み' : '未表示',
          style: context.textRoles.uiLabel.copyWith(color: color),
        ),
      ],
    );
  }
}

/// N回の確定要求が**どこまで進んだか**。
///
/// 成功した回も出す。「5問を確定しました」が出ないまま画面が次の答案へ移ると、
/// 何が起きたのか分からないまま次が始まる。
class _OutcomeNotice extends StatelessWidget {
  const _OutcomeNotice({required this.outcome});

  final SubmissionConfirmationOutcome outcome;

  @override
  Widget build(BuildContext context) {
    if (outcome.isComplete) {
      return _Notice(
        key: const Key('confirm-outcome-complete'),
        icon: Icons.check_circle_outline,
        tone: AppStatusTone.success,
        message: '${outcome.confirmed.length}問を確定しました。',
      );
    }
    // **どこまで確定したかを先に言う。** 「失敗しました」だけでは、すでに
    // 確定した設問の存在が人から隠れる。
    final done = outcome.confirmed.isEmpty
        ? '確定できた設問はありません。'
        : '${outcome.confirmed.map((n) => '問$n').join('・')} を確定しました。';
    return _Notice(
      key: const Key('confirm-outcome-partial'),
      icon: Icons.error_outline,
      tone: AppStatusTone.danger,
      message:
          '$done'
          '問${outcome.failedNumber} で失敗しました: ${outcome.message ?? '理由は分かりません'}。'
          '残り${outcome.remaining.length}問（${outcome.remaining.map((n) => '問$n').join('・')}）は'
          'そのまま確定し直せます。',
    );
  }
}

/// アイコン＋文。色は状態の唯一の手がかりにしない (Issue #25)。
class _Notice extends StatelessWidget {
  const _Notice({
    super.key,
    required this.icon,
    required this.tone,
    required this.message,
  });

  final IconData icon;
  final AppStatusTone tone;
  final String message;

  @override
  Widget build(BuildContext context) {
    final color = tone.color(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: AppIconSize.inline, color: color),
        const SizedBox(width: AppSpacing.xs),
        Expanded(child: Text(message, style: context.texts.bodySmall)),
      ],
    );
  }
}

/// 答案の状態。`SubmissionStatusVisual` から取る -- **この画面が3つ目の対応表を
/// 作ってはならない** (Issue #84)。
class _SubmissionStateChip extends StatelessWidget {
  const _SubmissionStateChip({required this.state});

  final String state;

  @override
  Widget build(BuildContext context) {
    final visual = SubmissionStatusVisual.of(state);
    final color = visual.tone.color(context);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(visual.icon, size: AppIconSize.dense, color: color),
        const SizedBox(width: AppSpacing.xs),
        Text(visual.label, style: context.textRoles.uiLabel),
      ],
    );
  }
}
