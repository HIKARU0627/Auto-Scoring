# Test timing（テストの待ち方）

`desktop` の renderer テスト（Vitest + React Testing Library）と、その e2e
（Playwright）で**非同期の待ち時間を誰が決めるか**、そして**何をしてはいけないか**を
固定する。Issue #426。

## なぜ文書にするか

待ち時間がホストの負荷で決まっていると、赤の意味が壊れる。あるワーカーが別の
変更を直している間の負荷で、無関係なテストが「1 秒に間に合わなかった」だけで赤く
なり、作業者は自分の変更を疑い、司令官は毎回「この赤は本物か」を切り分けることに
なる。`Quality` は必須 check なので、負荷由来の赤は main を止める。待ちの上限は
**負荷ではなく設定**で決める。

## 非同期の上限は設定で決める

- Vitest の `testTimeout` / `hookTimeout`（`desktop/vitest.config.mts`、60 秒）は
  `it` 全体の上限であって、`findBy*` / `waitFor` には効かない。
- RTL の非同期ユーティリティは**自前のタイムアウト**を持ち、既定は 1000ms。
  `desktop/test/renderer/setup.ts` が `configure({ asyncUtilTimeout: 5000 })` で
  既定を 5000ms にしている。
- 個々の呼び出しに `{ timeout }` を渡した場合はそちらが優先される。既存の
  `pdf-review-*.test.tsx` は `WAIT_MS = 5000` を明示しており、今回それと同じ予算を
  既定にした。
- 待ちはポーリングで、条件が満たされた時点で即座に返る。**固定 sleep は足していない。**

### 値（5000ms）の根拠とトレードオフ

2026-09-12 に `asyncUtilTimeout` を下げて renderer 全件（52 ファイル / 489 テスト）を
回した実測:

| `asyncUtilTimeout`     | 赤になるテスト | 内訳                                                                      |
| ---------------------- | -------------- | ------------------------------------------------------------------------- |
| 50ms                   | 7              | チャート系 4 + `grading-availability` 3                                   |
| 100ms                  | 2              | `home-chart-headroom.test.tsx`、`home-charts-f4b.test.tsx` のバー描画待ち |
| 250ms                  | 0              | —                                                                         |
| 500ms / 1000ms（既定） | 0              | —                                                                         |

つまり**100ms〜1000ms の帯に居るテストは 2 件**、50ms〜100ms の帯にも 5 件ある。
アイドル時点の実測最長は 250ms 未満なので、5000ms は約 20 倍の余裕に相当する。

トレードオフ: 上げれば負荷に強くなるが、**本当に壊れている**待ちは赤くなるまで
その秒数待つ。5000ms は「実測の 20 倍」と「壊れたときに 60 秒の `testTimeout` を
待ち切らない」の両立点として選んだ。より大きくすると壊れたテストのフィードバックが
遅れ、逆に小さくすると 1 秒問題を別の値に置き換えるだけになる。

### 経緯: Issue #393 の判断を置き換える

Issue #393（PR #400）は、負荷で赤くなる箇所を `findBy*` へ直し、**既定は上げず**、
決定的な合図が無い 1 か所だけ `{ timeout: 10000 }` を明示した（「既定を上げると
他のレースが見えなくなる」ため）。本 Issue #426 は、その方針を**計測に基づいて
置き換える**。待ちの長さはホスト性能ではなく設定で決める、という一点は同じで、
個別の `timeout` を足して回るより、既定を実測に足る値へ一度だけ上げる方が
「どのテストが特別扱いか」を消せる。5000ms は #393 が明示した 10000ms より小さく、
壊れた待ちのフィードバックは #393 の個別指定より速い。

## 固定スリープを使わない

`setTimeout` で待つ・`waitForTimeout` 相当で待つ、といった**固定スリープを足さない**。
遅いマシンで黙って偽陽性／偽陰性を作るだけで、上の「負荷で赤が決まる」問題を再生産
する。待つべきは「観測可能な状態」であり、`findBy*` / `waitFor` のポーリングで待つ。
方針は `docs/quality-gates.md` と `docs/linux-desktop-development.md`（固定 sleep ではなく
観測できるまでのポーリング）に揃える。

例外は**タイミングそのものを検証するテスト**で、`vi.useFakeTimers()` と
`vi.advanceTimersByTime(...)` で仮想時刻を進めるもの。実時間を消費せず、debounce の
境界を固定するためのものなので固定スリープではない。

## 操作した対象が、その操作で消えるとき（e2e）

「閉じる」ボタンや資料ウィンドウの「閉じる」のように、**click した対象がその click で
自分の page を消す**コントロールがある。Playwright の `click()` は
「actionability の確認 → dispatch → **後処理**」の順に進むため、dispatch で page が
先に消えると、後処理が**もう無い page** に当たって
`Target page, context or browser has been closed` で reject する。成功時も失敗時も
アプリの振る舞いは同じで、違うのは「閉じるのが後処理より速いかどうか」だけ
（Issue #466。Issue #417 / #439 / #446 と同じく**性質ではなくランナーの速さを測っている**）。
この reject を放置すると、同じ click が負荷次第で赤くなる。

対処は **reject を握りつぶすのではなく、責務を分ける**:

- 判定は `page.isClosed()`（操作した page が閉じたか）だけに任せる。
- click の reject は、**その時点で `page.isClosed()` が真のときだけ**捨てる。
  page がまだ開いているのに reject したなら、それは対象の不在・無効・detach などの
  本物の失敗なので rethrow する。
- 共通実装は `desktop/e2e/electron-launch.ts` の `clickClosingPage(target, page)`。
  window-controls の「閉じる」と material-window の「閉じる」が使う。

**「全部 `catch` で飲む」は禁止。** 飲むと**ボタンが壊れていても緑になる**。この形を
直したら、`desktop/src/` の閉じるハンドラ（`closeWindow` の IPC、資料ウィンドウの
`window.close()`）を一時的に no-op にする変異を入れ、**直したテストが確かに赤くなる**
ことを確かめる（`page.isClosed()` の poll がタイムアウトする）。これを示せない修正は
「落ちなくなっただけ」で検査を失っている。

`mainWindow.close()` のような **`page.close()` 自体はこの形ではない**。Playwright が
閉じる側なので後処理の競合が無く、そのまま `await` してよい（material-window の
「main window を閉じると material window も閉じる」がこれ）。

## 実時間の `wait` / `join` にアサーションを掛けない

実時間（`Date.now()` の差、`join` の所要時間など）をそのまま期待値にしない。
マシン負荷で値が変わるため、検証したい不変条件ではなくホスト性能をテストしてしまう。
backend 側で同じ形を Issue #417 が扱っている。**本 Issue はそのコードを触らない**（直すのは
#417 の担当）が、方針としてここに置く。振る舞いを固定したいなら、`Clock` などの注入した
境界を進めて検証する。

## 同期 `getBy*` を遷移直後に使わない

画面遷移や非同期ロードの直後に同期的な `getBy*` を使わない。まだ DOM が出ておらず、
負荷が乗るとだけ落ちる。`await screen.findBy*` か `await waitFor(...)` で
「その状態になるまで待つ」。`desktop/test/renderer/test-list-page.test.tsx` の
コメントが、実際にこの形で負荷時に落ちた例を残している。

## `waitFor` の中は `expect` だけにする

`waitFor` のコールバックは何度も呼ばれる。中で `fireEvent`・`userEvent`・タイマー
操作・再レンダーなどの**副作用を起こさない**。副作用は待ちの回数だけ暴れる。
2026-09-12 時点の全 `waitFor` 118 か所を走査し、副作用を持つものは **0 件**だった。
アサーション以外が必要なら、`waitFor` の外に出す。

## 単体（Vitest）と e2e（Playwright）でタイムアウトの持ち主が違う

- **Vitest**: `testTimeout` / `hookTimeout` は `desktop/vitest.config.mts`、`findBy*` /
  `waitFor` の予算は RTL（`asyncUtilTimeout`、本 Issue で 5000ms）。同じ秒数を
  使い回さない。
- **Playwright**: タイムアウトの持ち主は runner 側。`desktop/playwright.config.ts` の
  `timeout` / `expect.timeout` と、各呼び出しの `{ timeout }` で決まる。e2e は実プロセス
  起動を含むため別物で、Vitest 側の値とは揃えない（e2e の変更は Issue #425 の担当）。

## 内側のループの回し方（Issue #435）

`pnpm run check` は全スタックを回すので、コードを書いている最中のフィードバックには
遅すぎる。手を動かしている間は「変更した分だけ」を回し、押し切り前には必ず
`pnpm run check:pre-push`（Issue #409）と CI の必須 `Quality` を通す。

### 変更した分だけ回す

```bash
pnpm run test:app:changed
pnpm run test:backend:changed
pnpm run test:desktop:changed
```

- base は既定で `origin/main`（枝のコミットと未コミットの両方を見る）。
  `pnpm run test:app:changed -- --base HEAD` のように `--base <ref>` で変えられる。
- `--dry-run` を付けると、走らせるコマンドを表示して実行しない。
- `test:app:changed` / `test:backend:changed` は `scripts/changed-tests.mjs` が
  変更ファイルの module 参照（Dart の `package:auto_scoring_app/...`、Python の
  `auto_scoring....`）を test ファイルの本文と照合し、同名 stem も拾う。
  **import を直接辿れないテスト（ツリーを走査する不変条件テストなど）は選ばれない。**
  対応が取れなかった changed file は必ず標準出力に出す。
- `test:desktop:changed` は vitest の `--changed` に同じ base を渡す。選ぶのは
  vitest のモジュールグラフ。
- スタックのソースツリー外（`pubspec.yaml` など）を変更したときは、取りこぼしを
  避けるため**そのスタック全体**へ広げる。
- **これは押し切りの代わりではない。** 内側のループ専用である。push 前の検査は
  `pnpm run check:pre-push`、必須 check は CI の `Quality`。
- サイドカーを起動するテスト（app / desktop の一部）は、この開発機では
  `docs/linux-desktop-development.md` の env を前置する（Issue #425）。付けないと
  「起動を待って諦めた時間」を測ることになる。

### 内側のループと押し切りで並列度が違う（Issue #453）

backend の**押し切り**（`pnpm run check:pre-push`、`pnpm run check`、CI）は
`backend/pyproject.toml` の `addopts = "-m 'not live' -n auto --dist loadfile"` で
並列のまま回す（Issue #433）。`--dist loadfile` はテストモジュールを1ワーカーに固定する。

**内側のループ（`pnpm run test:backend:changed`）は、選ばれたのが 7 ファイル以下なら
`-n0` を足して直列に戻す。** `scripts/changed-tests.mjs` の backend ランナーが、
選択数だけを見て切り替える。8 ファイル以上は `addopts` の並列をそのまま使う。

理由は実測。開発機（12 コア）で `uv sync` 後、`uv run pytest <files>` を
既定（`-n auto --dist loadfile`）と `-n0` で交互に回した（2026-09-13、3〜5 回の最小値）:

| 選んだファイル          | 既定（`-n auto`） | `-n0`  |
| ----------------------- | ----------------- | ------ |
| 1（速い単体テスト）     | 1.94s             | 0.56s  |
| 5（速い単体テスト）     | 2.81s             | 1.27s  |
| 8（やや重いものを含む） | 8.91s             | 9.79s  |
| 12（同上）              | 9.41s             | 13.05s |

1〜5 ファイルでは `-n auto` の起動費（約 1.5 秒。`--dist loadfile` のせいで
残りのワーカーは仕事が無くても起動・終了する）が実行時間を上回る。8 ファイルで
並列が逆転し、それ以上では並列が勝つ。だから**境目を 7 ファイル**（8 以上は並列）に置く。

ファイル数は「重さ」の完全な代理ではない。`--dist loadfile` なので、重い e2e を1つだけ
選んだ場合は直列でも並列でもほぼ同じ（並列側に起動費が乗るだけ）で、並列が効くのは
重いファイルが**複数**選ばれたとき。このリポジトリの実際の選択を数えると、重い
e2e が複数入る選択は 11 ファイル以上だった（`backend/src/auto_scoring/domain/models.py` で
43 ファイルなど）ため、7 ファイルの境目で足りる。選択の全体像は
`scripts/changed-tests.mjs` の `BACKEND_SERIAL_MAX_FILES` のコメントに残す。

### watch モード

- desktop は `pnpm run test:desktop:watch`（vitest の watch）。
- app は `flutter test` に watch が無い（1 回限りの runner）ため入れない。IDE の
  テストランナーか `--plain-name` で絞る。
- backend は `pytest-watch` を足すことになるが、backend の依存追加は Issue #433 の
  担当なので、この Issue では入れない。

## 関連

- Issue #426（本 Issue）、#393（フレーク調査）、#417（backend の実時間待ち）、
  #435（内側のループの入口）、#466（操作が対象を消す e2e の待ち方）
- `desktop/test/renderer/setup.ts`、`desktop/vitest.config.mts`、`desktop/playwright.config.ts`、
  `desktop/e2e/electron-launch.ts`
