"""起動と、画面の行き来。

画面は 3 つ(ランディング / 作業 / 設定)。それぞれ ui/ の下に分けてあり、
ここは「どれを出すか」と「画面をまたぐ操作」(画像を渡す・コピー・キーボード)
だけを持つ。画面どうしは互いを知らない。
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from pathlib import Path

import flet as ft
from PIL import Image

from .core import ocr as ocr_call
from .core import source
from .ui import theme
from .ui.i18n import engine_label, t
from .ui.iiif_input import IIIFDialog
from .ui.landing import LandingView
from .ui.settings import SettingsView
from .ui.state import IMAGE_SUFFIXES, AppState, Doc, Job
from .ui.work import WorkView

TITLE = "Local OCR"

_VIEWS = {"landing": LandingView, "work": WorkView, "settings": SettingsView}


class App:
    """画面の入れ替えと、画面をまたぐ操作。各画面はこれを `ctx` として受け取る。"""

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.state = AppState()
        self.current = ""
        # 設定から戻る先。作業中に設定を開いても、作業に戻れるようにする。
        self._previous = "landing"
        self.view: object | None = None

        page.title = TITLE
        theme.setup(page)
        page.window.width = 1180
        page.window.height = 780
        page.window.min_width = 920
        page.window.min_height = 620
        page.window.prevent_close = True
        page.window.on_event = self._on_window_event
        page.on_keyboard_event = self._on_key

        # Flet 0.86 の FilePicker はサービス。pick_files() が選ばれたものを返す
        # (以前の on_result コールバックは無い)。
        self.picker = ft.FilePicker()
        page.services.append(self.picker)

        self.body = ft.Container(expand=True)
        page.add(self.body)
        self.go("landing")

        # ほかの道具に開いたままにしてあるなら、起動のときに開け直す。
        # 前回の終了でサーバは止まっているので、ここで立てないと
        # 「設定では開いているのに繋がらない」になる。
        bridge = self.state.bridge
        if bridge is not None and bridge.enabled:
            page.run_task(self._open_bridge)

    async def _open_bridge(self) -> None:
        """窓口を開け直す。**待つのは糸(スレッド)の中。** ここで待つと、
        重みを読んでいる 1 分ほど、画面が固まったまま出てこない。"""
        try:
            await asyncio.to_thread(self.state.bridge.turn_on)  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001 - 開けなくても、アプリは使える
            # 設定を開けば「開いていません」と、次にすることが出る。
            traceback.print_exc()

    # --- 画面の行き来 -----------------------------------------------------
    def go(self, name: str) -> None:
        if name == "settings":
            self._previous = self.current or "landing"
        self.current = name
        self.view = _VIEWS[name](self)
        self.body.content = self.view.build()
        self.page.update()

    def go_back(self) -> None:
        """設定から、開く前の画面へ戻る。"""
        self.go(self._previous if self._previous != "settings" else "landing")

    # --- 画面をまたぐ部品 -------------------------------------------------
    def engine_dropdown(self, width: int = 240, on_change=None) -> ft.Dropdown:
        """読む道具を選ぶ箱。どの画面でも同じものを出す。

        Flet 0.86 の Dropdown は on_change ではなく **on_select**。
        """
        dropdown = ft.Dropdown(
            value=self.state.engine_id,
            options=[
                ft.DropdownOption(key=e.id, text=engine_label(e)) for e in self.state.usable
            ],
            dense=True,
            text_size=13,
            width=width,
        )

        def handler(event) -> None:
            self.state.set_engine(dropdown.value)
            if on_change is not None:
                on_change(event)

        dropdown.on_select = handler
        return dropdown

    # --- 入口 -------------------------------------------------------------
    def pick_image(self) -> None:
        self.page.run_task(self._pick_async)

    async def _pick_async(self) -> None:
        files = await self.picker.pick_files(
            dialog_title=t("pick.dialog"),
            allowed_extensions=list(IMAGE_SUFFIXES),
        )
        if not files:
            return
        path = files[0].path
        try:
            image = ocr_call.load(path)
        except Exception as exc:  # noqa: BLE001 - 画面に出して続けられるようにする
            self.notify(t("pick.failed", error=exc))
            traceback.print_exc()
            return
        self.start_job(image, Path(path).name, Path(path))

    def paste_image(self) -> None:
        image = ocr_call.from_clipboard()
        if image is None:
            self.notify(t("paste.empty"))
            return
        self.start_job(image, t("source.pasted"))

    def pick_folder(self) -> None:
        self.page.run_task(self._pick_folder_async)

    async def _pick_folder_async(self) -> None:
        """フォルダの中の画像を、ページの束として開く。中のフォルダまでは潜らない。"""
        chosen = await self.picker.get_directory_path(dialog_title=t("pick.folder.dialog"))
        if not chosen:
            return
        try:
            bundle = await asyncio.to_thread(source.expand, chosen)
        except OSError as exc:
            self.notify(t("pick.failed", error=exc))
            return
        if not bundle.items:
            self.notify(t("pick.folder.empty"))
            return
        self.open_bundle(bundle)

    def open_iiif(self) -> None:
        """IIIF マニフェストの URL を聞く窓を出す。"""
        IIIFDialog(self).open()

    def open_bundle(self, bundle: source.Bundle) -> None:
        """入口が開いたページの並びを、作業画面の束にする。"""
        self.open_doc(Doc.of(bundle.items, title=bundle.title, origin=bundle.origin))

    def start_job(self, image: Image.Image, label: str, path=None) -> None:
        """画像を受け取ったら作業画面へ移り、そのまま読み始める。"""
        self.state.open_job(Job(source=label, image=image, path=path))
        self.go("work")
        self.view.start()  # type: ignore[union-attr]

    def open_doc(self, doc: Doc) -> None:
        """ページの束(フォルダ・IIIF)を開く。

        **1 枚のときだけ、そのまま読み始める。** 何十・何百ページを黙って
        読み始めると、取り寄せも読みも止められないまま走り出す。
        """
        self.state.open(doc)
        self.go("work")
        if doc.many:
            self.view.opened()  # type: ignore[union-attr]
        else:
            self.view.start()  # type: ignore[union-attr]

    # --- 知らせ -----------------------------------------------------------
    def notify(self, message: str) -> None:
        self.page.show_dialog(ft.SnackBar(content=ft.Text(message)))

    # --- キーボード -------------------------------------------------------
    def _on_key(self, e: ft.KeyboardEvent) -> None:
        """⌘V で貼り付け、⌘C でコピー、⌘O で開く(Windows は Ctrl)。"""
        if not (e.meta if sys.platform == "darwin" else e.ctrl):
            return
        key = (e.key or "").upper()
        if key == "O":
            self.pick_image()
        elif key == "V":
            self.paste_image()
        elif key == "C" and isinstance(self.view, WorkView):
            self.view.copy()

    # --- 終了 -------------------------------------------------------------
    def _on_window_event(self, e) -> None:
        if e.type == ft.WindowEventType.CLOSE:
            # 常駐しているエンジンも止めてから閉じる。
            self.state.shutdown()
            # destroy() はコルーチン。そのまま呼ぶと窓が閉じない (docs/design.md)。
            self.page.run_task(self.page.window.destroy)


def main(page: ft.Page) -> None:
    App(page)


def run() -> None:
    # ft.app() は非推奨。0.86 は ft.run()。
    ft.run(main)
