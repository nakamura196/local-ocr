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
footer: "Contact: nakamura.satoru@mail.u-tokyo.ac.jp"
---

The Windows version is updated automatically by the Microsoft Store.
The Mac version is not. Download the new version from [Releases](https://github.com/nakamura196/local-ocr/releases/latest) and replace the old one in your Applications folder.
Downloaded recognition models are kept, so you don't need to fetch them again.
{: .point }

Dates are in Japan time.

### 0.1.10 (4 October 2026)

- Yigdzin-1 (Tibetan) could fail with "Could not start the OCR engine" and read nothing. This happened on computers where another app was already using the port its reading engine listens on (8081). If the port is taken, it now moves to a free one. PaddleOCR-VL is fixed in the same way.
- If the engine still cannot start, the reason (in English) is now shown under the error. Please include it when you contact us.

### 0.1.9 (4 October 2026)

- When the app was force-quit or crashed, the reading engine it uses (llama-server) could keep running in the background, holding about 800 MB of memory. It now stops however the app ends. Closing the window stops it as before.

### 0.1.8 (4 October 2026)

- With Yigdzin-1 (Tibetan), a ruler in the photo could make the whole page end with "No text found". Lines that cannot be read are now skipped, and the other lines are still returned.
- When reading fails, the app no longer shows "No text found"; it reports the failure instead.
- Re-reading a line no longer replaces the text with just a short mark such as ༄༅། །.

### 0.1.7 (2 October 2026)

- Yigdzin-1 (Tibetan) no longer keeps repeating the same words after the end of a manuscript line. A page used to take several minutes and the result was buried in repetition; now only each line's reading is kept, and a page takes about 20 seconds to a minute.
- When a ruler or the edge of the paper is mistaken for a line, that line is left out of the result.

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
