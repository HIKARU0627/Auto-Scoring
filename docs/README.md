# docs

Specification, technology decisions, PoC records, and operational procedures for
Auto-Scoring. The specification of record is
[simplified-design-specification.md](./simplified-design-specification.md); where
it and [technology-stack.md](./technology-stack.md) disagree, the latter wins and
the former is updated in the same PR.

## 仕様・設計

| 文書                                                                             | 内容                                                                                           |
| -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| [simplified-design-specification.md](./simplified-design-specification.md)       | 簡易設計書。要件・画面・データ・MVP範囲の正本                                                  |
| [technology-stack.md](./technology-stack.md)                                     | 技術スタックの決定と却下した代替案、リポジトリ構成、依存方向（現行 Flutter と移行後 Electron） |
| [frontend-migration.md](./frontend-migration.md)                                 | Flutter → Electron 移行の決定・段取り・cut-over 条件（Issue #201）                             |
| [frontend-invariants.md](./frontend-invariants.md)                               | `app/test` が固定しているフロントエンド不変条件の一覧（移植先の正本、Issue #204）              |
| [business-rules-and-evaluation-data.md](./business-rules-and-evaluation-data.md) | 採点業務ルールと評価用データ、未決定事項（OCRサービス・AIモデル）                              |
| [grading-material-structure.md](./grading-material-structure.md)                 | 実際の採点資料を調べた構造の記録（内容は載せない）。設計が耐えるべき既知のケース               |
| [data-model-and-local-storage.md](./data-model-and-local-storage.md)             | エンティティ・SQLite スキーマ・`app-data/` の配置と不変条件                                    |
| [sidecar-api.md](./sidecar-api.md)                                               | サイドカーのハンドシェイク・認証・OpenAPI → Dart クライアント生成                              |

## 機能ごとの実装決定

| 文書                                                                       | 内容                                                             |
| -------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| [test-registration.md](./test-registration.md)                             | テスト登録とテストプロファイルの生成・人間による確定             |
| [criteria-extraction.md](./criteria-extraction.md)                         | 採点基準PDFからの配点・採点基準の抽出と人による確定              |
| `intake-and-settings.md`（Issue #101 で追加予定）                          | 登録と答案取込の統合画面、ディレクトリ取込、命名規則（型）の設定 |
| [answer-area-detection.md](./answer-area-detection.md)                     | 答案から回答欄を検出し、答案の上で人が直して確定する             |
| [answer-intake-and-preprocessing.md](./answer-intake-and-preprocessing.md) | 生徒答案の取り込み、レンダリング、OpenCV 前処理、回答欄 crop     |
| [ocr-recognition-pipeline.md](./ocr-recognition-pipeline.md)               | 文字認識パイプラインと低 Confidence の扱い                       |
| [ai-grading-pipeline.md](./ai-grading-pipeline.md)                         | AI 採点パイプラインと構造化出力                                  |
| [dependency-graph.md](./dependency-graph.md)                               | 設問間の依存グラフと解放条件                                     |
| [job-queue.md](./job-queue.md)                                             | 非同期ジョブキュー、並列度、リトライ分類                         |
| [pdf-review-overlay.md](./pdf-review-overlay.md)                           | PDF 表示と Annotation Overlay、座標の正規化                      |
| [review-edit-history.md](./review-edit-history.md)                         | レビューの修正・承認・Undo と追記のみの履歴                      |
| [pdf-export.md](./pdf-export.md)                                           | 確定 Annotation を描画した添削済み PDF 出力                      |
| [mvp-acceptance.md](./mvp-acceptance.md)                                   | 簡易設計書 §31 の全実装項目と、それを検証しているテストの対応表  |
| [design-tokens.md](./design-tokens.md)                                     | 画面のデザイントークン（フォント選定・配色・余白・モーション）   |
| [home-dashboard.md](./home-dashboard.md)                                   | ホーム画面が出す「次の一手」と進捗の決め方、状態の取得元         |
| [review-queue.md](./review-queue.md)                                       | 答案キューの並び順・設問粒度の進捗・答案をまたぐ連続レビュー     |
| [dependency-dag-progress-view.md](./dependency-dag-progress-view.md)       | 添削レビュー画面で AI 処理の進捗を依存 DAG として見せる          |
| [ui-ux-multi-agent-evaluation.md](./ui-ux-multi-agent-evaluation.md)       | UI/UX を複数AIエージェントに独立評価させた記録と採否             |

## PoC 記録

| 文書                                                                     | 内容                                                  |
| ------------------------------------------------------------------------ | ----------------------------------------------------- |
| [poc-1-japanese-handwriting-ocr.md](./poc-1-japanese-handwriting-ocr.md) | 日本語手書き OCR 候補の比較と `OCRProvider` 契約      |
| [poc-2-ai-grading.md](./poc-2-ai-grading.md)                             | AI 採点候補の比較、構造化出力、transport 選択         |
| [poc-3-pdf-coordinates.md](./poc-3-pdf-coordinates.md)                   | Flutter(pdfium) と Python 間の PDF 座標往復誤差の検証 |
| [poc-4-multi-layout-profiles.md](./poc-4-multi-layout-profiles.md)       | 複数レイアウトのテストプロファイル生成・往復検証      |
| [poc-5-scan-to-scan-drift.md](./poc-5-scan-to-scan-drift.md)             | 別々にスキャンされた同一様式の紙のずれの実測          |

## 配布・開発環境・運用

| 文書                                                           | 内容                                                                       |
| -------------------------------------------------------------- | -------------------------------------------------------------------------- |
| [windows-distribution.md](./windows-distribution.md)           | Windows 配布物・サイドカーのライフサイクル・障害復旧・署名手順             |
| [linux-desktop-development.md](./linux-desktop-development.md) | Linux 開発機でアプリを起動・スクリーンショットする手順（配布対象ではない） |
| [quality-gates.md](./quality-gates.md)                         | `pnpm run check` の各gate、git hooks、CIの対応関係                         |
| [agent-orchestration.md](./agent-orchestration.md)             | 複数エージェントの並列開発。役割・Task単位・完了判定・環境構築・復旧       |
| [review-ready-skills.md](./review-ready-skills.md)             | レビュー準備Skill群の構成・同期・エージェント間互換                        |
| [ai-agent-git-attribution.md](./ai-agent-git-attribution.md)   | AIエージェントのコミット/pushを専用GitHub Appへ帰属させる手順（任意）      |
| [mcp.md](./mcp.md)                                             | MCPサーバー設定を3つのエージェント別ファイルへ展開する方法                 |
| [orca-remote-environment.md](./orca-remote-environment.md)     | Windows の Orca から Ubuntu 上の Orca ランタイムへ接続する構築・運用手順   |
