# UI/UX を複数のAIエージェントに独立評価させた記録

GitHub Issue #71。UI改良4件（#66 Riverpod/go_router、#67 デザイントークン、#68 ホーム
ダッシュボード、#64 依存DAGの進捗表示）を入れたあと、**実装した本人以外の視点**で結果を
評価するために行った。

この文書は「誰が何を指摘し、それを採ったか採らなかったか、なぜか」の記録である。
指摘そのものを実装の指示として読まないこと。UI は好みの幅が大きく、**評価者の指摘を
そのまま採用したものは1件も無い**。

## 1. なぜ提供元を散らしたか

実装したエージェントは自分の判断基準で作っているので、同じ基準で自己評価しても盲点が残る。
同じベンダーのモデルだけを並べても、学習データも整列の癖も近いため「多様な視点」にはならない。
そこで**提供元の異なるモデル**を混ぜ、同一の材料・同一のプロンプトで、
**互いの評価を見せずに**独立に走らせた。

| 評価者   | CLI            | モデル                      | 提供元    | 指摘数 (high/medium/low) |
| -------- | -------------- | --------------------------- | --------- | ------------------------ |
| Gemini   | `agy`          | `gemini-3.1-pro-high`       | Google    | 5 (2/2/1)                |
| Codex    | `codex exec`   | 純正                        | OpenAI    | 9 (3/6/0)                |
| Claude   | `claude -p`    | 純正                        | Anthropic | 16 (6/7/3)               |
| Grok     | `cursor-agent` | `cursor-grok-4.6-high-fast` | xAI       | 10 (4/5/1)               |
| Composer | `cursor-agent` | `composer-2.5`              | Anysphere | 12 (1/6/5)               |

合計 **52件**。

**この表と以下の一致数は、すべて
[`evaluations.json`](./ui-ux-multi-agent-evaluation/evaluations.json) から数えたものである。**
最初の版では Claude の内訳だけが `6/9/1` と誤っていた。Claude だけ完了が遅く、そこだけ
集計スクリプトを使わず一覧を目で数えたためである（Issue #71 レビュー2回目）。
**手で数えた箇所だけが間違っていた**ので、以降の一致数には**該当する finding の id を
必ず併記する**。数えているのはその id の**評価者の異なり数**であり、読む側が JSON と
突き合わせて検算できる。

### 1.1 open-weights 枠は埋まらなかった（`gpt-oss-120b-medium` は視覚を持たない）

当初は open-weights モデル（`agy` の `gpt-oss-120b-medium`）を6体目に入れる予定だった。
**このモデルは画像を読めない。** そして厄介なことに、**読めないまま動いてしまう。**

CLI はエラーを返さない。プロンプトは受け取り、指示どおり JSON を組み立て、それらしい
文章を返す。**「動いているように見えて、実は何も読んでいない」**という失敗の形である。

これを撮影前に潰すため、**画像にしかない数値を答えさせる probe** を先に流した。
ホーム画面のスクリーンショット1枚を渡し、進捗バーの「確認済み N / M」の数値を答えるよう求め、
読めない場合は `CANNOT_READ_IMAGE` とだけ返すよう指示した。数値は画像の中にしか無いので、
本文だけを読んでいるモデルは答えようがない。

結果、このモデルは画像が渡っていないことを自分から述べ、`findings` を空で返した。

```json
{
  "overall_impression": "画像が提示されていないため、具体的な UI の評価を行うことができません。…",
  "what_works_well": ["画像の詳細が分かれば、正確な評価が可能です"],
  "findings": []
}
```

`agy` から選べる open-weights モデルはこれだけなので、**この環境では open-weights 枠を
埋められない**。5体で実施した。

**教訓: 視覚を要求する評価では、本番の前に probe を1回流す。** 出力が返ってきたことは、
画像が届いたことの証明にならない。

## 2. 各CLIの落とし穴

同じ「画像を添えてプロンプトを投げる」でも、CLI ごとに引っかかる場所が違った。
実行時に踏んだものを残す。

| CLI            | 踏んだこと                                                                                                                                                |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `agy`          | `--model` は `-p` **より前**に置かないと拾われない。非対話実行には `--dangerously-skip-permissions` が要る                                                |
| `cursor-agent` | `--trust` が要る（無いとワークスペースの信頼確認で止まる）                                                                                                |
| `codex exec`   | `-i/--image` が**プロンプト引数を飲んでしまう**ので、プロンプトは stdin から渡す。リポジトリ外のディレクトリで走らせるため `--skip-git-repo-check` も要る |
| `claude -p`    | 画像は Read ツール経由。パスを本文で示せばよい                                                                                                            |

## 3. 材料

`scripts/screenshot-linux-app.sh` と `scripts/seed-demo-app-data.py` で撮った
**28枚のPNG**（7画面 × ライト/ダーク × 1280x720 / 700x720）。取得手順は
[linux-desktop-development.md](./linux-desktop-development.md) §4.4。

画像はリポジトリにコミットしていない。評価者へ渡すためのもので、
公開物に載せるためのものではないからである。再取得の手順だけを残している。

プロンプトは全員に同一のものを渡した。内容は「アプリが何をするものか」「誰がどういう
状況で使うか」「評価してほしい7観点」「JSON 出力形式」「評価対象外（DEBUGリボン、
ダミーPDFの中身、OSのタイトルバー）」である。

### 3.1 評価者の生出力

**[`ui-ux-multi-agent-evaluation/evaluations.json`](./ui-ux-multi-agent-evaluation/evaluations.json)**
に5体ぶん（52件）をそのまま置いてある。この文書の「5/5が指摘」「4/5が指摘」という数字は、
そこを数えれば誰でも検証できる。**集約した側の要約だけを残すと、数字の裏付けが
リポジトリの中に無くなる**（Issue #71 レビュー1回目の指摘）。

CLI の出力から JSON を取り出しただけで、内容には手を入れていない（整形は Prettier）。
評価者のキーとモデルの対応は §1 の表にある。画像は合成データのスクリーンショットなので、
公開して差し支えない内容であることを確認したうえで置いている。

## 4. 集約結果

### 4.1 全員一致（5/5・全員 high）→ 起票した

**同じ設問について、状態表示が2つの粒度で矛盾する。** → #84

5体が独立に、同じ画面の同じ食い違いを指摘した唯一の項目である。

- `pdf-review-blocked`: DAGの問1は「承認済み」なのに、右パネルのバッジは「⚠ 要確認」
- `pdf-review-failed`: DAGの問1は「レビュー待ち」なのに、右パネルのバッジは「✓ AI処理済み」

**この1件だけは、指摘を受けてコードで根本原因を確認した。** データの誤りではなく
**スコープの不一致**である。`pdf_review_page.dart` の `_buildSubmissionStateChip` は
**答案全体**の state を描くが、その出力が**設問見出しの直下**に置かれているため、
読み手は「その設問の状態」として読む。DAGノードは設問ごとの状態を出しているので、
同じ「問1」について2つの粒度が並ぶ。どちらの表示も単体では正しい。

`grok` と `claude` が独立に同じ結論に達している。

> 状態の食い違いは、このアプリが一番守るべき「人が見てから確定する」を壊す。

**5/5**: `gemini` inconsistent-status-indicators (high) / `codex` conflicting-review-status
(high) / `claude` status-vocabulary-contradiction (high) / `grok`
review-q1-status-contradiction (high) / `composer` review-conflicting-state-labels (high)

左レールが状態を潰す問題も同じ根なので、この Issue に含めた。
**4/5**: `grok` review-rail-flattens-states (high) / `claude` rail-icons-indistinguishable
(medium) / `codex` narrow-question-labels-missing (medium) / `composer`
review-sidebar-icon-only-narrow (low)

### 4.2 多数一致（3〜4/5）→ 4本にまとめて起票した

**残り4本については、コードでの原因特定を行っていない。静止画からの観察である。**
各 Issue にもそう明記した。

| 起票 | 内容                                                                     | 一致数                                                              |
| ---- | ------------------------------------------------------------------------ | ------------------------------------------------------------------- |
| #85  | 承認に必要な判断材料が画面外にあるまま、承認ボタンだけが常に見えている   | 判断材料の切れ 4/5、アクションバー見切れ 3/5、DAGパネルの縦占有 5/5 |
| #86  | 失敗が要約件数から漏れ、下流の「待ち」が恒久停止を隠す                   | 要約から漏れる 3/5、待ちが恒久停止を隠す 1/5                        |
| #87  | テスト設定の回答欄が生の正規化座標だけで、切り出しの正しさを確認できない | 4/5                                                                 |
| #88  | 無効な操作に理由が無く、ホーム以外に戻る導線が無い                       | 無効ボタン 4/5、戻る導線 3/5                                        |

内訳（`finding id (severity)`）:

- **#85 判断材料の切れ 4/5** — `claude` score-panel-cut-off-by-action-bar (high) / `codex`
  narrow-review-evidence-hidden (high) / `gemini` narrow-view-layout-break (high) / `grok`
  review-narrow-hides-scoring (high)
- **#85 アクションバー見切れ 3/5** — `codex` narrow-review-action-clipping (high) / `claude`
  undo-button-clipped-narrow (high) / `composer` review-narrow-footer-cramped (medium)
- **#85 DAGパネルの縦占有 5/5** — `claude` dag-panel-fixed-height-mostly-empty (high) /
  `grok` review-narrow-hides-scoring (high) / `codex` graph-dominates-review (medium) /
  `gemini` graph-vertical-space (medium) / `composer` review-flowchart-vertical-cost (medium)
- **#86 失敗が要約から漏れる 3/5** — `claude` failure-absent-from-summary-counts (high) /
  `codex` ambiguous-completion-count (medium) / `grok` progress-counts-omit-attention (medium)
- **#86 待ちが恒久停止を隠す 1/5** — `claude` waiting-label-hides-permanent-block (medium)
- **#87 生の正規化座標 4/5** — `claude` answer-region-shown-as-raw-coordinates (high) /
  `codex` settings-technical-content-priority (medium) / `grok` settings-locked-coordinates
  (medium) / `composer` test-settings-coordinate-noise (medium)
- **#88 無効ボタンに理由がない 4/5** — `codex` disabled-actions-without-explanation (medium) /
  `claude` disabled-primary-without-reason (medium) / `composer`
  test-settings-disabled-without-reason (medium) / `grok` placeholder-as-only-label (low)
- **#88 戻る導線がない 3/5** — `claude` no-visible-focus-and-no-back (medium) / `grok`
  no-return-path (medium) / `composer` secondary-screens-no-nav (medium)

`grok` の review-narrow-hides-scoring と `claude` の no-visible-focus-and-no-back は、
1件で2つのことを観察しているので2か所に現れる。**同じ id を2つのテーマで数えている**
ことを隠さずに書いておく。

#85 は、別々に見えた3つの指摘（標準幅での切れ・狭幅での上下分離・アクションバーの
見切れ・DAGパネルの縦占有）を1本にまとめたものである。**すべて「縦の配分」という
同じ問題の別の面**だからである。個別に直すと、片方を直したぶんもう片方が悪くなる。

`claude` の指摘を採用の決め手にした。

> 承認ボタンだけが常時見えているため、スクロールせずEnterを押すのが最短ルートになり、
> 何十件も流す作業では実際にそうなる。human-in-the-loop の前提が崩れる。

### 4.3 対立した指摘 → 起票しない（実測してから判断する）

**ダークテーマのコントラスト評価が割れた。**

| 評価者 (finding id)                                      | 判断                                                                                                     |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `composer`（`what_works_well` の記述。finding ではない） | ダークでも主要テキストとアクション色のコントラストが保たれ、長時間の暗所作業でも負担が少なそう（好評価） |
| `claude` dark-primary-button-contrast (medium)           | ダークの主要ボタンは明るい水色背景に白に近い文字で、二次ボタンの方が読みやすい                           |
| `codex` dark-review-brightness-imbalance (medium)        | 白いPDF面とほぼ黒の判断パネルが隣接し、明暗差が大きい（別の論点）                                        |

**判断:** `claude` の指摘は具体的で検証可能（主要ボタンの文字コントラスト比を測れば決着する）。
`composer` の好評価は全体印象で、ボタン単体には言及していない。したがって
**両者は両立する**。ただしまだ数値で測っていないので、今回は起票せず、実測してから判断する。
`app/test/app_theme_contrast_test.dart` が既にコントラスト比を検査しているので、
測る場所はそこである。

### 4.4 材料の限界により採用しない → 起票しない

**「フォーカス表示が見当たらない」は、この材料からは判断できない。**

**3/5**: `claude` no-visible-focus-and-no-back (medium) / `composer`
no-visible-focus-indicator (medium) / `grok` keyboard-absent-outside-review (medium)。
最初の版はこれを2件と書いていたが、`grok` の1件を数え落としていた（レビュー2回目）。

撮影時にフォーカスを持つ要素が無かっただけで、フォーカス表示が無いことの証拠にならない。
実際 Issue #64 でフォーカスリングを追加し、`app/test/dependency_dag_panel_test.dart` が
フォーカスの可視性を検査している。

`codex` 自身がこの限界を正しく述べていた。

> 静止画からは、実際のフォーカス表示、キーボードだけでの操作完結性、
> アニメーションの有無までは判断できません。

#### これは材料設計の不備である

評価観点に「**キーボード操作**」「**フォーカスの位置**」「**動きの量**」を挙げながら、
静止画ではその3つに答えられない材料を渡した。観点と材料が噛み合っていない。

- 「フォーカスが見えない」という指摘が3件出たのは、評価者の誤りではなく**こちらの設計ミス**である
- この3観点は「**評価できなかった**」として扱う。良かったとも悪かったとも言えない
- 必要なら、静止画ではなく**スクリーンキャスト**で別途評価する

同じ理由で、静止画では次も評価できない。

- 実行中ノードのアニメーション（そもそも撮れない。加えてサイドカーが起動と同時にキューを
  回すため、`running` の状態を固定して撮れない — [linux-desktop-development.md](./linux-desktop-development.md) §4.4）
- スクロールした先（テスト設定画面の「設問依存関係グラフ」セクションの中身は写っていない）
- 答案取込画面でテストを選んだ後の状態（クリックできない）

### 4.5 「楽しさ」について → 起票せず、オーナーと方針を相談する

2/5 が指摘し、ともに low。

**2/5**: `composer` utilitarian-aesthetic (low)（実用一辺倒）/ `claude`
flat-affect-no-completion-feedback (low)（完了時の手応えが無い）

**件数と severity は低いが、軽い問題ではない。** これは
**プロジェクトオーナーが UI 改良を始めた動機そのもの**である
（「業務アプリとしてはシンプルでよいが、個人的に使っていて楽しくない」）。
評価者が静止画から「楽しさ」を判断しにくいため件数が少ないだけである。

UI改良4件を入れてなお、この軸が動いていない可能性がある。
**指摘を Issue 化するのではなく、方針をオーナーと決めるところからやり直す。**

### 4.6 起票しなかった残りの指摘（52件の行き先を全部書く）

上の §4.1〜§4.5 に現れない11件。**採否の判断は変えていない**が、どこへ行ったかを
書かずに落とすと、52件という数字だけが残って中身を追えなくなる。

| 内容                                           | 一致 | finding id                                                                                      |
| ---------------------------------------------- | ---- | ----------------------------------------------------------------------------------------------- |
| 開いた直後の選択が問1で、要確認の設問ではない  | 2/5  | `grok` review-opens-wrong-question (high) / `gemini` auto-focus-on-error (medium)               |
| テスト一覧が薄い（件数・進捗・更新日時が無い） | 2/5  | `claude` test-list-lacks-work-state (medium) / `grok` test-list-weaker-than-home (medium)       |
| フォーム画面の空白が大きい                     | 2/5  | `claude` form-screens-waste-layout (low) / `composer` form-screens-wide-empty-space (low)       |
| ホームの「レビューを続ける」が2か所にある      | 2/5  | `claude` duplicate-continue-cta-on-home (low) / `composer` home-duplicate-continue-review (low) |
| レビュー画面に進捗（何枚中何枚目か）が無い     | 1/5  | `claude` no-progress-context-in-review (medium)                                                 |
| 「確認済み」バッジが無効ボタンと見分けにくい   | 1/5  | `composer` confirmed-badge-low-salience (low)                                                   |
| 確認済みなのに「再実行」がプライマリ強調のまま | 1/5  | `gemini` primary-button-after-confirmation (low)                                                |

**「開いた直後の選択」だけは 2/5 で high を含む。** ホームの「要確認から開きます」を押して
来たのに、開くのは問1である、という指摘である。#84 の状態表示と同じ画面の話なので、
#84 を直すときに一緒に見ることになる。ここで別 Issue にしないのは、直し方が #84 の
結論（設問の状態をどこがどう出すか）に依存するためで、**却下したわけではない**。

残りは低い重みの単独指摘で、今回は起票していない。

## 5. 全員が独立に評価した点（維持すべきもの）

UI改良フェーズの狙いが伝わっていることの確認になる。壊さないための記録である。

- **色だけに依存しない状態表示**（5/5 が言及）— DAGカードがアイコン＋枠線＋日本語ラベルの
  三重表現。「モノクロでも読み分けられる」（`claude`）。Issue #25・#64 の狙いどおり
- **ショートカットの併記**（5/5 が言及）— 「覚える前から使えて、覚えたら速い」（`claude`）
- **ホーム最上段の「次の一手」**（5/5 が言及）— 「起動直後に次の一手が1つに絞られている」。
  Issue #68 の「数字を並べるだけのダッシュボードにしない」が効いている
- **ライト/ダークでレイアウト構造が完全に一致**（`claude`）— Issue #67 のトークン整備の成果

## 6. 再現方法

### 6.1 材料を撮る

```bash
# 1. デモデータを app-data へ書く（アプリを終了させてから）
uv run --project backend python scripts/seed-demo-app-data.py

# 2. 7画面 × ライト/ダーク × 標準幅/狭幅
./scripts/screenshot-linux-app.sh -r <route> -t <light|dark> -w <1280x720|700x720> -o <出力先>
```

route と画面の対応、撮れないもの、注意点は
[linux-desktop-development.md](./linux-desktop-development.md) §4.4 にある。
出力先は**リポジトリの外**にすること。

### 6.2 評価を回す

1. 全員に**同一のプロンプトと同一の画像**を渡す。プロンプトには
   「アプリが何をするものか」「誰がどう使うか」「7観点」「JSON 出力形式」
   「評価対象外（DEBUGリボン・ダミーPDFの中身・OSのタイトルバー）」を含める
2. **互いの評価を見せない。** 独立性がこの手法の全部である
3. 視覚を持つかどうかを probe で先に確かめる（§1.1）
4. 出力 JSON を集め、**重複・対立・単独**に分類する。複数が独立に同じことを言った指摘は
   優先度が高い
5. 採否を決め、**この文書に理由ごと記録する**

### 6.3 やってはいけないこと

- **指摘をそのまま実装しない。** UI は好みの幅が大きい。集約と取捨選択を経ること
- **評価者の文章をそのまま Issue に貼らない。** 何が問題かを自分の言葉で書き、
  評価者の指摘は根拠として引用する
- **材料で答えられない観点を評価させない。** 答えは返ってくるが、根拠が無い（§4.4）
