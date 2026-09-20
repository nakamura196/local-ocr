# Local OCR — 設計

画像の文字を、手元のパソコンだけで読む道具。macOS と Windows を 1 つのコードベースから出す。

## 位置づけ

[tei-scanner](https://github.com/nakamura196/tei-scanner)（Swift / macOS 専用 / Apple Vision のみ）の後継。
変えるのは 3 点。

1. **Windows でも動く**（Flet = Python + Flutter。`~/git/kim/archival-packager` と同じ作り）
2. **読む道具を選べる**（Apple Vision だけでなく、くずし字・漢籍も読める）
3. **入口と出口を増やす**（IIIF マニフェスト入力、TEI/XML 出力）

## 何をする道具か

**画像 → 文字**に徹する。読んだ文字をコピーして、利用者が好きなところへ貼る。
校正の画面（TEI/IIIF エディタ）とは**互いを知らない**。繋ぐときはクリップボード経由にする
（エディタ側に「枠の画像をコピー」を足せば、貼り付けるだけで繋がる）。

## 読む道具（エンジン）

| id | 名前 | 対応 | 取得 | 向き |
|---|---|---|---|---|
| `apple-vision` | Apple Vision | macOS | 不要 | 現代の活字・手書き。速い |
| `windows-ocr` | Windows 標準 OCR | Windows | 不要 | 同上。`Windows.Media.Ocr` |
| `ndl-lite` | NDLOCR Lite | 両方 | 約 160MB | 近代資料・活字 |
| `ndl-koten-lite` | NDL古典籍OCR Lite | 両方 | 約 78MB | 古典籍・くずし字 |
| `paddle-vl` | PaddleOCR-VL | 両方 | 約 1.8GB | 漢籍・多言語・版面解析 |
| `tibetan` | BDRC Yigdzin 1 | 両方 | 未定 | チベット語（**保留**） |

**共通の口は `engines/base.py` の `Engine`。** 足すときは `engines/__init__.py` の一覧に 1 行足すだけ。
取得・キャッシュ・進捗・失敗時の文面は共通側が持ち、エンジンには書かない。

### 各エンジンの実装メモ

- **Apple Vision**: pyobjc (`Vision` / `Quartz`)。`VNRecognizeTextRequest`。
  枠は左下原点の 0..1 で返るので、画素座標・左上原点に直す。**初回の呼び出しだけ約 15 秒**（以後 0.1 秒）
- **Windows 標準 OCR**: `winrt-Windows.Media.Ocr` ほか。日本語は言語パックが要る
- **NDL 2 種**: 上流は [ndl-lab/ndlocr-lite](https://github.com/ndl-lab/ndlocr-lite) と
  [ndl-lab/ndlkotenocr-lite](https://github.com/ndl-lab/ndlkotenocr-lite)。**どちらも CC BY 4.0**（表示が要る → NOTICE）。
  Python 実装があり、ONNX Runtime で動く。構成は レイアウト検出（DEIMv2 / RTMDet）→ 文字認識（PARSeq）→ 読み順
- **PaddleOCR-VL**: llama.cpp（`b10776`）の GGUF。常駐の `llama-server` を内側で立て、
  OpenAI 互換の窓口に投げる。**サーバの存在は利用者に見せない**
- **チベット語**: BDRC「Yigdzin 1」（Apache-2.0）は **PaddleOCR-VL-1.6 の派生**なので同じ道に乗る見込み。
  ただし配布は safetensors のみで **GGUF が無い**。変換の実験が要るため v1 では見送る

## 入口

- 画像ファイルを選ぶ
- **クリップボードから貼り付ける** ← エディタとの連携はここ
- フォルダ（複数ページの一括処理）
- **IIIF マニフェストの URL** ← 各カンバスの画像を順に読む

## 出口

- 文字をコピー
- テキストで保存
- **TEI/XML**。tei-scanner と同じ形にする:
  1 ページ = 1 `<surface>` + `<graphic>`、1 行 = 1 `<zone>` と `<lb corresp="#…">`
  （枠を返さないエンジン（PaddleOCR-VL の版面読み）では `<zone>` を省く）

## 画面

**市販のアプリと同じ水準に仕上げる。** 道具として毎日開かれるものなので、
「動くが素っ気ない」では使われない。

### 起動画面（ランディング）

起動直後はいきなり作業画面にせず、**受け皿の画面**を出す。

- アプリ名と、1 行の説明（「画像の文字を、このパソコンの中で読みます」）
- 画面の大半を占める**投入エリア**。ドラッグ＆ドロップを受け、
  「画像を選ぶ」「貼り付け」「フォルダ」「IIIF マニフェスト」を並べる
- **「画像はこのパソコンから出ません」を目に入る場所に置く。**
  手元で動くことがこの道具の価値なので、隠さない
- 読む道具（エンジン）は控えめに。既定は**取得の要らないもの**（macOS なら Apple Vision）にして、
  何も準備せずに 1 回目が成功するようにする
- 前回開いたものがあれば、その続きから戻れるようにする

### 作業画面

左右 2 面。左に版面（枠の重ね描きつき）、右に読んだ行。
行を選ぶと対応する枠が光る（tei-scanner と同じ操作感）。
上部に エンジン / 実行 / コピー / 保存（テキスト・TEI/XML）。

### 設定画面

読む道具の一覧。それぞれ「取得済み / 未取得（◯◯MB）」を出し、その場で取得・削除できる。
1.8GB のものがあるので、**何をいつ落とすかを利用者が決められる**ようにする。

### 状態の見せ方

空・読み込み中・取得中・失敗の 4 つを、どの画面でも同じ形で出す。
失敗は**何をすればよいかまで**書く（「起動していません」で終わらせない）。

### 仕上げ

- アプリのアイコン（配布物・Dock・ストア掲載で要る）
- 日本語 / 英語の切り替え（tei-scanner と同じ範囲）
- 明るい / 暗いテーマの両方で破綻しないこと
- キーボード: ⌘V で貼り付け、⌘C でコピー、⌘O で開く

## 配る

`~/git/kim/archival-packager` と同じ。

- **macOS**: `flet build macos` → Developer ID + hardened runtime で署名 → 公証 → staple → `.dmg` → GitHub Releases
- **Windows**: 手元に Windows 機が無いので **GitHub Actions でビルド** → MSIX → **Microsoft Store**。
  **ストアに出すと Microsoft が署名し直す**ので、Windows 用の証明書を買わずに済む
- 署名鍵: `Developer ID Application: Satoru Nakamura (Q6S8JS6GWV)`
- 公証: 1Password の `app-store-connect-notarization`、秘密鍵は `~/.private_keys/AuthKey_<KEY_ID>.p8`

## 進め方

1. **器とエンジンの口**（済）+ Apple Vision（済）+ PaddleOCR-VL（済）
2. **画面の作り直し**（ランディング → 作業画面 → 設定の 3 面構成）
3. 出口: テキスト保存 / TEI/XML
4. 入口: フォルダ / IIIF マニフェスト
5. Windows 標準 OCR
6. NDL 2 種（ここが一番重い）
7. アイコンと多言語、明暗テーマの詰め
8. 配布（署名・公証・ストア申請）
9. チベット語（GGUF 変換の実験から）

## 踏んだ落とし穴（Flet 0.86）

古い版の書き方がそこら中の記事に残っているので、**必ず手元で確かめてから使う**。

- `ft.app()` は非推奨。`ft.run()`
- ボタンのラベルは `text` ではなく `content`
- `ft.ImageFit` は無い。`ft.BoxFit`
- `ft.dropdown.Option` ではなく `ft.DropdownOption`。変更の通知は `on_change` ではなく **`on_select`**
- `FilePicker` は overlay ではなく **`page.services`** に足す。`on_result` は無く、
  **`await picker.pick_files(...)` が選ばれたものを返す**（ハンドラを `async def` にする）
- クリップボードは `page.clipboard.set/get/get_image/set_image`。**すべて await が要る**
- `ft.Image` は `src` が必須。空文字で置くくらいなら作らない
- **前の実行のウィンドウが残る。** 「Working…」のまま固まって見えるときは、たいてい古い窓を見ている。
  `pkill -f Flet.app` してから確かめる
