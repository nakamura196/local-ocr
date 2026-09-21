"""IIIF マニフェストの URL を受け取る窓。

**窓を閉じてから知らせない。** マニフェストが読めたかどうかは、この窓の中で
出す。閉じてから画面の下に小さく出しても、URL を打ち直せる場所に戻れない。

クリップボードに URL が入っていれば、最初から入れておく。マニフェストの URL は
たいてい別の画面からコピーしてくるので、貼る手間をここで省く。
"""

from __future__ import annotations

import asyncio
import traceback
from typing import TYPE_CHECKING

import flet as ft

from ..core import source
from . import i18n, status, theme
from .i18n import t

if TYPE_CHECKING:
    from ..app import App


class IIIFDialog:
    def __init__(self, ctx: App) -> None:
        self.ctx = ctx
        self.page = ctx.page
        self.busy = False
        self.field = ft.TextField(
            label=t("iiif.url"),
            autofocus=True,
            dense=True,
            keyboard_type=ft.KeyboardType.URL,
            on_submit=lambda _: self.submit(),
        )
        self.state = status.Inline(bar_width=200)
        self.state.hide()
        self.cancel_button = ft.TextButton(
            t("common.cancel"), on_click=lambda _: self.page.pop_dialog()
        )
        self.open_button = ft.FilledButton(t("common.open"), on_click=lambda _: self.submit())

    def open(self) -> None:
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(t("iiif.title")),
                content=ft.Container(
                    content=ft.Column(
                        [self.field, theme.muted(t("iiif.note"), 11), self.state.control],
                        spacing=10,
                        tight=True,
                    ),
                    width=520,
                ),
                actions=[self.cancel_button, self.open_button],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )
        self.page.run_task(self._prefill)

    async def _prefill(self) -> None:
        """クリップボードの URL を入れておく。文字が入っていなければ何もしない。"""
        try:
            text = (await self.page.clipboard.get() or "").strip()
        except Exception:  # noqa: BLE001 - 入っていなくても、窓は使える
            return
        if not self.field.value and source.is_url(text) and len(text) < 2000:
            self.field.value = text
            self.page.update()

    # --- 開く -------------------------------------------------------------
    def submit(self) -> None:
        if not self.busy:
            self.page.run_task(self._load)

    async def _load(self) -> None:
        url = (self.field.value or "").strip()
        if not source.is_url(url):
            self.state.show(status.failed(t("iiif.error.parse"), t("iiif.error.detail")))
            self.page.update()
            return
        self._set_busy(True)
        try:
            bundle = await asyncio.to_thread(source.expand, url, i18n.current())
        except Exception as exc:  # noqa: BLE001 - 窓の中に出して、打ち直せるようにする
            traceback.print_exc()
            self.state.show(status.explain(exc))
            self._set_busy(False)
            return
        self.page.pop_dialog()
        self.ctx.open_bundle(bundle)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.field.disabled = busy
        self.open_button.disabled = busy
        if busy:
            self.state.show(status.loading(t("iiif.loading")))
        self.page.update()
