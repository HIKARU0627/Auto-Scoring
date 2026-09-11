# AI 利用料の記録と表示（Issue #187）

GitHub Issue [#187](https://github.com/HIKARU0627/Auto-Scoring/issues/187)（親 [#3](https://github.com/HIKARU0627/Auto-Scoring/issues/3)）。
司令官決定（2026-09-11 コメント）に基づく設計記録。

## 何を解決するか

利用者が自分の API キーで採点する以上、**1 回の採点でいくら使ったか**と**月間の累計**をアプリが伝える。
推測した金額を確定した金額のように出さない（Issue #187 本文）。

## 採った案

### 1. 何を測るか — provider が返す usage（トークン数）

- 各 `AIProvider` アダプタが応答から `TokenUsage`（`input_tokens` / `output_tokens`）を読み取れるときだけ記録する。
- 返さない provider（例: Codex app-server、Vertex の一部経路）では **記録しない**（0 と書かない）。
- 金額換算は利用者が設定した **1000 トークンあたりの単価**（`GET/PUT /grading-cost`）があるときだけ行う。未設定なら取込画面と同様「単価が未設定」と言い、**0 円と表示しない**。
- 画面は次の 2 つを区別する:
  - **トークン数は分かるが単価未設定** → トークン数を出し、金額は出さない
  - **トークン数すら分からない** → 「トークン数: 不明」と出す（0 と表示しない）

### 2. どこに出すか

| 場所                                    | タイミング                                | 内容                                                                |
| --------------------------------------- | ----------------------------------------- | ------------------------------------------------------------------- |
| 答案確定画面（`SubmissionConfirmPage`） | 答案 1 枚の採点ジョブがすべて完了したあと | その 1 枚のトークン合計と、単価設定時のみ金額                       |
| 設定画面 API キータブ（`ApiKeyTab`）    | 常時（読み込み時）                        | 当月の自前積算累計                                                  |
| 設定画面 API キータブ                   | OpenRouter 疎通確認後                     | **別行**で provider 側の usage/limit（「provider 側の数字」と明示） |

### 3. どこに貯めるか — 既存の試行記録を拡張（新テーブルなし）

Issue #35 の `domain.ai_provider.ProviderAttempt` と成功時の `GradeResult` を拡張する。

- **成功した採点**: `GradeResult.input_tokens` / `output_tokens`（nullable。AI 行のみ）
- **フォールバック途中の失敗**: `ProviderAttempt` に同じ nullable トークン列を追加し、`jobs.provider_attempts`（JSON 列）に直列化して保存

usage は試行の属性であり、別テーブルに切らない。

### 4. OpenRouter の残高 — 混ぜない

- 自前積算（`GradeResult` のトークン × 単価）と provider の `GET /key` の usage/limit は **別行**。
- 合算・補完しない。OpenRouter 以外では provider 行を出さない。

## 捨てた案

| 案                                           | 理由                                                                                        |
| -------------------------------------------- | ------------------------------------------------------------------------------------------- |
| 呼び出し回数 × 手入力単価の概算              | 設問ごとに入力長が大きく変わり桁で外れる。司令官決定で不採用                                |
| 新テーブル `ai_usage_events`                 | 試行と usage の対応を自前で維持する羽目になる。司令官決定で不採用                           |
| リポジトリ内の vendor 料金表                 | 陳腐化する。PoC 2 §7.4 と同じ理由で `cost_usd` を記録しない方針を本番でも踏襲               |
| `classification_unit_cost`（取込単価）の流用 | 単位が「1 判定 1 回」でありトークン単位ではない（`docs/criteria-extraction.md` と同じ論点） |
| provider 残高を自前積算の代わりに使う        | アプリ外の利用も含む別物。混ぜると誤解を招く                                                |

## API（OpenAPI 変更）

共有スキーマのため PR 前に司令官へ相談する（Issue 指示）。変更内容:

1. `GradeResultResponse` — `input_tokens`, `output_tokens`（`integer | null`）
2. `GET` / `PUT` `/grading-cost` — `token_unit_cost: float | null`（1000 トークンあたり、未設定は `null`）
3. `GET` `/submissions/{submission_id}/ai-usage` — 答案 1 枚の集計
4. `GET` `/ai-usage/monthly` — 当月の自前積算累計
5. `VerifyApiKeyResponse` — `provider_account_usage`, `provider_account_limit`（OpenRouter のみ。nullable）

### `SubmissionAiUsageResponse`（新規）

```json
{
  "input_tokens": 1200,
  "output_tokens": 340,
  "token_unit_cost": null,
  "estimated_cost": null,
  "usage_availability": "known"
}
```

`usage_availability`:

- `known` — すべての AI 採点試行でトークンが記録されている
- `partial` — 一部のみ記録（合計は記録済み分のみ）
- `unknown` — 1 件もトークンが無い

`estimated_cost` は `token_unit_cost` が設定されかつ `usage_availability` が `known` のときだけ数値。それ以外は `null`。

## 実装順序

1. 本ドキュメント
2. usage 記録（backend アダプタ → `GradeResult` / `ProviderAttempt` → migration）
3. 集計 API
4. 答案確定画面
5. 設定画面の月間累計と OpenRouter provider 行
6. 受入テストと変異検査

## 変異検査（PR 記載用）

1. `formatAiUsageCost`（または同等）で「単価未設定でも金額を出す」形に一時的に戻す
2. `desktop/test/ai-usage-display.test.ts` が赤になることを確認
3. 元に戻して緑に戻す

手順と結果を PR 本文に書く。
