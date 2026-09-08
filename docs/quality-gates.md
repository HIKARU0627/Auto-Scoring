# Quality gates

Local commands and GitHub Actions run the same checks. Each check is a `scripts`
entry in `package.json`, invoked as `pnpm run <script>`.

| Gate               | Command                  | CI step (`.github/workflows/ci.yml`) |
| ------------------ | ------------------------ | ------------------------------------ |
| Agent skill mirror | `pnpm run skills:check`  | Check agent skill mirrors            |
| Formatting         | `pnpm run format:check`  | Check formatting                     |
| OpenAPI contract   | `pnpm run openapi:check` | OpenAPI contract                     |
| Lint               | `pnpm run lint`          | Lint                                 |
| Typecheck          | `pnpm run typecheck`     | Typecheck                            |
| Test               | `pnpm run test`          | Test                                 |
| Build              | `pnpm run build`         | Build                                |
| Everything         | `pnpm run check`         | (all of the above)                   |

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

## 新しい公開経路を作ったら、そこへ流れ込むものを全部見直す

Issue #97 は「なぜ採点が使えないかを画面で伝える」ために、`GET /grading/availability`
という**新しい公開経路**を作った。そこで既存の文字列が2回続けて漏れた:

1. `create_ai_provider()` の設定エラー本文（読めなかった温度の値・未知 transport 名・
   `AUTO_SCORING_CODEX_EXECUTABLE` の設定値）。「ログにしか出ない」前提で書かれていた。
2. Vertex アダプタが `AUTO_SCORING_VERTEX_PROJECT` / `AUTO_SCORING_GEMINI_MODEL` から
   組み立てる**リクエスト URL**。httpx が INFO で出し、サイドカーは root を INFO にして
   回転ファイルログへ書くため、404 応答だけで永続ログに残った。

どちらも「操作者が API キーを別の変数へ貼った」という同じ事故で、どちらも
**誰かが意図して作った経路ではない**。

**経路を数え上げるのではなく、外へ出る場所にゲートを置く。** 経路の列挙は必ず
取りこぼす（次はヘッダ、リトライの診断、例外の `__cause__` 連鎖）。
`backend/src/auto_scoring/api/secret_redaction.py` が「設定値とは何か」を1か所で定義し、
テキストがこのプロセスを出る2か所 -- `install_log_redaction`（ログ設定はここだけ。
uvicorn は `log_config=None` で起動するので uvicorn のロガーも root のハンドラを通る）と
`build_ai_provider`（reason を作るのはここだけ）-- が同じ規則を適用する。

ゲートはあくまで網であって免罪符ではない。値を本文に書くメッセージは今も不具合であり
（`adapters/ai_grading/factory.py` のモジュール docstring）、網はこのプロセスが
**設定として渡された値しか知らない**。

**テストは「認証情報が無い状態」だけを見ない。** 2 は「ADC があって実際に通信する」
経路にしか無く、未設定だけを流していた漏洩テストでは踏めなかった
（`tests/test_sidecar.py` の URL 漏洩テストは `MockTransport` の 404 で実際に通る）。

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
