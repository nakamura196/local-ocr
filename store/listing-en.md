# Microsoft ストア 掲載情報(英語)

`listing-ja.md` の英語版。**節の見出しは日本語のまま**にしてある。
両方を同じ書式で読めるようにするため。

**日本語版の翻訳ではない。** 同じことを英語の読者に向けて書き直したもの。
片方を直したら、もう片方も見ること。事実(同梱物の版、対応エンジン、
できないこと)がずれると、どちらかが嘘になる。

雛形は [archival-packager](https://github.com/nakamura196/archival-packager) の
`store/listing-en.md`。

**ここが正本。** 2026-09-24 にこのファイルのまま `scripts/store_submit.py` で送り、英語の掲載を初めて出した。
ストアの欄は素のテキストで、改行はそのまま表示される。**段落の途中で折り返さないこと。**

---

## 製品名

Local OCR

## 簡単な説明(Short description・最大 1000 文字)

Reads the characters in an image on your own computer — nothing leaves the device. Choose the recognition engine to match the material: modern print, Japanese cursive (kuzushiji), Chinese classical texts, or Tibetan. For archives, libraries and researchers digitising and transcribing historical documents.

## 説明(Description)

Local OCR is a desktop application that recognises the characters in an image and turns them into text. Recognition happens entirely on your computer; no image or recognised text is sent anywhere.

It was built for researchers and librarians who need to transcribe large volumes of pre-modern material — cursive Japanese and classical Chinese in particular.

What it does:
• Several recognition engines to choose from, suited to different material (modern print, Japanese cursive (kuzushiji), Chinese classical / multilingual text, and Tibetan)
• Reads image files, the clipboard, a folder of page images, or a IIIF manifest URL
• Exports plain text (.txt) or TEI/XML (.xml)
• Compares two engines run over the same page, side by side
• Also usable from the command line, for batch processing

Why you might use it:
• Nothing else to install. The tools that run the recognition engines are bundled
• Originals are never modified. Files are read only
• Nothing is sent externally, apart from a one-time model download per engine and, if you use it, the IIIF manifest you point it at

Who it is for:
Anyone responsible for digitising and transcribing pre-modern documents or early printed books at an archive, library, museum or research institution. It does not assume you are an information systems specialist.

Please note:
• The interface is Japanese and English
• The recognition models for the PaddleOCR-VL engine (about 1.8 GB) and the Tibetan Yigdzin-1 engine (about 1.7 GB) are downloaded the first time you use them

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

`store/screenshots/en/01-landing.png`(1486×973。要件の1366×768以上)。
2026-09-22、CIのWindows runnerで`scripts/screenshot-windows.ps1`(雛形は
archival-packager)が撮った。settings.jsonを仕込んで言語をenに固定している
(runnerの既定言語には依存しない)。
**掲載情報には言語ごとに1枚以上の画像が要る**(archival-packagerが実測。
画像なしで送ると `NoScreenshotsOfAnyType` で確定段階から弾かれる) — ja側も
同じ手順で撮ってある。
**まだ「起動直後の何も読んでいない画面」だけ。** README のmacOS版(画像を
読ませて認識済み)と同じ形にするのは次の課題。
