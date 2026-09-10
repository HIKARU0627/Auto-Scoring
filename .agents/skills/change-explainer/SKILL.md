---
name: change-explainer
description: 現在のPull Requestに含まれる変更内容を解析し、人間がdiffを読む前に全体像を把握できるChange Summaryを生成して、GitHub App経由でPRコメントとして同期するスキル。PRの変更説明を書きたいとき、レビュー依頼前にPRへ変更概要コメントを付けたい・更新したいときに使用する。PRごとに常に最新の説明コメントを1つだけ維持する。
---

# Change Explainer

## 目的

現在のPull Request全体の変更を解析し、レビュー担当者がdiffを見る前に内容を把握できる**Change Summary**を生成する。生成した内容は**GitHub App経由でPRコメントとして投稿・更新**する。

PRには常に「**今このPRに何が含まれているか**」を説明する最新のChange Summaryコメントが**1つだけ**存在する状態を維持する。変更履歴の追記はしない（履歴はGitのコミットに任せる）。

> `git-workflow-and-versioning` の "Change Summaries" は、実装直後にチャットへ出す作業サマリ（CHANGES MADE / DIDN'T TOUCH / CONCERNS）。本スキルはそれとは別物で、PR全体を対象にレビュー担当者向けの説明を生成し、GitHub AppでPRコメントとして1つ維持することを担う。

## 責務分離

| 操作 | 手段 |
|---|---|
| ローカルの差分取得（`git diff` / `git log` など） | 標準の `git` |
| PR取得・PRコメント取得・作成・編集 | `AGENTS.md` «GitHub App authentication» が指定する経路 |

GitHub 操作の経路は `AGENTS.md` に従う。GitHub App 帰属を採用しているリポジトリでは `./scripts/invoke-github-app-api.ps1` を使い、`gh` へフォールバックしない。採用していないリポジトリでは `gh` などプロジェクトが指定するツールを使う。いずれの場合も GitHub App 秘密鍵・トークンをスキルや生成物へ保存しない。詳細は `AGENTS.md` と `docs/ai-agent-git-attribution.md` に従う。以下の例は GitHub App 経路（`invoke-github-app-api.ps1`）で示す。`gh` を使う場合は `gh api` の同等呼び出しに読み替える。

## 前提

- GitHub App 帰属を採用しているリポジトリでは `./scripts/configure-github-app-git-attribution.ps1` によるworktree単位の設定が済んでいる。
- 解析対象のブランチはリモートへpush済み（未pushならPR差分が最新でない旨を報告する）。
- `<owner>` / `<repo>` は対象リポジトリの実際の owner / repo 名に読み替える。

## フロー

```text
1. 現在のブランチと base(main) を特定する
2. git でPR全体の差分を取得・解析する
3. Change Summary を生成する（出力形式は references/output-format.md）
4. GitHub App でこのブランチに対応する open PR を検索する
5. PR がない → コメントは投稿せず、生成した Summary と「PR未作成」を報告して終了
6. PR がある → 既存の change-explainer コメントを検索する
7. なし → コメントを作成する / あり → そのコメントを編集する
8. 実行結果（PR番号・コメントURL・作成/編集の別）を報告する
```

## Step 1-2: 差分の取得

```bash
git rev-parse --abbrev-ref HEAD
git fetch origin main
git --no-pager diff --stat origin/main...HEAD
git --no-pager diff origin/main...HEAD
git --no-pager log --oneline origin/main..HEAD
```

`origin/main...HEAD`（3点）で、mainから分岐した後のPR全体の変更を対象にする。

## Step 3: Change Summary の生成

出力の構成・粒度・文体は [references/output-format.md](./references/output-format.md) に従う。最低限、次を含める。

- 変更概要 / 主な変更 / ファイルごとの変更点 / 影響範囲 / 注意点・懸念点 / 用語

lockファイル・自動生成ファイル・フォーマットのみの変更は詳細に立ち入らない。一般的な開発用語は注釈しない。

## Step 4: 対応するPRの検索（GitHub App）

```powershell
$owner = '<owner>'   # head の owner
$branch = '<current-branch>'
./scripts/invoke-github-app-api.ps1 -Method Get `
  -Endpoint "/repos/<owner>/<repo>/pulls?state=open&head=$owner`:$branch"
```

- 返り値が空配列 → **PRなし**。Step 5 へ。
- 複数該当は通常ないが、複数返った場合は `head.ref` が完全一致する open PR を選ぶ。

## Step 5: PRが存在しない場合

`change-explainer` は**PRを勝手に作成しない**。生成したChange Summary本文を出力し、「対応するPRが存在しないためコメントは投稿していない」ことを明示して終了する。

呼び出し元が `review-ready` の場合、PR作成はその Step 5 の責務である。ここで終了したら、Step 5 を先に済ませてから再実行する。

## Step 6: 既存コメントの検索

```powershell
./scripts/invoke-github-app-api.ps1 -Method Get `
  -Endpoint "/repos/<owner>/<repo>/issues/<PR_NUMBER>/comments?per_page=100"
```

編集対象は、次を**すべて**満たすコメントに限定する。

1. 本文に Hidden Marker `<!-- change-explainer -->` を含む
2. `user.type` が `Bot` で、セットアップ済みGitHub App（`<app-slug>[bot]`）が作成したコメントである

人間や他のBotが作成したコメントは編集しない。該当が複数あれば最も古いものを残して更新し、他は本文冒頭に `<!-- change-explainer:superseded -->` を付けて内容を空のリンク案内に置き換える（削除はしない）。

## Step 7: コメントの作成 / 編集

コメント本文の先頭に識別マーカーと解析時のHEAD SHAを埋め込む。

```markdown
<!-- change-explainer -->
<!-- change-explainer-head: <HEAD_SHA> -->

# Change Summary

（references/output-format.md に従った本文）
```

本文は一時ファイルに書き、`-BodyPath` で渡す（改行・記号のエスケープ事故を避ける）。`body` フィールドを持つJSONを組み立てる。

### 作成

```powershell
# comment.json = { "body": "<マーカー付き本文>" }
./scripts/invoke-github-app-api.ps1 -Method Post `
  -Endpoint "/repos/<owner>/<repo>/issues/<PR_NUMBER>/comments" `
  -BodyPath ./comment.json
```

### 編集

```powershell
./scripts/invoke-github-app-api.ps1 -Method Patch `
  -Endpoint "/repos/<owner>/<repo>/issues/comments/<COMMENT_ID>" `
  -BodyPath ./comment.json
```

本文はPR全体を基準に**毎回作り直す**。前回本文への差分追記はしない。

一時ファイル（`comment.json` など）は生成物としてコミットしない。作業後に削除する。

## Step 8: 報告

- PR番号とコメントURL
- 作成 / 編集の別
- 解析に使ったHEAD SHA
- PRがなかった場合はその旨とSummary本文

## 再実行時の挙動

PRへ追加pushされた後に再実行する場合も、新規コメントは作らない。Step 6 で既存コメントを取得し、最新のPR全体を解析した本文で**編集**する。`<!-- change-explainer-head -->` を最新SHAへ更新する。

## 検証（このスキルの完了条件）

- [ ] PR全体（`origin/main...HEAD`）の変更を解析した
- [ ] 変更概要・主な変更・ファイルごとの変更・変更理由・影響範囲・注意点・用語を含む
- [ ] lockファイルや自動生成物を過剰に説明していない
- [ ] GitHub App経由でPRコメントを投稿または編集した
- [ ] Hidden Marker `<!-- change-explainer -->` で既存コメントを識別した
- [ ] GitHub App自身が作成したコメントだけを編集対象にした
- [ ] PR更新時は新規作成せず既存コメントを編集した
- [ ] 本文は最新PR全体を基準に再生成し、差分追記になっていない
- [ ] 古いChange Summaryを複数残していない
- [ ] PRが存在しない場合にPRを作成していない
