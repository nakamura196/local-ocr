# Local OCR

[English](#english) · [日本語](#日本語)

## English

A desktop application that reads the characters in an image **on your own
computer**. macOS and Windows. Choose the recognition engine to match the
material — modern print, Japanese cursive (kuzushiji), or Chinese classical
texts — and export plain text or TEI/XML.

### Download

| Platform | Where |
| --- | --- |
| macOS | [Releases](https://github.com/nakamura196/local-ocr/releases/latest) (signed and notarised `.dmg`) |
| Windows | Microsoft Store — coming soon |

Nothing else to install. `llama-server`, which runs the PaddleOCR-VL model,
is bundled with the application; recognition models are fetched on first use.

### What it does

Images in, characters out — nothing else. Recognition happens entirely on
your computer.

- **Input**: image files, the clipboard, a folder of page images, or a
  [IIIF](https://iiif.io/) manifest URL
- **Output**: plain text (`.txt`) or TEI/XML (`.xml`)
- **Compare**: run two engines over the same page and read the results
  side by side
- Japanese and English interface, light and dark

### Links

- [Source code](https://github.com/nakamura196/local-ocr) (MIT)
- [Privacy policy](privacy-policy.md)

### Credits

Satoru Nakamura (The University of Tokyo).
Contact: nakamura@hi.u-tokyo.ac.jp

---

## 日本語

画像に写っている文字を **手元の端末の中だけで** 読み取るデスクトップ
アプリケーションです。macOS と Windows に対応します。現代の活字、崩し字、
漢文など、資料に合わせて認識エンジンを選べます。プレーンテキストまたは
TEI/XML で書き出せます。

### ダウンロード

| | |
| --- | --- |
| macOS | [Releases](https://github.com/nakamura196/local-ocr/releases/latest)(署名・公証済みの `.dmg`) |
| Windows | Microsoft Store — 近日公開 |

導入作業は要りません。PaddleOCR-VL のモデルを動かす `llama-server` はアプリに
同梱しています。認識モデルは初回使用時に取得します。

### できること

画像を入れると、文字が出てきます。文字の認識はすべて手元の端末の中で行います。

- **入力**: 画像ファイル、クリップボード、ページ画像を集めたフォルダ、
  [IIIF](https://iiif.io/) マニフェストの URL
- **出力**: プレーンテキスト(`.txt`)または TEI/XML(`.xml`)
- **比較**: 同じページを2つのエンジンで読ませて、結果を並べて確認
- 日本語・英語の画面、ライト・ダーク両対応

### リンク

- [ソースコード](https://github.com/nakamura196/local-ocr)(MIT)
- [プライバシーポリシー](privacy-policy.md)

### 開発

中村 覚(東京大学)
連絡先: nakamura@hi.u-tokyo.ac.jp
