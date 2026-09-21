"""設定画面。読む道具ごとに「取得済み / 未取得（◯◯MB）」を出し、その場で取得・削除する。

1.8GB のものがあるので、**何をいつ落とすかは利用者が決める。** 作業画面が
黙って落とし始めることはしない。
"""

from __future__ import annotations

import threading
import traceback
from typing import TYPE_CHECKING

import flet as ft

from ..core import fetch
from ..core.paths import data_dir
from ..engines import Engine, runs_here
from . import i18n, status, theme
from .i18n import LANGUAGES, engine_label, engine_note, t

if TYPE_CHECKING:
    from ..app import App

OS_NAMES = {"darwin": "macOS", "win32": "Windows"}


class SettingsView:
    def __init__(self, ctx: App) -> None:
        self.ctx = ctx
        self.page = ctx.page
        self.state = ctx.state
        self.cards = [EngineCard(self, e) for e in self.state.engines]
        self.disk = theme.muted("")

    def build(self) -> ft.Control:
        self._sync_disk()
        return ft.Column(
            [
                theme.top_bar(
                    [
                        theme.back_button(lambda _: self.ctx.go_back()),
                        ft.Text(t("common.settings"), size=15, weight=ft.FontWeight.W_600),
                    ]
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            _section(t("settings.engines"), t("settings.engines.note")),
                            *[c.build() for c in self.cards],
                            ft.Container(height=8),
                            _section(t("settings.look"), t("settings.look.note")),
                            theme.card(self._theme_row(), padding=12),
                            ft.Container(height=8),
                            _section(t("settings.language"), t("settings.language.note")),
                            theme.card(self._language_row(), padding=12),
                            ft.Container(height=8),
                            _section(t("settings.storage"), t("settings.storage.note")),
                            theme.card(
                                ft.Column(
                                    [
                                        ft.Text(
                                            str(data_dir()), size=12, selectable=True
                                        ),
                                        self.disk,
                                    ],
                                    spacing=4,
                                ),
                                padding=12,
                            ),
                        ],
                        spacing=10,
                        scroll=ft.ScrollMode.AUTO,
                        expand=True,
                    ),
                    padding=ft.Padding.all(theme.PAD),
                    expand=True,
                ),
            ],
            spacing=0,
            expand=True,
        )

    def _theme_row(self) -> ft.Control:
        from .theme import theme_mode

        current = {
            ft.ThemeMode.SYSTEM: "system",
            ft.ThemeMode.LIGHT: "light",
            ft.ThemeMode.DARK: "dark",
        }[theme_mode()]
        picker = ft.SegmentedButton(
            segments=[
                ft.Segment(value="system", label=ft.Text(t("settings.theme.system"), size=12)),
                ft.Segment(value="light", label=ft.Text(t("settings.theme.light"), size=12)),
                ft.Segment(value="dark", label=ft.Text(t("settings.theme.dark"), size=12)),
            ],
            selected=[current],
            show_selected_icon=False,
            on_change=lambda e: theme.set_theme_mode(
                self.page, next(iter(e.control.selected))
            ),
        )
        return ft.Row([picker], vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _language_row(self) -> ft.Control:
        picker = ft.SegmentedButton(
            segments=[
                ft.Segment(value=code, label=ft.Text(name, size=12))
                for code, name in LANGUAGES.items()
            ],
            selected=[i18n.current()],
            show_selected_icon=False,
            on_change=self._on_language,
        )
        return ft.Row([picker], vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _on_language(self, event) -> None:
        i18n.set_current(next(iter(event.control.selected)))
        # 画面ごと作り直す。文字は組み立てのときに決まるので、作り直さないと変わらない。
        self.ctx.go("settings")

    def _sync_disk(self) -> None:
        used = sum(
            a.size_on_disk() for e in self.state.engines for a in e.assets if a.fetched()
        )
        self.disk.value = (
            t("settings.storage.used", size=fetch.human(used))
            if used
            else t("settings.storage.empty")
        )

    def refresh(self) -> None:
        self._sync_disk()
        for card in self.cards:
            card.sync()
        self.page.update()


class EngineCard:
    """読む道具 1 つ分。取得・削除と、その進みぐあいを持つ。"""

    def __init__(self, view: SettingsView, engine: Engine) -> None:
        self.view = view
        self.page = view.page
        self.engine = engine
        self.busy = False
        self.state_chip = ft.Container()
        self.progress = status.Inline(bar_width=220)
        self.progress.hide()
        self.get_button = ft.FilledTonalButton(
            t("settings.fetch"), icon=ft.Icons.DOWNLOAD_OUTLINED, on_click=lambda _: self.fetch()
        )
        self.remove_button = ft.TextButton(
            t("common.delete"),
            icon=ft.Icons.DELETE_OUTLINE,
            on_click=lambda _: self.confirm_remove(),
        )

    def build(self) -> ft.Control:
        self.sync()
        return theme.card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Row(
                                        [
                                            ft.Text(
                                                engine_label(self.engine),
                                                size=14,
                                                weight=ft.FontWeight.W_600,
                                            ),
                                            self.state_chip,
                                        ],
                                        spacing=10,
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    ),
                                    theme.muted(engine_note(self.engine)),
                                ],
                                spacing=4,
                                expand=True,
                            ),
                            self.get_button,
                            self.remove_button,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                    self.progress.control,
                ],
                spacing=8,
            ),
            padding=14,
        )

    # --- 表示の更新 -------------------------------------------------------
    def sync(self) -> None:
        engine, assets = self.engine, list(self.engine.assets)
        here = runs_here(engine)
        fetched = here and all(a.fetched() for a in assets)
        size = fetch.human(fetch.total_bytes(assets)) if assets else ""

        if not here:
            names = "・".join(OS_NAMES.get(p, p) for p in sorted(engine.platforms))
            self.state_chip.content = theme.chip(
                ft.Icons.BLOCK, t("settings.state.unsupported", names=names)
            )
        elif not assets:
            self.state_chip.content = theme.chip(
                ft.Icons.CHECK_CIRCLE_OUTLINE, t("settings.state.none_needed"), ft.Colors.PRIMARY
            )
        elif fetched:
            self.state_chip.content = theme.chip(
                ft.Icons.CHECK_CIRCLE_OUTLINE,
                t("settings.state.fetched", size=size),
                ft.Colors.PRIMARY,
            )
        else:
            self.state_chip.content = theme.chip(
                ft.Icons.DOWNLOAD_OUTLINED,
                t("settings.state.not_fetched", size=size),
                ft.Colors.TERTIARY,
            )

        self.get_button.visible = here and bool(assets) and not fetched
        self.get_button.disabled = self.busy
        self.remove_button.visible = here and bool(assets) and fetched and not self.busy

    # --- 取得 -------------------------------------------------------------
    def fetch(self) -> None:
        if self.busy:
            return
        self.busy = True
        self.sync()
        self.progress.show(status.fetching(t("settings.fetch.start"), None))
        self.page.update()
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self) -> None:
        def on_progress(label: str, ratio: float | None) -> None:
            self.progress.show(status.fetching(label, ratio))
            self.page.update()

        try:
            fetch.download_all(self.engine.assets, on_progress)
            self.progress.plain(t("settings.fetch.done"))
        except Exception as exc:  # noqa: BLE001 - 画面に出して続けられるようにする
            self.progress.show(
                status.failed(
                    t("settings.fetch.failed", error=exc), t("settings.fetch.failed.detail")
                )
            )
            traceback.print_exc()
        finally:
            self.busy = False
            self.view.refresh()

    # --- 削除 -------------------------------------------------------------
    def confirm_remove(self) -> None:
        size = fetch.human(sum(a.size_on_disk() for a in self.engine.assets))
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(t("settings.remove.title")),
            content=ft.Text(
                t("settings.remove.body", engine=engine_label(self.engine), size=size)
            ),
            actions=[
                ft.TextButton(t("common.cancel"), on_click=lambda _: self.page.pop_dialog()),
                ft.FilledButton(t("common.delete"), on_click=lambda _: self._do_remove()),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)

    def _do_remove(self) -> None:
        self.page.pop_dialog()
        try:
            # 常駐しているものは先に止める。動いたまま消すと、次の起動で
            # 壊れた状態のまま残ることがある。
            self.engine.shutdown()
            for asset in self.engine.assets:
                fetch.remove(asset)
            self.progress.plain(t("settings.remove.done"))
        except Exception as exc:  # noqa: BLE001 - 画面に出して続けられるようにする
            self.progress.show(
                status.failed(
                    t("settings.remove.failed", error=exc), t("settings.remove.failed.detail")
                )
            )
            traceback.print_exc()
        self.view.refresh()


def _section(title: str, note: str) -> ft.Control:
    return ft.Column(
        [ft.Text(title, size=13, weight=ft.FontWeight.W_600), theme.muted(note, 11)],
        spacing=1,
    )
