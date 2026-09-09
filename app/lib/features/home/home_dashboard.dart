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
/// (`backend/.../adapters/submission_intake.py`)。**ホームはその先を何も
/// 知らない。** 採点が終わっても、人間が全設問を承認しても、答案の `state` は
/// `ai_processed` のまま動かない -- `state` を書き換えるのは取込と
/// `_sync_submission_review_state` だけで、後者は `needs_review` / `reviewed`
/// の答案にしか働かないためである。採点が**始まったかどうか**すら `state` には
/// 出ない (起票の有無は `listJobs` にしか現れず、ホームは引かないと決めている
/// -- §4)。文言はそこを跨がない (`docs/home-dashboard.md` §3.1)。
library;

import 'package:flutter/material.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/core/design/app_status_tone.dart';
import 'package:auto_scoring_app/core/submission_work_bucket.dart';

/// [HomeWorkBucket] は `core/submission_work_bucket.dart` へ移した (Issue #113)。
/// 答案キューが同じ畳み方と同じ並び順を要るようになり、`core` は `features` を
/// import できないためである。ここから再輸出しているのは、この語彙の読み手が
/// いまもホーム側に多く、import 元を全部書き換える意味が無いからである。
export 'package:auto_scoring_app/core/submission_work_bucket.dart'
    show HomeWorkBucket;

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
  /// 1: 取込済みの答案があるテスト
  /// 2: 登録が途中、または取込に失敗した答案があるテスト
  /// 3: 待っていれば進む、あるいは片付いているテスト
  ///
  /// **0 と 1 を分けているのが要点。** ここをまとめて「レビューが止まって
  /// いるテスト」1段にすると、同順のタイブレークがテストの新しさになるため、
  /// 古いテストの要確認が新しいテストの通常レビューに負ける。要確認を先に
  /// 開くという §2.1 の優先順位はテストをまたいでも成り立たなければならず、
  /// [HomeDashboard._resumeTarget] はこの並びを信じて先頭から探す。
  ///
  /// [HomeDashboard._pickVisible] もこの並びを信じて、[settledOrder] より前を
  /// カードから落とさない (Issue #151)。段を増やすときは、その段が「手が要る」
  /// 側なのかを決めてから足すこと。
  int get order {
    if (countOf(HomeWorkBucket.needsReview) > 0) return 0;
    if (countOf(HomeWorkBucket.intakeDone) > 0) return 1;
    if (isDraft || countOf(HomeWorkBucket.failed) > 0) return 2;
    return settledOrder;
  }

  /// [order] の最下段 -- **ホームから促すことが何も無いテスト**。
  ///
  /// 「片付いた」とは言わない。答案が1件も取り込まれていないテストもここに
  /// 来るし、`ai_processed` のまま止まった答案は [HomeWorkBucket.intakeDone]
  /// なので、そもそもここには来ない。言えるのは「この画面から開く候補が無い」
  /// までである (§3.1)。
  static const int settledOrder = 3;

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

  /// ホームから開く候補になるbucket。[HomeWorkBucket] の宣言順がそのまま
  /// 優先順位で、要確認 -> 取込済み の順に開く。
  ///
  /// 「人間の作業待ち」とは呼べない。[HomeWorkBucket.intakeDone] には
  /// レビュー済みの答案も残りうるからである (§3.1)。ここが言えるのは
  /// 「開いて確かめる価値がある答案」までで、開いた先が実際にどうなっているかは
  /// 添削レビュー画面が答える。
  static const Set<HomeWorkBucket> _resumableBuckets = {
    HomeWorkBucket.needsReview,
    HomeWorkBucket.intakeDone,
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
///
/// **[tests] は全テストである。数える対象と、カードに並べる対象を分けてある**
/// (Issue #151)。以前はホームが「新しい順に8件」だけ答案を読み、その8件の上で
/// 件数も「次の一手」も決めていた。溢れたテストの要確認は帯の数に入らず、
/// カードも出ないので、**利用者から見ると仕事が残っていないように見えた** --
/// カードが出ないことは見れば分かるが、数が3件足りないことは誰にも見えない。
class HomeDashboard {
  const HomeDashboard._({required this.tests, required this.visibleTests});

  /// カードとして並べるテストの本数の目安。
  ///
  /// ホームは「最近使用したテスト」を見せる画面で (簡易設計書 §16.1)、去年の
  /// テストまで並べる場所ではない。ただし**これは上限ではなく、片付いている
  /// テストを切る位置である** -- 手が要るテストは何件あっても隠さない
  /// ([visibleTests])。
  ///
  /// 数を大きくするだけでは同じ事故が再発する。11件へ広げても、手が要るテストが
  /// 12件あれば12件目はまた消える。**原因は上限の値ではなく、上限を新しさで
  /// 切っていたことにある。**
  static const int maxTests = 8;

  /// 表示順に並んだ**全テスト**。人間待ちのものが先、その中では新しい順。
  ///
  /// 件数 ([count])、「次の一手」([nextAction])、レビューの再開先
  /// ([_resumeTarget]) は、いずれもこの全件の上で決まる。
  final List<HomeTestProgress> tests;

  /// カードとして実際に並べるテスト。[tests] の先頭からの連続した一部。
  final List<HomeTestProgress> visibleTests;

  /// カードに並べなかったテストの数。
  ///
  /// **「数えていないテスト」ではない。** 答案は全件読んでいるので、ここに
  /// 入るのは [HomeTestProgress.order] が最下段のテスト -- ホームから開く
  /// 答案が1件も無いものだけである。
  int get hiddenTestCount => tests.length - visibleTests.length;

  /// 全テストと、その答案から組み立てる。
  ///
  /// [submissionsByTestId] は [tests] と同じテストを覆っていることを前提に
  /// する (呼び出し側が両方を1回のロードで揃える)。
  factory HomeDashboard.from({
    required List<TestResponse> tests,
    required Map<String, List<SubmissionResponse>> submissionsByTestId,
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
    return HomeDashboard._(
      tests: List.unmodifiable(progress),
      visibleTests: List.unmodifiable(_pickVisible(progress)),
    );
  }

  /// カードに出す範囲を、件数ではなく**手が要るかどうか**で切る。
  ///
  /// [tests] は [HomeTestProgress.order] 順に並んでいて、最下段
  /// ([HomeTestProgress.settledOrder]) は「ホームから開く答案が無いテスト」で
  /// ある。したがって先頭からその境目までが「手が要るテスト」で、**そこは
  /// 何件あっても全部出す**。[maxTests] が削るのは、その後ろの片付いた尾だけ。
  ///
  /// **これが Issue #151 の核心である。** 新しい順に8件取ると、どの8件が残るかは
  /// 取込順に依存し、要確認を抱えたテストが理由もなく落ちる。手が要るものを
  /// 先に確保すれば、落ちるのは「落ちても困らないもの」だけになる。
  static List<HomeTestProgress> _pickVisible(List<HomeTestProgress> ordered) {
    final settledFrom = ordered.indexWhere(
      (test) => test.order == HomeTestProgress.settledOrder,
    );
    if (settledFrom < 0) return ordered;
    return ordered
        .take(settledFrom < maxTests ? maxTests : settledFrom)
        .toList();
  }

  bool get isEmpty => tests.isEmpty;

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
  ///
  /// 文言は**この画面が答案の `state` から実際に知っていることしか言わない**。
  /// 採点の進み具合 (§3.1)、再取込が通るかどうか、`draft` のどの確認手順が
  /// 残っているかは、いずれもホームが取得していないので断定しない。
  HomeNextAction get nextAction {
    if (_resumeTarget case (final test, final submission)) {
      final bucket = HomeWorkBucket.of(submission.state);
      final isFlagged = bucket == HomeWorkBucket.needsReview;
      final awaiting = count(HomeWorkBucket.intakeDone);
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
            : '取込済みの答案が$awaiting件あります',
        // 「古い順」はテストをまたがない。[_resumeTarget] はまずテストを選び
        // (要確認優先、同じ段ではテストの新しい順)、その中で取込の古い順に
        // 1件を採る。全テストを通した最古ではないので、そう読める書き方を
        // しない (`docs/home-dashboard.md` §2.1)。
        detail: isFlagged
            ? '人の確認が必要と判定された答案から開きます'
                  '${awaiting > 0 ? '（ほかに取込済みが$awaiting件）' : ''}'
            // **「AI採点は開始済み」とは言わない。** 起票を試みるのは答案取込
            // 画面だが、409や通信断で失敗しうるし、この仕組みより前に
            // 取り込まれた答案には一度も行われていない。どちらも
            // `ai_processed` のままジョブ0件で止まり、待っても進まない --
            // そしてホームはジョブを引かないので、その区別がつかない
            // (§3.1、review round 1 P2-1)。開けば添削レビュー画面が答える。
            : '取込と回答欄の抽出は終わっています。'
                  'AI採点とレビューがどこまで進んだかはホームでは分かりません。'
                  'テストごとに、取込の古い順に開きます',
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
        // 「取り込み直せば直る」とは言わない。再取込が受け付けられるのは
        // その答案に下流のデータ (認識・採点・レビュー・ジョブ) が無いときだけ
        // で、あるものは 409 で拒否される
        // (`backend/.../domain/submission_intake.py` の `decide_reintake`)。
        // ホームは下流の有無を取得していないので、どちらになるか分からない。
        detail:
            '答案取込画面で対象のテストを選ぶと、失敗した答案が一覧に出ます'
            '（${failed.test.name}）',
        actionLabel: '答案取込を開く',
        route: AppRoutes.intake,
      );
    }
    if (_firstDraftTest case final draft?) {
      return HomeNextAction(
        icon: Icons.pending_actions,
        tone: AppStatusTone.neutral,
        headline: '登録が途中のテストがあります',
        // どの確認手順が残っているかは言わない。`draft` から `ready` へ進むには
        // プロファイルと設問依存関係グラフの両方の確定が要る
        // (`complete-registration`) が、どちらが済んでいるかはプロファイルと
        // グラフを取得しないと分からず、ホームは取得していない。
        detail:
            '${draft.test.name} の登録がまだ完了していません'
            '（回答欄と設問依存関係の確認が要ります）',
        actionLabel: '登録を続ける',
        route: AppRoutes.testSettings(draft.test.id),
      );
    }
    if (count(HomeWorkBucket.processing) > 0) {
      return HomeNextAction(
        icon: HomeWorkBucket.processing.icon,
        tone: HomeWorkBucket.processing.tone,
        headline: '処理中の答案が${count(HomeWorkBucket.processing)}件あります',
        // 取込の結果は3通りある (回答欄が揃えば `ai_processed`、ページや回答欄が
        // 足りなければ `needs_review`、失敗すれば `error`)。「レビュー待ちに
        // なります」と1つに決めない。
        detail: '終わると取込済み・要確認・取込失敗のいずれかになります',
        // 行き先が無い唯一の分岐。押せるものが「更新」しか無い状態を、
        // 押せないボタンではなく押せるボタンで表す。
        actionLabel: '最新の状況に更新',
      );
    }
    if (tests.isNotEmpty) {
      return HomeNextAction(
        icon: Icons.upload_file,
        tone: AppStatusTone.success,
        // 「レビュー待ちはありません」とは言えない -- レビューが済んだか
        // どうかを `state` から読めないので (§3.1)。言えるのは「この画面から
        // 開く候補が無い」ことだけである。
        //
        // **範囲の但し書きはもう要らない** (Issue #151)。[tests] は全テストで、
        // カードに載らなかったぶんも答案まで数えてある。以前はここが
        // 「直近N件のテストに…ありません」だった -- 数えていないテストの不在を
        // 断定しないためだったが、いまは数えていないテストが無い。
        headline: 'いま開く答案はありません',
        // 「問題がなければ」を外さない。回答欄が揃わなかった答案は
        // 要確認として止まり、起票そのものが失敗することもある
        // (`docs/job-queue.md`「起票のタイミング」)。
        detail:
            '次の答案を取り込むと、回答欄の抽出まで自動で行われ、'
            '問題がなければAI採点もそのまま始まります',
        actionLabel: '答案を取り込む',
        route: AppRoutes.intake,
      );
    }
    return const HomeNextAction(
      icon: Icons.add_task,
      tone: AppStatusTone.neutral,
      headline: 'まだテストが登録されていません',
      // 登録は「フォルダを選べば終わり」ではない。`ready` になるにはプロファイルと
      // 設問依存関係グラフの確定まで要る (`complete-registration`)。
      //
      // 文言は Issue #95 決定 1 に従う: **模範解答PDFは要求しない**。実在しない
      // ため廃止した (簡易設計書 §6.3「模範解答PDF（廃止）」)。必須は採点基準PDFと
      // 生徒答案で、Issue #101 でフォルダごと取り込む形になった。
      detail:
          '教科のフォルダを選ぶと、採点基準と答案をまとめて取り込めます。'
          '取り込んだあと、配点と回答欄を確認すると採点を始められます',
      actionLabel: 'テストを登録する',
      route: AppRoutes.intake,
    );
  }
}
