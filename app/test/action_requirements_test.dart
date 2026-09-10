import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/core/action_requirements.dart';

/// 無効な操作の理由を、ウィジェットを1つも立てずに確かめる (Issue #88)。
///
/// ここが守っているのは2つの性質である。
///
/// 1. **無効なら理由が1件以上ある。** 関数が空を返すのは有効なときだけ。
/// 2. **有効なら理由が0件。** 条件を満たすと文言が消える。
///
/// どちらも画面側では確かめにくい (無効の組み合わせを総当たりするには、画面の
/// 状態を全部作らなければならない) ので、判定を `core` に置いた理由がそのまま
/// このファイルの理由になる。
void main() {
  /// 出してよい形の文かどうか。
  ///
  /// 「できません」で終わる文は状態の報告であって、**何をすれば有効になるか**を
  /// 言っていない。#88 が直しているのはまさにそこなので、形のほうを検査する。
  void expectActionable(ActionRequirement requirement) {
    expect(requirement.id, isNotEmpty);
    expect(requirement.message, isNotEmpty);
    expect(
      requirement.message,
      endsWith('。'),
      reason: '${requirement.id}: 1文として閉じていない',
    );
    // 診断文の材料が混ざっていないこと。例外クラス名・HTTPステータス・内部の
    // 理由語は講師に読ませる物ではない (AGENTS.md «Security»)。
    expect(
      requirement.message,
      isNot(matches(RegExp(r'Exception|[Ee]rror|HTTP|[0-9]{3} '))),
      reason: '${requirement.id}: 診断文が混ざっている',
    );
  }

  group('資料取込', () {
    test('型を選ぶまで「フォルダを選ぶ」は押せず、理由が出る', () {
      final unmet = intakeFolderPickRequirements(
        busy: false,
        templateChosen: false,
      );
      expect(unmet.map((r) => r.id), ['intake-template']);
      unmet.forEach(expectActionable);
    });

    test('型を選ぶと理由が消える', () {
      expect(
        intakeFolderPickRequirements(busy: false, templateChosen: true),
        isEmpty,
      );
    });

    test('処理中は、それ自体が理由になる', () {
      // 無効なのに理由が1つも無い状態を作らないための1本。進捗表示だけに
      // 頼ると、進捗表示を置き忘れた画面で灰色のボタンが黙る。
      expect(
        intakeFolderPickRequirements(
          busy: true,
          templateChosen: true,
        ).map((r) => r.id),
        ['busy'],
      );
    });

    test('フォルダ側の理由は、画面の状態の後ろに並ぶ', () {
      final unmet = intakeImportRequirements(
        busy: true,
        classifying: false,
        folderRequirements: [ActionRequirement.intakeNothingToImport],
      );
      expect(unmet.map((r) => r.id), ['busy', 'intake-nothing-to-import']);
    });

    test('判定中も理由になる', () {
      expect(
        intakeImportRequirements(
          busy: false,
          classifying: true,
          folderRequirements: const [],
        ).map((r) => r.id),
        ['busy'],
      );
    });

    test('条件が揃えば理由は0件', () {
      expect(
        intakeImportRequirements(
          busy: false,
          classifying: false,
          folderRequirements: const [],
        ),
        isEmpty,
      );
    });
  });

  group('テスト設定: プロファイル', () {
    List<String> confirmIds({
      bool busy = false,
      bool alreadyConfirmed = false,
      int regionCount = 1,
      int unassignedRegionCount = 0,
      bool mustSeeAnswerSheetFirst = false,
      bool answerSheetRegistered = true,
    }) => answerProfileConfirmRequirements(
      busy: busy,
      alreadyConfirmed: alreadyConfirmed,
      regionCount: regionCount,
      unassignedRegionCount: unassignedRegionCount,
      mustSeeAnswerSheetFirst: mustSeeAnswerSheetFirst,
      answerSheetRegistered: answerSheetRegistered,
    ).map((r) => r.id).toList();

    test('枠が1つも無ければ、引き方まで言う', () {
      expect(confirmIds(regionCount: 0), ['answer-regions-missing']);
      expect(
        ActionRequirement.answerRegionsMissing.message,
        contains('回答欄を自動検出'),
      );
    });

    test('未割り当ての枠は件数ごと出る', () {
      expect(confirmIds(unassignedRegionCount: 3), [
        'answer-regions-unassigned',
      ]);
      expect(
        ActionRequirement.answerRegionsUnassigned(3).message,
        contains('3件'),
      );
    });

    test('答案が未登録か、登録済みで描けていないかで文を分ける', () {
      // 次の手が違う: 取り込むのか、再試行するのか。1本の文にまとめると、
      // どちらかの人に見当違いの指示を読ませることになる。
      expect(
        confirmIds(mustSeeAnswerSheetFirst: true, answerSheetRegistered: false),
        ['answer-sheet-unseen'],
      );
      expect(
        confirmIds(mustSeeAnswerSheetFirst: true, answerSheetRegistered: true),
        ['answer-sheet-unrendered'],
      );
    });

    test('確定済みなら「確定済み」と言う', () {
      expect(confirmIds(alreadyConfirmed: true), ['profile-already-confirmed']);
    });

    test('条件が揃えば理由は0件', () {
      expect(confirmIds(), isEmpty);
    });

    test('理由はすべて、次にできることを言う形になっている', () {
      for (final unmet in [
        confirmIds(regionCount: 0),
        confirmIds(unassignedRegionCount: 1),
        confirmIds(mustSeeAnswerSheetFirst: true, answerSheetRegistered: false),
        confirmIds(mustSeeAnswerSheetFirst: true, answerSheetRegistered: true),
      ]) {
        expect(unmet, isNotEmpty);
      }
      for (final requirement in [
        ActionRequirement.busy,
        ActionRequirement.answerRegionsMissing,
        ActionRequirement.answerRegionsUnassigned(1),
        ActionRequirement.answerSheetUnseen,
        ActionRequirement.answerSheetUnrendered,
        ActionRequirement.profileAlreadyConfirmed,
      ]) {
        expectActionable(requirement);
      }
    });

    test('「修正内容を保存」が無効な状態は、確定ボタンの理由が必ず覆う', () {
      // 画面はこの2つのボタンに1つの理由欄しか置いていない。置いてよいのは
      // 保存の理由が確定の理由の部分集合だからで、その包含関係をここで総当たり
      // する -- 片方の条件だけを足すと落ちる。
      for (final busy in [false, true]) {
        for (final confirmed in [false, true]) {
          for (final regionCount in [0, 1]) {
            final save = answerProfileSaveRequirements(
              busy: busy,
              // 画面の `hasRegions` は「リストが null でない」。枠0件の
              // リストは保存できて確定できない、という既存の意味を保つ。
              hasRegions: regionCount > 0,
              alreadyConfirmed: confirmed,
            );
            final confirm = answerProfileConfirmRequirements(
              busy: busy,
              alreadyConfirmed: confirmed,
              regionCount: regionCount,
              unassignedRegionCount: 0,
              mustSeeAnswerSheetFirst: false,
              answerSheetRegistered: true,
            );
            expect(
              confirm.map((r) => r.id).toSet(),
              containsAll(save.map((r) => r.id)),
              reason:
                  'busy=$busy confirmed=$confirmed regions=$regionCount: '
                  '保存が無効なのに、その理由がどこにも出ない',
            );
          }
        }
      }
    });
  });

  group('テスト設定: 依存関係グラフ', () {
    test('グラフが無ければ、作り方を言う', () {
      expect(
        dependencyGraphConfirmRequirements(
          busy: false,
          hasGraph: false,
          alreadyConfirmed: false,
        ).map((r) => r.id),
        ['dependency-graph-missing'],
      );
    });

    test('条件が揃えば理由は0件', () {
      expect(
        dependencyGraphConfirmRequirements(
          busy: false,
          hasGraph: true,
          alreadyConfirmed: false,
        ),
        isEmpty,
      );
    });
  });

  group('テスト設定: 登録完了', () {
    test('配点はボタンを無効にしない', () {
      // #88 より前からの仕様。この Issue は理由を出す話であって、条件を締める
      // 話ではない -- 締めるなら別 Issue である。
      expect(
        completeRegistrationRequirements(
          busy: false,
          alreadyComplete: false,
          profileConfirmed: true,
          dependencyGraphConfirmed: true,
        ),
        isEmpty,
      );
    });

    test('未確定のものを名指しする', () {
      expect(
        completeRegistrationRequirements(
          busy: false,
          alreadyComplete: false,
          profileConfirmed: false,
          dependencyGraphConfirmed: false,
        ).map((r) => r.id),
        ['profile-unconfirmed', 'dependency-graph-unconfirmed'],
      );
    });

    test('完了済みなら「完了済み」と言う', () {
      expect(
        completeRegistrationRequirements(
          busy: false,
          alreadyComplete: true,
          profileConfirmed: true,
          dependencyGraphConfirmed: true,
        ).map((r) => r.id),
        ['registration-already-complete'],
      );
    });

    test('採点開始までに残るものには配点が入る', () {
      expect(
        gradingStartRequirements(
          criteriaSettled: false,
          profileConfirmed: true,
          dependencyGraphConfirmed: true,
          dependencyGraphStale: false,
        ).map((r) => r.id),
        ['criteria-unconfirmed'],
      );
    });

    test('グラフが古いのは、未確定とは別の文になる', () {
      expect(
        gradingStartRequirements(
          criteriaSettled: true,
          profileConfirmed: true,
          dependencyGraphConfirmed: true,
          dependencyGraphStale: true,
        ).map((r) => r.id),
        ['dependency-graph-stale'],
      );
      // 未確定なら「確定してください」が先で、古いかどうかは次の問題。
      expect(
        gradingStartRequirements(
          criteriaSettled: true,
          profileConfirmed: true,
          dependencyGraphConfirmed: false,
          dependencyGraphStale: true,
        ).map((r) => r.id),
        ['dependency-graph-unconfirmed'],
      );
    });

    test('全部揃えば残りは0件', () {
      expect(
        gradingStartRequirements(
          criteriaSettled: true,
          profileConfirmed: true,
          dependencyGraphConfirmed: true,
          dependencyGraphStale: false,
        ),
        isEmpty,
      );
    });
  });

  group('設定: API キー', () {
    test('資格情報ストアが使えないとき、代わりの手を言う', () {
      final unmet = apiKeySaveRequirements(
        busy: false,
        credentialStoreAvailable: false,
      );
      expect(unmet.map((r) => r.id), ['credential-store-unavailable']);
      expect(unmet.single.message, contains('環境変数'));
    });

    test('キーが無いと疎通は確認できない', () {
      expect(
        apiKeyVerifyRequirements(
          busy: false,
          configured: false,
        ).map((r) => r.id),
        ['api-key-not-configured'],
      );
    });

    test('条件が揃えば理由は0件', () {
      expect(
        apiKeySaveRequirements(busy: false, credentialStoreAvailable: true),
        isEmpty,
      );
      expect(apiKeyVerifyRequirements(busy: false, configured: true), isEmpty);
    });
  });

  test('進行中しか理由にならない操作', () {
    expect(whileRunningRequirements(running: true).map((r) => r.id), ['busy']);
    expect(whileRunningRequirements(running: false), isEmpty);
  });

  test('id は一意で、文は全部「次にできること」の形をしている', () {
    // 文言の置き場が1か所であることの検査。`id` が衝突すると、画面の `Key` も
    // 衝突して、どちらの理由が出ているのか分からなくなる。
    final all = <ActionRequirement>[
      ActionRequirement.busy,
      ActionRequirement.intakeTemplate,
      ActionRequirement.intakeNothingToImport,
      ActionRequirement.intakeTargetUnassigned(1),
      ActionRequirement.intakeTestNameEmpty(1),
      ActionRequirement.intakeRequiredRoleMissing(1),
      ActionRequirement.intakeProposalUnconfirmed(1),
      ActionRequirement.intakeAnswerUnrouted(1),
      ActionRequirement.intakeNonAnswerUnroutable(1),
      ActionRequirement.answerRegionsMissing,
      ActionRequirement.answerRegionsUnassigned(1),
      ActionRequirement.answerSheetUnseen,
      ActionRequirement.answerSheetUnrendered,
      ActionRequirement.profileAlreadyConfirmed,
      ActionRequirement.dependencyGraphMissing,
      ActionRequirement.dependencyGraphAlreadyConfirmed,
      ActionRequirement.criteriaUnconfirmed,
      ActionRequirement.profileUnconfirmed,
      ActionRequirement.dependencyGraphUnconfirmed,
      ActionRequirement.dependencyGraphStale,
      ActionRequirement.registrationAlreadyComplete,
      ActionRequirement.credentialStoreUnavailable,
      ActionRequirement.apiKeyNotConfigured,
    ];
    expect(all.map((r) => r.id).toSet(), hasLength(all.length));
    all.forEach(expectActionable);
  });
}
