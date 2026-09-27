---
lang: en
home_url: /en.html
image: /assets/ogp/ogp-en.png
title: Changelog
eyebrow: Local OCR
lead: What changed in each version. Newest first.
alternate: { title: 日本語, url: changelog.html, lang: ja }
nav:
  - { title: Home, url: en.html }
  - { title: Guide (Japanese), url: guide.html }
  - { title: GitHub, url: "https://github.com/nakamura196/local-ocr" }
footer: "Contact: nakamura@hi.u-tokyo.ac.jp"
---

The Windows version is updated automatically by the Microsoft Store.
The Mac version is not. Download the new version from [Releases](https://github.com/nakamura196/local-ocr/releases/latest) and replace the old one in your Applications folder.
Downloaded recognition models are kept, so you don't need to fetch them again.
{: .point }

Dates are in Japan time.

### 0.1.6 (28 September 2026)

- Draw a box on the image to read only that area.
- Choose how each engine reads, in Settings.
  - PaddleOCR-VL: "Text only" (as before) or "With line positions"
  - The two NDL engines: "Find the lines, then read" (as before) or "Read as one line"
- With "With line positions", PaddleOCR-VL lines are re-sorted into vertical reading order. Interlinear notes (warichū) come out right column first, then left.
- The app tells you when lines went missing or the same character was repeated.

### 0.1.5 (26 September 2026)

- The TEI/IIIF Editor's "Page OCR" can use PaddleOCR-VL, with a position (box) for each line.
- Fixed PaddleOCR-VL breaking down on images with a ruler in them.
- The editor's new URL (tei-editor.ldas.jp) can connect without changing any settings.

### 0.1.4 (25 September 2026)

- Darker, thicker scrollbars that are easier to find.
- On the Compare screen, the engine checkboxes wrap instead of running off the screen.
- Large page images are shrunk before display, so the app stays responsive.

### 0.1.3 (24 September 2026)

- Added Yigdzin-1, an engine for Tibetan.

### 0.1.2 (23 September 2026)

- On a Japanese Mac, the open and save dialogs are in Japanese.
- The menu shows each engine's full name.
- Download sizes use one unit.

### 0.1.1 (23 September 2026)

- Fixed a Japanese Mac showing the English screen on first launch.
- The model folder can be moved with the `LOCAL_OCR_DATA_DIR` environment variable (for advanced users).

### 0.1.0 (22 September 2026)

First release, for Mac, followed by Windows on the Microsoft Store.

- Read an image, check the result, and save it as text or TEI/XML.
- Engines: NDLOCR-Lite (modern Japanese print), NDL Kotenseki OCR-Lite (pre-modern Japanese, cursive), PaddleOCR-VL (classical Chinese, multilingual), Apple Vision (Mac only).
- The Compare screen shows two engines' results side by side.
