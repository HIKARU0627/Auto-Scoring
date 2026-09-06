# AI一次添削支援アプリ 簡易設計書

## 1. 概要

### 1.1 目的

塾からPDF形式で提供される以下の資料を利用し、答案添削作業を効率化する。

- 生徒答案
- 模範解答
- 採点・添削マニュアル

AIが一次添削を行い、人間はAIの結果を確認・修正・承認することを基本とする。

完全自動採点ではなく、**Human-in-the-loop型の添削支援システム**として設計する。

効率的に採点を行うために並列で採点を行えるようにする。

---

## 2. システムの基本方針

### 2.1 AIの役割

AIは以下を担当する。

- 生徒答案の読み取り
- 模範解答との比較
- 採点マニュアルに基づく判定
- 点数候補の生成
- ○・×等の添削記号候補の生成
- コメント候補の生成
- 判定根拠の生成
- 判定信頼度の算出

AIの判定を最終結果とはしない。

### 2.2 人間の役割

人間は以下を担当する。

- AIによる文字認識結果の確認
- AI採点結果の確認
- 添削位置の確認
- 点数・コメントの修正
- AI結果の承認または却下
- 判読困難な答案の手動添削

---

# 3. 対象環境

## 3.1 アプリ形式

Windows向けデスクトップアプリを基本とする。

### 暫定技術

- Flutter
- Dart
- Material Design 3

### 対応プラットフォーム

- Windows以外も対応するか
  - macOS、Linuxへは将来的に対応させる

---

# 4. 入力データ

## 4.1 必須入力

1つのテストについて以下を登録する。

### 模範解答PDF

採点基準となる正答を取得するために使用する。

### 採点マニュアルPDF

以下の情報を抽出する。

- 配点
- 加点条件
- 減点条件
- 部分点
- 許容表現
- 添削コメント規則
- その他採点上の注意事項

### 生徒答案PDF

実際に添削する対象。

---

## 4.2 PDF構造

テストごとにPDFレイアウトが異なることを前提とする。

そのため、

> 全テスト共通の固定座標

は使用しない。

代わりに、テスト単位で「テストプロファイル」を生成する。

---

# 5. テストプロファイル

## 5.1 概要

新しいテストを登録した際に、PDFの構造を解析し、そのテスト専用の情報を保存する。

例：

```text
テスト
 ├─ Page 1
 │   ├─ 問1
 │   ├─ 問2
 │   └─ 問3
 │
 └─ Page 2
     ├─ 問4
     └─ 問5
```

## 5.2 保存する情報

設問ごとに以下を保持する。

- 問題番号
- ページ番号
- 問題文領域
- 回答欄領域
- ○×等を配置する候補領域
- コメント配置候補領域
- 配点
- 採点ルール
- 模範解答

座標については可能な限り0〜1の正規化座標で保持する。

> PoC 4（Issue #15）でこのスキーマの往復（生成→人間確認→再適用）を検証した。
> ドメインモデルは `RegionKind`（問題文領域／回答欄領域／○×等の候補領域／配点／
> 採点ルール／模範解答）ごとに `Region` を持ち、`Profile.status` が
> `DRAFT`（未確認）→`CONFIRMED`（確認済み）の一方向で遷移する。詳細は
> [`poc-4-multi-layout-profiles.md`](./poc-4-multi-layout-profiles.md)。

例：

```json
{
  "questionId": "q3",
  "page": 2,
  "answerArea": {
    "x": 0.15,
    "y": 0.42,
    "width": 0.7,
    "height": 0.18
  }
}
```

---

# 6. テスト登録フロー

```text
模範解答PDF
+
採点マニュアルPDF
        ↓
PDF解析
        ↓
問題・回答欄・採点基準をAIが推定
        ↓
テストプロファイル生成
        ↓
人間による確認
        ↓
必要なら領域・採点基準を修正
        ↓
テスト登録完了
```

## 6.1 重要方針

AIによるレイアウト推定を無条件で採用しない。

初回のみ人間が、

- 設問の対応
- 回答欄
- 配点
- 採点基準

を確認する。

---

# 7. 答案解析

## 7.1 前処理

答案PDFをページ単位で画像化する。

必要に応じて以下を行う。

- 傾き補正
- 回転補正
- 拡大縮小補正
- ノイズ低減
- コントラスト調整
- テストプロファイルとの位置合わせ

画像処理にはOpenCVを使用する。

> 取込・保存・前処理の実装はIssue #17で行った。PDFの検証（拡張子・MIME・magic bytes・
> size上限・page数・暗号化・破損）、同一PDFの再取込方針、回答欄切り出しは
> 「テストプロファイルとの位置合わせ」ではなく`Question.answer_area`
> （Issue #11で導入済みの設問ごとの正規化座標）を直接使う実装とした。
> デスキュー等の前処理はプレビュー画像にのみ適用し、切り出し座標には影響しない。
> 詳細・未決事項は[`answer-intake-and-preprocessing.md`](./answer-intake-and-preprocessing.md)。

---

# 8. 手書き文字認識

## 8.1 基本方針

OCR結果のみを信用しない。

以下の2種類を組み合わせる。

```text
答案画像
   ├─ OCR
   │    ├─ 認識文字
   │    ├─ Bounding Box
   │    └─ Confidence
   │
   └─ Vision AI
```

Vision AIには可能であれば、

- 元答案画像
- OCR結果
- 模範解答
- 採点ルール

を同時に入力する。

---

## 8.2 Confidence

文字認識について信頼度を保持する。

例：

```text
HIGH
MEDIUM
LOW
```

または、

```text
0.00 ～ 1.00
```

### 低Confidenceの場合

自動で確定しない。

UI上で、

> 文字認識要確認

として人間へ提示する。

---

## 8.3 OCR技術

### OCR技術

以下のどれを使用するかは実際のパフォーマンステスト後に決定する。

- Vision対応LLM
- Google Document AI
- Azure AI Vision
- ローカルOCR
- 複数方式の併用

最初から固定しない。

`OCRProvider`として抽象化する。

---

# 9. AI採点

## 9.1 入力

設問ごとに以下をAIへ入力する。

- 問題文
- 生徒答案画像
- OCR結果
- 模範解答
- 採点基準
- 配点

---

## 9.2 出力

AIから自由文だけを返させず、構造化データとして取得する。

例：

```json
{
  "questionId": "q3",

  "recognition": {
    "text": "光合成によって酸素が発生する",
    "confidence": 0.91
  },

  "grading": {
    "score": 4,
    "maxScore": 5,
    "confidence": 0.88
  },

  "criteria": [
    {
      "id": "criterion-1",
      "result": "pass",
      "confidence": 0.97
    },
    {
      "id": "criterion-2",
      "result": "partial",
      "confidence": 0.76
    }
  ],

  "comment": "理由の説明が不足しています。",

  "annotations": []
}
```

---

# 10. 採点Confidence

以下のConfidenceは分離する。

### Recognition Confidence

文字を正しく読み取れた可能性。

### Grading Confidence

読み取った答案に対して採点が正しい可能性。

例えば、

```text
文字認識：98%
採点判断：63%
```

という状態を許容する。

---

# 11. 添削Annotation

## 11.1 対応候補

以下を扱える設計とする。

- ○
- ×
- △
- チェック
- 下線
- 取り消し線
- 囲み
- コメント
- 点数

### 別候補

実際の塾の添削ルールで必要なAnnotation種類を確認する。

---

# 12. Annotation位置決定

## 12.1 基本方針

AI自身にPDF座標を直接推測させない。

例えばAIは、

```json
{
  "target": "行く",
  "type": "correction",
  "comment": "過去形"
}
```

までを返す。

座標決定はアプリ側が担当する。

---

## 12.2 固定領域への記号

○・×・得点など、設問単位の記号については、

```text
Question
↓
テストプロファイル
↓
Annotation配置領域
```

から位置を求める。

---

## 12.3 特定文字への添削

OCRが取得したBounding Boxを利用する。

```text
AI
「この単語を訂正」

↓


OCR
対象単語のBounding Box

↓

Annotation位置決定
```

---

## 12.4 位置特定できない場合

無理に本文付近へ配置しない。

設問単位のコメント領域へ退避させる。

例：

```text
問3

⚠ 時制表現について確認
```

---

# 13. PDF表示

## 13.1 編集中

元PDF自体は直接編集しない。

```text
PDF
+
Annotation Overlay
```

として表示する。

### 利点

- ○×を移動可能
- コメントを編集可能
- AI添削を削除可能
- Undo可能
- PDF破損を防止

---

# 14. PDF出力

人間によるレビュー完了後、

```text
元PDF
+
確定Annotation
        ↓
pypdfium2 + pypdf
        ↓
添削済みPDF
```

> PDF ライブラリは PoC 3（Issue #12）で `pypdfium2` + `pypdf` に確定した。
> 経緯は [`technology-stack.md`](./technology-stack.md) §3.1 /
> [`poc-3-pdf-coordinates.md`](./poc-3-pdf-coordinates.md)。

として新しいPDFを生成する。

元PDFは変更しない。

---

# 15. メインUI

Material Design 3を利用する。

基本レイアウト：

```text
┌─────────────────────────────────────────────┐
│ Top App Bar                                 │
├──────────┬───────────────────┬──────────────┤
│          │                   │              │
│ Navigation│                  │ Inspector    │
│ Rail      │    PDF Viewer    │              │
│          │                   │ AI採点結果   │
│ 問1       │                   │ 採点基準     │
│ 問2       │                   │ コメント     │
│ 問3       │                   │ Confidence   │
│          │                   │              │
├──────────┴───────────────────┴──────────────┤
│ 修正       却下             承認して次へ    │
└─────────────────────────────────────────────┘
```

---

# 16. 主な画面

## 16.1 ホーム

表示内容：

- テスト一覧
- 最近使用したテスト
- 新規テスト登録
- 添削途中答案

---

## 16.2 テスト登録画面

入力：

- 模範解答PDF
- 採点マニュアルPDF

処理：

- PDF解析
- 採点ルール抽出
- テストプロファイル生成

> Issue #16でFlutter側の画面（`app/lib/features/test_registration/`）とAPI
> （`POST /tests`ほか）を実装した。登録直後はテストプロファイルも設問依存関係グラフも
> 未確認の`draft`状態で、両方を確認・確定するまでテスト登録は完了しない（§6.1）。
> 詳細は[`test-registration.md`](./test-registration.md)。

---

## 16.3 テスト設定画面

確認・修正：

- ページ
- 設問
- 回答欄
- 配点
- 採点基準
- Annotation領域
- 設問依存関係グラフ（Issue #26のedge候補・並列実行層。確認するまで登録完了にならない）

> Issue #16で実装。§13の「PDF + Annotation Overlay」表示ではなく、region一覧を
> フィールド編集するUIとした（PDFオーバーレイでの視覚編集は未実装、後続Issueで検討）。
> 詳細・理由は[`test-registration.md`](./test-registration.md)。

---

## 16.4 答案取込画面

生徒答案PDFを追加する。

> Issue #17でFlutter側の画面（`app/lib/features/answer_intake/`）とAPI
> （`POST /tests/{test_id}/submissions`ほか）を実装した。取込方式は
> business-rules-and-evaluation-data.md §2 (4) の確定（1PDF = 1生徒、生徒識別は
> 人間が手動割当）に従う。詳細は
> [`answer-intake-and-preprocessing.md`](./answer-intake-and-preprocessing.md) §9・§11。

### 取り込み方法

取り込み方法を選択できるようにする

- 1PDF = 1生徒か
- 1PDFに複数生徒が含まれるか
- PDFファイル名に生徒識別情報が含まれるか
- 一括投入方法

---

## 16.5 添削レビュー画面

中央：

- PDF

右：

- AI認識文字
- 点数
- 採点根拠
- Confidence
- コメント
- 採点基準

操作：

- 承認
- 修正
- 却下
- AI再判定
- Annotation移動
- Annotation追加
- Annotation削除

---

# 17. キーボード操作

大量答案を処理するため、マウス操作だけに依存しない。

候補：

```text
Enter
→ 承認して次へ

E
→ 編集

X
→ AI結果却下

↑ ↓
→ 設問移動

Ctrl + Z
→ Undo
```

---

# 18. データ管理

## 18.1 DB

SQLiteを基本とする。

保持する主なEntity：

```text
Test

Question

Rubric

Submission

RecognitionResult

GradeResult

Annotation

Review
```

> 複数設問の依存関係（Issue #26）は上記に加えて `DependencyGraph` /
> `DependencyEdge` をテスト単位・バージョン管理で保持する。draft（AI候補）→
> 人間確認→confirmed の流れと、confirmed graphのみがSubmission処理を許可する
> ゲートは [`dependency-graph.md`](./dependency-graph.md) を参照。

---

# 19. Review履歴

AI結果と人間の最終判断は両方保存する。

例：

```text
AI
4 / 5点

↓

Human
3 / 5点
```

として記録する。

目的：

- 修正内容の確認
- AI精度評価
- 将来的な改善
- Undo
- 操作履歴

---

# 20. AI Provider

AIサービスをアプリ本体から分離する。

```text
AIProvider
 ├─ OpenAIProvider
 ├─ GeminiProvider
 ├─ ClaudeProvider
 └─ LocalProvider
```

---

# 21. バックエンド

暫定：

```text
Python
+
FastAPI
```

担当：

- PDF解析
- PDF生成
- OCR
- AI通信
- OpenCV画像処理
- テスト構造解析

Flutterとlocalhost通信する。

---

# 22. PDF処理

Python側で `pypdfium2`（ラスタライズ）と `pypdf`（オーバーレイ・出力）を利用する
（PoC 3 / Issue #12 で確定。旧記載は PyMuPDF）。

用途：

- PDF読込
- ページ画像化
- 座標取得
- Annotation描画
- PDF出力

---

# 23. ファイル構成

概念上は以下のように管理する。

```text
app-data/

├─ database.sqlite

├─ tests/
│   └─ <test-id>/
│       ├─ model-answer.pdf
│       ├─ manual.pdf
│       └─ profile.json
│
├─ submissions/
│   └─ <submission-id>/
│       └─ source.pdf
│
└─ exports/
    └─ corrected.pdf
```

実際の保存方式は実装時に決定する。

---

# 24. エラー処理

以下を正常系とは別に扱う。

### PDF解析失敗

人間に通知する。

### 回答欄検出失敗

手動領域指定へ切り替える。

### OCR失敗

答案画像をそのまま人間へ提示する。

### AI API失敗

再実行可能にする。

### AI低Confidence

自動確定せず要確認状態にする。

### Annotation位置特定失敗

設問コメント領域へ退避する。

### PDF出力失敗

元PDFを破壊しない。

---

# 25. 状態管理

答案・設問は最低限以下の状態を持つ。

```text
未処理

AI処理中

AI処理済み

要確認

確認済み

出力済み

エラー
```

---

# 26. セキュリティ・個人情報

答案には個人情報が含まれる可能性がある。

そのため基本方針として、

- 元答案をクラウドストレージへ自動アップロードしない
- ローカル保存を基本とする
- 不要な外部通信を行わない
- APIへ送信するデータを必要最低限にする

---

# 27. データ保持

以下を決定する必要がある。

- 元答案の保存期間
- 添削済み答案の保存期間
- AIログの保存期間
- 生徒名等をDBへ保存するか
- アプリ終了後も答案を保持するか
- 一括削除機能が必要か

---

# 28. ログ

最低限以下を記録する。

- AI処理成功 / 失敗
- OCR失敗
- PDF解析失敗
- AI採点結果
- 人間による修正
- PDF出力結果

ただし、生徒答案本文をデバッグログへ無条件に書き込まない。

---

# 29. パフォーマンス

大量答案を想定し、

```text
答案1 → AI処理
答案2 → AI処理
答案3 → AI処理
...
```

をバックグラウンドキューとして処理できる構造にする。

人間が答案1をレビューしている間に、

```text
答案2
答案3
答案4
```

のAI処理を進められる構造を目標とする。

---

# 30. PoC

本格実装前に以下を検証する。

## PoC 1

手書き認識。

実際の答案で、

- 綺麗な字
- 普通の字
- 汚い字

をどの程度認識できるか確認する。

---

## PoC 2

採点。

実際の、

- 模範解答
- マニュアル
- 答案

を利用して、人間の採点との一致率を測定する。

---

## PoC 3

PDF座標。

PDF上の特定位置へ、

- ○
- ×
- コメント

を正しく表示・出力できるか確認する。

---

## PoC 4

レイアウト変更。

異なる形式のテストを複数投入し、

```text
テストプロファイル生成
↓
人間による修正
↓
各答案への適用
```

> PoC 4（Issue #15）で「生成 → 人間確認 → 再適用」の往復が成立することを検証した。
> プロファイルは常に未確認（DRAFT）で保存され、人間確認（`Profile.confirm`）を経て
> はじめて答案へ再適用できる。詳細・fixture・実測値は
> [`poc-4-multi-layout-profiles.md`](./poc-4-multi-layout-profiles.md)。

が機能するか確認する。

---

# 31. 最初のMVP

最初のバージョンでは以下に限定する。

### 実装する

- テスト登録
- 模範解答PDF読込
- マニュアルPDF読込
- 生徒答案PDF読込
- PDF表示
- AI文字認識
- AI採点
- 点数表示
- ○×表示
- コメント表示
- AI結果修正
- AI結果承認
- 添削済みPDF出力

### 後回し候補

- AIの自動学習
- クラウド同期
- 複数端末同期
- チーム共有
- 詳細な分析ダッシュボード
- 完全自動添削
- 複数AIによるConsensus採点

---

# 32. 技術スタック

> 本章の暫定項目・抽象化（`AIProvider` / `OCRProvider` 等）の最終決定は
> `[technology-stack.md](./technology-stack.md)`（技術スタック調査・決定書）にまとめた。
> 食い違う場合はそちらを優先する。

## Desktop / UI

```text
Flutter
Dart
Material Design 3
```

## Backend

```text
Python
FastAPI
Pydantic
```

## PDF

```text
pypdfium2 + pypdf
```

## Image Processing

```text
OpenCV
```

## Database

```text
SQLite
```

## AI

```text
AIProvider abstraction
```

具体的なモデルは要判断。

## OCR

```text
OCRProvider abstraction
```

具体的なサービスはPoC後に判断する。

---

# 33. 未決定事項

実装前またはPoC後にユーザー判断が必要な項目。
各項目の現時点の反映状況は `[technology-stack.md](./technology-stack.md)` §7 を参照。

業務ルール・対象範囲・データ保持（本章の項目 4〜18、20〜23 および §27・§31）の確定は
`[business-rules-and-evaluation-data.md](./business-rules-and-evaluation-data.md)`（GitHub
Issue #8）で行った。食い違う場合はそちらを優先する。

1. Windows専用とするか
2. 使用するAIモデル
3. 使用するOCR
4. 外部AI APIへ答案を送信可能か
5. 答案PDFの実際のファイル構造
6. 1PDFあたりの生徒数
7. 必要な添削記号
8. コメントの記入ルール
9. 点数の記入位置
10. 採点方式

- 加点式
  - 減点式
  - 両方

1. 部分点の扱い
2. 記述式以外の問題を対象とするか
3. 数式を対象とするか
4. 英作文を対象とするか
5. 図・グラフ問題を対象とするか
6. 答案保存期間
7. AI処理履歴保存期間
8. 生徒識別情報を保存するか
9. AI低Confidenceの基準値
10. PDF出力形式
11. 元PDFへ上書きするか

- 原則として新規PDF出力を推奨

1. キーボードショートカット
2. AIによる自動コメント生成をどこまで許可するか
3. 複数答案の並列AI処理数

---

# 34. 全体処理フロー

```text
【テスト登録】

模範解答PDF
+
採点マニュアルPDF
        ↓
AI / PDF解析
        ↓
テストプロファイル
        ↓
人間が確認
        ↓
登録


【答案処理】

生徒答案PDF
        ↓
画像前処理
        ↓
レイアウト位置合わせ
        ↓
回答欄抽出
        ↓
OCR + Vision
        ↓
文字認識
        ↓
採点AI
        ↓
点数 / コメント / Annotation
        ↓
PDF Overlay
        ↓
人間レビュー
        ↓
承認 / 修正 / 却下
        ↓
PDF書き込み
        ↓
添削済みPDF
```

---

# 35. 設計上の最重要原則

本システムでは以下を守る。

1. AIの結果を無条件で確定しない
2. 読めない文字を無理に推測しない
3. AIにPDF座標を直接決めさせない
4. 元PDFを破壊しない
5. AI結果と人間の最終結果を分離して保持する
6. OCR・AIサービスを交換可能にする
7. テスト形式が変わることを前提とする
8. 人間の確認作業自体を高速化する
9. 生徒データの外部送信可否を最優先で確認する
10. 実際の答案を用いたPoCで精度を確認してから本格開発する
