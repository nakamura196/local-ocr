---
title: "読む道具（エンジン）を足す"
eyebrow: Local OCR 技術資料
---

**PP-OCR の仲間の新しいモデルは、Python のファイルにデータを 1 件足すだけで増やせます。**
公式が ONNX を出しているモデルなら、変換も、ファイルの置き直しも要りません。
このページは、その手順を順に書いたものです。作業はプルリクエストを出すところまでで、
新しい版として配るのは中村が行います（[`CONTRIBUTING.md`](../CONTRIBUTING.md)）。

言葉を 2 つだけ先に書きます。

- **エンジン**: 画像から文字を読む道具 1 つのこと。アプリの「読む道具」の 1 行にあたります
- **ONNX**（オニックス）: 学習済みのモデルを、どの機械でも動かせる形にしたファイルの形式。拡張子は `.onnx`

## (a) どの型か見分ける

足したいモデルを見て、次のどれかを選びます。

1. **PP-OCR の仲間で、ONNX のファイルがある** → このページの (b)。データを 1 件足すだけです。
   名前に `PP-OCR` が付くもの（検出と読み取りが別のファイルに分かれている形）が当てはまります
2. **llama-server に載る GGUF の画像言語モデル** → (c)。`paddle_vl.py` と `yigdzin.py` を手本にします。
   GGUF（ジージーユーエフ）は、大きな言語モデルを手元で動かすためのファイル形式です。
   名前に `VL` が付く、画像を読む言語モデルはこちらです
3. **それ以外**（Tesseract、別の形式のモデルなど） → 作業を始めずに、中村へ Issue で相談してください。
   足すための土台（取得・設定画面・書き出し）は共通ですが、読む部分は新しく書くことになります

迷ったら 3 にして構いません。

## (b) PP-OCR の仲間を足す

**方針: 同じ言語を読むモデルを 2 つ並べません。** 利用者が選べなくなるためです。
新しい版が既存のモデルより読めるなら、足さずに**置き換えます**（`MODELS` の該当の 1 件を書き換えます）。
いま入っているのは `ppocrv6-small`（中国語・英語・日本語、ラテン文字の言語）です。
足すのは、まだ読めない言語（韓国語、キリル文字、アラビア文字など）のモデルです。

流れは次の 9 つです。公式が ONNX を出しているか（手順 1）で、2 つに分かれます。

### 準備

```
cd local-ocr
git switch main
git pull
git switch -c feat/ppocr-<モデルの名前>
uv sync
```

`<モデルの名前>` は `ppocrv6-tiny` のような短い名前にします。

### 手順 1: 公式に ONNX があるか調べる

PaddlePaddle は、モデルごとに `<名前>_onnx` という repo を Hugging Face に置いています。
repo（リポジトリ）は、ファイルをまとめて置く場所のことです。

- 検索: <https://huggingface.co/PaddlePaddle> で、探している名前に `_onnx` を付けて検索します
- 例: `PP-OCRv6_small_det_onnx`、`PP-OCRv6_small_rec_onnx`、`korean_PP-OCRv5_mobile_rec_onnx`

**検出（`det`）と読み取り（`rec`）が 1 組で要ります。** 世代を揃えます。
`PP-OCRv5` の言語別（これから足していく候補です）の読み取りモデル（`korean_…`、`cyrillic_…`、`arabic_…` など）は、
検出に `PP-OCRv5_mobile_det_onnx` を使います。
ライセンスが **Apache-2.0** であることも、repo の上のほうに出ているので確かめます。
Apache-2.0 以外のときは、そこで止まって Issue に書いてください。

ONNX の repo が **ある** → 手順 2 へ。**ない** → 一番下の「公式に ONNX が無いとき」へ。

### 手順 2: 番号と大きさを調べる

**番号**は、その repo のある時点の版を指す 40 桁の文字列（コミットの番号）です。
番号で固定しておくと、公式があとで中身を差し替えても、こちらの結果は変わりません。
次のコマンドで、番号と大きさが分かります（検出と読み取りの 2 つの repo を並べて書きます）。

```
python3 scripts/ppocr/info.py PaddlePaddle/PP-OCRv6_tiny_det_onnx PaddlePaddle/PP-OCRv6_tiny_rec_onnx
```

repo ごとに、番号と、そのまま貼れる `PpocrFile(...)` の行が 2 行ずつ（`inference.onnx` と
`inference.yml`）出ます。`inference.yml` は、しきい値や文字の一覧が書かれた設定ファイルです。
アプリがこれを読むので、**文字の一覧を自分で作る必要はありません。**

### 手順 3: データを 1 件足す

`src/local_ocr/engines/ppocr.py` を開きます。ファイルの途中に `MODELS = [` があり、
その中に `PpocrModel(...)` が並んでいます。**一番下に 1 件足します。** 手本は
`ppocrv6-small` です（`MODELS` に、いま 1 件だけ入っています）。

```python
    PpocrModel(
        id="ppocrv6-tiny",
        label="PP-OCRv6 tiny（中国語・英語・日本語ほか）",
        label_en="PP-OCRv6 tiny (Chinese, English, Japanese and more)",
        hint="活字（主に横書き）を行ごとに読みます。いちばん軽い版です。",
        hint_en="Reads print (mostly horizontal) line by line. The lightest version.",
        detector=PpocrFile(<手順 2 で出た検出の inference.onnx の行>),
        recognizer=PpocrFile(<読み取りの inference.onnx の行>),
        det_config=PpocrFile(<検出の inference.yml の行>),
        rec_config=PpocrFile(<読み取りの inference.yml の行>),
    ),
```

`PpocrFile(...)` の中は、手順 2 で出た行をそのまま貼ります（行の末尾の `# …` は消して構いません）。
ほかの項目の意味は次のとおりです。

- `id`: 内部の名前。半角の英数字とハイフンで、ほかと重ならないものにします。**一度公開したら変えません**
  （設定ファイルやスクリプトがこの名前を使うため）
- `label` / `label_en`: 設定画面などに出る名前（日本語 / 英語）
- `hint` / `hint_en`: 名前の下の説明文。**取得する大きさは自動で入る**ので、書かなくて構いません
- `dictionary`: 文字の一覧のファイル。公式の ONNX（`inference.yml` がある）では書きません

画面の英語は、`label_en` / `hint_en` に書けば出ます。`ui/i18n.py` を直す必要はありません。

### 手順 4: 取得と動作を確かめる

```
uv run pytest tests/test_ppocr.py
uv run local-ocr --list-engines
```

1 つ目が全部通り、2 つ目の一覧に足したモデルの行が出れば、登録はできています。
大きさ（`初回だけ 〇〇MB ほど…`）が、手順 2 の合計とおおむね合っているかも見ます。

**自分で用意した画像を 1 枚読ませます。**

```
uv run local-ocr <画像のパス> --engine ppocrv6-tiny --fetch
```

`--fetch` は、モデルを取得してから読む、という指定です（初回だけ必要）。
次の 3 つを見ます。

- 行数と文字が、画像と合っている
- 縦書きや傾いた行があれば、それも 1 枚試す（読めないのは正常なことがあります。結果を記録します）
- 同じ画像を、すでにあるモデル（`--engine ppocrv6-small` など）でも読み、比べる

**結果は PR に貼ります。** 画像・出力・どちらが良かったかを 3〜5 行で書けば十分です。

アプリの画面でも 1 回確かめます。

```
PYTHONPATH=src .venv/bin/python main.py
```

設定を開き、足した道具が並んでいること（日本語・English の両方で名前が出ること）、
取得して読めることを確かめ、**スクリーンショットを撮って PR に貼ります。**

### 手順 5: 表示（NOTICE）と一覧を直す

- `NOTICE`: 「PP-OCR (PaddlePaddle)」の節にあるリンクに、足した repo を書き足します。
  変換を自分でしたとき（下の節）は、「変換した人」も書きます
- `README.md`: 「Recognition engines」の表（英語）と「読む道具（エンジン）」の表（日本語）に 1 行ずつ足します
- `docs/guide-more.md`: 「ほかの読む道具を取得する」の表と、道具の名前の表に 1 行ずつ足します
- `docs/design.md`: 「読む道具（エンジン）」の表に 1 行足します

大きさの数字は、アプリの `--list-engines` に出る値に揃えます。

### 手順 6: 更新履歴

更新履歴（`docs/changelog.md` と `docs/changelog-en.md`）は、版を配るときに中村が書きます。
**あなたは触りません。** そのかわり、PR の説明に「利用者から見て何が変わるか」を
日本語と英語で 1 行ずつ書いてください（例: 「PP-OCRv6 tiny を読む道具に追加しました。」）。

### 手順 7: 点検してからプルリクエストを出す

```
uv run pytest
uv run --with ruff==0.16.8 ruff check .
```

どちらも通ることを確かめます。そのあと、直したファイルを 1 つずつ指定してコミットします。

```
git add src/local_ocr/engines/ppocr.py NOTICE README.md docs/guide-more.md docs/design.md
git commit -m "feat: PP-OCRv6 tiny を読む道具に足す"
git push -u origin feat/ppocr-ppocrv6-tiny
```

`git add .` と `git add -A` は使いません（意図しないファイルが入るのを防ぐため）。
コミットの題は `feat: 〜` の形で、日本語で書きます。そのあと GitHub でプルリクエストを作り、
手順 4 の結果とスクリーンショット、更新履歴の 1 行を本文に書きます。

### 公式に ONNX が無いとき

公式が Paddle の形（`inference.json` と `inference.pdiparams`）でだけ出しているモデルは、
自分で ONNX に変換します。**重みは変えません。形式を変えるだけです。**
ただし、手順が増えます。まず、中村に Issue で「このモデルを足したい」と知らせてください。

1. **公式のモデルの番号を調べる。** `https://huggingface.co/PaddlePaddle/<モデル名>` の
   「Files and versions」の最新のコミット番号（40 桁）を控えます。
   ライセンスが Apache-2.0 であることも確かめます
2. **変換する。** 次の 1 行を実行します。必要なもの（Paddle など）は、uv が使い捨ての環境に用意します。
   アプリには何も入りません。初回は 1〜2GB 近いダウンロードがあります
   ```
   uv run scripts/ppocr/convert.py PaddlePaddle/<モデル名> --rev <手順 1 の番号>
   ```
   `ppocr-out/` に `<モデル名>.onnx` ができます。読み取りのモデルなら、文字の一覧
   `<モデル名>.dict.json` もできます。最後に、ファイルの大きさと、入出力の形が表示されます
3. **自分の Hugging Face の repo に置く。** repo を作り、2 つのファイルをアップロードします。
   Apache-2.0 の `license` を、モデルカード（`README.md`）に書きます。元のモデルの名前と番号、
   変換に使ったコマンドも書きます（書き方の手本は、公式の `PaddlePaddle/PP-OCRv5_mobile_rec` のモデルカードです）
4. **置いた repo の番号（40 桁）を控える。** アップロード後の最新のコミット番号です。
   `python3 scripts/ppocr/info.py <自分の repo の名前>` でも分かります
5. **データを足す。** 手順 3 と同じですが、`PpocrFile` の repo と番号が自分の repo になり、
   ファイル名は変換で作った名前（`<モデル名>.onnx`）です。`det_config` と `rec_config` は無いので、
   文字の一覧を `dictionary=PpocrFile(..., "<モデル名>.dict.json", <大きさ>)` で渡します。
   しきい値などは PP-OCRv5 の公式の値（既定）になります。モデルによって違う場合は、中村に相談してください
6. **NOTICE に「変換した人」を書く**（手順 5）。あとは手順 4 から同じです

`scripts/ppocr/convert.py` は、2026-10-15 に Mac で PP-OCRv5 mobile の読み取りモデルを変換して動かしました（Windows では未確認）。
結果は中村が確認します。うまく動かないときは、出たエラーをそのまま Issue に貼ってください。

## (c) GGUF の画像言語モデル（llama-server に載るもの）

PaddleOCR-VL と Yigdzin-1 がこの型です。**ONNX の型より大きな作業**で、手本をなぞりながら進めます。
着手の前に、中村に Issue で相談してください。見る場所は次のとおりです。

1. **取得するもの**: `src/local_ocr/core/yigdzin_assets.py` が手本です。モデル本体と、画像を見る部分
   （`mmproj`）の 2 つの GGUF の取得先を、動かない番号つきで書きます
2. **エンジンのクラス**: `src/local_ocr/engines/yigdzin.py`（行を見つけてから読む形）か
   `src/local_ocr/engines/paddle_vl.py`（ページごと読む形）を写します。
   `id`・`label`・`note`・`platforms`・`assets`・`recognize` が要ります
3. **llama-server の起動**: `src/local_ocr/core/runtime.py`。別のポート（`default_port`）を選びます。
   llama-server の本体は同梱済みなので、足すものはありません
4. **一覧に足す**: `src/local_ocr/engines/__init__.py` の `_ALL` に 1 行足します
5. **英語の名前**: `engines/` のクラスに `label_en` と `note_en` を持たせれば出ます。
   今あるエンジンのように `ui/i18n.py` の `engine.<id>.label` に書いても構いません
6. **試験**: `tests/test_yigdzin.py` が手本です。モデルが無くても通る部分を中心に書きます
7. **表示と一覧**: 下のチェックリストのとおり

## (d) 出す前のチェックリスト

- [ ] ライセンスが再配布を許すもの（Apache-2.0 / MIT / CC BY など）で、repo の表示で確かめた
- [ ] モデルの取得先が、40 桁の番号（コミット）で固定されている（`main` などの枝の名前では指さない）
- [ ] 取得する大きさが、実際のファイルの大きさと合っている（`info.py` か `--list-engines`）
- [ ] `label_en` / `hint_en`（または `note_en`）が書いてあり、英語の画面で名前が出る
- [ ] `NOTICE` に、元のモデルの名前・ライセンス・取得先を書いた
- [ ] `README.md`、`docs/guide-more.md`、`docs/design.md` の一覧に足した
- [ ] 画像を実際に読ませた結果（行数・数行の出力・既存のモデルとの比較）を PR に貼った
- [ ] アプリの画面のスクリーンショットを PR に貼った
- [ ] PR の説明に、更新履歴に載せる 1 行（日本語と英語）を書いた。更新履歴のファイルは触っていない
- [ ] `uv run pytest` が通る
- [ ] `uv run --with ruff==0.16.8 ruff check .` が通る
- [ ] `git add` はファイルを 1 つずつ指定した。`.env` や鍵のファイルは含めていない
