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

## 関連

- Issue #426（本 Issue）、#393（フレーク調査）、#417（backend の実時間待ち）
- `desktop/test/renderer/setup.ts`、`desktop/vitest.config.mts`、`desktop/playwright.config.ts`
