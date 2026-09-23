"""日本語 / 英語。画面に出る文字はすべてここを通す。

**画面の中に文字を直接書かない。** 書いた瞬間に片方の言語だけ直し忘れる。
足すときは `_STRINGS` に 1 行足す。訳が無い鍵は日本語のまま出す(落とさない)。
"""

from __future__ import annotations

import locale
import os
import re
import sys

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
    "work.save.text.page": ("テキスト（このページ）", "Text — this page"),
    "work.save.text.all": ("テキスト（すべてのページ）", "Text — all pages"),
    "work.save.tei.page": ("TEI/XML（このページ）", "TEI/XML — this page"),
    "work.save.tei.all": ("TEI/XML（すべてのページ）", "TEI/XML — all pages"),
    "work.save.empty": ("保存できる文字がまだありません", "There is no text to save yet"),
    "work.save.none_read": (
        "まだ読み終えたページがありません。「すべて読む」を押してください。",
        "No pages have been read yet. Press Read all.",
    ),
    "work.save.done": ("保存しました: {name}", "Saved: {name}"),
    "work.save.done.pages": (
        "保存しました: {name}（{pages} ページ）",
        "Saved: {name} ({pages} pages)",
    ),
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
    "work.copy.line": ("この行をコピー", "Copy this line"),
    "work.copy.line.done": (
        "この行をコピーしました（{chars} 文字）",
        "Copied this line ({chars} characters)",
    ),
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
    # --- ページの束(フォルダ・IIIF) ---
    "work.page": ("{index} / {total} ページ", "Page {index} of {total}"),
    "work.page.prev": ("前のページ", "Previous page"),
    "work.page.next": ("次のページ", "Next page"),
    "work.loading.page": ("版面を読み込んでいます…", "Opening the page image…"),
    "work.opened": (
        "{count} ページを開きました。「読む」でこのページ、「すべて読む」で全部を読みます。",
        "Opened {count} pages. Read does this page; Read all does every page.",
    ),
    "work.read.all": ("すべて読む", "Read all"),
    "work.read.stop": ("中止", "Stop"),
    "work.read.stopping": (
        "いま読んでいるページまでで止めます",
        "Stopping after the page being read",
    ),
    "work.read.done.count": ("読み終わり {done} / {total}", "{done} of {total} read"),
    "work.read.progress": (
        "{index} / {total} ページ目を読んでいます…（{name}）",
        "Reading page {index} of {total} ({name})…",
    ),
    "work.read.all.done": ("{count} ページを読み終わりました", "Read {count} pages"),
    "work.read.all.done.failed": (
        "{count} ページを読み終わりました（{failed} ページは読めませんでした）",
        "Read {count} pages ({failed} could not be read)",
    ),
    "work.read.all.stopped": (
        "{count} ページまで読んで止めました",
        "Stopped after {count} pages",
    ),
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
    "settings.storage.iiif": (
        "IIIF で取り寄せた版面: {size}",
        "Page images fetched over IIIF: {size}",
    ),
    "settings.storage.iiif.removed": (
        "取り寄せた版面を削除しました",
        "Removed the fetched page images",
    ),
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
    # --- ほかの道具から使えるようにする ---
    "settings.share": ("ほかの道具から使えるようにする", "Let other tools use this"),
    "settings.share.note": (
        "このパソコンの中の別の道具（校正の画面など）から、この OCR を呼べるようにします。",
        "Let another tool on this computer (a proofreading page, say) call this OCR.",
    ),
    "share.switch": ("窓口を開ける", "Open it"),
    "share.endpoint": ("接続先", "Address"),
    "share.endpoint.copy": ("接続先をコピー", "Copy the address"),
    "share.endpoint.copied": ("接続先をコピーしました", "Copied the address"),
    "share.privacy": (
        "開いている間も、画像はこのパソコンから出ません。",
        "Even while this is open, images never leave this computer.",
    ),
    "share.engines": (
        "いま外から使えるのは PaddleOCR-VL だけです。",
        "For now PaddleOCR-VL is the only engine offered here.",
    ),
    "share.origins": ("許可する相手", "Pages allowed to connect"),
    "share.origins.note": (
        "ここに書いた頁からしか繋げません。",
        "Only the pages listed here can connect.",
    ),
    "share.origins.browser": (
        "はじめて繋ぐとき、ブラウザが「ローカルネットワークへの接続を許可しますか」と一度だけ聞きます。",
        "The first time, the browser asks once whether to allow a local network connection.",
    ),
    "share.origins.empty": (
        "まだ誰も許可していないので、どの頁からも繋げません。",
        "Nobody is allowed yet, so no page can connect.",
    ),
    "share.origin.hint": ("https://…", "https://…"),
    "share.origin.add": ("追加", "Add"),
    "share.origin.remove": ("この相手を外す", "Remove this one"),
    "share.origin.bad.empty": (
        "相手の住所を入れてください。",
        "Type the address of the page.",
    ),
    "share.origin.bad.wildcard": (
        "* は使えません。繋いでよい相手を 1 つずつ足してください。",
        "* is not allowed. Add each page you trust, one at a time.",
    ),
    "share.origin.bad.scheme": (
        "https://example.com の形で入れてください。",
        "Enter it like https://example.com.",
    ),
    "share.origin.bad.path": (
        "頁までではなく、その手前まで（例: https://example.com）を入れてください。",
        "Leave off the path — just https://example.com.",
    ),
    "share.state.opening": (
        "開いています。初めて開くときは 1 分ほどかかります。",
        "Opening. The first time takes about a minute.",
    ),
    "share.state.reopening": (
        "許可する相手が変わったので、開き直しています。",
        "Reopening with the new list.",
    ),
    "share.state.closing": ("閉じています。", "Closing."),
    "share.state.open": (
        "開いています。ほかの道具から使えます。",
        "Open. Other tools can use it now.",
    ),
    "share.state.down": ("開いていません", "It is not open"),
    "share.state.down.detail": (
        "いちど切ってから、もう一度入れ直してください。",
        "Switch it off and on again.",
    ),
    "share.state.other": (
        "閉じましたが、ほかのプログラムが同じポート（{port}）を使っています。",
        "Closed, but another program is using port {port}.",
    ),
    # --- 入口 ---
    "pick.dialog": ("読みたい画像を選びます", "Choose an image to read"),
    "pick.failed": ("画像を開けませんでした: {error}", "Could not open the image: {error}"),
    "pick.folder.dialog": ("読みたい画像の入ったフォルダを選びます", "Choose a folder of images"),
    "pick.folder.empty": (
        "このフォルダに画像がありません（中のフォルダまでは見ません）",
        "No images in that folder (sub-folders are not searched)",
    ),
    # --- IIIF マニフェスト ---
    "iiif.title": ("IIIF マニフェストから開く", "Open a IIIF manifest"),
    "iiif.url": ("マニフェストの URL", "Manifest URL"),
    "iiif.note": (
        "マニフェストと版面は、その配信元から取り寄せます。読むのはこのパソコンの中だけです。",
        (
            "The manifest and its page images come from their server."
            " The reading itself stays on this computer."
        ),
    ),
    "iiif.loading": ("マニフェストを読んでいます…", "Reading the manifest…"),
    "iiif.opened": ("{label}（{count} ページ）", "{label} ({count} pages)"),
    "iiif.error.detail": (
        "URL がマニフェスト（JSON）のものか、開ける状態かを確かめてください。",
        "Check that the URL points at a manifest (JSON) and that it is reachable.",
    ),
    "iiif.error.fetch": (
        "マニフェストを取り寄せられませんでした: {error}",
        "Could not fetch the manifest: {error}",
    ),
    "iiif.error.parse": (
        "マニフェストとして読めませんでした（JSON ではありません）",
        "That is not a manifest (it is not JSON)",
    ),
    "iiif.error.collection": (
        "これはコレクションです。中のマニフェストの URL を渡してください。",
        "That is a collection. Give the URL of one of its manifests.",
    ),
    "iiif.error.empty": (
        "このマニフェストには版面が 1 枚もありませんでした",
        "That manifest has no page images",
    ),
    "iiif.error.image": (
        "版面を取り寄せられませんでした: {error}",
        "Could not fetch the page image: {error}",
    ),
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
        "読む画像。フォルダなら中の画像すべて、IIIF マニフェストの URL なら全カンバスを読みます。",
        "Images to read. A folder reads every image in it; a IIIF manifest URL reads every canvas.",
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
    "cli.manifest": (
        "マニフェストを読みました: {label}（{count} ページ）",
        "Read the manifest: {label} ({count} pages)",
    ),
    # --- 時間 ---
    "timing.plain": ("{seconds} 秒", "{seconds}s"),
    "timing.with_prepare": ("{seconds} 秒（準備 {prepare} 秒）", "{seconds}s (setup {prepare}s)"),
    # --- 読む道具の名前(訳が無ければ engines/ 側の日本語をそのまま出す) ---
    "engine.apple-vision.label": ("Apple Vision（macOS 標準）", "Apple Vision (macOS built-in)"),
    "engine.apple-vision.note": (
        "取得するものはありません。現代の活字・手書きに向きます。",
        "Nothing to download. Good for modern print and handwriting.",
    ),
    "engine.ndl-koten-lite.label": (
        "NDL古典籍OCR Lite（くずし字）",
        "NDL Koten OCR Lite (kuzushiji)",
    ),
    "engine.ndl-koten-lite.note": (
        "初回だけ 79MB ほど取得します。古典籍・くずし字に向きます。",
        "Downloads about 79MB the first time. Good for pre-modern Japanese books.",
    ),
    "engine.ndl-lite.label": ("NDLOCR Lite（近代の活字）", "NDL OCR Lite (modern print)"),
    "engine.ndl-lite.note": (
        "初回だけ 150MB ほど取得します。近代資料の活字・手書きに向きます。",
        "Downloads about 150MB the first time. Good for modern print and handwriting.",
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
    """OS の言語。分からなければ英語にしておく。

    **環境変数 (LANG) を頼りにしない。** 端末から起動すると LANG が入っているが、
    Finder やスタートメニューから起動したアプリには入らない。v0.1.0 はこれを
    頼りにしていたため、日本語の Mac でも初回は英語の画面になっていた
    (2026-09-22、デモ動画の収録で発覚。開発中は端末から起動していて気づかなかった)。
    OS の「言語と地域」の設定を直接読む。
    """
    code = _os_ui_language()
    if not code:
        try:
            code = locale.getlocale()[0] or ""
        except (TypeError, ValueError):
            code = ""
        code = code or os.environ.get("LANG", "")
    return "ja" if code.lower().startswith("ja") else "en"


def _os_ui_language() -> str:
    """OS の画面の言語 ("ja-JP" など)。取れなければ空文字。"""
    try:
        if sys.platform == "darwin":
            # システム設定 → 言語と地域 の「優先する言語」の先頭
            from Foundation import NSLocale

            langs = NSLocale.preferredLanguages()
            return str(langs[0]) if langs else ""
        if sys.platform == "win32":
            import ctypes

            # 下位 10 ビットが主言語。0x11 が日本語 (LANG_JAPANESE)
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return "ja" if lang_id & 0x3FF == 0x11 else "en"
    except Exception:  # noqa: BLE001 — 取れなければ従来の方法に任せる
        return ""
    return ""


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
