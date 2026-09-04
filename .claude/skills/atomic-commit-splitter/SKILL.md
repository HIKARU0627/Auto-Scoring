---
name: atomic-commit-splitter
description: すでに一括で行われた未コミットの変更を解析し、変更目的ごとのAtomic Commitへ再構成するスキル。大量の未コミット変更が混在しているとき、複数の機能・修正・リファクタリングが1つの作業ツリーに混ざっているとき、レビュー前にコミット履歴を整理したいときに使用する。git-workflow-and-versioningが「最初からAtomic Commitを維持する予防」なのに対し、これは「混ざった変更を整理・修復する」役割。
---

# Atomic Commit Splitter

## 目的

すでに一括で実装され、未コミット状態で混在している変更を解析し、**変更目的ごとのAtomic Commit**へ再構成する。

## `git-workflow-and-versioning` との役割分担

| スキル | 役割 |
|---|---|
| `git-workflow-and-versioning` | 予防。実装→テスト→コミット→次タスク、と最初からAtomic Commitを維持する。**Atomic Commitの定義、コミットメッセージ規約（`feat` / `fix` / `refactor` / `test` / `docs` / `chore`）、コミット前の確認（staged diff・秘密情報・test/lint）はこちらが定める** |
| `atomic-commit-splitter` | 整理・修復。すでに混ざってしまった未コミット変更を、部分ステージングで複数のAtomic Commitへ分割する**手順のみ**を定める |

概念・規約は重複させない。本スキルは分割の実務手順に限定する。

## 前提

- ローカルRepositoryの操作には標準の `git` のみを使用する。Interactive rebaseやAgent固有のGitツールに依存しない。
- コミット前に、このリポジトリの `AGENTS.md` «GitHub App authentication» に従い、Author / Committer と push 認証が正しいことを確認する。GitHub App 帰属を採用しているリポジトリでは `./scripts/configure-github-app-git-attribution.ps1` の設定が済んでいること。
- push・PR操作は本スキルの対象外。`review-ready` または `change-explainer` が担当する。

## 基本フロー

```text
1. git status で変更ファイル一覧を確認
2. git diff（未ステージ）と git diff --cached（ステージ済み）で変更全体を取得
3. 変更全体を1つずつ読み、何が行われたか理解する
4. 変更を「目的」単位で分類し、Commit Plan を作成する
5. Plan の先頭コミットに必要な変更だけを stage する
6. git diff --cached で、stage内容が単一の目的だけか確認する
7. コミット前の確認（staged diff・秘密情報・test/lint は `git-workflow-and-versioning` に従う）
8. commit する
9. 残りの変更について 5〜8 を繰り返す
10. git status がクリーンになったら、git log --oneline で結果を確認する
```

## Step 1-3: 変更の把握

```bash
git status
git --no-pager diff
git --no-pager diff --cached
```

- 生成物・lockファイル（`pnpm-lock.yaml` / `package-lock.json` / `Cargo.lock` / `poetry.lock` など）・フォーマットのみの変更は、目的の1つとして別枠で扱う。混ぜない。
- 変更が大きい場合はファイルごと・hunkごとに要約メモを作り、後の分類に使う。

## Step 4: Commit Plan の作成

分割は**ファイル単位ではなく変更の目的単位**で行う。実際にコミットする前に、必ず次の形式で計画を書き出す。

```text
Commit 1
feat(auth): add Google OAuth support

Files:
- src/auth/oauth.ts
- src/routes/auth.ts

Reason:
Google OAuthログイン機能の本体。


Commit 2
refactor(auth): simplify authentication utilities

Files:
- src/auth/utils.ts
- src/auth/oauth.ts の一部hunk

Reason:
既存認証処理の整理。挙動は変えていない。


Commit 3
test(auth): add OAuth tests

Files:
- tests/auth/oauth.test.ts

Reason:
追加したOAuth機能のテスト。
```

粒度の原則（1コミット = 1つの論理的変更）は `git-workflow-and-versioning` の "Atomic Commits" を参照。本スキルでは分割単位 ＝ **変更目的** とだけ決める。

順序の指針:
1. 前提となるリファクタリング・準備的変更を先に
2. 機能追加・バグ修正を次に
3. テスト・ドキュメント・生成物を後に

各コミットが単体でビルド・テスト可能になるよう順序を決める。

## Step 5-6: 部分ステージング

### ファイル単位で分けられる場合

```bash
git add src/auth/oauth.ts src/routes/auth.ts
git --no-pager diff --cached
```

### 同一ファイル内に複数の目的が混在する場合

hunk単位で分割する。Interactive stagingが扱いにくい環境でも動くよう、`git add -p` のみに依存しない。次のいずれかを使う。

- **`git add -p`（対話が使える場合）**: `y` / `n` / `s`（hunk分割）/ `e`（手動編集）で選択する。
- **patchファイル経由（対話に依存しない方法、推奨フォールバック）**:

  ```bash
  # 1. 対象ファイルの差分をパッチとして書き出す
  git --no-pager diff -- src/auth/oauth.ts > /tmp/oauth.patch

  # 2. パッチを編集し、このコミットに含めるhunkだけを残す
  #    （残すhunk以外を削除。ヘッダ行 "diff --git" 〜 "@@" の対応に注意）

  # 3. 編集後パッチを index にだけ適用する
  git apply --cached /tmp/oauth.patch

  # 4. 確認
  git --no-pager diff --cached -- src/auth/oauth.ts
  ```

- **一時退避を使う方法**: 目的Aの行だけを残した版を作ってstage → `git stash push --keep-index` で残りを退避 → コミット → `git stash pop`。stashは他worktreeと共有されるため、必ず `-m "atomic-split-<topic>"` でタグ付けし、`git stash list` でSHAを控え、`git stash apply <sha>` で戻す。

ステージ後は必ず `git diff --cached` を読み、**そのコミットの目的以外の変更が混ざっていないこと**を確認する。混ざっていたら `git restore --staged <path>` で戻す。

## Step 7: コミット前の確認

staged diff の確認・秘密情報チェック・test / lint / typecheck の実行は `git-workflow-and-versioning` の "Pre-Commit Hygiene" に従う。ここでは分割特有の注意だけ挙げる。

- `git diff --cached` を読み、そのコミットの目的以外の変更が混ざっていないことを確認する（混在していたら `git restore --staged <path>`）。
- 中間コミットでもビルド・テストが壊れない順序にする（Step 4 の順序指針）。
- E2E / build など重い検証は全コミット確定後に1回でよい。失敗は最終報告に含める。

## Step 8-9: コミットと繰り返し

`git commit` する（メッセージ規約は `git-workflow-and-versioning`）。`git status` がクリーンになるまで Step 5〜8 を繰り返す。

## Step 10: 結果確認

```bash
git --no-pager log --oneline -n 10
git --no-pager diff <再構成前のHEAD>..HEAD --stat
```

- 再構成前後で**最終的な作業ツリーの内容が一致している**ことを `git diff` で確認する（分割で内容を変えていないこと）。
- 各コミットが1つの目的を持つこと、無関係な変更が混ざっていないことを確認する。

## すでに整理済みの場合

未コミット変更が単一の目的しか含まない場合、無理に複数コミットへ分割しない。1コミットで確定し、その旨を報告する。

## やらないこと

- すでに共有・push済みのコミット履歴の書き換え（force pushが必要な操作）は行わない。
- 分割のためにコードの挙動を変更しない。挙動の整理が必要なら別途 `code-simplification` を使い、独立したコミットにする。
- push・PR作成・PRコメントは行わない。

## 検証（このスキルの完了条件）

- [ ] `git status` と `git diff` から変更全体を解析した
- [ ] ファイル単位ではなく変更目的単位で分類した
- [ ] コミット前に Commit Plan を文章で作成した
- [ ] 同一ファイル内の混在も、対話に依存しない方法で分割できた
- [ ] 各コミットが1つの明確な変更意図を持つ
- [ ] 各コミット前に `git diff --cached` を確認した
- [ ] 無関係な変更を同じコミットに含めていない
- [ ] 再構成前後で作業ツリーの最終内容が一致している
