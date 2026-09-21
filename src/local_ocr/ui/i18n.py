"""日本語 / 英語。画面に出る文字はすべてここを通す。

**画面の中に文字を直接書かない。** 書いた瞬間に片方の言語だけ直し忘れる。
足すときは `_STRINGS` に 1 行足す。訳が無い鍵は日本語のまま出す(落とさない)。
"""

from __future__ import annotations

import locale
import os
import re

from ..core import prefs

LANGUAGES = {"ja": "日本語", "en": "English"}

# 鍵: (日本語, English)
_STRINGS: dict[str, tuple[str, str]] = {
    # --- 共通 ---
    "app.lead": ("画像の文字を、このパソコンの中で読みます。", "Read text out of images, entirely on this computer."),
    "common.back": ("戻る", "Back"),
    "common.settings": ("設定", "Settings"),
    "common.open": ("開く", "Open"),
    "common.cancel": ("やめる", "Cancel"),
    "common.delete": ("削除", "Delete"),
    "common.engine": ("読む道具", "OCR engine"),
    # --- ランディング ---
    "landing.drop.title": ("読みたい画像を、ここから渡してください", "Give me the image you want read"),
    "landing.drop.hint": ("枠の中をクリックしても、画像を選べます", "Click anywhere in this area to choose an image"),
    "landing.pick": ("画像を選ぶ", "Choose image"),
    "landing.paste": ("貼り付け", "Paste"),
    "landing.folder": ("フォルダ", "Folder"),
    "landing.iiif": ("IIIF マニフェスト", "IIIF manifest"),
    "landing.soon": (
        "フォルダの一括処理と IIIF マニフェストは次の版で対応します",
        "Folders and IIIF manifests are coming in the next version",
    ),
    "landing.privacy": ("画像はこのパソコンから出ません", "Images never leave this computer"),
    "landing.resume": ("前回の続き: {source}", "Last time: {source}"),
    "landing.resume.forget": ("この記録を消す", "Forget this"),
    "landing.not_fetched": ("未取得（{size}）", "Not downloaded ({size})"),
    # --- 作業画面 ---
    "work.mode.one": ("1 つで読む", "One engine"),
    "work.mode.compare": ("くらべる", "Compare"),
    "work.run": ("読む", "Read"),
    "work.run.compare": ("くらべて読む", "Read with each"),
    "work.copy": ("コピー", "Copy"),
    "work.save": ("保存", "Save"),
    "work.save.text": ("テキスト（.txt）", "Text (.txt)"),
    "work.save.tei": ("TEI/XML（.xml）", "TEI/XML (.xml)"),
    "work.save.empty": ("保存できる文字がまだありません", "There is no text to save yet"),
    "work.save.done": ("保存しました: {name}", "Saved: {name}"),
    "work.save.done.with_image": (
        "保存しました: {name}（版面を {image} として隣に置きました）",
        "Saved: {name} (the page image went next to it as {image})",
    ),
    "work.save.no_image": (
        "版面がないので TEI/XML では保存できません",
        "TEI/XML needs the page image",
    ),
    "work.save.no_image.detail": (
        "TEI/XML は行の枠を版面の座標で書くので、画像が要ります。テキストでは保存できます。",
        "TEI/XML records each line's box in page coordinates, so it needs the image. You can still save as text.",
    ),
    "save.dialog.text": ("テキストの保存先を選びます", "Where to save the text"),
    "save.dialog.tei": ("TEI/XML の保存先を選びます", "Where to save the TEI/XML"),
    "work.lines": ("読んだ行", "Lines"),
    "work.lines.count": ("{count} 行", "{count} lines"),
    "work.view.lines": ("行ごと", "By line"),
    "work.view.whole": ("まとめて", "All text"),
    "work.empty.lines": (
        "まだ読んでいません。上の「読む」を押してください。",
        "Nothing read yet. Press Read above.",
    ),
    "work.no_image": ("画像がありません", "No image"),
    "work.text_only": ("画像がありません（文字だけを持ち帰りました）", "No image (text only)"),
    "work.no_image.title": ("読む画像がありません", "There is no image to read"),
    "work.no_image.detail": (
        "最初の画面に戻って、画像を選ぶか貼り付けてください。",
        "Go back to the first screen and choose or paste an image.",
    ),
    "work.no_image.action": ("最初の画面へ", "Back to start"),
    "work.preparing": ("読む準備をしています", "Getting ready"),
    "work.reading": ("読んでいます…", "Reading…"),
    "work.reading.with": ("{engine} で読んでいます…", "Reading with {engine}…"),
    "work.reading.many": ("{count} つの道具で読んでいます…", "Reading with {count} engines…"),
    "work.waiting": ("待っています", "Waiting"),
    "work.done": ("読み終わりました（{count} 行 / {chars} 文字{timing}）", "Done ({count} lines / {chars} characters{timing})"),
    "work.nothing_found": ("文字が見つかりませんでした", "No text found"),
    "work.nothing_found.detail": (
        "別の読む道具を選ぶか、画像を大きく切り直してみてください。",
        "Try another engine, or crop the image larger.",
    ),
    "work.copy.empty": ("コピーできる文字がまだありません", "There is no text to copy yet"),
    "work.copy.done": ("{chars} 文字をコピーしました", "Copied {chars} characters"),
    "work.engine.changed": (
        "読む道具を {engine} にしました。「読む」を押してください。",
        "Engine set to {engine}. Press Read.",
    ),
    "work.consent.title": (
        "{engine} は、はじめに {size} の取得が必要です",
        "{engine} needs a {size} download first",
    ),
    "work.consent.detail": (
        "取得は 1 回だけです。設定画面からいつでも削除できます。",
        "It downloads once. You can remove it anytime in Settings.",
    ),
    "work.consent.action": ("{size} を取得して読む", "Download {size} and read"),
    # --- くらべる ---
    "compare.pick": ("くらべる道具を 1 つ以上選んでください", "Choose at least one engine to compare"),
    "compare.showing": ("版面に表示中", "Shown on the page"),
    "compare.use": ("これを使う", "Use this"),
    "compare.not_fetched": ("まだ取得していません", "Not downloaded yet"),
    "compare.not_fetched.detail": (
        "設定で取得すると、くらべられます。",
        "Download it in Settings to include it.",
    ),
    "compare.empty": ("まだ読んでいません", "Nothing read yet"),
    "compare.stats": ("{count} 行 / {chars} 文字 / {timing}", "{count} lines / {chars} chars / {timing}"),
    "compare.summary": ("{engine} {count} 行 / {timing}", "{engine} {count} lines / {timing}"),
    # --- 設定 ---
    "settings.engines": ("読む道具", "OCR engines"),
    "settings.engines.note": ("使うものだけ取得すれば足ります。", "Download only the ones you use."),
    "settings.look": ("見た目", "Appearance"),
    "settings.look.note": ("画面の明るさを選べます。", "Choose how the app looks."),
    "settings.theme.system": ("システムに合わせる", "Match system"),
    "settings.theme.light": ("明るい", "Light"),
    "settings.theme.dark": ("暗い", "Dark"),
    "settings.language": ("言語 / Language", "Language / 言語"),
    "settings.language.note": ("画面の言葉を選べます。", "Choose the language of the app."),
    "settings.storage": ("置き場所", "Where files go"),
    "settings.storage.note": ("取得したものはここに入ります。", "Downloads are kept here."),
    "settings.storage.used": ("いま使っている大きさ: {size}", "Currently using {size}"),
    "settings.storage.empty": ("まだ何も取得していません", "Nothing downloaded yet"),
    "settings.fetch": ("取得", "Download"),
    "settings.state.none_needed": ("取得はいりません", "Nothing to download"),
    "settings.state.fetched": ("取得済み（{size}）", "Downloaded ({size})"),
    "settings.state.not_fetched": ("未取得（{size}）", "Not downloaded ({size})"),
    "settings.state.unsupported": ("この機械では使えません（{names} 用）", "Not available on this machine ({names} only)"),
    "settings.fetch.start": ("取得を始めます", "Starting download"),
    "settings.fetch.done": ("取得できました。すぐ使えます。", "Downloaded. Ready to use."),
    "settings.fetch.failed": ("取得できませんでした: {error}", "Download failed: {error}"),
    "settings.fetch.failed.detail": (
        "ネットにつながっているかを確かめて、もう一度お試しください。途中まで取得した分は残っているので、続きから進みます。",
        "Check your internet connection and try again. Whatever finished is kept, so it resumes.",
    ),
    "settings.remove.title": ("取得したものを削除しますか", "Remove the downloaded files?"),
    "settings.remove.body": (
        "{engine} の {size} を消します。\nあとでいつでも取り直せます。",
        "This removes {size} for {engine}.\nYou can download it again anytime.",
    ),
    "settings.remove.done": ("削除しました", "Removed"),
    "settings.remove.failed": ("削除できませんでした: {error}", "Could not remove: {error}"),
    "settings.remove.failed.detail": (
        "ほかのアプリがファイルを使っていないか確かめてください。",
        "Check that no other app is using these files.",
    ),
    # --- 入口 ---
    "pick.dialog": ("読みたい画像を選びます", "Choose an image to read"),
    "pick.failed": ("画像を開けませんでした: {error}", "Could not open the image: {error}"),
    "paste.empty": (
        "クリップボードに画像がありません。画像をコピーしてからお試しください。",
        "There is no image on the clipboard. Copy an image first.",
    ),
    "source.pasted": ("貼り付けた画像", "Pasted image"),
    "source.last": ("前回の画像", "Last image"),
    # --- 端末から使う(CLI) ---
    "cli.description": (
        "画像の文字を、このパソコンの中で読みます。",
        "Read text out of images, entirely on this computer.",
    ),
    "cli.help.paths": (
        "読む画像。フォルダを渡すと、その中の画像をすべて読みます。",
        "Images to read. Give a folder to read every image in it.",
    ),
    "cli.help.engine": (
        "読む道具の id（--list-engines で一覧が出ます）",
        "Which engine to use (--list-engines lists them)",
    ),
    "cli.help.format": ("出し方。text か tei。", "Output format: text or tei."),
    "cli.help.out": (
        "書き出し先。省くと標準出力に出します。",
        "Where to write. Prints to standard output when omitted.",
    ),
    "cli.help.title": (
        "TEI の題。省くとファイル名から作ります。",
        "Title for the TEI. Taken from the file name when omitted.",
    ),
    "cli.help.fetch": (
        "読む道具がまだ手元に無ければ取得します。",
        "Download the engine first if it is not here yet.",
    ),
    "cli.help.quiet": ("進みぐあいを出しません。", "Do not print progress."),
    "cli.help.list": ("読む道具の一覧を出して終わります。", "List the engines and stop."),
    "cli.no_images": ("読む画像がありません。", "No images to read."),
    "cli.not_found": ("見つかりません", "not found"),
    "cli.unknown_engine": (
        "{engine} という読む道具はありません。--list-engines で一覧が出ます。",
        "There is no engine called {engine}. Use --list-engines to see them.",
    ),
    "cli.unsupported": (
        "{engine} はこの機械では使えません。",
        "{engine} does not run on this machine.",
    ),
    "cli.not_fetched": (
        "{engine} は、はじめに {size} の取得が必要です。--fetch を付けると取得します。",
        "{engine} needs a {size} download first. Add --fetch to download it.",
    ),
    "cli.read": (
        "{name}: {count} 行 / {chars} 文字 / {seconds} 秒",
        "{name}: {count} lines / {chars} chars / {seconds}s",
    ),
    "cli.wrote": (
        "{name} に書きました（{pages} ページ）",
        "Wrote {name} ({pages} pages)",
    ),
    "cli.failed": (
        "{name} を読めませんでした: {error}",
        "Could not read {name}: {error}",
    ),
    "cli.source.many": ("{count} 枚の画像", "{count} images"),
    # --- 時間 ---
    "timing.plain": ("{seconds} 秒", "{seconds}s"),
    "timing.with_prepare": ("{seconds} 秒（準備 {prepare} 秒）", "{seconds}s (setup {prepare}s)"),
    # --- 読む道具の名前(訳が無ければ engines/ 側の日本語をそのまま出す) ---
    "engine.apple-vision.label": ("Apple Vision（macOS 標準）", "Apple Vision (macOS built-in)"),
    "engine.apple-vision.note": (
        "取得するものはありません。現代の活字・手書きに向きます。",
        "Nothing to download. Good for modern print and handwriting.",
    ),
    "engine.paddle-vl.label": ("PaddleOCR-VL（漢籍・多言語）", "PaddleOCR-VL (multilingual)"),
    "engine.paddle-vl.note": (
        "初回だけ 1.8GB ほど取得します。版面ごと読み、縦書きにも向きます。",
        "Downloads about 1.8GB the first time. Reads a whole page, including vertical text.",
    ),
    # --- うまくいかないとき ---
    "error.server.title": ("OCR を起動できませんでした", "Could not start the OCR engine"),
    "error.server.detail": (
        "設定を開き、「OCR の本体」を削除してから取り直すと直ることがあります。",
        "In Settings, remove the engine's files and download them again.",
    ),
    "error.file.title": ("ファイルを扱えませんでした: {error}", "Could not use the file: {error}"),
    "error.file.detail": (
        "ファイルが移動・削除されていないかを確かめてください。",
        "Check that the file has not been moved or deleted.",
    ),
    "error.not_fetched.title": (
        "この読む道具は、まだ取得が済んでいません",
        "This engine has not been downloaded yet",
    ),
    "error.not_fetched.detail": (
        "設定を開いて取得してください。取得が済むまでは別の読む道具を選べます。",
        "Download it in Settings. Until then, you can pick another engine.",
    ),
    "error.other.title": ("うまくいきませんでした: {error}", "Something went wrong: {error}"),
    "error.other.detail": (
        "同じ画像で別の読む道具を試すか、画像を開き直してください。",
        "Try another engine with the same image, or open the image again.",
    ),
}


def _system_language() -> str:
    """OS の言語。分からなければ英語にしておく。"""
    try:
        code = locale.getlocale()[0] or ""
    except (TypeError, ValueError):
        code = ""
    code = code or os.environ.get("LANG", "")
    return "ja" if code.lower().startswith("ja") else "en"


def current() -> str:
    saved = str(prefs.get("lang") or "")
    return saved if saved in LANGUAGES else _system_language()


def set_current(code: str) -> None:
    prefs.save(lang=code if code in LANGUAGES else "ja")


def t(key: str, **kw: object) -> str:
    """鍵から文字を引く。鍵が無ければ鍵そのものを返す(気づけるように)。"""
    pair = _STRINGS.get(key)
    if pair is None:
        return key
    text = pair[1] if current() == "en" else pair[0]
    return text.format(**kw) if kw else text


def engine_label(engine) -> str:
    """読む道具の名前。訳が無ければ、道具が持っている日本語をそのまま出す。"""
    return _lookup(f"engine.{engine.id}.label", engine.label)


def engine_note(engine) -> str:
    return _lookup(f"engine.{engine.id}.note", engine.note)


def engine_short(engine) -> str:
    """括弧より前だけの短い名前。くらべる画面の見出しに使う。"""
    return re.split(r"[（(]", engine_label(engine))[0].strip()


def _lookup(key: str, fallback: str) -> str:
    pair = _STRINGS.get(key)
    if pair is None:
        return fallback
    return pair[1] if current() == "en" else pair[0]
