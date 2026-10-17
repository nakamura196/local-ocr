---
lang: en
home_url: /en.html
image: /assets/ogp/ogp-en.png
title: The compare screen now highlights where engines disagree
eyebrow: News · 16 October 2026
lead: Read the same image with two or more engines, and the characters they read differently are highlighted. You only need to check the highlighted places.
alternate: { title: 日本語, url: 2026-10-16-compare-diff.html, lang: ja }
nav:
  - { title: Home, url: ../en.html }
  - { title: News, url: ../news-en.html }
  - { title: Changelog, url: ../changelog-en.html }
footer: "Contact: nakamura.satoru@mail.u-tokyo.ac.jp"
---

Available from version 0.1.11.
The Windows version is updated by the Microsoft Store. On a Mac, download the new version from [Releases](https://github.com/nakamura196/local-ocr/releases/latest).

### Watch

A page of a classical Chinese book read with PaddleOCR-VL and PP-OCRv6, with the highlighted characters checked against the page image (about 1 minute, with narration and captions).

<iframe src="https://www.youtube-nocookie.com/embed/Wydw_eBCwZs?rel=0" title="Local OCR: comparing two OCR engines" style="width:100%;aspect-ratio:16/9;border:0" allow="encrypted-media; picture-in-picture; fullscreen" allowfullscreen loading="lazy"></iframe>

### What changed

Press "Compare" at the top and tick two or more engines.
Characters that the engines read differently get a yellow background and an underline.
Where nothing is highlighted, every engine read the same.

- In the "In use" column, a character is highlighted if any other engine read it differently
- In the other columns, a character is highlighted if it differs from the "In use" result
- Each column shows how much it agrees (for example "96%") and how many characters differ
- To turn the highlighting off, switch off "Highlight differences" at the top

### Check highlighted characters against the page

A highlight only means the readings differ. It doesn't say which one is right.
On the page in the video, the highlights fell into three kinds:

- **Text outside the main text**: one engine also read the ruler and the library label in the photo
- **Misreadings**: for example 機栝 read as 機恬. The page image shows which is right
- **Variant forms**: 別 and 别 are the same character in different forms. Not necessarily an error

### Also changed

The label on the result used for copying and saving is now "In use".
For a result without line positions (no boxes on the image) it reads "In use (no positions)".

Other changes in this version are in the [changelog](../changelog-en.html).
