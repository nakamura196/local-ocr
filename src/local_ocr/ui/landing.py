"""起動画面。いきなり作業画面を出さず、まず受け皿を出す。

**「画像はこのパソコンから出ません」を目に入る場所に置く。** 手元で動くことが
この道具の値打ちなので、隠さない。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from ..core import fetch
from . import theme
from .i18n import engine_note, t

if TYPE_CHECKING:
    from ..app import App

TITLE = "Local OCR"


class LandingView:
    def __init__(self, ctx: App) -> None:
        self.ctx = ctx
        self.page = ctx.page
        self.state = ctx.state
        self.engine_note = theme.muted("")
        self.engine_state = ft.Container()

    def build(self) -> ft.Control:
        drop = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.IMAGE_OUTLINED, size=52, color=ft.Colors.PRIMARY),
                    ft.Text(
                        t("landing.drop.title"),
                        size=15,
                        weight=ft.FontWeight.W_500,
                    ),
                    theme.muted(t("landing.drop.hint")),
                    ft.Container(height=6),
                    ft.Row(
                        [
                            ft.FilledButton(
                                t("landing.pick"),
                                icon=ft.Icons.IMAGE_OUTLINED,
                                tooltip="⌘O",
                                on_click=lambda _: self.ctx.pick_image(),
                            ),
                            ft.OutlinedButton(
                                t("landing.paste"),
                                icon=ft.Icons.CONTENT_PASTE,
                                tooltip="⌘V",
                                on_click=lambda _: self.ctx.paste_image(),
                            ),
                            ft.OutlinedButton(
                                t("landing.folder"),
                                icon=ft.Icons.FOLDER_OPEN_OUTLINED,
                                disabled=True,
                                tooltip=t("landing.soon"),
                            ),
                            ft.OutlinedButton(
                                t("landing.iiif"),
                                icon=ft.Icons.LINK,
                                disabled=True,
                                tooltip=t("landing.soon"),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=10,
                        wrap=True,
                    ),
                    ft.Container(height=10),
                    theme.chip(
                        ft.Icons.LOCK_OUTLINE,
                        t("landing.privacy"),
                        ft.Colors.PRIMARY,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=8,
                tight=True,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
            padding=ft.Padding.all(24),
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=ft.BorderRadius.all(theme.RADIUS),
            ink=True,
            on_click=lambda _: self.ctx.pick_image(),
        )

        self._sync_engine()
        body = ft.Container(
            content=ft.Column(
                [
                    ft.Column(
                        [theme.heading(TITLE, 26), theme.muted(t("app.lead"), 13)],
                        spacing=2,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    drop,
                    *self._resume(),
                    self._engine_row(),
                ],
                spacing=theme.GAP,
                expand=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.all(theme.PAD),
            expand=True,
        )

        return ft.Column(
            [
                theme.top_bar(
                    [
                        ft.Icon(ft.Icons.DOCUMENT_SCANNER_OUTLINED, color=ft.Colors.PRIMARY),
                        ft.Text(TITLE, size=15, weight=ft.FontWeight.W_600),
                    ],
                    [
                        ft.IconButton(
                            ft.Icons.SETTINGS_OUTLINED,
                            tooltip=t("common.settings"),
                            on_click=lambda _: self.ctx.go("settings"),
                        )
                    ],
                ),
                body,
            ],
            spacing=0,
            expand=True,
        )

    # --- 前回の続き -------------------------------------------------------
    def _resume(self) -> list[ft.Control]:
        last = self.state.last()
        if last is None:
            return []
        preview = " ".join(last.text.split())[:46]
        card = theme.card(
            ft.Row(
                [
                    ft.Icon(ft.Icons.HISTORY, size=18, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Column(
                        [
                            ft.Text(t("landing.resume", source=last.source), size=13),
                            theme.muted(preview + ("…" if len(last.text) > 46 else ""), 11),
                        ],
                        spacing=1,
                        expand=True,
                    ),
                    ft.TextButton(t("common.open"), on_click=lambda _: self._open_last()),
                    ft.IconButton(
                        ft.Icons.CLOSE,
                        icon_size=16,
                        tooltip=t("landing.resume.forget"),
                        on_click=lambda _: self._forget(),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
            padding=10,
        )
        return [card]

    def _open_last(self) -> None:
        last = self.state.last()
        if last is None:
            return
        self.state.job = last
        self.ctx.go("work")

    def _forget(self) -> None:
        self.state.forget()
        self.ctx.go("landing")

    # --- 読む道具(控えめに) -----------------------------------------------
    def _engine_row(self) -> ft.Control:
        return ft.Row(
            [
                theme.muted(t("common.engine")),
                self.ctx.engine_dropdown(width=250, on_change=self._on_engine),
                self.engine_state,
                self.engine_note,
                ft.Container(expand=True),
                ft.TextButton(
                    t("common.settings"),
                    icon=ft.Icons.SETTINGS_OUTLINED,
                    on_click=lambda _: self.ctx.go("settings"),
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
        )

    def _on_engine(self, _event=None) -> None:
        self._sync_engine()
        self.page.update()

    def _sync_engine(self) -> None:
        engine = self.state.engine
        self.engine_note.value = engine_note(engine)
        if engine.assets and not engine.available():
            size = fetch.human(fetch.total_bytes(engine.assets))
            self.engine_state.content = theme.chip(
                ft.Icons.DOWNLOAD_OUTLINED,
                t("landing.not_fetched", size=size),
                ft.Colors.TERTIARY,
            )
        else:
            self.engine_state.content = None
