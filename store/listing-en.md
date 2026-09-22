# Microsoft ストア 掲載情報(英語)

`listing-ja.md` の英語版。**節の見出しは日本語のまま**にしてある。
両方を同じ書式で読めるようにするため。

**日本語版の翻訳ではない。** 同じことを英語の読者に向けて書き直したもの。
片方を直したら、もう片方も見ること。事実(同梱物の版、対応エンジン、
できないこと)がずれると、どちらかが嘘になる。

雛形は [archival-packager](https://github.com/nakamura196/archival-packager) の
`store/listing-en.md`。

---

## 製品名

Local OCR

## 簡単な説明(Short description・最大 1000 文字)

Reads the characters in an image on your own computer — nothing leaves the
device. Choose the recognition engine to match the material: modern print,
Japanese cursive (kuzushiji), or Chinese classical texts. For archives,
libraries and researchers digitising and transcribing historical documents.

## 説明(Description)

Local OCR is a desktop application that recognises the characters in an
image and turns them into text. Recognition happens entirely on your
computer; no image or recognised text is sent anywhere.

It was built for researchers and librarians who need to transcribe large
volumes of pre-modern material — cursive Japanese and classical Chinese in
particular. It is the successor to
[tei-scanner](https://github.com/nakamura196/tei-scanner) (macOS only, Apple
Vision only).

What it does

- Several recognition engines to choose from, suited to different material:
  modern print, Japanese cursive (kuzushiji), and Chinese classical /
  multilingual text
- Reads image files, the clipboard, a folder of page images, or a
  [IIIF](https://iiif.io/) manifest URL
- Exports plain text (.txt) or TEI/XML (.xml)
- Compares two engines run over the same page, side by side
- Also usable from the command line, for batch processing

Why you might use it

- Nothing else to install. The tools that run the recognition engines are
  bundled
- Originals are never modified. Files are read only
- Nothing is sent externally, apart from a one-time model download per
  engine and, if you use it, the IIIF manifest you point it at

Who it is for

Anyone responsible for digitising and transcribing pre-modern documents or
early printed books at an archive, library, museum or research institution.
It does not assume you are an information systems specialist.

Please note

- The interface is Japanese and English
- The PaddleOCR-VL engine's recognition model is about 1.8 GB and is
  downloaded the first time you use it

Developed by Satoru Nakamura (The University of Tokyo).

## 検索キーワード(最大 7 つ)

OCR
kuzushiji
handwritten text recognition
digital archive
transcription
historical documents
character recognition

## カテゴリ

日本語版と同じ(Productivity)。カテゴリは言語ごとには変えられない。

## スクリーンショット

**未撮影(2026-09-22 時点)。** `store/screenshots/en/` に置く。
**掲載情報には言語ごとに1枚以上の画像が要る**(archival-packagerが実測。
画像なしで送ると `NoScreenshotsOfAnyType` で確定段階から弾かれる)。
`en-US` の掲載情報を出すには、パッケージ(AppxManifest)が `en-US` を
Resources に宣言している必要がある。

CI の Windows ビルドで撮る場合、初回起動は OS の言語に従うので、runner が
英語環境である限り何もしなくても英語の画面が撮れる(archival-packager の
`scripts/screenshot-windows.ps1` が手本になる。local-ocr にはまだ無い)。
