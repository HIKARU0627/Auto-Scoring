/// 「今どうなっていて、次に何をすればいいか」を、既存APIの応答だけから
/// 組み立てた純粋なデータ (Issue #68)。
///
/// ウィジェットを持たないのは意図的で、優先順位の判断 -- どれが「続き」か --
/// はこのアプリのUIで最も意見の入る部分なので、画面を立ち上げずに
/// `home_dashboard_test.dart` から直接読める形にしてある。
///
/// 入力は `listTestRegistrations` と `listSubmissions` の2つだけ。処理の
/// 進み具合も答案の `state` から読む -- `listJobs` は答案1件ずつのAPIなので、
/// ホームで呼ぶと答案の数だけリクエストが出る。
///
/// **`state` から読めないことは書かない。** §25 の状態機械で
/// `UNPROCESSED -> AI_PROCESSING -> AI_PROCESSED` が表しているのは取込時の
/// 画像前処理と回答欄抽出までで、OCR/AI採点は `AI_PROCESSED` の先から始まる
/// (`backend/.../adapters/submission_intake.py`)。したがって答案の `state`
/// だけを見て「採点が終わった」とは言えない。この画面の文言はそこを跨がない
/// (`docs/home-dashboard.md` §3)。
library;

import 'package:flutter/material.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/core/design/app_status_tone.dart';

/// §25の7つの答案状態を、ホーム画面が実際に区別する5つへ畳んだもの。
///
/// 答案取込・添削レビューは7状態をそのまま1行ずつ見せるが、ホームは
/// 「人間を待たせているものが何件あるか」を数える画面なので、単位が違う。
/// だからあの2画面のラベル表と共通化していない (docs/design-tokens.md §6)。
///
/// [awaitingReview] と [needsReview] を分けているのが要点。どちらも人間の
/// 作業待ちだが、`needs_review` はAIが「自分では決められなかった」と言って
/// いる答案で、色を割く価値があるのはこちらだけである
/// (docs/design-tokens.md §3.1)。
enum HomeWorkBucket {
  /// `needs_review` -- 取込時に回答欄を確定できなかった、確認していない設問が
  /// 残っているなど、**人が見ないと先へ進めない**もの。理由そのものは
  /// `review_reason` にあり、答案取込画面が1行ずつ出す。
  needsReview(
    label: '要確認',
    icon: Icons.warning_amber,
    tone: AppStatusTone.attention,
  ),

  /// `ai_processed` -- 取込と回答欄の抽出まで終わり、人がまだ確認していない
  /// もの。**「採点済み」ではない**（この先が採点で、そこは `state` からは
  /// 読めない）。
  awaitingReview(
    label: 'レビュー待ち',
    icon: Icons.rate_review_outlined,
    tone: AppStatusTone.neutral,
  ),

  /// `unprocessed` / `ai_processing` -- 待っていれば進むもの。ホームでは
  /// 人間に何も求めないので色を持たない。
  processing(label: '処理中', icon: Icons.autorenew, tone: AppStatusTone.neutral),

  /// `error` -- 取込・処理が完了しなかったもの。放っておくとその生徒の答案が
  /// 黙って欠けるので、件数が0でない限りホームから隠さない。
  failed(label: '取込失敗', icon: Icons.error_outline, tone: AppStatusTone.danger),

  /// `reviewed` / `exported` -- 終わったもの。進捗バーの分子。
  done(
    label: '確認済み',
    icon: Icons.verified_outlined,
    tone: AppStatusTone.success,
  );

  const HomeWorkBucket({
    required this.label,
    required this.icon,
    required this.tone,
  });

  /// 日本語ラベル。色は状態の唯一の手がかりにしない (Issue #25) ため、
  /// ラベル・アイコン・強調度は常に3点セットで決める。
  final String label;
  final IconData icon;
  final AppStatusTone tone;

  static HomeWorkBucket of(String submissionState) => switch (submissionState) {
    'needs_review' => HomeWorkBucket.needsReview,
    'ai_processed' => HomeWorkBucket.awaitingReview,
    'unprocessed' || 'ai_processing' => HomeWorkBucket.processing,
    'error' => HomeWorkBucket.failed,
    'reviewed' || 'exported' => HomeWorkBucket.done,
    // 知らない状態を [done] に入れると進捗バーが嘘をつく。サイドカーが
    // 先に新しい状態を覚えた場合でも「まだ動いている」側へ倒す。
    _ => HomeWorkBucket.processing,
  };
}

/// 1つのテストの進み具合。
class HomeTestProgress {
  HomeTestProgress({
    required this.test,
    required List<SubmissionResponse> submissions,
  }) : counts = _countByBucket(submissions),
       resumableSubmission = _pickResumable(submissions);

  final TestResponse test;

  /// 0件のbucketは持たない -- 画面はこのMapをそのまま並べるので、
  /// 「0件」の行が混ざらないようにここで落としておく。
  final Map<HomeWorkBucket, int> counts;

  /// この画面から直接開く1件。要確認を優先し、同じbucket内では取込順
  /// (古い順) -- 答案は届いた順に片付けるものなので、最後に取り込んだ
  /// 答案を先頭に出すと、ずっと後ろに残る1件ができる。
  final SubmissionResponse? resumableSubmission;

  /// 登録がまだ終わっていないテスト。答案は取り込めない (§6.1)。
  bool get isDraft => test.status != 'ready';

  int get total => counts.values.fold(0, (sum, count) => sum + count);

  int countOf(HomeWorkBucket bucket) => counts[bucket] ?? 0;

  int get doneCount => countOf(HomeWorkBucket.done);

  /// 表示順。小さいほど上。[HomeDashboard.nextAction] の優先順位と同じ並びに
  /// してある -- 一番上のカードが「次の一手」の続きに見えるように。
  ///
  /// 0: 要確認の答案があるテスト（AIが人間に投げ返した）
  /// 1: レビュー待ちの答案があるテスト
  /// 2: 登録が途中、または取込に失敗した答案があるテスト
  /// 3: 待っていれば進む、あるいは片付いているテスト
  ///
  /// **0 と 1 を分けているのが要点。** ここをまとめて「レビューが止まって
  /// いるテスト」1段にすると、同順のタイブレークがテストの新しさになるため、
  /// 古いテストの要確認が新しいテストの通常レビューに負ける。要確認を先に
  /// 開くという §2.1 の優先順位はテストをまたいでも成り立たなければならず、
  /// [HomeDashboard._resumeTarget] はこの並びを信じて先頭から探す。
  int get order {
    if (countOf(HomeWorkBucket.needsReview) > 0) return 0;
    if (countOf(HomeWorkBucket.awaitingReview) > 0) return 1;
    if (isDraft || countOf(HomeWorkBucket.failed) > 0) return 2;
    return 3;
  }

  static Map<HomeWorkBucket, int> _countByBucket(
    List<SubmissionResponse> submissions,
  ) {
    final counts = <HomeWorkBucket, int>{};
    for (final submission in submissions) {
      final bucket = HomeWorkBucket.of(submission.state);
      counts[bucket] = (counts[bucket] ?? 0) + 1;
    }
    return Map.unmodifiable(counts);
  }

  /// 人間の作業待ちのbucket。[HomeWorkBucket] の宣言順がそのまま優先順位で、
  /// 要確認 -> レビュー待ち の順に開く。
  static const Set<HomeWorkBucket> _resumableBuckets = {
    HomeWorkBucket.needsReview,
    HomeWorkBucket.awaitingReview,
  };

  static SubmissionResponse? _pickResumable(
    List<SubmissionResponse> submissions,
  ) {
    final open =
        submissions
            .where(
              (s) => _resumableBuckets.contains(HomeWorkBucket.of(s.state)),
            )
            .toList()
          ..sort((a, b) {
            final byBucket = HomeWorkBucket.of(
              a.state,
            ).index.compareTo(HomeWorkBucket.of(b.state).index);
            if (byBucket != 0) return byBucket;
            return a.createdAt.compareTo(b.createdAt);
          });
    return open.isEmpty ? null : open.first;
  }
}

/// ホームが一番上に出す「次の一手」。
///
/// 1つだけ出す。候補を3つ並べるとそれは結局ダッシュボードで、選ぶ手間を
/// 画面から人間へ戻すことになる (Issue #68「数字を並べるだけのダッシュボード
/// にしないこと」)。全体像はこの下のテストカードが持つ。
class HomeNextAction {
  const HomeNextAction({
    required this.icon,
    required this.tone,
    required this.headline,
    required this.detail,
    required this.actionLabel,
    this.route,
  });

  final IconData icon;
  final AppStatusTone tone;

  /// 状況そのもの (「要確認の答案が3件あります」)。
  final String headline;

  /// なぜそれが次なのか、開くと何が起きるか。
  final String detail;

  final String actionLabel;

  /// `null` なら押しても行き先が無い状態 (AIの処理待ち) で、画面は
  /// 「更新」として扱う。
  final String? route;
}

/// ホーム画面1枚ぶんのデータ。
class HomeDashboard {
  const HomeDashboard({required this.tests, required this.hiddenTestCount});

  /// ホームが答案まで読みに行くテストの上限。
  ///
  /// 2つの理由がある。(1) 内訳は `listSubmissions` をテストごとに呼んで
  /// 数えるので、上限が無いとホームを開くたびにテストの数だけリクエストが
  /// 出る。(2) そもそもホームは「最近使用したテスト」を見せる画面で
  /// (簡易設計書 §16.1)、去年のテストまで並べる場所ではない。
  ///
  /// 溢れたぶんは「テスト一覧」から辿れる。ホーム側にもその件数を出す。
  static const int maxTests = 8;

  /// 表示順に並んだテスト。人間待ちのものが先、その中では新しい順。
  final List<HomeTestProgress> tests;

  /// [maxTests] に入らなかったテストの数。
  final int hiddenTestCount;

  /// 直近 [maxTests] 件のテストと、その答案から組み立てる。
  ///
  /// [submissionsByTestId] は [tests] と同じテストを覆っていることを前提に
  /// する (呼び出し側が両方を1回のロードで揃える)。
  factory HomeDashboard.from({
    required List<TestResponse> tests,
    required Map<String, List<SubmissionResponse>> submissionsByTestId,
    required int hiddenTestCount,
  }) {
    final progress =
        [
          for (final test in tests)
            HomeTestProgress(
              test: test,
              submissions: submissionsByTestId[test.id] ?? const [],
            ),
        ]..sort((a, b) {
          final byOrder = a.order.compareTo(b.order);
          if (byOrder != 0) return byOrder;
          return b.test.createdAt.compareTo(a.test.createdAt);
        });
    return HomeDashboard(tests: progress, hiddenTestCount: hiddenTestCount);
  }

  bool get isEmpty => tests.isEmpty && hiddenTestCount == 0;

  int count(HomeWorkBucket bucket) =>
      tests.fold(0, (sum, test) => sum + test.countOf(bucket));

  /// 取込に失敗した答案を持つ最初のテスト。`null` なら失敗は無い。
  HomeTestProgress? get _firstFailedTest {
    for (final test in tests) {
      if (test.countOf(HomeWorkBucket.failed) > 0) return test;
    }
    return null;
  }

  /// 「レビューを続ける」で開く1件と、それが属するテスト。
  ///
  /// 先頭から探すだけでよいのは、[tests] が [HomeTestProgress.order] で
  /// 並んでいて、その第一段が「要確認を含むか」だから -- テストの新しさより
  /// 先に答案のbucketで比べたことになる。したがって、要確認の答案がどれか1つ
  /// でもあれば、ここが返すのは必ずその要確認である。
  (HomeTestProgress, SubmissionResponse)? get _resumeTarget {
    for (final test in tests) {
      final submission = test.resumableSubmission;
      if (submission != null) return (test, submission);
    }
    return null;
  }

  /// 登録が途中で止まっているテスト。
  HomeTestProgress? get _firstDraftTest {
    for (final test in tests) {
      if (test.isDraft) return test;
    }
    return null;
  }

  /// 次の一手。上から順に「人間にしかできないこと」「待っていれば進むこと」
  /// 「まだ何も無いなら始めること」。
  HomeNextAction get nextAction {
    if (_resumeTarget case (final test, final submission)) {
      final bucket = HomeWorkBucket.of(submission.state);
      final isFlagged = bucket == HomeWorkBucket.needsReview;
      final awaiting = count(HomeWorkBucket.awaitingReview);
      // 見出しが名指ししたbucketだけを数える。2つを足すと、要確認1件と
      // レビュー待ち9件で「要確認の答案が10件あります」と読ませてしまい、
      // 下のカードが示す要確認1件と食い違う。残りは説明文が引き取る。
      //
      // [isFlagged] が false のとき要確認は必ず0件である ([_resumeTarget]
      // は要確認があればそれを返す) ので、逆向きの但し書きは要らない。
      return HomeNextAction(
        icon: bucket.icon,
        tone: bucket.tone,
        headline: isFlagged
            ? '要確認の答案が${count(HomeWorkBucket.needsReview)}件あります'
            : 'レビュー待ちの答案が$awaiting件あります',
        detail: isFlagged
            ? '人の確認が必要と判定された答案から開きます'
                  '${awaiting > 0 ? '（ほかにレビュー待ちが$awaiting件）' : ''}'
            : '取込と回答欄の抽出まで終わっています。古い順に開いていきます',
        actionLabel: 'レビューを続ける',
        route: AppRoutes.pdfReview(
          testId: test.test.id,
          submissionId: submission.id,
        ),
      );
    }
    // レビューすべき答案が無くなってから失敗を出す。取込失敗は放置できない
    // が、レビューの列に割り込ませるほど急ぐものでもない (テストカード側では
    // 常に見えている)。
    if (_firstFailedTest case final failed?) {
      return HomeNextAction(
        icon: HomeWorkBucket.failed.icon,
        tone: HomeWorkBucket.failed.tone,
        headline: '取込に失敗した答案が${count(HomeWorkBucket.failed)}件あります',
        detail: '同じPDFを取り込み直すと、その答案をやり直せます（${failed.test.name}）',
        actionLabel: '答案取込を開く',
        route: AppRoutes.answerIntake,
      );
    }
    if (_firstDraftTest case final draft?) {
      return HomeNextAction(
        icon: Icons.pending_actions,
        tone: AppStatusTone.neutral,
        headline: '登録が途中のテストがあります',
        detail: '${draft.test.name} は回答欄と設問依存関係の確認が終わっていません',
        actionLabel: '登録を続ける',
        route: AppRoutes.testSettings(draft.test.id),
      );
    }
    if (count(HomeWorkBucket.processing) > 0) {
      return HomeNextAction(
        icon: HomeWorkBucket.processing.icon,
        tone: HomeWorkBucket.processing.tone,
        headline: '処理中の答案が${count(HomeWorkBucket.processing)}件あります',
        detail: '終わった答案はここにレビュー待ちとして並びます',
        // 行き先が無い唯一の分岐。押せるものが「更新」しか無い状態を、
        // 押せないボタンではなく押せるボタンで表す。
        actionLabel: '最新の状況に更新',
      );
    }
    if (tests.isNotEmpty) {
      return const HomeNextAction(
        icon: Icons.upload_file,
        tone: AppStatusTone.success,
        headline: 'レビュー待ちの答案はありません',
        detail: '次の答案を取り込むと、回答欄の抽出まで自動で進みます',
        actionLabel: '答案を取り込む',
        route: AppRoutes.answerIntake,
      );
    }
    return const HomeNextAction(
      icon: Icons.add_task,
      tone: AppStatusTone.neutral,
      headline: 'まだテストが登録されていません',
      detail: '模範解答と採点マニュアルのPDFを登録すると、答案を取り込めるようになります',
      actionLabel: 'テストを登録する',
      route: AppRoutes.testRegistration,
    );
  }
}
