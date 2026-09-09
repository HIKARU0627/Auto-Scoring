# Quality gates

Local commands and GitHub Actions run the same checks. Each check is a `scripts`
entry in `package.json`, invoked as `pnpm run <script>`.

| Gate               | Command                  | CI job / step (`.github/workflows/ci.yml`)    |
| ------------------ | ------------------------ | --------------------------------------------- |
| Agent skill mirror | `pnpm run skills:check`  | App → Check agent skill mirrors               |
| Formatting         | `pnpm run format:check`  | App → Check formatting                        |
| OpenAPI contract   | `pnpm run openapi:check` | App → OpenAPI contract                        |
| Lint               | `pnpm run lint`          | App → Lint (`:app`), Backend → Lint           |
| Typecheck          | `pnpm run typecheck`     | App → Typecheck (`:app`), Backend → Typecheck |
| Test               | `pnpm run test`          | App → Test (`:app`), Backend → Test           |
| Build              | `pnpm run build`         | App → Build (`:app`), Backend → Build         |
| Everything         | `pnpm run check`         | (all of the above, across both jobs)          |

`openapi:check` regenerates `backend/openapi/openapi.json` and the Dart client
in `app/packages/auto_scoring_api/` and fails on any git diff. It needs `uv`,
`dart`, and Java (openapi-generator) on PATH, so it stays out of the git hooks
(`check:pre-commit` / `check:pre-push`) and runs only in `pnpm run check` and CI.
See [`sidecar-api.md`](./sidecar-api.md) §4.

`package.json` is a task runner over the two stacks. Each gate fans out to an
`:app` (Flutter) and a `:backend` (Python) script:

| Gate        | `:app`                                                  | `:backend`                           |
| ----------- | ------------------------------------------------------- | ------------------------------------ |
| `lint`      | `dart format --set-exit-if-changed` + `flutter analyze` | `ruff check` + `ruff format --check` |
| `typecheck` | `flutter analyze`                                       | `mypy` (`strict`)                    |
| `test`      | `flutter test`                                          | `pytest`                             |
| `build`     | `flutter build windows --debug`                         | `python -c "import auto_scoring"`    |

`format` / `format:check` stay on Prettier for the repo-level files; `app/` and
`backend/` are in `.prettierignore` because Dart and Ruff own their formatting.

## CI のジョブ構成と、必須チェック `Quality`

CI は 4 ジョブ。`app` と `backend` が実作業、`quality` は**判定を集約するだけ**の
ジョブで、`package` は独立。`needs` で繋がっているのは `quality` だけなので、
`app` / `backend` / `package` は同時に走る。**待ち時間は和ではなく最大値。**

| ジョブ    | 表示名            | 中身                                                               | ツールチェーン                    |
| --------- | ----------------- | ------------------------------------------------------------------ | --------------------------------- |
| `app`     | App               | skill mirror, format, openapi, `:app` の lint/typecheck/test/build | Flutter SDK + uv + Node           |
| `backend` | Backend           | `:backend` の lint/typecheck/test/build                            | uv + Node（**Flutter SDK なし**） |
| `quality` | **Quality**       | 上 2 つの結果を判定するだけ                                        | なし（ubuntu）                    |
| `package` | Package (Windows) | PyInstaller バンドル + インストーラ                                | Flutter SDK + uv + Node           |

### 置き場所の理由

- **`openapi:check` は `app` に置く。** `dart` が要る（Dart クライアントを再生成する）
  ので、Flutter SDK を復元済みのジョブでしか動かない。`backend` に置くと 1.7 GB の
  SDK をもう一度復元することになり、何も得しない。
- **`backend` には Flutter SDK も `pnpm install` も入れない。** どのステップも
  `dart` にも node 依存にも触らないため。SDK 復元を省くだけで約 1.6 分減り、
  このジョブが全体の所要を決めるので、そのまま全体に効く。
- **`backend` は `windows-latest` のまま。** Linux ランナーなら約 3 倍速いが、
  これは Windows 専用製品で、サイドカーのパス・ファイル I/O の挙動は
  「Linux では通り、先生の実機で落ちる」の典型。速さのために出荷先の検証を
  やめることはしない。

### `Quality` が必須チェックである以上、外してはいけない 2 点

`main` の ruleset が要求する status check の context は **`Quality` の 1 つだけ**。
この名前のチェックが消えると、以後すべての PR がマージ不能になる。したがって
**実作業のジョブは別名にし、集約ジョブに `name: Quality` を付ける。**

集約ジョブには **`if: always()` が必須**で、`needs` の各 `result` を明示的に
判定して失敗させること。`needs` が失敗すると依存ジョブは **skipped** になり、
**GitHub は skipped の必須チェックを成功として扱う。** ここを外すと、ビルドが
赤いままマージゲートだけが緑に見える。到達したこと自体は何の成功の証拠でもない。

## git hooks vs CI

- `.githooks/pre-commit` runs `pnpm run check:pre-commit` (skill mirror +
  formatting): fast, deterministic, non-destructive.
- `.githooks/pre-push` runs `pnpm run check:pre-push` (lint + typecheck + test).
- Hooks can be bypassed with `--no-verify`, so GitHub Actions runs the full set
  as a merge gate. Make the real checks required in the branch ruleset.
- `pnpm run bootstrap` points the current worktree at `.githooks/`
  (`git config core.hooksPath .githooks`).

### Hook files must carry the executable bit

`core.hooksPath` being set is not enough. Git skips a hook it cannot execute and
says so only as a hint on stderr, so nothing fails and the hook simply never
runs. Both hooks sat at `100644` from the day they were added until Issue #75,
which is why `--no-verify` pushes had no effect either.

A hook must be tracked as `100755` — that is the mode every clone checks out
with — and, on POSIX, the checked-out file needs the bit as well, because that
is what git tests before running it. To verify:

```console
$ git ls-files --stage .githooks/
100755 9b4f0291... 0	.githooks/pre-commit
100755 27237d0d... 0	.githooks/pre-push

$ git hook run --ignore-missing pre-commit
```

`git hook run` executes the hook, or prints `hook was ignored because it's not
set as executable` instead — the one command that answers "would git actually
run this?".

When adding a hook, set both modes:

```sh
chmod +x .githooks/<name>                      # this worktree (POSIX only)
git update-index --chmod=+x .githooks/<name>   # the tracked mode
```

### Hooks inherit git's environment

**Rule: a hook must drop the inherited git environment before it shells out to
any external tool.**

```sh
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE GIT_PREFIX
```

Git exports those four variables into every hook process, pointing at _this_
repository, and everything the hook runs inherits them. A tool that calls git
for its own purposes — locating a repository root, reading its own version,
resolving config — therefore inspects this repository instead of wherever it
actually lives. Nothing errors; the tool just quietly gets the wrong answer.

The instance that surfaced here (Issue #75): Flutter shells out to git to
identify its own SDK, so under a hook it read this repository and reported
version `0.0.0-unknown`, failing `app/pubspec.yaml`'s `>=3.41.0` constraint.
`flutter analyze` and `flutter test` broke inside the hook while working fine
from a normal shell, which made every `git push` fail the moment the hooks
started running. `.githooks/pre-push` carries the `unset` for that reason.

Verify a new hook with `git hook run --ignore-missing <name>`. Running its
`pnpm run check:*` script directly from a shell does **not** reproduce the hook
environment, which is why this trap stayed invisible for as long as it did.

### Where the check lives

`pnpm run bootstrap` checks every file in `.githooks/` for both modes and
**fails** rather than warns — a warning is what let this go unnoticed. Keep `.githooks/`
free of non-hook files (notes, READMEs); the check has no way to tell them apart.

## Adding heavier gates

Add integration / e2e / contract jobs directly to `.github/workflows/ci.yml` as
separate jobs, and add matching `package.json` scripts. Keep hook-run checks
fast; put anything slow or environment-heavy in CI only.

## ローカル全 green は CI green を意味しない

CI は `windows-latest` の**素のランナー**で走る。開発機に入っていて
ランナーに入っていないものにテストが依存すると、ローカルだけ通る。実際に
起きた例（Issue #35）: `create_ai_provider()` は `codex` 実行ファイルが無い
ホストではその provider をチェーンから外す。この開発機には Codex レビュー用に
`codex` が入っているためローカルは全 green、Windows ランナーには無いため
3 件が落ちた。

**ホストを見る判定はテストへ注入し、両方の分岐を通す。** skip で逃げると
その経路が CI で一度も検証されなくなる。`create_ai_provider()` は
`executable_available` と `token_source_factory` を引数で受け取り、テストは
「この環境には codex がある／ADC がある」を**宣言する**（`os.environ` も
`env=` で明示的に渡す）。

外部依存を疑うときは、それらを外した環境で流して確かめられる:

```bash
# codex を除いた PATH・ADC 無し・1Password トークン無し・メタデータサーバ到達不可
env -u GOOGLE_APPLICATION_CREDENTIALS -u OP_SERVICE_ACCOUNT_TOKEN \
    HOME=/tmp/no-home CLOUDSDK_CONFIG=/tmp/no-home/gcloud \
    GCE_METADATA_HOST=169.254.169.254.invalid NO_GCE_CHECK=true \
    PATH=/usr/local/bin:/usr/bin:/bin \
  bash -c 'cd backend && uv run pytest -q'
```

同種の依存として注意するもの: `gcloud`/ADC、`op`(1Password)、`codex`、
ネットワーク到達性、ロケール、`HOME` 配下の設定。ネットワークを使うアダプタは
`httpx.Client` を注入して `MockTransport` で閉じる（`tests/test_ai_provider_*`）。

## 全 green は「画面で動く」を意味しない

このリポジトリでは「テストが緑なのに画面では動いていない」事故が繰り返し
起きている。緑が嘘をつく形は 2 つあり、どちらも**テストの書き方**が原因である。

### 否定形のアサーションは、起こす側が止まっても赤くならない

「〜が表示されない」「一覧に出ない」「呼ばれない」は、**画面がそもそも
描けていなくても通る**。`expect(find.byKey(...), findsNothing)` は widget が
1 つも build されていないときに最もよく通るし、`assert "sub-1" not in ids` は
`ids` が空なら通る。直近で 2 件見つかっている。

**否定を書くときは、先に肯定を書く。** 「画面が描けている」「一覧が引けて
いる」を名指しで assert し、そのうえで無いことを言う。可能なら否定を
「全体が期待どおりである」の形（集合や辞書の完全一致）に置き換える --
`test_finished_submission_reachability.py` の
`{row["id"]: row["state"] for row in ...} == {...}` がその形で、確認済みが
**入っている**ことと余計なものが**入っていない**ことを 1 本で言っている。

### 回帰テストは、直す前の壊れた状態へ戻して落ちることを確かめる

新しいテストが緑なのは、直したからとは限らない。**そのテストが何も
掴んでいない**だけのこともある。足したら必ず、直した箇所を壊して赤くなる
ことを実測する（値を変えるのではなく、**直した性質**を壊す）。

同時に「既存のどのテストが同じ変異を捕まえるか」も分かる。全件を流せば、
その回帰テストが**新しい保証を足したのか、既にあった保証を言い直した
だけなのか**が区別できる。Issue #137 では 4 つの変異のうち 2 つが新しい穴
（`GET /tests/{id}/submissions` と `GET /submissions/{id}` が確認済みの答案を
隠しても、他の 1713 件は緑のままだった）で、残り 2 つは既存のテストが
捕まえていた。

**壊した状態を残さないこと。** 確かめ終えたら `git status` と `git diff` で
実測してから次へ進む。

**変異させる前にコミットしておくこと。** 戻し方は `git checkout -- <path>` に
なるが、これは**同じファイルの未コミットの編集ごと消す**。Issue #137 では実際に
これで実装中の 4 箇所の編集を失った（`git status` にそのファイルが出なくなって
気付いた）。コミット済みなら、変異は必ず 1 コマンドで正確に戻せる。

## 新しい公開経路を作ったら、そこへ流れ込むものを全部見直す

Issue #97 は「なぜ採点が使えないかを画面で伝える」ために、`GET /grading/availability`
という**新しい公開経路**を作った。そこで既存の文字列が**3ラウンド続けて**漏れた:

1. `create_ai_provider()` の設定エラー本文（読めなかった温度の値・未知 transport 名・
   `AUTO_SCORING_CODEX_EXECUTABLE` の設定値）。「ログにしか出ない」前提で書かれていた。
2. Vertex アダプタが `AUTO_SCORING_VERTEX_PROJECT` / `AUTO_SCORING_GEMINI_MODEL` から
   組み立てる**リクエスト URL**。httpx が INFO で出し、サイドカーは root を INFO にして
   回転ファイルログへ書くため、404 応答だけで永続ログに残った。
3. 2 を「値をマスクする」で塞いだ直後、**httpx がホスト名を小文字化する**ため、
   `AUTO_SCORING_VERTEX_LOCATION` に大文字を含む値を入れると完全一致の置換をすり抜けた。
   パスは `***` になるのにホスト名には残る、という形で。

どれも「操作者が API キーを別の変数へ貼った」という同じ事故で、どれも
**誰かが意図して作った経路ではない**。

### 教訓 A: 経路を数え上げるのではなく、外へ出る場所にゲートを置く

経路の列挙は必ず取りこぼす。`backend/src/auto_scoring/api/secret_redaction.py` が
「設定値とは何か」を1か所で定義し、テキストがこのプロセスを出る2か所 --
`install_log_redaction`（ログ設定はここだけ。uvicorn は `log_config=None` で起動するので
uvicorn のロガーも root のハンドラを通る）と `build_ai_provider`（reason を作るのはここだけ）
-- が同じ規則を適用する。

### 教訓 B: マスクは「値がどう表現されるか」を全部知っていないと成立しない

3 がそれを示した。**完全一致は常に一手遅れる**（小文字化の次は URL エンコード、
エスケープ、切り詰め）。値の表現形をライブラリが決める以上、こちら側の照合を
足し続ける勝負にはならない。

**消すのをやめて、出さない。** `api/sidecar.py` の `_VERBOSE_LOGGERS` が INFO を
許すのは `auto_scoring` / `uvicorn` / `alembic` だけで、root は WARNING。httpx も
httpcore も、**まだ足していない将来の依存も**、既定で INFO を出せない。

### 教訓 B-2: 出さないなら、必要な情報は「安全な部品から組み立てて」出し直す

止めた直後の説明「必要な情報は `GradeResult` の再現性3つ組と `Job.last_error` に
残っている」は**間違いだった（レビュー4回目）**。採点が成功したときにしか成り立たない。
チェーンが 401/403/404 で全滅すると `GradeResult` は作られず、`Job.last_error` は
`"call failed"` に畳まれるので、`gcloud auth application-default login` のやり直し(401)・
API の有効化(403)・`AUTO_SCORING_GEMINI_MODEL` の綴り(404) が区別できない。
**「繋げない端末はそう言う」ためのIssueで、「繋がらなかった」しか言えない状態だった。**

直し方は「危ない文字列を濾す」ではなく **「安全な文字列を組み立てる」**:
`domain/ai_provider.py` の `ProviderAttempt` は provider の**固定識別子**（アダプタの
`name` リテラル。`describe().model` は設定なので使わない）・**例外クラス名**
（`ErrorCategory` と1:1）・**HTTPステータスの数値**しか持てない。例外メッセージ・
レスポンスボディ・URL・ヘッダは入れない。出口は2つ: `Job.last_error`（API と画面へ）と
`FallbackAIProvider` の WARNING 1行（フォールスルーした段ごと。成功して落ちたときも残る）。

**「全部のケースを診断できる」とは書けない。** 書けるのは「この3つを記録する」まで。

マスクは残してあるが、それは**このプロジェクト自身が書く文字列**（値を補間して作るので
変換が入らない）に対する網であって、ライブラリ出力に対する第一の防御ではない。
`secret_redaction.py` は「何に対応し、何に対応していないか」を明示している
（対応: 逐語一致。非対応: 大文字小文字の変換・URLエンコード・エスケープ・切り詰め・
複数引数への分割。**この一覧が網羅だとは主張しない**）。

### 教訓 C: テストは「認証情報が無い状態」だけを見ない

2 と 3 は「ADC があって実際に通信する」経路にしか無く、未設定だけを流していた漏洩テストでは
踏めなかった。`tests/test_sidecar.py` は実アダプタ・`MockTransport` の 404・実ハンドラを通し、
**ディスク上のバイト列**を検査する（大文字を含む値を使い、原文と小文字化後の両方を探す）。
同時に自前の INFO 行が残ることも確認する -- 「何も書かないビルド」で空振りに通らないように。

## Where the gate list lives

The gate list is defined in two places that must stay in step:

- `package.json` — the `check`, `check:pre-commit`, `check:pre-push` scripts.
- `.github/workflows/ci.yml` — one step per gate (split out so a failure names
  itself in the CI UI).

When you add or remove a gate, update both, and this table.

## Toolchain

| Tool    | Pin                                                       | Restored by                                    |
| ------- | --------------------------------------------------------- | ---------------------------------------------- |
| Node    | `.node-version`                                           | `pnpm install --frozen-lockfile`               |
| pnpm    | `package.json` `packageManager`                           | Corepack                                       |
| Flutter | `app/.fvmrc` (3.41.4 stable) + `.github/workflows/ci.yml` | `flutter pub get` (uses `app/pubspec.lock`)    |
| Python  | `backend/.python-version` (3.12)                          | `uv sync --locked` (downloads the interpreter) |
| uv      | `.github/workflows/ci.yml` (`setup-uv` version)           | —                                              |

`pnpm run bootstrap` restores all four in one step. CI (`.github/workflows/ci.yml`)
runs on `windows-latest` so the Flutter Windows debug build is exercised as a
merge gate; it installs the Flutter SDK (`subosito/flutter-action`) and `uv`
(`astral-sh/setup-uv`) before the gates.
