# Orcaを使ったマルチエージェント・オーケストレーション開発ガイド

> 更新日: 2026-09-10  
> 対象: OrcaでClaude Code / Codex / Cursor CLIなど複数のAIコーディングエージェントを並列運用する開発者  
> 方針: **Issue間はOrcaで並列化し、必要なIssueだけClaude Code Agent TeamsでIssue内部を並列化する**

---

## 目次

1. [この資料の目的](#1-この資料の目的)
2. [結論: 推奨アーキテクチャ](#2-結論-推奨アーキテクチャ)
3. [Orca Orchestrationの基本モデル](#3-orca-orchestrationの基本モデル)
4. [Worktree設計](#4-worktree設計)
5. [Commander Agentの責務](#5-commander-agentの責務)
6. [Issueの分解と依存関係](#6-issueの分解と依存関係)
7. [Workerの起動](#7-workerの起動)
8. [エージェント間通信](#8-エージェント間通信)
9. [通知欠落に強い設計](#9-通知欠落に強い設計)
10. [Worker Contract](#10-worker-contract)
11. [レビューと完了判定](#11-レビューと完了判定)
12. [Claude Code Agent Teamsとの併用](#12-claude-code-agent-teamsとの併用)
13. [Claude / Codex / Cursor CLIの使い分け](#13-claude--codex--cursor-cliの使い分け)
14. [推奨実行フロー](#14-推奨実行フロー)
15. [Commander Agentプロンプト例](#15-commander-agentプロンプト例)
16. [Worker Agentプロンプト例](#16-worker-agentプロンプト例)
17. [障害・復旧設計](#17-障害復旧設計)
18. [アンチパターン](#18-アンチパターン)
19. [導入チェックリスト](#19-導入チェックリスト)
20. [参考資料](#20-参考資料)

---

# 1. この資料の目的

OrcaではClaude Code、Codex、Cursor CLI、OpenCodeなど複数のCLIエージェントを、独立したGit worktree上で並列に動かせる。

ただし、単純に

```text
Commander
├── Agent A
├── Agent B
└── Agent C
```

という構成にして、各Agentに

```text
「終わったらCommanderに知らせて」
```

と指示するだけでは、以下の問題が起こりやすい。

- 完了通知をCommanderが取得できない
- Agentが終了したのか、待機しているのか分からない
- Workerがクラッシュすると永久に待つ
- 同じIssueを二重実行する
- 古いWorkerからの通知で新しいRetryを誤って完了扱いする
- Issue間の依存関係が曖昧になる
- Commanderのcontextだけに状態が存在し、再開時に復元できない
- UI上の「done」と、開発タスクとしての「completed」を混同する

この資料では、これを

> **LLM同士の会話ではなく、Orcaの永続的なOrchestration stateをSingle Source of Truthにする**

ことで解決する。

---

# 2. 結論: 推奨アーキテクチャ

基本構成は次の通り。

```text
                         Developer
                             │
                             ▼
                    ┌────────────────┐
                    │ Commander Agent│
                    │  Coordinator   │
                    └───────┬────────┘
                            │
                    Orca Orchestration
                            │
             ┌──────────────┼──────────────┐
             │              │              │
          Task #101      Task #102      Task #103
             │              │              │
          Dispatch       Dispatch       Dispatch
             │              │              │
      Worktree #101  Worktree #102  Worktree #103
             │              │              │
         Claude          Codex        Cursor CLI
```

原則:

```text
1 GitHub Issue
    =
1 Orca Task
    =
1 Worktree
    =
1 Branch
    =
1 primary Worker
```

大きなIssueだけ、Claude Code Agent TeamsをIssue内部で利用する。

```text
Orca Commander
│
├── Issue #101
│    └── Claude Code Team Lead
│         ├── Implementer
│         ├── Tester
│         └── Reviewer
│
├── Issue #102
│    └── Codex
│
└── Issue #103
     └── Cursor CLI
```

重要なのは責任範囲を分けることである。

| 層 | 担当 |
|---|---|
| Orca Commander | Issue間の依存関係、Agent選択、Worktree、進捗、失敗復旧 |
| Orca Task / Dispatch | 実行状態の永続管理 |
| Worker | 1 Issueの実装 |
| Claude Agent Teams | 1つの大きなIssue内部の協調 |
| GitHub | Issue / PR / CI / 最終成果物 |

---

# 3. Orca Orchestrationの基本モデル

Orca Orchestrationは以下の要素で構成される。

```text
Run
 ├── Task
 │    └── Dispatch
 │          └── Worker
 │
 ├── Task
 │    └── Dispatch
 │          └── Worker
 │
 ├── Messages
 └── Decision Gates
```

## 3.1 Run

Runはオーケストレーション全体のnamespaceであり、Coordinator Inboxのホームになる。

例:

```text
Run: "Open GitHub Issuesを処理する"
```

Run自身がWorkerをスケジューリングするわけではない。

---

## 3.2 Task

Taskは実際の作業単位。

代表的な状態:

```text
pending
ready
dispatched
completed
failed
blocked
```

GitHub Issue単位でTaskを作る構成が扱いやすい。

```text
Issue #101 → Task #101
Issue #102 → Task #102
Issue #103 → Task #103
```

Taskには依存関係を持たせられるため、DAGとして管理できる。

---

## 3.3 Dispatch

Dispatchは

> **特定のTaskを、特定のWorkerに実行させた1回の試行**

を表す。

この区別は非常に重要。

```text
Task #101
│
├── Dispatch A  ← failed
│
└── Dispatch B  ← retry / succeeded
```

`taskId`だけではなく`dispatchId`も通信に含めることで、古いWorkerから遅れて届いた通知が新しいRetryを誤完了させることを防げる。

---

## 3.4 Worker

実際にコードを書くCLI Agent。

例:

- Claude Code
- Codex
- Cursor CLI
- OpenCode
- Gemini
- Antigravity

OrcaはCLIエージェントをworktreeの作業ディレクトリで起動する。

---

## 3.5 Message

CoordinatorとWorker間の通信。

代表例:

```text
worker_done
question
escalation
heartbeat
status
dispatch
```

「Agentがterminal上でidleになった」ことと、`worker_done`は別物として扱う。

---

## 3.6 Decision Gate

Commanderが判断を必要とする場面を明示的に停止できる。

例:

```text
DB migrationを含めてよいか？
        │
     ┌──┴──┐
    YES    NO
```

Gateを解決するまで関連Taskを進めない、といった制御に使える。

---

# 4. Worktree設計

Orcaはworktree-nativeであり、各タスクを独立したGit worktreeで扱う。

```text
origin/main
│
├── issue/101-auth
├── issue/102-settings
├── issue/103-responsive
└── issue/104-docs
```

各worktreeには独立して以下が存在する。

- branch
- files
- agent terminals
- editor state
- browser state

## 推奨ルール

### Rule 1: 1 Issue = 1 Worktree

独立Issueを同じworktreeで処理しない。

### Rule 2: 原則同じbase refから開始

独立Issue:

```text
origin/main
├── #101
├── #102
└── #103
```

### Rule 3: 依存Issueは並列化しないか、親子関係を明示

```text
#101 API schema変更
   ↓
#102 Frontend対応
```

この場合は無理に完全並列化しない。

### Rule 4: Agent Teams内部でも同一ファイル競合を避ける

Claude Code Agent Teams自体はteammateごとにGit worktreeを自動分離する方式ではない。

したがって同じIssue内でも、

```text
Agent A → src/api/**
Agent B → src/components/**
Agent C → tests/**
```

のようなownershipを決める。

---

# 5. Commander Agentの責務

Commanderは「一番コードを書くAgent」ではない。

主な責務は以下。

```text
GitHub Issuesを読む
        ↓
Issueを分類
        ↓
依存関係を解析
        ↓
Task作成
        ↓
適切なAgentを選択
        ↓
Workerをdispatch
        ↓
Inboxを監視
        ↓
質問 / escalation処理
        ↓
完了結果を検証
        ↓
必要ならReview Workerを起動
        ↓
PR / 完了条件を確認
        ↓
Task completed
```

## Commanderが原則やらないこと

- 大規模な実装
- Workerの仕事の横取り
- 同じIssueを別Workerへ無断で二重dispatch
- terminalの表示だけを見て完了判定
- `worker_done`を受けただけで無条件にTaskをcompletedにする
- Workerからの自然言語だけを唯一の状態ソースにする

---

# 6. Issueの分解と依存関係

Issueを次の3種類に分類する。

## 6.1 Independent

例:

```text
#101 Login buttonの表示崩れ
#102 README修正
#103 Settings pageレスポンシブ対応
```

並列実行可能。

---

## 6.2 Dependent

例:

```text
#201 User schemaを変更
#202 新schemaを使用するAPIを追加
#203 新APIを使用するUIを追加
```

```text
#201
 ↓
#202
 ↓
#203
```

DAGとして扱う。

---

## 6.3 Conflict-prone

明示的な依存関係はなくても、同じファイル群を大きく変更するIssue。

```text
#301 Header全面リファクタ
#302 Navigation構造変更
```

両方が

```text
components/Header.tsx
components/Navigation.tsx
```

を変更するなら、並列実行によるmerge conflictのコストが高い。

この場合は:

1. 直列化する
2. ownershipを再分割する
3. 共通変更を先行Issueとして切り出す

のいずれかを選ぶ。

---

# 7. Workerの起動

## 7.1 まずOrca runtimeを確認

```bash
orca status --json
```

Orchestrationは実行中のOrca runtimeと通信する。

また、OrchestrationはExperimental機能なので、利用バージョンではSettings → Experimentalから有効化する。

---

## 7.2 Skillを導入

Orca公式は`orchestration` skillを提供している。

```bash
npx skills add https://github.com/stablyai/orca --skill orchestration --global
```

CLIからの導入例:

```bash
orca skills install --skill orchestration
```

Agentに実際のコマンドを操作させる前に、現在インストールされているOrcaに一致するguideを読み込ませる。

```bash
orca skills get orchestration --full
```

**CLI flagsは更新され得るため、Agentに記憶だけでコマンドを生成させない。**

---

## 7.3 Runを作る

```bash
orca orchestration run-create \
  --objective "Open GitHub Issuesを依存関係を考慮して並列実装する" \
  --json
```

---

## 7.4 Taskを作る

```bash
orca orchestration task-create \
  --task-title "Issue #101 - Login bug" \
  --spec "Issue #101を調査・修正し、必要なテストを追加して完了条件を満たす" \
  --json
```

---

## 7.5 Workerを起動

新しい子worktreeを作る例:

```bash
orca orchestration worker-start \
  --task <taskId> \
  --worktree new-child \
  --name issue-101-login \
  --agent codex \
  --setup run \
  --json
```

現在のworktreeで動かす場合:

```bash
orca orchestration worker-start \
  --task <taskId> \
  --worktree current \
  --agent claude \
  --json
```

Claude / Codex / Cursorでは、対応しているモデルに対して起動時model / effort overrideを指定できるバージョンもある。

```bash
orca orchestration worker-start \
  --task <taskId> \
  --worktree current \
  --agent claude \
  --model <model-id> \
  --effort high \
  --json
```

実際のmodel IDは固定値を資料にハードコードせず、現在の環境で確認する。

---

# 8. エージェント間通信

Orca Commander方式では、Agent Teamsのような完全mesh通信を再現することを目標にしない。

推奨はhub-and-spoke。

```text
               Commander
             /     |      \
          Claude  Codex  Cursor
```

## 8.1 Worker → Commander

完了:

```text
worker_done
```

質問:

```text
question
```

問題:

```text
escalation
```

生存確認:

```text
heartbeat
```

---

## 8.2 Commander → Worker

dispatch宛に追加指示を送れる。

```bash
orca orchestration send \
  --to dispatch:<dispatchId> \
  --subject "Follow-up" \
  --body "API contractが更新されたため、新しい型定義を確認してください。" \
  --json
```

---

## 8.3 Workerから質問する

blocking questionはローカルTUI上で人間入力を待つのではなく、Orchestration経由にする。

```bash
orca orchestration ask \
  --to <coordinatorHandle> \
  --question "Shared componentを変更してよいですか？" \
  --options "shared,page-only" \
  --timeout-ms 600000 \
  --json
```

これによりCommanderが質問を一元管理できる。

---

# 9. 通知欠落に強い設計

この資料で最も重要な部分。

## 9.1 「UI通知」と「Orchestration Message」を区別する

OrcaにはAgent status hooksがあり、

```text
working
waiting
done
```

をUIに表示できる。

これは便利だが、**業務上の完了プロトコルとしては使用しない。**

UI state:

```text
terminalがidleになった
```

Task completion:

```text
worker_doneを受信
+ outcome確認
+ validation通過
```

は意味が違う。

---

## 9.2 CommanderはInboxをpoll / waitする

基本:

```bash
orca orchestration check \
  --wait \
  --types worker_done,escalation,question \
  --timeout-ms 900000 \
  --json
```

Deliveryを処理したらACKする。

```bash
orca orchestration check \
  --ack <deliveryId> \
  --wait \
  --types worker_done,escalation,question \
  --timeout-ms 900000 \
  --json
```

Orcaのdefault `check`は、bound Runにおけるoldest unacked DeliveryをFIFOで扱う。

### 原則

```text
receive
  ↓
validate
  ↓
process
  ↓
persist resulting state
  ↓
ACK
```

**処理前にACKしない。**

---

## 9.3 ACKが重要な理由

悪い構成:

```text
Worker
 ↓
notification
 ↓
Commanderが別処理中
 ↓
見逃す
 ↓
永久待機
```

推奨構成:

```text
Worker
 ↓
Orca Inbox
 ↓
unacked Deliveryとして保持
 ↓
Commander取得
 ↓
処理
 ↓
ACK
```

これにより「一瞬の通知」を状態同期の根幹にしなくて済む。

---

# 10. Worker Contract

OrcaでdispatchされたWorkerには、通信方法のpreambleが注入される。

Commander側でも以下を運用ルールとして明文化する。

## 必須ルール

### 1. `worker_done`は必ず1回送る

成功時だけでなく失敗時も送る。

### 2. `taskId`と`dispatchId`を両方含める

Retryとの取り違え防止。

### 3. outcomeを明示

```text
succeeded
failed
```

### 4. 長時間処理ではheartbeatを送る

### 5. blocking questionは`orca orchestration ask`

### 6. 完了メッセージに短いsummaryを含める

最低限:

- 何をしたか
- 何を発見したか
- 何が残っているか
- 主な変更ファイル
- test結果

---

## worker_done例

```bash
orca orchestration send \
  --type worker_done \
  --subject "Issue #101 completed" \
  --body "Login redirect raceを修正し、回帰テストを追加。対象テストはpass。" \
  --task-id <taskId> \
  --dispatch-id <dispatchId> \
  --outcome succeeded \
  --files-modified "src/auth/login.ts,tests/auth/login.test.ts" \
  --json
```

---

# 11. レビューと完了判定

`worker_done --outcome succeeded`は

> Worker本人が「実装は終わった」と報告した

ことを意味する。

それだけでIssue completedにはしない方が安全。

## 推奨Quality Gate

```text
Worker Done
   ↓
Diff inspection
   ↓
Tests
   ↓
Independent Review
   ↓
Critical findings?
   │
 ┌─┴─┐
YES  NO
 │    │
Fix   PR Ready
 │
Re-review
```

## 完了条件の例

Taskをcompletedにする条件:

- acceptance criteriaを満たした
- lint / typecheck / testが必要範囲でpass
- 未解決のCritical / High review findingがない
- 不要な変更がない
- branchが期待したIssueだけを含む
- 必要ならPRを作成済み
- CI結果を確認済み、またはCI待ち状態を明示

---

# 12. Claude Code Agent Teamsとの併用

## 12.1 Agent Teamsが強い部分

Claude Code Agent Teamsには以下がある。

- Team Lead
- 独立contextを持つteammates
- shared task list
- task dependency
- direct teammate messaging
- mailbox
- automatic message delivery
- teammate idle notification
- plan approval
- task completion hooks

そのため、**1つの複雑なIssue内部で密な連携が必要**なら、Orca上の独立Workerを大量に生成するよりAgent Teamsが自然。

---

## 12.2 Orcaが強い部分

OrcaはClaudeだけでなく、

- Claude Code
- Codex
- Cursor CLI
- OpenCode
- Gemini
- Antigravity
- その他CLI Agent

を同じ開発環境で扱える。

さらにIssue単位をworktreeで安全に分離できる。

---

## 12.3 推奨境界

```text
             Orca Commander
                    │
       ┌────────────┼────────────┐
       │            │            │
    Issue A      Issue B      Issue C
       │            │            │
 Claude Team      Codex        Cursor
       │
  ┌────┼────┐
 Impl Test Review
```

### Orcaが管理

- Issue
- Issue dependency
- worktree
- branch
- primary model / Agent
- Dispatch
- completion tracking
- cross-Issue scheduling
- retry
- cross-provider coordination

### Claude Agent Teamsが管理

- 1 Issue内のsubtasks
- Claude teammates間のmessage
- shared task list
- intra-Issue review
- intra-Issue investigation

---

## 12.4 Agent Teamsを使う基準

使う:

- 大型Issue
- Frontend / Backend / Testに分けやすい
- 複数仮説を競わせるデバッグ
- 設計レビューと実装を並行したい
- teammates間で情報交換が必要

使わない:

- 1〜2ファイルの小修正
- 逐次依存が非常に強い
- 同じファイルを全員が触る
- 単純なREADME修正
- Agent Teamsのtoken overheadが見合わない

---

# 13. Claude / Codex / Cursor CLIの使い分け

以下はOrca公式のルールではなく、実運用向けの推奨例。

## Claude Code / Agent Teams

向いているもの:

- 大型機能
- repo全体を理解する必要がある変更
- 複数Agentの協議が有効
- architectureを含む変更
- 複雑なデバッグ

```text
Large / collaborative
        ↓
Claude Agent Teams
```

---

## Codex

向いているもの:

- 独立した実装Issue
- バグ修正
- リファクタ
- テスト追加
- Independent Review
- Claude実装に対する別モデルレビュー

```text
Claude implementation
        ↓
Codex independent review
```

異なるモデル系統をReviewerに使うことで、同じ推論傾向による見落としを減らせる。

---

## Cursor CLI

向いているものの例:

- Frontend中心
- UI調整
- React / Next.js周辺
- コンポーネント単位の変更

ただし、モデル選択はCursor自身の設定側で管理され、Orcaが通常のCursor設定を恒久的に上書きするわけではない。

---

# 14. 推奨実行フロー

## Phase 0: Discovery

```text
GitHub Issues取得
      ↓
Open issue一覧化
      ↓
acceptance criteria確認
```

---

## Phase 1: Planning

各Issueについて:

```text
size
dependencies
conflicting files
risk
recommended agent
need Agent Teams?
```

を決定。

例:

| Issue | Size | Dependency | Agent | Parallel |
|---|---|---|---|---|
| #101 Auth | Large | none | Claude Team | Yes |
| #102 README | Small | none | Codex | Yes |
| #103 Profile UI | Medium | #101 API | Cursor | No / after #101 |
| #104 Tests | Medium | none | Codex | Yes |

---

## Phase 2: Run / Task creation

```text
Run
├── Task #101
├── Task #102
├── Task #103 (depends on #101)
└── Task #104
```

---

## Phase 3: Dispatch

`ready`なTaskのみ起動。

```text
#101 → Claude
#102 → Codex
#104 → Codex
```

`#103`はblocked/pending。

---

## Phase 4: Supervision loop

```text
while run_has_unfinished_tasks:

    delivery = wait_for_inbox()

    for message in delivery:

        if message.type == "worker_done":
            validate_dispatch_identity()
            inspect_result()

            if result_is_valid:
                run_quality_gate()
            else:
                retry_or_escalate()

        elif message.type == "question":
            answer_or_create_decision_gate()

        elif message.type == "escalation":
            resolve_or_block_task()

        elif message.type == "heartbeat":
            update_liveness()

    ack(delivery)

    reconcile_task_state()
    reconcile_worker_state()

    dispatch_newly_ready_tasks()
```

---

## Phase 5: Review

例:

```text
Claude Team implementation
          ↓
Codex review
          ↓
findings
          ↓
Claude fix
          ↓
tests
```

---

## Phase 6: Ship

```text
Review pass
   ↓
commit
   ↓
push
   ↓
PR
   ↓
CI
   ↓
merge
```

---

# 15. Commander Agentプロンプト例

以下はベースライン例。プロジェクトに合わせて変更する。

```text
You are the Commander Agent responsible for coordinating software development
through Orca Orchestration.

Your primary responsibility is orchestration, not implementation.

## Source of truth

Treat Orca orchestration state as the source of truth for:
- task ownership
- dispatch lifecycle
- completion
- retry state
- blocking questions

Do not rely solely on terminal idle state, UI notifications, or conversational
memory to determine whether work is complete.

Before mutating orchestration state, load the current Orca orchestration guide:

    orca skills get orchestration --full

Do not invent CLI flags from memory.

## Planning

For each issue:

1. Read the issue and acceptance criteria.
2. Determine dependencies on other issues.
3. Estimate size and risk.
4. Identify likely overlapping files.
5. Decide whether the issue can run in parallel.
6. Choose the most appropriate agent.
7. Use a separate worktree for each independent issue.

Prefer:
- Claude Code / Agent Teams for large collaborative tasks.
- Codex for independent implementation, fixes, tests, and independent review.
- Cursor CLI for frontend/UI-heavy work when appropriate.

Do not start a task whose required dependency is incomplete.

## Dispatch

Use Orca Tasks and supervised Workers for tracked work.

Each dispatched worker must have a clearly scoped task with:
- goal
- acceptance criteria
- owned scope
- required validation
- forbidden or out-of-scope changes

Never intentionally dispatch two workers to own the same task simultaneously,
unless explicitly running a controlled race/comparison.

## Communication

Process coordinator inbox messages through Orca Orchestration.

Expected message types include:
- worker_done
- question
- escalation
- heartbeat

Do not consider a task complete merely because its agent becomes idle.

For every worker_done:
1. Verify taskId.
2. Verify dispatchId belongs to the active dispatch.
3. Verify outcome.
4. Read the worker summary.
5. Inspect the diff and validation results.
6. Run or assign the required review.
7. Only then mark the task completed.

Acknowledge inbox deliveries only after their contents have been safely processed.

## Reliability

Periodically reconcile:
- task-list
- active dispatches
- worker state
- heartbeat/liveness

If a worker stops responding:
1. inspect worker state/output;
2. determine whether work was completed but not reported;
3. recover the result if safe;
4. otherwise mark the attempt failed or blocked;
5. start an explicit retry dispatch if appropriate.

Never let the entire run wait forever for a single missing notification.

## Review

Implementation and approval are separate responsibilities.

For substantial changes, prefer an independent reviewer. When practical,
use a different model/provider from the implementer.

Critical or high-severity findings must be resolved before completion.

## Completion

A task is complete only when:
- acceptance criteria are met;
- required tests/checks pass;
- review gates pass;
- no known blocking issue remains;
- the result belongs to the current active dispatch.

At the end of the run, provide:
- completed issues
- failed/blocked issues
- PR/branch status
- unresolved risks
- relevant follow-up work
```

---

# 16. Worker Agentプロンプト例

Orca側のinjected Worker Contractに加え、作業内容の明確化に使う。

```text
You are an implementation worker operating under an Orca Commander.

Work only on the assigned task.

## Scope

Issue:
<ISSUE>

Goal:
<GOAL>

Acceptance criteria:
<CRITERIA>

Owned files / domain:
<SCOPE>

Out of scope:
<OUT_OF_SCOPE>

## Rules

- Do not start unrelated refactors.
- Do not change shared interfaces without notifying the Commander when the
  change affects other active tasks.
- Run the required tests/checks before completion.
- If blocked by a decision, ask through Orca orchestration instead of waiting
  indefinitely for local terminal input.
- During long active work, send heartbeat messages as required by the injected
  Worker Contract.
- Send worker_done exactly once for the current dispatch, including the task ID,
  dispatch ID, outcome, summary, and modified files.
- Send worker_done on failure as well as success.

## Completion report

Summarize:
1. What changed
2. Why
3. Files changed
4. Tests/checks run
5. Known limitations
6. Remaining follow-up, if any
```

---

# 17. 障害・復旧設計

## 17.1 Workerからworker_doneが届かない

まず通知待ちを続けるのではなく、状態を調べる。

```bash
orca orchestration worker-show \
  --dispatch <dispatchId> \
  --json
```

直近出力:

```bash
orca orchestration worker-read \
  --dispatch <dispatchId> \
  --limit 50 \
  --json
```

Task一覧:

```bash
orca orchestration task-list --json
```

---

## 17.2 Workerがハングした

必要なら停止。

```bash
orca orchestration worker-stop \
  --dispatch <dispatchId> \
  --json
```

その後、retryを明示。

```bash
orca orchestration worker-start \
  --task <taskId> \
  --retry-of <dispatchId> \
  --worktree current \
  --agent codex \
  --json
```

Retry placementは明示的に指定する。

---

## 17.3 完了したWorker terminalを残し続けない

完了後にinspect可能な状態を保ちながらreleaseできる。

```bash
orca orchestration worker-release \
  --dispatch <dispatchId> \
  --json
```

あとから必要なら`worker-read`で確認する。

デバッグ目的で明示的に保持したい場合だけretainを使う。

---

## 17.4 Taskをblockedにする

外部credential待ちなど:

```bash
orca orchestration task-update \
  --id <taskId> \
  --status blocked \
  --result '{"reason":"waiting on credentials"}' \
  --json
```

「何となく止まっている」状態を作らず、block reasonを永続化する。

---

## 17.5 Resetは最終手段

```bash
orca orchestration reset --tasks --json
orca orchestration reset --messages --json
orca orchestration reset --all --json
```

Resetはruntime-global orchestration stateへ影響する。

**別Commanderが動作中に安易に実行しない。**

---

# 18. アンチパターン

## Anti-pattern 1: terminal sendだけでオーケストレーション

```text
Commander
 ↓
terminal send
 ↓
"終わったら教えて"
```

ownership、completion tracking、DAGが必要ならsupervised Workerを使う。

`terminal send`は一回限りの軽量prompt向け。

---

## Anti-pattern 2: idle = completed

```text
agent idle
   ≠
task completed
```

idleは単にAgentが現在生成していないだけの可能性がある。

---

## Anti-pattern 3: Commanderのcontextだけに状態を持つ

悪い例:

```text
「たしかAgent Bは#102をやっていたはず」
```

正:

```text
Task
Dispatch
Message
Worktree
```

から復元可能にする。

---

## Anti-pattern 4: ACKしてから処理する

```text
receive
 ↓
ACK
 ↓
processing failure
```

ではDeliveryを失ったのと同じ状態になり得る。

推奨:

```text
receive
 ↓
process
 ↓
persist
 ↓
ACK
```

---

## Anti-pattern 5: すべてを並列化

Parallelismは目的ではない。

```text
parallel value
-
merge conflict
-
coordination overhead
-
token cost
-
review cost
```

がプラスになる場合だけ並列化する。

---

## Anti-pattern 6: すべてをClaude Agent Teams化

小IssueにAgent Teamsを使うとcoordination/token overheadが増える。

Agent Teamsは密な協調が価値を持つIssueだけに限定する。

---

## Anti-pattern 7: Worker同士を無制限に直接会話させる

Claude Agent Teamsとは異なり、異種CLI AgentのOrca運用ではCommanderを通信hubにした方が状態を追跡しやすい。

必要なcross-worker情報はCommanderがroutingする。

---

# 19. 導入チェックリスト

## Orca

- [ ] Orca CLIが利用可能
- [ ] `orca status --json`が成功する
- [ ] Orchestration Experimental featureを有効化
- [ ] `orchestration` skillを導入
- [ ] `orca skills get orchestration --full`をCommanderに読ませる
- [ ] Agent status hooksの状態を確認
- [ ] Git worktree方針を決める

Agent status hooks:

```bash
orca agent hooks status --json
```

---

## Repository

- [ ] base branchを決める
- [ ] setup hooksを設定する
- [ ] package install / env準備を自動化する
- [ ] CLAUDE.md / AGENTS.md等のプロジェクト規約を整備する
- [ ] lint / typecheck / test commandを明文化する
- [ ] PR completion criteriaを明文化する

---

## Commander

- [ ] Orchestration stateをsource of truthにする
- [ ] Issue dependency解析をする
- [ ] 1 Issue = 1 Taskを基本とする
- [ ] 1 Issue = 1 worktreeを基本とする
- [ ] `worker-start`でtracked workerを起動する
- [ ] `check --wait`でInboxを読む
- [ ] 処理後にACKする
- [ ] `worker_done`のtaskId / dispatchIdを検証する
- [ ] timeout時にreconciliationする
- [ ] retryを新しいDispatchとして扱う
- [ ] Review Gateを設ける

---

## Worker

- [ ] Scopeが明確
- [ ] acceptance criteriaが明確
- [ ] owned files/domainが明確
- [ ] out-of-scopeが明確
- [ ] long taskでheartbeat
- [ ] blocking questionはOrchestration経由
- [ ] failure時もworker_done
- [ ] taskId + dispatchIdを含める
- [ ] test結果を報告
- [ ] 変更ファイルを報告

---

## セキュリティ上の注意

Orcaのbuilt-in agent launchでは、対応CLIについてpermission-bypass / yolo系flagを初期値として用いる構成がある。

例として公式資料にはClaude、Codex、Cursor等についてpermission bypass系の起動方式が説明されている。

これは独立worktreeを前提に操作摩擦を減らす設計だが、

> **worktree分離はOS権限やcredentialへのアクセスをsandboxするものではない**

点に注意する。

以下を扱う環境では特にpermission policyを見直す。

- production credentials
- cloud admin credentials
- secrets
- destructive database commands
- deployment
- billing
- package publication
- infrastructure mutation

「worktreeが捨てられる」ことと、「Agentのすべての副作用が捨てられる」ことは同義ではない。

---

# 推奨する最終形

```text
                         GitHub Issues
                              │
                              ▼
                      Commander Agent
                              │
                       Orca Run / Inbox
                              │
             ┌────────────────┼────────────────┐
             │                │                │
          Task A           Task B           Task C
             │                │                │
        Dispatch A       Dispatch B       Dispatch C
             │                │                │
        Worktree A       Worktree B       Worktree C
             │                │                │
      Claude Agent Team      Codex          Cursor CLI
             │
       ┌─────┼─────┐
    Implement Test Review
             │
             └──────── worker_done ────────┐
                                           │
Codex ─────────────── worker_done ─────────┤
Cursor ────────────── worker_done ─────────┤
                                           ▼
                                     Orca Inbox
                                           │
                                    process + ACK
                                           │
                                    Reconciliation
                                           │
                                      Quality Gate
                                           │
                                          PR
```

最も重要な設計原則は以下の5点。

1. **Issue間の並列化はOrcaで行う**
2. **1 Issue = 1 Worktreeを基本にする**
3. **通信ではなくOrchestration stateを真実の情報源にする**
4. **Inbox + ACK + Reconciliationで通知欠落に耐える**
5. **密なIssue内協調だけClaude Agent Teamsへ委譲する**

これにより、

```text
「Agentから通知が来なかったのでCommanderが止まる」
```

という設計から、

```text
「通知がなくてもTask / Dispatch / Worker stateから復旧できる」
```

設計へ移行できる。

---

# 20. 参考資料

以下は2026-09-10時点で確認した公式資料。

## Orca

- Orca Docs — Orchestration  
  https://www.onorca.dev/docs/cli/orchestration

- Orca Docs — Skills registry & MCP  
  https://www.onorca.dev/docs/cli/skills

- Orca Docs — Worktrees  
  https://www.onorca.dev/docs/model/worktrees

- Orca Docs — Supported agents  
  https://www.onorca.dev/docs/agents/supported

- Orca Docs — Agent hooks & memory  
  https://www.onorca.dev/docs/agents/hooks-memory

- Orca Docs — Worktree checkpoints  
  https://www.onorca.dev/docs/cli/worktree-checkpoints

- Orca Docs — CLI reference  
  https://www.onorca.dev/docs/cli/reference

- Orca Docs — Race three agents on the same task  
  https://www.onorca.dev/docs/recipes/parallel-agents

## Claude Code

- Claude Code Docs — Agent Teams  
  https://code.claude.com/docs/en/agent-teams

- Claude Code Docs — Run agents in parallel  
  https://code.claude.com/docs/en/agents

---

## バージョン追従について

Orca公式はCLI flagsがアプリとともに変化し得るとしている。

そのため、CommanderやWorkerのSkill/Promptにコマンドを完全固定せず、実行前に

```bash
orca skills get orchestration --full
```

を読み、その環境のOrca versionに対応したcommand guideを使うことを推奨する。

この資料中のCLI例は2026-09-10時点の公式資料に基づく。
