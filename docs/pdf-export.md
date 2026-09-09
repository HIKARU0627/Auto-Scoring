# 添削済みPDF出力

GitHub Issue [#23](https://github.com/HIKARU0627/Auto-Scoring/issues/23)（親
[#3](https://github.com/HIKARU0627/Auto-Scoring/issues/3)）の実装記録。対象は
全設問の人間レビュー完了後、元PDFを変更せず確定済みAnnotationを描画した新しい
添削済みPDFを生成する機能一式 -- バックエンドの生成・永続化・API
(`backend/src/auto_scoring/domain/pdf_export.py` /
`domain/annotation_layout.py` / `adapters/pdf/pdfium_pypdf_engine.py` の
`render_annotations` / `jobs/export_processor.py` /
`api/export_router.py`) と、Flutter側の出力実行・進捗・保存先表示・再試行
(`app/lib/features/pdf_review/export_dialog.dart`)。

依存: #12（PDF座標往復・`PdfEngine`契約、PoC 3）、#22（レビュー操作履歴 --
`domain.review_workflow.effective_latest_review`/`resolve_effective_grade`
をそのまま再利用する）。

## 1. 全体フロー

```text
POST /submissions/{id}/export
        ↓
未確認設問チェック（domain.pdf_export.unconfirmed_question_ids）
  → 1件でもあれば409、対象question_idを返して終了
        ↓
書く場所チェック（domain.pdf_export.unplaceable_question_ids、Issue #120）
  → 1件でもあれば409、対象question_idを返して終了
        ↓
review-version snapshotを計算し、直近の成功Exportと比較
（domain.pdf_export.decide_reexport）
        ↓
[reuse_existing] 何もせず既存Exportをそのまま返す（200）
[accept_new / accept_new_superseding] Job(kind=EXPORT)を作成しqueueへ投入（202）
        ↓
ExportJobProcessor.process（jobs/export_processor.py）
  1. 設問ごとに resolve_effective_grade で確定Gradeを解決
  2. build_export_marks でAnnotationを座標解決（annotation_layout.py）
  3. app-data外のtemp fileへ PdfEngine.render_annotations で生成
  4. page数などを検証（失敗すればここで打ち切り、DB/app-dataに一切触れない）
  5. transactional_operation: Export行のcommit成功後にのみ
     app-data/exports/ へatomic rename
```

## 2. Annotation位置解決（`domain/annotation_layout.py`）

`app/lib/core/pdf_review_geometry.dart`（Issue #21/#22）の
`resolveAnnotationRect`をPythonへ移植したもの。添削レビュー画面が確定させた
Annotationの位置と、最終PDFに描画される位置が一致することを保証するため、
Dart側と同じ解決順序（簡易設計書 §12.1-12.4）を踏襲する:

1. `Annotation.rect`が明示されていればそのまま使う。
2. `anchor_text`があれば、そのGrade attemptのOCR `RecognitionResult.boxes`と
   完全一致で突き合わせ、`Question.answer_area`でcrop相対座標をpage相対座標へ
   変換する（新しい試行を優先、`recognitions_up_to_attempt`で
   attemptスコープを絞る）。
3. それでも解決できないものは`None`を返す。**答案の上には何も描かない。**

Dart側とPython側は別言語のため実装は共有できない。両者が同じ挙動になることは
`app/test/pdf_review_geometry_test.dart`と
`backend/tests/test_annotation_layout.py`をそれぞれ用意して担保する。

### 2.1 SCOREの描画文字列は確定Gradeから直接組み立てる

AIが提案するSCORE種別Annotationの`comment`フィールドは自由文字列であり、
人間が編集で点数を修正した後もAI提案時点の文字列のまま残り得る
（`docs/review-edit-history.md` §5「Annotationの図形編集はIssue #22の
対象外」）。出力するSCOREテキストは`Annotation.comment`を一切使わず、
その設問の確定`GradeResult.score`（`f"{awarded}/{maximum}"`）から
毎回組み立てる（`domain.pdf_export.build_export_marks`）。こうすることで、
表示される点数が常に実際に確定した点数と一致することを保証する。

#### 2.1.1 点数はSCORE種別Annotationを待たずに必ず描く（Issue #120）

上の規約には抜けがあった。**描画文字列は確定Gradeから作っていたが、
そもそもマークを作るきっかけがAIの提案だった。**`AnnotationKind.SCORE`の
`Annotation`を生成するコードはこのリポジトリのどこにも無く
（テストだけが作っていた）、実機検証ではどのプロバイダも SCORE 種別を
返さなかった。結果として**出力PDFに点数が1文字も描かれなかった。**

`build_export_marks`は、`score_area`を持つ設問について**必ず1つ**
SCOREマークを出す。AIがSCORE種別を返してきた場合はそれを別マークにしない
（同じ位置に同じ文字列を重ねて描くことになるため）。
確定Gradeが唯一の出所という §2.1 の規約はそのままで、
**来ないかもしれない提案を待つのをやめた**だけである。

#### 2.0.1 固定位置種別のscore_areaフォールバックは廃止した（Issue #141）

上の手順3には長らく「○×△・点数などの固定位置種別は`Question.score_area`
へフォールバックする（§12.2）」という段があった。**これを廃止した。**

§12.2 は「解答全体に対する記号」を Annotation 配置領域へ置く規約であって、
「AIが指した語をこちらが見つけられなかった」場合の規約ではない。
2つは別のことなのに、同じ退避先に集められていた。

実機再検証では、AIが作った注釈14件が**1件残らずこの経路を通った**
（一致条件については §2.4）。さらに Issue #120 以降、`score_area` は
回答欄と同じ高さの帯として導出される。結果、ある教科の出力PDFには
**ページの高さの23%を横切る赤い×**が、しかも点数と同じ矩形に重ねて
描かれた。誤りは式の一部分なのに、答案全体を消したように見える。

**位置が分からないなら、答案の上には何も描かない。**
§12.4 が最初からそう書いている（「無理に本文付近へ配置しない」）。
記号は §2.3 の余白帯へ、「位置特定できず」と添えて文字で出す。

明示`rect`がある場合（人がレビュー画面で置いた印）は従来どおり答案の上に
描く。**位置が分かっているものまで余白へ追い出すわけではない。**

同じ判断を Dart 側（`app/lib/core/pdf_review_geometry.dart`）にも入れる。
両者は同じ位置解決を別実装で持っており（§2 冒頭）、片方だけ直すと
レビュー画面とPDFで位置がずれる。レビュー画面では、置けなかった注釈は
Inspector の「設問コメント」欄に出る（`_fallbackAnnotationsFor`）——
つまり画面側の退避先は元から §12.4 のとおりだった。

### 2.2 位置解決できないAnnotationは`comment_area`へ退避する

`resolve_annotation_rect`が`None`を返した場合、そのAnnotationの図形は
描かず、コメント文だけを`Question.comment_area`
（簡易設計書 §12.4「設問単位のコメント領域へ退避させる」）へ
「位置特定できず」を添えて書く（§2.3）。
`comment_area`も未設定の場合はそのAnnotationの描画を諦める（スキップする）。

#### 2.2.1 「comment_areaは常に設定される前提」は崩れていた（Issue #120）

ここには長らく次の未決事項が残っていた ——
「テスト登録時に`comment_area`は常に設定される前提のため実運用では
発生しないはずだが、万一発生した場合に例外で全体を失敗させるより、
確定した他のAnnotationは出力しきる方を選んだ」。

**この前提はすでに崩れていた。**`score_area`/`comment_area`は
`SCORE`/`ANNOTATION_AREA`領域からしか作られないのに、Issue #103 が
「配点の入力口を1つに絞る」ため`SCORE`領域を画面から外し、
`ANNOTATION_AREA`はそもそも新経路の画面に無い。したがって
Issue #101 → #103 → #105 で登録したテストは**全設問で両方とも`None`**であり、
「発生しないはず」が100%発生していた。#103 の判断自体は正しく、
見落としていたのは**それに依存していた側**である。

Issue #120 で次の3つを決めた。

**(1) 書く場所は確定済み回答欄から導出する**
（`domain.annotation_layout.derive_mark_areas`）。回答欄の**真下の帯**
（回答欄と同じ高さか、ページに残っている分の少ない方）を使い、
右 20% を点数、残りをコメントに割る。人が赤ペンを入れる場所であり、
生徒が書いた内容の上に重ならない。回答欄がページ下端まで達していて帯が
取れない場合だけ回答欄そのものへ退避する（答案の上に重なるのは良くないが、
何も描かれていないPDFよりは良い）。

導出は**登録時**（`build_questions_and_rubrics`）に`Question`へ書く。
出力時だけで解決しなかったのは、添削レビュー画面が
`app/lib/core/pdf_review_geometry.dart`という**別実装**で同じ位置解決を
しているためで（§2 冒頭）、片側だけ導出すると画面とPDFで位置がずれる。
登録時に書けばAPI応答に載り、Dart側は変更なしで一致する。

**手で置いた`SCORE`/`ANNOTATION_AREA`領域があればそちらが優先される。**
導出はあくまで誰も置かなかった設問のための下限であって、上書きではない。
画面に入力口を戻すわけでもないので、#103 の「入力口は1つ」は壊れない。

**(2) 検出（#105 の仕組みの流用）は採らなかった。**
実資料には設問ごとに得点記入枠が印字されている教科があるが（#105 の調査で観測）、
**全教科にあるとは書けない。** 無い教科では今と同じ空のPDFになるため、
検出は下限にはできない。後から検出が入れば`Question.score_area`が
埋まるだけで、消費側（`build_export_marks`）は1行も変わらない。
**検出は (1) の代替ではなく、上に載る改善**という整理である。

**(3) 書く場所が決まらないときは出力前に断る。**
回答欄も`score_area`も無い設問は、書く場所が本当に存在しない。
`domain.pdf_export.unplaceable_question_ids`が対象設問を挙げ、
`POST /submissions/{id}/export`が未確認設問チェックと**同じ形**で
409 + `question_ids`を返す。実機では202が返り、ジョブが成功し、
元の答案とほぼバイト同一のPDFが出ていた。**黙って空のPDFを出すより、
出力前に断る。**

#### 2.2.2 書く場所が無い設問は、拒まずに左余白へ書く（Issue #150）

**#120 の (3)「書く場所が決まらないときは出力前に断る」は、実機で高すぎた。**

実機再検証 #4 で、**7教科中4教科（物理・現代文・生物・古漢）が1枚も出力できなかった。**
原因は、回答欄が検出できなかった設問（#131）が1問でもあると、`score_area` の無いその
1問のために**答案まるごと**拒まれることだった。物理は画面が「5/5問 確定」と出している
状態で拒まれている。**人が全問を確定させ終えた労働が、成果物にならなかった。**

#120 が断る判断をしたときの比較対象は「黙って空のPDFを出す」であり、その比較では断るのが
正しかった。#150 が足したのは第3の選択肢である。

**決定: `score_area` の無い設問の点数は、そのページの左余白帯へ、設問番号を添えて書く**
（`domain.pdf_export.fallback_score_areas` / `_FALLBACK_SCORE_STRIP`）。

採らなかった2つと、その理由:

- **その設問だけ点数を描かずに出す** — 確定済みの採点結果を黙って捨てて成功を返す形で、
  Issue #121 で直したばかりの失敗と同じ。紙を持つ人には欠落が見えない。
- **拒む（理由を正しくして）** — #137 が消した行き止まりの別経路。理由が正しくなっても、
  利用者が自分で解消できない点は変わらない（回答欄の検出は画面から直せない）。

**なぜ答案の脇ではなく余白か。** その設問は回答欄が分かっていない。ページ上のどこに置いても
「ここがその設問だ」という嘘になる。位置が分からない注釈を答案に描くのをやめたのが #141 で、
理由はそのまま同じである。余白帯は位置について何も主張せず、「この設問は何点だった」という
**分かっている事実だけ**を伝える。だから行には必ず設問番号を付ける（`問2 4/5`）。
余白に `4/5` とだけ書いてあっても、どの設問のものか分からない。

##### 位置は実データで測って決めた（推測ではない）

司令塔から「まず実データで、その位置に生徒の筆跡があるかを確かめること。重ならない位置が
取れるならそちらを選ぶこと」という条件が付いた。測った。

対象の答案PDF全13ページ（生徒答案PDFを持つ11教科ぶん）を描画し、スキャンのページ枠を除いて
**幅1%刻みの暗ピクセル密度**を取った。

| 帯（ページ幅に対する位置）    | 実測                                                                                                 |
| ----------------------------- | ---------------------------------------------------------------------------------------------------- |
| `x` ∈ [0.00, 0.03]            | **13ページ中12ページで空**（最大 0.02%＝実質ゼロ）。#150 が塞いでいる4教科では最大 0.15%（点が数個） |
| `x` ∈ [0.03, 0.05]            | 4教科で印字（罫線・文字）が出始める（最大 2.6%）                                                     |
| ページ下端 `y` ∈ [0.95, 1.00] | 7教科で 2.7〜9.2%。**下端の帯は空ではない**                                                          |
| ページ上端 `y` ∈ [0.00, 0.05] | 8教科は空だが、残りは 2.2〜3.7%。加えてここは受験番号欄などの識別情報が載る                          |

したがって帯は `x` ∈ [0.005, 0.035]、`y` ∈ [0.05, 0.95] とした。
**重なりは既定にしていない。重ならない位置が実測で取れたので、そちらを選んでいる。**

唯一この帯に実質的なものがある1ページ（1教科の [0.01, 0.02] にスキャン端のノイズ）は、
全設問が自前の `score_area` を持つ教科で、この退避先には到達しない。

将来、余白まで使われた答案が来れば重なりうる。そのときも書く方を採る:
**確定済みの点数を丸ごと失うより、余白の小さな文字が印字に重なる方がましである。**
これは #120 の先例（「答案の上に重なるのは良くないが、何も描かれていないPDFよりは良い」）と
同じ結論だが、根拠は引用ではなく上の実測である。

##### 帯に収まらないときは、やはり断る

帯の高さは 0.90、1件あたりの下限は `_MIN_FALLBACK_SCORE_HEIGHT`（`_MIN_NOTE_HEIGHT`×4）
なので、1ページあたり18件まで。19件目からは場所が無く、`unplaceable_question_ids` が
その設問を挙げて 409 になる（**#120 のチェックは死んでいない。意味が狭まっただけ**）。

1件あたり4行分を確保するのは、帯の幅がページの3%（A4で約18pt）しかないためである。
`_draw_text` は幅に対して折り返し、入り切らない行を**省略記号で切り詰める**。
注釈のコメントは切り詰めてよいが、**点数は切り詰めてはいけない**。
`問2 4/5` は帯の中で数行に縦に積まれる（読める向きなので折り返し自体は問題ない）。

##### 出力時に解決する。登録時ではない

#120 の導出（`derive_mark_areas`）は**登録時**に `Question` へ書いた。理由は、添削レビュー
画面が別実装で同じ位置解決をしており、片側だけ導出すると画面とPDFがずれるからだった。
**この退避先は出力時に解決する。** 理由が2つある。

1. **既に登録済みの答案を、再登録なしで救うため。** #150 は実機で今ブロックしている問題で、
   登録し直しは答案との紐付けをやり直すことになる。
2. **#120 が登録時を選んだ理由が、ここでは発生しない。** ずれるのは「画面とPDFが同じものを
   別の位置に描く」場合である。この退避先が描くのは、画面が**元から1つも描いていない**設問
   （`score_area` が `null` なので画面にも枠が出ない）の点数であり、突き合わせる相手がいない。

##### #133 も同じ退避先を使えるようにしてある

#133 は「縦書きで導出された得点欄が最小フォントサイズ (6pt) を下回る」問題で、
**同じ「点数を書く場所」の問題の別の形**である（場所はあるが小さすぎる）。
`_FALLBACK_SCORE_STRIP` と `_fallback_score_slots` は「自前の場所が使えない設問の
点数をページの余白へ退避させる」ものなので、#133 が挙げている選択肢 (2)
「最小フォントサイズを下回るときは別の場所に置く」はこの仕組みをそのまま使える。
**#150 では #133 に手を付けない**（判断には実物の計測が要る、と #133 自身が書いている）。
ここで用意したのは退避先であって、どの条件で退避させるかの判断ではない。

##### 残っている穴

この退避先が運ぶのは**点数だけ**である。同じ設問の注釈コメントは、`comment_area` も `null`
なので #141 の規則どおり落ちる（帯の幅が3%しかなく、散文を置けない）。#150 の範囲は
「確定した点数が取り出せない」ことなので、ここでは広げていない。別Issueとして扱う。

### 2.3 注釈のコメント文は図形と切り離し、必ず`comment_area`へ書く（Issue #141）

**実機再検証では、AIが作った注釈14件のコメントが1文字も出力PDFに描かれていなかった。**

原因は描画側にある。`_draw_mark`
（`adapters/pdf/pdfium_pypdf_engine.py`）が`AnnotationMark.text`を
描くのは`SCORE`と`COMMENT`の2種別だけで、`CROSS`/`CIRCLE`などの図形種別に
渡された`text`は**参照されずに捨てられていた**。
`build_export_marks`は×の説明文を`text`に載せて渡していたので、
ドメイン側は「渡した」、エンジン側は「描かない」で釣り合っており、
テストも通っていた。

Issue #141 で、1つの`Annotation`が出す2つのものを分離した。

- **図形**（×・○・△・下線・囲み）は答案の上、位置解決できた矩形に描く。
- **コメント文**は常に設問の`comment_area`（余白帯）へ1行として描く。
  答案の上には決して描かない。

こうすると、エンジンが文字を描く種別（`COMMENT`）にしかコメント文が渡らず、
「渡したのに描かれない」経路が無くなる。副次的に、位置解決できた
`COMMENT`種別が生徒の筆跡の上に散文を重ね書きしていた問題も消える
（`COMMENT`は図形を持たないので、余白帯の1行だけを出す）。

行頭には種別記号（`×` `○` `△` `＿` `□`）を付ける。余白の
「× 記述が不完全です。」が答案上のどの図形の説明かを、読む側が辿れるようにするため。
簡易設計書 §12.4 の例（`⚠ 時制表現について確認`）と同じ形である。

#### 2.3.1 余白帯に入り切らないときは、件数を書く

注釈は1件につき帯の1スライスを占める（`_stacked_note_rects`）。
1つの矩形に複数行をまとめないのは、`render_annotations`が各マークを
自分の矩形の左上から独立に描くためで、長いコメントが1件あるだけで
他の注釈が帯の下端外へ押し出される。

**入り切らない場合の挙動は設計として決める。**
`_MIN_NOTE_HEIGHT`（6ptのフォントを1.2行送りで置ける最小の高さ）で
割り切れる数だけスライスを作り、**最後のスライスに
「ほか{n}件は余白に収まらず未表示」と書く。**
黙って打ち切らない。Issue #121 で「長いコメントで採点結果ごと捨てて成功を返す」
事故が起きており、同じ形の失敗がここでも作れる
（帯の浅い設問で注釈5件のうち2件だけ描いて完成に見える）。
入らなかった件数を出すのは1行のコストで、紙を持つ人に欠落が見える。

### 2.5 `target`の書き方をAIに伝える（Issue #141）

`anchor_text` の出どころは AI の `AnnotationCandidate.target` である。
注釈は座標を持たない（簡易設計書 §12.1）ので、アプリはこの文字列を
OCR の語 box から探して位置を決める。**つまり `target` は説明ではなく引用**
なのだが、そうとはどこにも書かれていなかった。

- `GRADING_SYSTEM_INSTRUCTIONS` は `target` に一言も触れていなかった。
- 生成される JSON Schema の `target` は `{"type": "string"}` だけだった。

実機再検証では、複数のプロバイダが答案に存在しない文字列を書いた
（読み取りを正しい表記に直した、手書きの式を LaTeX 風に書き直した、
隣接していない2つの解答を1つに連結した、白紙の解答欄に架空の
プレースホルダを書いた）。§2.4.1 の残り8件のうち6件がこれで、
突き合わせ側の問題ではない。

**逐語引用の規則を、モデルが読む2つの経路の両方に書く。**
`GRADING_SYSTEM_INSTRUCTIONS`（信頼される指示チャネル）と
`AnnotationCandidate.target` の schema description の両方である。
片方しか読まないモデルでも規則が届くようにするため。
引用できないなら注釈を出さない、までを含めて書く。

#### 2.5.1 この項目はローカルで実効性を検証できない

`backend/tests/test_ai_grading_anchor_target.py` が固定できるのは
「2つの経路の両方に規則が載っている」ことまでである。
**規則がモデルの出力を実際に変えるかは、ここでは分からない。**
確認は次の実機再検証に委ねる。

## 3. `PdfEngine.render_annotations`（Issue #23で追加）

`domain/pdf_engine.py`の`PdfEngine`契約へ新しいメソッドを追加した。
既存の`stamp_markers`（PoC 3由来、赤い正方形1種類のみ）は
`backend/poc/`・複数のテストfixture生成に使われ続けているため、シグネチャを
変更せずそのまま残し、代わりに新しいメソッドを追加した（`pdf_engine.py`の
元のdocstringは「`stamp_markers`を将来widenする」と書いていたが、
利用箇所が異なるため別メソッドとした）。

- `AnnotationMark`（`domain/pdf_engine.py`）: 種別・page正規化rect・
  （score/commentのみ）描画文字列を持つ値オブジェクト。座標決定は
  ドメイン層（`domain.pdf_export.build_export_marks`）の責務のまま。
- 実装（`adapters/pdf/pdfium_pypdf_engine.py`）は既存の
  `_overlay_pdf`/`_filled_square`と同じ「対象pageのMediaBoxと同じ
  MediaBoxを持つ1ページのオーバーレイPDFを作り`merge_page`で重ねる」
  方式を踏襲する。○×△・下線・囲みはpypdfの生content stream命令
  （`_filled_square`と同じ流儀）ではなく、reportlabの`Canvas`
  （楕円・直線・矩形・パス）で描画する。

### 3.1 新規依存: reportlab

コメント・点数のテキスト描画には日本語フォントの埋め込みが要る。
`pypdf`/`pypdfium2`にはテキストレイアウト・フォント埋め込みAPIが無く、
既存の手書きバイト列PDF生成（`_overlay_pdf`）へCID
フォント埋め込みを自前実装するのは著しく過大な工数になるため、
AGENTS.md「既存コード・標準ライブラリ・既存依存で満たせない場合のみ追加」
に従い`reportlab`（BSD系ライセンス、PyMuPDFのようなAGPL/商用ライセンス
問題が無い）を新規依存として追加した（`backend/pyproject.toml`）。
`Canvas`はTrueTypeフォントを`pdfmetrics.registerFont(TTFont(...))`
経由で登録すると、保存時に自動的にサブセット埋め込みする。

### 3.2 日本語フォントの解決（Windows専用の暫定方針）

MVPの対象OSはWindowsのみ（簡易設計書 §3.1）で、CIも`windows-latest`
（`docs/quality-gates.md`）のため、OS同梱の日本語フォントをそのまま使う
方針にした。フォントファイルをリポジトリへ同梱・再配布する必要が無く、
ライセンス上のリスクも増えない。候補は優先順位付きリストで解決する
（`adapters/pdf/pdfium_pypdf_engine.py`の`_JAPANESE_FONT_CANDIDATES`）:

```text
C:\Windows\Fonts\YuGothM.ttc
C:\Windows\Fonts\meiryo.ttc
C:\Windows\Fonts\msgothic.ttc
C:\Windows\Fonts\msmincho.ttc
```

いずれも存在しない場合は`JapaneseFontNotFoundError`を送出し、
export jobはFAILED（`ErrorCategory.PERMANENT`）として記録される
（形の崩れた文字やフォールバック描画で誤魔化さない）。純粋な図形種別
（○×△・下線・囲み）はフォントに一切依存しないため、コメント/点数の
Annotationを一切含まない設問だけの出力はフォント未検出でも失敗しない。

**未決事項**: macOS/Linux対応時はこの解決方式が使えないため、フォント
ファイルをアプリへ同梱するか、embeddable Google Noto Sans JPなどの
再配布可能フォントを採用するかを別Issueで決定する必要がある。

なお Issue #67 で、**Flutter 側の画面表示用**には Noto Sans JP（SIL OFL 1.1）を
`app/assets/fonts/` へ同梱することを決めた（[design-tokens.md](./design-tokens.md) §2）。
ここの未決事項は**それとは別**である: 画面表示は端末上で描くだけだが、PDF出力は
フォントをサブセット埋め込みした**成果物を配る**ため、必要な確認が変わる。
同じフォントを流用できる見込みはあるので、その Issue ではここから検討を始めればよい。

**テストだけの回避（製品挙動は不変）**: 上記の候補が1つも無い環境では、
文字描画を伴うテストは`backend/tests/font_support.py`が
**そのテストのassertionが必要とするグリフを実際に持つ**ローカルフォントを
候補リストの末尾へ追記してから走る。Windowsでは本物が先に見つかるため
何も起きず、**製品コードと`_JAPANESE_FONT_CANDIDATES`は変更していない**。
描けるフォントがどれも無いときはassertionを緩めずskipする
（[mvp-acceptance.md](./mvp-acceptance.md) §4）。

## 4. `Export`エンティティとJob

Issue #23の実施内容「出力job、hash、生成時刻、元Submission、review version
を保存する」への対応。

- `Job`（kind=`export`、`domain/models.py`の`JobKind.EXPORT`は Issue #11の
  時点で既に列挙値として存在していたが、本Issueまで生成する経路が無かった）
  が出力の実行単位。`question_id`/`dependency_graph_version`は常に`None`
  （submission単位の処理であり、設問DAGスケジューリングの対象外）。
  進捗表示・再試行は既存の`GET /jobs/{id}`・`POST /jobs/{id}/retry`を
  そのまま再利用する（Issue #18で実装済みのjob queueは`question_id`が
  `None`のjobを既に正しく素通りする -- `_finalize_result`の
  `if current.question_id is not None:`分岐）。
- `Export`（新規テーブル、migration `0014_exports`）は**成功した出力のみ**
  記録する。失敗した試行はJobの`state=failed`にのみ残る（「失敗した
  Export」という行は存在しない）。`job_id`にUNIQUE制約を張り、
  `ExportJobProcessor`は処理開始時に`export_id(job)`
  （`f"export:{job.id}"`、`grade_result_id`/`recognition_result_id`と同じ
  決定的id方式）で既存行を確認する -- クラッシュ後の再起動でjobが再実行
  された場合に二重生成・二重挿入を防ぐ（`jobs/grading_processor.py`の
  `existing_grade`チェックと同じ冪等性パターン）。
- `review_versions`（`QuestionReviewVersion`のtuple）は出力時点の各設問の
  review履歴の長さ（= 最新`Review.version`）のスナップショット。次回出力
  要求時に「前回から何か変わったか」を判定する材料になる（§5）。

## 5. 再出力方針の決定表（Issue #23受入条件）

`docs/answer-intake-and-preprocessing.md` §2「同一PDFの再取込方針」と同じ
決定表形式で記録する。実装は`domain.pdf_export.decide_reexport`。

| このSubmissionの既存Exportの状態                                                                  | 判定                     | 動作                                                                                                                      |
| ------------------------------------------------------------------------------------------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| 成功したExportが1件も無い                                                                         | `accept_new`             | 新規ファイルを生成する                                                                                                    |
| 直近の成功Exportのreview-version snapshotが現在と完全一致（どの設問も再editもUndoもされていない） | `reuse_existing`         | 新規ファイルを生成せず、既存Exportをそのまま返す                                                                          |
| 直近の成功Exportのreview-version snapshotと現在が異なる（少なくとも1設問の履歴が進んだ）          | `accept_new_superseding` | `LocalFileStore.allocate_export_path`の連番規則で新規ファイルを生成する。以前の成功Exportのファイル・DB行は一切変更しない |

判断の根拠:

- 誤って同じ「出力」ボタンを連打した場合に、内容が同一のファイルを
  無意味に量産しない（`answer-intake-and-preprocessing.md`の同一PDF
  再取込方針と同じ理由）。
- 一方でレビューが実際に変わった（Undo・再edit・再承認）後の出力要求は、
  常に新しい内容を反映した新規ファイルであるべきで、古い出力を黙って
  上書きしてはならない（business-rules-and-evaluation-data.md §2 (15)
  「元PDFは上書きしない」と同じ精神を出力ファイルにも適用する）。
- 比較は`Export.id`やタイムスタンプではなく、設問ごとのreview履歴の長さの
  値そのもので行う。「どちらが古いか」ではなく「レビュー状態が同じか」を
  問うだけなので、この判定に順序関係は要らない。

## 6. ファイル名・衝突・atomic write（既存決定の再確認）

出力ファイル名規則（`<元ファイル名>_corrected.pdf`、衝突時は
`_corrected_2`と連番）と保存先（`app-data/exports/`）は
`business-rules-and-evaluation-data.md` §2 (14)・
`docs/data-model-and-local-storage.md` §5で既に決定済みで、
`adapters/local_storage.py`の`LocalFileStore.allocate_export_path`
（Issue #11時点で実装済み、本Issueまで呼び出し元が無かった）がそのまま使える。

`ExportJobProcessor`は次の順序を守る（Issue #23受入条件「失敗・cancel時に
元PDFと以前の成功出力を変更せず、壊れた完成ファイルを残さない」）:

1. app-data外のscratch temp fileへ生成する（生成失敗はここで検知、
   app-data・DBに一切触れない）。
2. 生成物を`PdfEngine.page_count`で検証する（page数が元PDFと一致しない
   場合は失敗として扱う）。
3. 検証済みのバイト列とExport行を`adapters.atomic.transactional_operation`
   で束ね、DB commitが成功した後にのみ`LocalFileStore.write_atomic`
   （同一ディレクトリへの一時ファイル→`os.replace`）で書き込む。

`ExportJobProcessor`の実行全体は`api.app.create_app`が既に持っている
PDFium直列化用ロック（旧`intake_lock`、本Issueで`pdfium_lock`へ改名し
export処理とも共有）の中で行う。これはPDFium自体のスレッド安全性のためだが、
副次的に「同じファイル名stemを持つ2つのsubmissionへの同時export」が
`allocate_export_path`の空きファイル名チェックで衝突するレースも防ぐ
（このロックが無いと、2つのexport jobが同時に同じ`<stem>_corrected.pdf`
を「空いている」と判定し、片方がもう片方の出力を`os.replace`で
上書きしてしまう可能性があった）。

## 7. Job queueの複数kind対応

Issue #18のjob queue（`jobs/queue.py`）は「`JobQueueService`は常に
1つの`JobProcessor`だけを持つ」設計だったが、それまでシステム内の
job kindが`GRADING`のみだったため単一processorで問題が無かった。本Issueで
`EXPORT`という2つ目のkindが生まれたため、`jobs/routing_processor.py`の
`ByKindJobProcessor`（`job.kind`で委譲先を振り分けるだけの薄いラッパー）を
新設し、`api.app.create_app`が既定で
`ByKindJobProcessor(default=GradingJobProcessor, overrides={EXPORT:
ExportJobProcessor})`を組み立てて`JobQueueService`へ渡す。`job_processor`
引数を直接渡すテスト・呼び出しは従来どおり「その1つのprocessorが全kindを
処理する」という既存の上書き挙動を維持する（この場合`ByKindJobProcessor`
は使われない）。`JobQueueService`自体には一切変更を加えていない。

## 8. API

`backend/src/auto_scoring/api/export_router.py`に追加:

| メソッド | パス                                   | 用途                                                                       |
| -------- | -------------------------------------- | -------------------------------------------------------------------------- |
| POST     | `/submissions/{submission_id}/export`  | §1のフロー。409（拒否・§8.1）/ 200（`reuse_existing`）/ 202（新規job投入） |
| GET      | `/submissions/{submission_id}/exports` | 成功したExport一覧（保存先表示・出力履歴）                                 |

### 8.1 409は1種類ではない（Issue #150）

`POST .../export` は2つの理由で 409 を返す。**本文の `detail.code` がどちらかを名乗る**
（`api.export_router.ExportConflictCode`）。

| `detail.code`           | 意味                                         | 利用者の直し方                             |
| ----------------------- | -------------------------------------------- | ------------------------------------------ |
| `unconfirmed_questions` | 未確認の設問がある（Issue #23）              | `question_ids` の設問を確定させる          |
| `no_room_for_score`     | 点数を書ける場所が無い（#120／#150、§2.2.2） | **確定では解消しない。**ページに余白が無い |

**なぜコードが要るか。** #120 が2つ目の 409 を足したとき、本文の形は1つ目と同じ
`{message, question_ids}` のままだった。Dart 側は 409 が1種類だった頃に書かれており、
`SidecarErrorKind.conflict` に潰して Issue #23 の文言
「未確認の設問があるため出力できません」を**両方に**出していた。
実機再検証 #4 では、**全問を確定させ終えた利用者に「確定させろ」と表示していた。**
画面の指示は役に立たないどころか**従いようがない**（その作業は既に済んでいる）。

コードを本文に入れたのは、`detail` が両方の 409 が既に対象設問を載せている場所であり、
FastAPI が dict の `detail` をそのまま通すからである。`HTTPException.detail` は OpenAPI に
型が出ないので**生成された Dart クライアントは影響を受けない**。`SidecarApiClient` が
`detail.question_ids` と同じ経路で生の本文から読む。

**知らないコードを推測で既知の文言に寄せてはいけない。**Dart 側は未知のコードなら
サイドカーの `message` をそのまま出す（`export_dialog.dart` の `_refusalDetail`）。
そっけない理由の方が、嘘の直し方よりましである。

進捗・再試行は新規エンドポイントを作らず、Issue #18で実装済みの
`GET /jobs/{job_id}` / `POST /jobs/{job_id}/retry` /
`GET /submissions/{submission_id}/jobs`をそのまま再利用する
（kind=exportのJobもこれらのエンドポイントで等しく扱える）。

## 9. Flutter側

`app/lib/core/widgets/export_dialog.dart`の`ExportDialog`が（Issue #137で`features/pdf_review/`から移動）
「出力実行→進捗→保存先表示/再試行」の全ライフサイクルを1つのdialogで
完結させる。添削レビュー画面（`pdf_review_page.dart`）のAppBarへ
「PDF出力」ボタン（`review-export-button`）を追加し、このdialogを開くだけ。

- 出力要求（`AppDependencies.requestExport`）が409を返した場合、
  `SidecarApiException.conflictCode` / `conflictQuestionIds`
  （`sidecar_api_client.dart`の`_translate`が409レスポンスの
  `detail.code` / `detail.question_ids`から抽出する）を読み、
  **拒否の種別ごとの見出しと直し方**、および対象設問一覧を表示する（§8.1）。
  Issue #150 まではフィールド名が `unconfirmedQuestionIds` で、種別を持たず、
  常に「未確認の設問がある」と表示していた。
- `decision: reuse_existing`ならjobを一切pollせず即座に保存先を表示する。
- 新規job投入時は`GET /jobs/{id}`（`AppDependencies.getJob`、新設）を
  1秒間隔でpollし、`succeeded`になったら`listExports`で該当jobの
  `file_path`を取得して表示する。`failed`/`cancelled`ならエラーと
  「再試行」ボタン（`POST /jobs/{id}/retry`、`AppDependencies.retryJob`、
  新設）を表示する。
- 既存のreview action（edit/reject/regrade/approve/undo, Issue #22）と
  同じく、Flutter側は永続化された状態を都度取得するだけで、dialog自身は
  出力結果を推測・キャッシュしない。

## 10. 検証

- `backend/tests/test_annotation_layout.py`: `resolve_annotation_rect`
  （明示rect・anchor_text解決・crop→page座標変換・ゼロ面積answer_areaの
  扱い・複数attemptでの最新優先・固定位置種別のscore_areaフォールバック・
  未解決時`None`）、attemptスコープ関数の単体テスト。
- `backend/tests/test_pdf_export.py`: 未確認判定・review-version
  snapshot・`decide_reexport`の3分岐・`build_export_marks`
  （SCOREはGradeの点数を描画・COMMENTはAnnotation自身のコメントを描画・
  `comment_area`フォールバック・未解決時スキップ・attemptスコープの
  絞り込み）の単体テスト。
- `backend/tests/test_pdf_annotation_rendering.py`: 実`pypdf`+`pdfium`で
  ○×△・下線・囲みの各形状がpixel検査（PoC 3と同じ「赤色検出」手法）で
  正しい位置に描画されること、点数・長い日本語コメント（複数行折り返し）が
  対応するrect内に描画されること、複数page文書で他pageを汚さないこと、
  回転pageでも正しい位置に描画されること、フォント未検出時に
  `JapaneseFontNotFoundError`で失敗し出力ファイルを残さないこと、
  フォント未検出でも図形のみのAnnotationは影響を受けないことを検証。
  点数と日本語コメントを同時に描く1件は両方のグリフを持つフォントを要求する
  （素のUbuntuには無い。`fonts-ipafont-gothic`で解決 ——
  §3.2、mvp-acceptance.md §4.3）。
- `backend/tests/test_export_processor.py`: 実SQLite + 実
  `PdfiumPypdfEngine`で、Export生成・記録・sha256一致・元PDF不変、
  未確認設問がある場合の拒否（Export行・ファイルとも作られない）、
  同一jobの再実行に対する冪等性、同一submissionへの2回目の出力が
  連番ファイルを生成し1回目のファイルを変更しないこと、生成失敗時に
  Export行・ファイルとも作られず元PDFも変更されないこと、失敗した
  再試行が既存の成功Exportへ影響しないことを検証（失敗注入含む）。
- `backend/tests/test_export_api.py`: `TestClient` + 実queueで
  `POST/GET .../export(s)`をエンドツーエンドに検証（404・409＋対象
  question_id・202＋job実行完了までのpolling・`reuse_existing`の200）。
- `app/test/export_dialog_test.dart`: 進捗→成功表示、`reuse_existing`の
  即時表示、未確認設問一覧表示、失敗→再試行→成功のライフサイクル全体を
  widget testで検証。

## 11. 対象外（Issue本文どおり）

- 元PDFへの上書き、クラウド保存、一括外部配信はMVP対象外
  （簡易設計書 §14・§26、business-rules-and-evaluation-data.md §2 (14)(15)）。
- Export結果のFlutter内プレビュー表示（保存先パスの表示のみ）。
