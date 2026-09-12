# エージェント・オーケストレーション運用ガイド

複数のAIエージェントを並列で動かして開発するときの、役割・単位・完了判定の決め方。
共通規約の正本は [`AGENTS.md`](../AGENTS.md)、タスクエントリーポイントは
[`package.json`](../package.json) の `scripts`、CIは
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml)。

基本方針は次の1行に尽きる。

> **Issue間の並列化は Orca Orchestration が持ち、Issue内部の分担だけをエージェント側の
> チーム機能に委ねる。完了の真実は会話ではなく Orchestration state にある。**

## 0. 最初に自分の役割を決める

読み進める前に、いま自分がどれなのかを確定させる。役割を取り違えると、他人の担当を
横取りするか、誰も進めない状態で待ち続けることになる。

| いまの状況                                                          | 役割             | 読むもの                                            |
| ------------------------------------------------------------------- | ---------------- | --------------------------------------------------- |
| プロンプトに Task ID / Dispatch ID を含む preamble が注入されている | Worker           | 注入された preamble が正本。本書 §4                 |
| 人間から「複数Issueを並列で進めて」「監督して」と頼まれた           | Commander        | 本書 §3。まず §2 でskillを読む                      |
| 人間から1つのIssueを直接頼まれた（preamble無し、監督の依頼も無し）  | 単独エージェント | 本書 §4.4。RunもTaskも作らない                      |
| 「別のエージェントに渡して」とだけ頼まれた（監督は不要）            | 受け渡し         | `orca-cli` を使う。Run / Task / Dispatch を作らない |

単独エージェントが勝手に Run を作って自分を監督しない。監督を頼まれていないのに
lifecycle メッセージ（`worker_done` など）を送らない。

## 1. 単位と責務

```text
1 GitHub Issue = 1 Orca Task = 1 有効な Dispatch = 1 worktree = 1 branch = 1 PR
```

Dispatch は「その Task を誰かに実行させた1回の試行」。失敗して retry すれば Task は
同じまま Dispatch が変わる。**古い Dispatch から遅れて届いた完了報告で、新しい試行を
完了扱いにしない**ため、報告には常に Task ID と Dispatch ID の両方を載せる。

| 層                              | 責務                                                              | 正本                                           |
| ------------------------------- | ----------------------------------------------------------------- | ---------------------------------------------- |
| Commander                       | Issue の分類・依存・衝突予測、Agent選択、dispatch、受信、完了検証 | Orca Orchestration state                       |
| Orca Task / Dispatch            | 誰が何を持っていて、どの試行が有効かの永続記録                    | `orca orchestration task-list` / `worker-list` |
| Worker                          | 1 Issue の実装と、その検証結果の報告                              | 注入された preamble                            |
| Issue内の分担（Agent Teams 等） | 1つの大きな Issue の中の分割                                      | 本書 §5                                        |
| 共通規約                        | 依存方向、security、Git/GitHub、完了条件                          | [`AGENTS.md`](../AGENTS.md)                    |
| GitHub                          | Issue / PR / CI / 最終成果物                                      | GitHub                                         |

Commander は「一番コードを書くエージェント」ではない。Commander が実装を横取りすると、
Task の ownership と、diff を見る第三者がいなくなる。

## 2. コマンドを記憶で作らない

Orca の CLI flag はアプリ更新で変わる。**Orchestration state を変更する操作の前に、
その環境にインストールされている skill を読む。**

```bash
orca skills get orchestration --full                                  # 全文
orca skills get orchestration --references                            # 参照文書の一覧
orca skills get orchestration --reference references/recovery-and-cleanup.md
```

本書はリポジトリ固有の方針だけを決める。コマンド・flag・lifecycle の正本は上の skill。
両者が食い違ったら skill が勝ち、本書を同じPRで直す。

`orca status --json` が `runtime.state: ready` を返すことを最初に確認する。
Orchestration がまだ有効でない環境では、Orca の Settings → Experimental で有効化する。

## 3. Commander の手順

### 3.1 Issue を読む

`gh` は使わない（`AGENTS.md` «GitHub App authentication»）。Issue も PR も GitHub App
経由で読む。

```powershell
./scripts/invoke-github-app-api.ps1 -Method Get `
  -Endpoint "/repos/<owner>/<repo>/issues?state=open&per_page=100"
```

Issue 本文の受入条件と、それが指す `docs/` の文書までを Commander が読む。ここを読まずに
spec を書くと、Worker は Issue に無い前提を自分で発明する。

### 3.2 Issue を3つに分類する

| 分類           | 意味                                       | 扱い                                                    |
| -------------- | ------------------------------------------ | ------------------------------------------------------- |
| Independent    | 依存も、触るファイルの重なりも無い         | 同時に起動する                                          |
| Dependent      | 先行 Issue の成果物が無いと着手できない    | `--deps` で順序を持たせる                               |
| Conflict-prone | 依存は無いが同じファイルを大きく書き換える | 直列化 / ownership 再分割 / 共通部を先行Issueへ切り出し |

依存は**本物の順序があるときだけ**入れる。3〜4段より深い鎖を作るくらいなら、並列の波を
複数回に分けたほうが速い。

### 3.3 このリポジトリで実際に衝突するもの

並列化の前にここを見る。ここを外すと、並列で得た時間を conflict の解決で失う。

| 対象                                                                   | 衝突する理由                                                                                                                                                            | 対処                                                |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| OpenAPI schema（`backend/` の API 層）                                 | `app/packages/auto_scoring_api/` の生成物が同じファイル群へ落ちる。`openapi:generate` は `dart run build_runner build` を呼び、このホストでは**同時に走らせると詰まる** | schema を変える Issue は直列化。生成は同時に1つだけ |
| `docs/simplified-design-specification.md` / `docs/technology-stack.md` | 全Issueが同じ正本を更新する                                                                                                                                             | 章単位で ownership を切るか直列化                   |
| `docs/mvp-acceptance.md`                                               | 実装項目↔テストの対応表に全Issueが行を足す                                                                                                                              | 同上                                                |
| `app/lib/core/` の共有 widget・design token                            | 複数機能から参照される                                                                                                                                                  | 共通変更を先行 Issue として切り出す                 |
| `.agents/skills/`                                                      | `pnpm run skills:sync` が `.claude/skills/` を再生成する                                                                                                                | skill を触る Issue は同時に1つだけ                  |
| `pnpm-lock.yaml` / `backend/uv.lock`                                   | 依存追加が重なると解決不能な差分になる                                                                                                                                  | 依存を足す Issue は直列化                           |

同時に走る Worker が同じ重いgateを一斉に回すと、リソース競合で**本来の欠陥と無関係な赤**
が出る。並列実行中に落ちたテストは、単独で再実行して切り分けてから原因を判断する。

**「いま実際にどこが衝突しているか」はリポジトリ内の `pnpm run inflight` が返す**
（全 worktree の変更ファイル、open PR、`origin/main` からの遅れ、同じファイルを触る
worktree / PR の衝突）。上の表が「衝突しやすい対象の一覧」なのに対し、これは「いま衝突して
いる場所の実測」で、Commander も各 Worker も自分で叩ける。dispatch 前に両方を見る。

### 3.4 Task spec に必ず書くこと

spec は単体で読んで完結していなければならない。Worker は Commander の会話履歴を見られない。

| 項目        | 内容                                                                       |
| ----------- | -------------------------------------------------------------------------- |
| Target      | 対象の Issue 番号、ファイル・レイヤー・画面                                |
| Change      | 出すべき具体的な結果                                                       |
| Constraints | 守る不変条件、触ってはいけない範囲、参照すべき `docs/` の文書              |
| Ownership   | この Worker が編集してよい範囲と、他 Worker との境界                       |
| Acceptance  | 完了を証明する観測可能なもの（どのテストが緑になるか、どの出力が変わるか） |

このリポジトリでは、spec に次を必ず含める。

- `AGENTS.md` と、その Issue に対応する `docs/` の文書を読むこと
- 実装後に `.agents/skills/review-ready/SKILL.md` に従い、push → PR作成 → Change Summary
  まで行うこと。**PR は Worker が作る**（`change-explainer` は PR を作らない）
- PR本文に `Closes #<Issue番号>`（Sub-issue なら親Issueも参照）
- **マージはしないこと**

### 3.5 Worker を起動する

このリポジトリでは **Issue ごとに独立した worktree を作る**。Orca の既定は「新しい Worker
＝新しいターミナル、worktree は共有」だが、ここでは Issue ごとに別 branch を持つため共有
できない。

```bash
orca orchestration run-create --objective "<何を並列に片付けるか>" --json
orca orchestration worker-start \
  --spec "<§3.4 の spec>" \
  --task-title "Issue #<n> <要約>" \
  --worktree new-top-level --name issue-<n>-<slug> --base-branch origin/main \
  --setup run --agent claude --json
```

`--setup run` により `orca.yaml` の setup hook（`scripts/bootstrap-worktree.ps1`）が走り、
依存導入・`.githooks/` 有効化・GitHub App 帰属が新しい worktree に適用される。新しい
worktree では `run` が既定だが、明示しておく。飛ばすと Worker は依存も hook も帰属設定も
無い状態で始まり、検証とコミットの両方で詰まる。

依存のある Task は先に `task-create --deps` で作り、`task-list --ready` を外部メモリとして
使う。全 independent Task を**待つ前に**起動する。

エージェントとモデルの選び方:

| 仕事                                                                  | 既定                                                                                           |
| --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| 調査・設計・実機での動作確認（GUI操作やスクリーンショット判断を含む） | Claude Opus                                                                                    |
| 原因が特定済みの修正、テスト追加、機械的なリファクタ                  | Claude Sonnet または Codex                                                                     |
| 独立レビュー                                                          | 実装者と別系統のモデル（例: Claude 実装 → Codex レビュー）                                     |
| UI/UX 評価                                                            | 実装者以外の複数モデル（[ui-ux-multi-agent-evaluation.md](./ui-ux-multi-agent-evaluation.md)） |

枠を使い切りかけている provider を選ばない。**失敗して返るのではなく、CLI 自身のプロンプト
で止まる**（§8）。`--agent` に渡すのは Orca が知っている CLI の識別子（このホストでは
`claude` / `codex`）で、
表の「Claude Opus」のようなモデル名ではない。迷ったら Opus を選ぶ。`--model` は人間がモデルを指名したときだけ渡し、それ以外は利用者の
既定を継がせる。渡した場合は receipt の `launch.requested` と `launch.effective` を比べ、
要求しただけで「そのモデルで動いている」と書かない。

### 3.6 受信ループ

```text
check --wait で受け取る
      ↓
中身を処理する（質問へ返信 / worker_done を検証 / escalation を解決）
      ↓
結果を永続化する（Task 状態、次の dispatch、gate）
      ↓
そこで初めて ACK する
```

**処理より先に ACK しない。** ACK 済みの Delivery は再送されないため、処理中に落ちると
その報告は失われたのと同じになる。

タイムアウトや空の応答は「失敗」ではなく checkpoint。3回続けて空だったら、待つのをやめて
`worker-list --include-remote` で実際の状態を数える。**エージェントがidleになったことは、
完了ではない。** 停止を証明できたときだけ stop / abandon / retry へ進む
（`references/recovery-and-cleanup.md`）。

### 3.7 完了判定

`worker_done --outcome succeeded` は「Worker本人が終わったと申告した」に過ぎない。
Task を完了として扱う前に、Commander が次を確認する。

- 報告の Task ID / Dispatch ID が、いま有効な Dispatch のものである
- Issue の受入条件を満たしている
- 必要な gate が通っている（通せなかった gate は理由付きで報告されている）
- branch にその Issue 以外の変更が混ざっていない
- Critical / High のレビュー指摘が残っていない
- PR が作られ、`Closes #<n>` がある。CI 結果を確認したか、待ちであることが明示されている

有効な `worker_done` は Task と Dispatch を自動的に settle させる。その後に
`task-update --status completed` を追加で撃たない。

レビューだけを頼んだ Worker の `worker_done` は、指摘の集約を許すだけで、Commander が
自分でファイルを直す許可にはならない。修正は dispatch し直すか、担当を明示的に決める。

### 3.8 後片付け

settle した Worker には必ず次のどれか1つを、ACK の前に決める。

1. 同じターミナルを次の Dispatch で再利用する
2. `worker-retain`（人間がデバッグのために残すと言ったとき）
3. `worker-release`

出力を見たいという理由でターミナルを生かしたままにしない。release 後も `worker-read` で
読める。`worker-list --terminal-state reclaimable` が空になるまで Commander のターンを
終えない。

**`worker-release` はターミナルの生死を決めるだけで、worktree・branch は消さない。** PR が
マージされた Issue の worktree は、その時点で残す理由が無い。定期的に（2026-09-10 に実施した
ような棚卸しのタイミングでよい）次を確認する:

1. `orca worktree list` と、GitHub で closed/merged になった Issue 番号を突き合わせる。
2. 突き合わせが取れた worktree だけ `orca worktree rm --worktree "id:<repo-id>::<path>"` で
   消す。人間が明示的に残すと言った worktree（例: `megamouth`）と、稼働中の Dispatch が使って
   いる worktree は対象外。
3. 消す前に対象 worktree の `git status` を見る。**コミットされていない変更がある worktree は
   消さない**（`worker-abandon` 直後の未報告作業を捨てることになるため）。

## 4. Worker の手順

### 4.1 dispatch された場合

注入された preamble が正本。そのうえでこのリポジトリでは:

1. `AGENTS.md` と、spec が指す `docs/` の文書を読む。
2. 割り当てられた Task **だけ**をやる。範囲外を見つけたら別 Issue に切り出す。
3. 判断が必要で止まったら、ローカルの質問UIを開かず preamble の `ask` で Commander に聞く。
   Commander はローカルTUIを見られない。
4. 共有インターフェース（OpenAPI schema、`app/lib/core/`、`docs/` の正本）を変えるときは、
   他の Task に影響するため先に Commander へ知らせる。
5. 実装後に `.agents/skills/review-ready/SKILL.md` を実行する（可読性 → 検証 → Atomic Commit
   → push → **PR作成** → Change Summary）。PR が無ければ自分で作る。**マージはしない。**
6. `worker_done` を、その Dispatch につき**ちょうど1回**、成功でも失敗でも送る。3文程度の
   要約、Task ID、Dispatch ID、明示的な `--outcome` を必ず含める。失敗を文章だけで匂わせない。
7. 送ったら、そのターンを終えて待機する。次の指示を自分から取りに行かない。

### 4.2 着手前チェック（pre-flight）

作業を始める前に次を機械的に確認する。**古い base・既に他が進めている作業・既存 PR に
気づかないまま着手するのが、衝突の共通原因**（Issue #451 の 5 件）。ルールとして覚える
のではなく、この順番で手を動かせば自然に確認が終わる形にする。

1. **最新の `origin/main` を取り込む。** `git fetch origin main` の後、
   `git merge-base --is-ancestor origin/main HEAD` が偽なら遅れている。
   `git merge origin/main`（または rebase）で取り込む。**取り込む前に重い gate を回さない。**
   既に直っているフレーキーで赤くなり、自分の変更を疑う時間を失う（PR #440 の実例）。
2. **`pnpm run inflight` を実行する。** 全 worktree の変更ファイル・open PR・
   `origin/main` からの遅れ・**自分が触るファイルと他 worktree / open PR の衝突**が出る。
   衝突があれば着手せず、preamble の `ask` で Commander に範囲を確認する。
   この情報は以前 Commander の scratchpad にしか無く、ワーカーは見られなかった。
3. **対象 Issue の本文だけでなくコメントも読む。** 既に PR が出ている・範囲が訂正されている
   場合がある。`Closes #<n>` を持つ open PR を探し、**Issue 本文だけを見て「PR が無い」
   「0 コミット」と判断しない**（PR #434 / #427 の実例）。
4. **自分の worktree が一意か確認する。** `git worktree list` は全 worktree を返すので、
   同じ Issue の作業が別 worktree で進んでいないかを見る。

### 4.3 検証はどこまで通すか

`pnpm run check` が正本の gate。ただし **Linux では `build:app`（`flutter build windows`）
が構造的に通らない**（[orca-remote-environment.md](./orca-remote-environment.md) §8）。
Linux で作業する Worker は通せる gate をすべて通し、**通せなかった gate と理由を
`worker_done` に書く**。「全部通した」と書かない。Windows CI が最終的な正本。

`pnpm run check` は生成物（Dartクライアント）に差分を残すことがある。完了前に
`git status` を見て、意図しない生成物を持ち込んでいないか確かめる。

### 4.4 監督されていない単独作業の場合

§4.1 の 1・2・5、§4.2（着手前チェック）、§4.3（検証）を守る。`worker_done` は送らない
（受け取る相手がいない）。人間へ直接報告する。

## 5. Issue 内部の並列化

1つの Issue の中でさらに分担したいときだけ、エージェント側のチーム機能（Claude Code の
Agent Teams / subagent）を使う。

| 使う                                        | 使わない                                     |
| ------------------------------------------- | -------------------------------------------- |
| `app/` と `backend/` の両方に跨る大きな機能 | 1〜2ファイルの修正                           |
| 複数の仮説を同時に潰したい調査・デバッグ    | 逐次依存が強く、分けても待ち合わせになる作業 |
| 実装と、別視点のレビューを並行したい        | 全員が同じファイルを触る作業                 |
| 独立に測れる評価（UI/UX、性能）             | 調整コストが得られる並列度に見合わない作業   |

**チームのメンバーは同じ worktree を共有する。** Orca の Task 単位と違ってファイル分離が
無いので、担当を path で切る。

```text
メンバー A → backend/src/**
メンバー B → app/lib/features/**
メンバー C → tests / docs
```

## 6. レビュー

実装と承認は別の責務。まとまった変更には、**実装者と別系統のモデル**のレビューを入れる。
同じ推論傾向による見落としが減る。

- コードレビュー: 実装が Claude なら Codex に独立レビューさせる、など。
- UI/UX: 実装者以外の複数モデルに独立評価させ、一致した指摘だけを起票する。手順と
  過去の結果は [ui-ux-multi-agent-evaluation.md](./ui-ux-multi-agent-evaluation.md)。
- Critical / High の指摘は完了前に解消する。
- GitHub 上の承認レビューは不要。**マージの実行は Commander または人間の手順**。Worker は
  マージしない（§4.1）。
- **マージ判断の委譲（オーナー、2026-09-10）。** オーナーの発言（原文）:
  「特に問題がなさそうであればあなたの判断でマージしてください。許可します」。
  これ以降、Commander は PR ごとに人間へ確認を取らずに squash merge する
  （2026-09-10 にマージした 12 件がその最初の適用）。
- **委譲されたのはマージの「判断」であって、検証の省略ではない。** マージ前に確認する
  ことは委譲前と同じ、§3.7 の完了判定そのもの: 報告の Task ID / Dispatch ID が有効な
  Dispatch のものである／Issue の受入条件を満たしている／必要な gate が通っている／
  branch にその Issue 以外の変更が混ざっていない／Critical・High のレビュー指摘が残って
  いない／PR に `Closes #<n>` がある。**「必須 check が緑」は、この6項目の1つでしかない。**
  緑でも他の項目が崩れていれば、Commander は自分の判断で止める。赤・未完了・受入条件未達の
  PR は、委譲の前後にかかわらずマージしない。
- **委譲に含まれないもの**: force push、ブランチ削除以外の破壊的操作、本番設定の変更。
  これらは委譲前と同じく、実行前にオーナーへ確認する。

## 7. 初回構築

### 7.1 必要環境

- Git / Node.js（`.node-version`）/ Corepack・pnpm（`package.json` の `packageManager`）
- PowerShell 7（`pwsh`）— bootstrap と GitHub App 帰属スクリプトが使う
- Flutter SDK（`app/.fvmrc`）、[uv](https://docs.astral.sh/uv/)（`backend/.python-version`）
- `pnpm run openapi:check` は追加で Java（openapi-generator）を要求する
- Orca（隔離worktreeと Orchestration。素の branch 運用でも `pnpm run bootstrap` は動く）
- （任意）専用GitHub AppのInstallationと、ローカルだけに置いた秘密鍵

```bash
pnpm install && pnpm run bootstrap
```

`pnpm run bootstrap` は依存を導入し、`.githooks/` を現在の worktree で有効化し、GitHub App
帰属が設定済みならそれも適用する。

### 7.2 GitHub リポジトリ設定

個人開発でも main へ直接 push せず、変更の根拠と CI 結果を PR に残す。

- merge方式: squash merge のみ / merge後 branch 自動削除: 有効
- main ruleset: branch削除禁止、force-push禁止、PR必須、会話解決必須。承認レビューは不要
- required checks: `Quality`（`.github/workflows/ci.yml` の job 名。必須はこの1つ）

check名を変えるときは workflow、ruleset、[quality-gates.md](./quality-gates.md) を同じPRで
更新する。

### 7.3 Orca リポジトリ設定

Settings → Repository で対象リポジトリを選ぶ。

| 設定             | 値                                                     |
| ---------------- | ------------------------------------------------------ |
| Base ref         | `origin/main`                                          |
| Setup hook       | `pwsh -NoProfile -File scripts/bootstrap-worktree.ps1` |
| Setup run policy | デフォルトで実行                                       |
| Agent startup    | setup完了まで待つ                                      |

setup hook は `orca.yaml` に宣言済み。secret、token、個人環境の絶対パスを `orca.yaml` へ
書かない。Ubuntu ランタイムへ繋いで動かす構成は
[orca-remote-environment.md](./orca-remote-environment.md)。

### 7.4 権限とsecretの注意

Orca の agent 起動は、worktree が隔離されている前提で permission bypass 系の既定を持つ
構成がある。**worktree の隔離は、OS権限や認証情報をサンドボックスするものではない。**
worktree を捨てても、エージェントが外部に対して起こした副作用は消えない。

- APIキーは 1Password CLI 経由で取り、平文でファイルへ置かない。
- 実際の採点資料はリポジトリ外にあり、公開物・Issue・ログ・スクリーンショットへ出さない。
- 破壊的なデータ操作や本番設定変更の前に、範囲・バックアップ・影響範囲を人間に確認する。

## 8. 復旧

### worker_done が来ない

待ち続ける前に状態を数える。

```bash
orca orchestration worker-list --run <run_id> --include-remote --json
orca orchestration worker-show --dispatch <dispatch_id> --json
orca orchestration worker-read --dispatch <dispatch_id> --limit 50 --json
```

`live` / `unverifiable` / `exited` を取り違えない。接続が切れただけの `unverifiable` は
プロセスの死ではなく、stop・abandon・retry・release のどれも正当化しない。

作業は終わっていたのに報告されなかっただけ、という場合がある。**捨てる前に worktree の
`git status` と `git log` を見る。**

### 「live なのに進まない」— agent CLI 自身のプロンプトで止まる

**Orchestration の観測がすべて正常でも、Worker が止まっていることがある。** 実測した例:

```text
Approaching rate limits  Switch to <cheaper-model> for lower credit usage?
› 1. Switch   2. Keep current model   3. Keep current model (never show again)
```

このとき Orca 側は `liveness: live` / `activity: working` /
`attention.requiresAction: false` / `nextAction: none` を返す。**Orchestration から見た
Worker は健康そのもので、Commander は timeout まで待ち続ける。**

agent CLI 自身が出すプロンプト（レート制限の警告、モデル切替、初回の信頼確認、再ログイン）
は orchestration message にならない。だから待ち時間が想定を超えたら、projection を見るだけ
で終わらせず、**画面そのものを読む**。

```bash
orca orchestration worker-read --dispatch <dispatch_id> --source terminal --limit 30 --json
```

止まっていたら、そのプロンプトに答えるか、下の手順で別 agent へ retry する。

### 止まった Worker を retry する

実測した順序。`worker-stop` だけでは retry できないことがある。

```bash
# 1. 停止を試みる。既存ターミナルを再利用した Worker では
#    state=stop_unknown / processAction=none になり、Dispatch は settle しない
orca orchestration worker-stop --dispatch <dispatch_id> --json

# 2. settle していなければ retry は task_not_startable で断られる。
#    abandon は「プロセスを止めたとは主張せずに」orchestration 上を settle させる
orca orchestration worker-abandon --dispatch <dispatch_id> --json

# 3. retry は新しい Dispatch として起こす。配置は継承されないので明示する
orca orchestration worker-start --task <task_id> --retry-of <dispatch_id> \
  --worktree "id:<repo-id>::<worktree-path>" --agent claude --json
```

`--retry-of` は**そのTaskの最新の settled Dispatch**を指す必要がある。abandon した
Dispatch は `outcome: failed` として残り、Task は次の試行へ進む。同じ Task が3回続けて
失敗すると circuit-break して Task 自体が failed になる。新しい Run を作って迂回しない。

abandon はプロセスもファイルも触らないので、worktree と terminal は残る。receipt の
`residualResources` に出るものを、あとで片付ける（`orca worktree rm --worktree "id:..."`）。

### Task が外部要因で進まない

「なんとなく止まっている」状態を作らず、理由を永続化する。

```bash
orca orchestration task-update --id <task_id> --status blocked --result '{"reason":"..."}' --json
```

### setup が失敗する

1. Node.js、`pwsh`、Git が PATH にあるか確認する。
2. `pnpm install` の失敗なら Node / pnpm の version と lockfile 差分を見る。lockfile を
   無断で更新しない。
3. GitHub App 帰属を使うなら [ai-agent-git-attribution.md](./ai-agent-git-attribution.md)
   の初回設定を既存 checkout で済ませてから `pnpm run bootstrap` を再実行する。
4. `git config --get core.hooksPath` が `.githooks` であることを確認する。

### hook または CI が失敗する

表示された最初の失敗コマンドを単独で再実行する。`--no-verify` は原因調査中の一時確認に
限定し、CI が緑になるまでマージしない。CI 環境だけで落ちる場合は Node / pnpm、環境変数、
OS差分を確認する。**検査自体を消して通さない。**

### reset は最終手段

`orca orchestration reset` は runtime 全体の orchestration state に効く。別の Commander が
動いている可能性があるので、人間の指示なしに実行しない。

## 9. やってはいけないこと

| アンチパターン                                       | なぜ壊れるか                                                         |
| ---------------------------------------------------- | -------------------------------------------------------------------- |
| ターミナルに「終わったら教えて」と送るだけで管理する | ownership も試行の記録も残らず、再開時に誰が何を持つか復元できない   |
| idle を完了とみなす                                  | 生成していないだけの状態と、成果物が受入条件を満たした状態は別物     |
| 状態を Commander の会話履歴だけに持つ                | context が切れた時点で全部消える。Task / Dispatch から復元可能にする |
| 処理より先に ACK する                                | 処理中に落ちるとその報告は失われる                                   |
| とにかく全部並列にする                               | conflict 解決・調整・token・レビューのコストが並列の利益を超える     |
| 小さな Issue までチーム分割する                      | 調整のオーバーヘッドだけが増える                                     |
| Worker 同士を自由に直接会話させる                    | 状態が追えなくなる。跨る情報は Commander が中継する                  |
| Commander が実装を横取りする                         | diff を見る第三者がいなくなり、Task の ownership も壊れる            |
