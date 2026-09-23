# Local OCR

A desktop application that reads the characters in an image **on your own
computer**. One codebase, macOS and Windows. Choose the recognition engine to
match the material — modern print, Japanese cursive (kuzushiji), or Chinese
classical texts — and export plain text or TEI/XML.

Successor to [tei-scanner](https://github.com/nakamura196/tei-scanner)
(Swift, macOS only, Apple Vision only).

By Satoru Nakamura (The University of Tokyo).

[English](#english) · [日本語](#日本語)

## English

![Local OCR reading a page of the Taketori monogatari: line boxes over the
scanned scroll on the left, the recognised lines on the right](docs/images/screenshot-en.png)

<sub>Sample page: *Taketori monogatari*, 3 scrolls, early Edo period —
National Diet Library Digital Collections,
<https://dl.ndl.go.jp/pid/1287221/1/2> (see [`NOTICE`](NOTICE)).</sub>

### Download

| Platform | Where | Notes |
| --- | --- | --- |
| macOS | [`.dmg` from Releases](https://github.com/nakamura196/local-ocr/releases/latest) | Signed and notarised by Apple — no "unidentified developer" prompt |
| Windows | [Microsoft Store](https://apps.microsoft.com/detail/9N07ZD1ZPKBZ) | Free; the Store signs it, so no SmartScreen warning |

Nothing else to install. `llama-server` is bundled. **Recognition models are
downloaded on first use** — up to about 1.8 GB for PaddleOCR-VL, less for the
others — so the first run of an engine takes a while and needs a network
connection. Everything after that stays on your machine.

There is also a [page with more detail](https://nakamura196.github.io/local-ocr/).
To run from source instead, see [Development](#development).

### What it does

Images in, characters out — nothing else. The recognised text is yours to copy
into whatever tool you proofread in.

- **Input**: image files, the clipboard, a folder of page images, or a
  [IIIF](https://iiif.io/) manifest URL
- **Output**: plain text (`.txt`) or TEI/XML (`.xml`) with `facsimile` zones,
  in the same shape tei-scanner produced
- **Compare**: run two engines over the same page and read the results
  side by side
- **Command line**: `local-ocr image.jpg`, `local-ocr folder --format tei
  --out out.xml`, `--list-engines`. The CLI does not import the GUI toolkit, so
  it runs on headless machines
- Japanese and English interface, light and dark

### Recognition engines

| Engine | Platform | Download | Suited to |
| --- | --- | --- | --- |
| Apple Vision | macOS | — | Modern print and handwriting. Fast |
| Windows OCR | Windows | — | Same. Not implemented yet |
| [NDLOCR Lite](https://github.com/ndl-lab/ndlocr-lite) | both | 157 MB | Modern Japanese print |
| [NDL Kotenseki OCR Lite](https://github.com/ndl-lab/ndlkotenocr-lite) | both | 83 MB | Pre-modern Japanese, cursive |
| PaddleOCR-VL | both | ~1.8 GB | Chinese classical texts, multilingual |

Models are fetched on first use and cached; `llama-server`, which runs the
PaddleOCR-VL model, is bundled with the application.

### Privacy

Recognition happens entirely on your computer. No image and no recognised text
is sent anywhere.

The one exception is the IIIF input: the manifest and the page images are
fetched from the repository that publishes them. They are then read locally.

### Development

Python 3.12 and [uv](https://docs.astral.sh/uv/).

```
uv sync
PYTHONPATH=src .venv/bin/python main.py          # the application
PYTHONPATH=src .venv/bin/python -m local_ocr.cli --list-engines
./scripts/fetch-binaries.zsh                     # needed before PaddleOCR-VL
uv run pytest
```

The design notes are in [`docs/design.md`](docs/design.md); the release
procedure is in [`docs/release.md`](docs/release.md). Both are in Japanese.
Commit messages are in English.

### Licence

MIT — see [`LICENSE`](LICENSE).

The recognition models and the bundled binaries carry their own terms; the
attributions required by them are in [`NOTICE`](NOTICE). The two NDL models are
CC BY 4.0, and llama.cpp is MIT.

## 日本語

![『竹取物語』の 1 ページを読んだところ。左に枠を重ねた版面、右に読んだ行が
並ぶ](docs/images/screenshot-ja.png)

<sub>写っている資料: 『竹取物語』3軸, 江戸前期 — 国立国会図書館デジタルコレクション
<https://dl.ndl.go.jp/pid/1287221/1/2> （[`NOTICE`](NOTICE) 参照）。</sub>

### ダウンロード

| | 入手先 | 備考 |
| --- | --- | --- |
| macOS | [Releases の `.dmg`](https://github.com/nakamura196/local-ocr/releases/latest) | Apple の署名・公証済み。「開発元が未確認」の警告は出ません |
| Windows | [Microsoft ストア](https://apps.microsoft.com/detail/9N07ZD1ZPKBZ) | 無料。ストアが署名するので警告は出ません |

ほかに入れるものはありません。`llama-server` は同梱しています。
**文字を読むためのモデルは、初回に使うときに取得します**
（PaddleOCR-VL で 1.8GB ほど。ほかはもっと小さい）。そのため、
各エンジンの 1 回目だけ時間がかかり、ネットワークが要ります。
以降は端末の中だけで動きます。

くわしくは[紹介ページ](https://nakamura196.github.io/local-ocr/)にあります。
手元のソースから動かす場合は[開発](#開発)へ。

### 何をする道具か

**画像 → 文字**に徹します。読んだ文字をコピーして、校正に使っている道具へ貼ってください。

- **入口**: 画像ファイル、クリップボードからの貼り付け、フォルダ（複数ページ一括）、
  [IIIF](https://iiif.io/) マニフェストの URL
- **出口**: テキスト（`.txt`）、または `facsimile` の枠付き TEI/XML（`.xml`）。
  形は tei-scanner が出していたものと同じです
- **くらべる**: 同じページを 2 つの道具で読み、結果を左右に並べて見られます
- **端末から**: `local-ocr 画像.jpg`、`local-ocr フォルダ --format tei --out out.xml`、
  `--list-engines`。画面の部品を読み込まないので、画面の無い機械でも動きます
- 日本語と英語、明るい配色と暗い配色

### 読む道具（エンジン）

| 道具 | 対応 | 取得 | 向き |
| --- | --- | --- | --- |
| Apple Vision | macOS | 不要 | 現代の活字・手書き。速い |
| Windows 標準 OCR | Windows | 不要 | 同上。未実装 |
| [NDLOCR Lite](https://github.com/ndl-lab/ndlocr-lite) | 両方 | 157MB | 近代資料・活字 |
| [NDL古典籍OCR Lite](https://github.com/ndl-lab/ndlkotenocr-lite) | 両方 | 83MB | 古典籍・くずし字 |
| PaddleOCR-VL | 両方 | 約 1.8GB | 漢籍・多言語 |

モデルは初回に取得して手元に残します。PaddleOCR-VL を動かす `llama-server` は
アプリに同梱します。

### 画像はどこへも送りません

読み取りはすべてこのパソコンの中で行います。画像も、読んだ文字も、外に出ません。

ただし IIIF を入口にしたときだけは、マニフェストと版面を、公開している配信元から
**取り寄せます**。読むのはそのあと、このパソコンの中です。

### 開発

Python 3.12 と [uv](https://docs.astral.sh/uv/)。

```
uv sync
PYTHONPATH=src .venv/bin/python main.py          # アプリ
PYTHONPATH=src .venv/bin/python -m local_ocr.cli --list-engines
./scripts/fetch-binaries.zsh                     # PaddleOCR-VL を使う前に
uv run pytest
```

設計は [`docs/design.md`](docs/design.md)、配る手順は
[`docs/release.md`](docs/release.md) にあります。コミットメッセージは英語です。

### ライセンス

MIT（[`LICENSE`](LICENSE)）。

モデルと同梱した実行ファイルには、それぞれの条件があります。表示が必要なものは
[`NOTICE`](NOTICE) にまとめてあります。NDL の 2 つは CC BY 4.0、llama.cpp は MIT です。
