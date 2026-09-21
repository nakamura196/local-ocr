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

### Status

**Not released yet.** No signed build is published; run it from source for now
(see [Development](#development)).

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
| [NDLOCR Lite](https://github.com/ndl-lab/ndlocr-lite) | both | 150 MB | Modern Japanese print |
| [NDL Kotenseki OCR Lite](https://github.com/ndl-lab/ndlkotenocr-lite) | both | 79 MB | Pre-modern Japanese, cursive |
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

### いまの状態

**まだ配っていません。** 署名済みの配布物はありません。当面は手元で動かしてください
（[開発](#開発)）。

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
| [NDLOCR Lite](https://github.com/ndl-lab/ndlocr-lite) | 両方 | 150MB | 近代資料・活字 |
| [NDL古典籍OCR Lite](https://github.com/ndl-lab/ndlkotenocr-lite) | 両方 | 79MB | 古典籍・くずし字 |
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
