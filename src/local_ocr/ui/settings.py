"""設定画面。読む道具ごとに「取得済み / 未取得（◯◯MB）」を出し、その場で取得・削除する。

1.8GB のものがあるので、**何をいつ落とすかは利用者が決める。** 作業画面が
黙って落とし始めることはしない。

「ほかの道具から使えるようにする」もここに置く。開けている間だけサーバを
立てたままにし、接続先と、繋いでよい相手を表に出す(`core/bridge.py`)。
"""

from __future__ import annotations

import asyncio
import threading
import traceback
from typing import TYPE_CHECKING

import flet as ft

from ..core import bridge as bridge_core
from ..core import fetch, iiif, reading
from ..core.bridge import Bridge
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
        # 常駐のサーバを持つ道具が 1 つも無ければ、窓口の節ごと出さない。
        self.bridge = ctx.state.bridge
        self.bridge_card = BridgeCard(self, self.bridge) if self.bridge else None
        self.disk = theme.muted("")
        # IIIF で取り寄せた版面。黙って増えるものなので、大きさを見せて消せるようにする。
        self.iiif_note = theme.muted("")
        self.iiif_row = ft.Row(
            [
                self.iiif_note,
                ft.TextButton(
                    t("common.delete"),
                    icon=ft.Icons.DELETE_OUTLINE,
                    on_click=lambda _: self._clear_iiif(),
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        )

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
                            *self._share_section(),
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
                                        self.iiif_row,
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

    def _share_section(self) -> list[ft.Control]:
        if self.bridge_card is None:
            return []
        return [
            _section(t("settings.share"), t("settings.share.note")),
            self.bridge_card.build(),
            ft.Container(height=8),
        ]

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
        cached = iiif.cache_bytes()
        self.iiif_note.value = t("settings.storage.iiif", size=fetch.human(cached))
        # 取り寄せていないうちは、行ごと出さない(使っていない人に見せる意味がない)。
        self.iiif_row.visible = bool(cached)

    def _clear_iiif(self) -> None:
        iiif.clear_cache()
        self.refresh()

    def refresh(self) -> None:
        self._sync_disk()
        for card in self.cards:
            card.sync()
        if self.bridge_card is not None:
            self.bridge_card.sync()
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
                    *self._mode_rows(),
                ],
                spacing=8,
            ),
            padding=14,
        )

    def _mode_rows(self) -> list[ft.Control]:
        """読み方を選ぶ欄。選べる道具(PaddleOCR-VL・NDL)だけに出す。"""
        own = reading.modes(self.engine)
        if not own:
            return []
        group = ft.RadioGroup(
            value=self.view.state.mode_of(self.engine),
            on_change=self._on_mode,
            content=ft.Column(
                [
                    ft.Radio(
                        value=mode,
                        label=f"{t('mode.' + mode)} — {t('mode.' + mode + '.detail')}",
                        label_style=ft.TextStyle(size=12),
                    )
                    for mode in own
                ],
                spacing=0,
            ),
        )
        return [
            ft.Divider(height=1),
            ft.Text(t("settings.mode"), size=12, weight=ft.FontWeight.W_500),
            group,
        ]

    def _on_mode(self, event) -> None:
        mode = str(event.control.value or "")
        if mode in reading.modes(self.engine):
            self.view.state.set_mode(self.engine.id, mode)

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
            # 窓口は閉じない。ほかの道具は窓口から使い続けられ、消した道具を
            # 頼まれたときは窓口が「取得していません」と返す(`core/gateway.py`)。
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


class BridgeCard:
    """ほかの道具に開く窓口。開けている間だけサーバを立てたままにする。

    出すのは 2 つ。**接続先**(相手が投げる先)と、**繋いでよい相手**の一覧。
    どちらも隠すと、繋がらないときに何を直せばよいか分からなくなる。
    """

    def __init__(self, view: SettingsView, bridge: Bridge) -> None:
        self.view = view
        self.page = view.page
        self.bridge = bridge
        self.busy = False
        # 開こうとして駄目だったときの言い分。`status.explain` が作る。
        self.report: status.Report | None = None

        self.switch = ft.Switch(
            value=bridge.enabled, tooltip=t("share.switch"), on_change=self._on_toggle
        )
        self.endpoint = ft.Text(
            bridge.endpoint, size=13, weight=ft.FontWeight.W_500, selectable=True
        )
        self.state_line = status.Inline(bar_width=180)
        self.origin_rows = ft.Column(spacing=2)
        self.new_origin = ft.TextField(
            hint_text=t("share.origin.hint"),
            dense=True,
            expand=True,
            text_size=13,
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            on_submit=lambda _: self.add_origin(),
        )
        self.details = ft.Container(visible=False)

    def build(self) -> ft.Control:
        self.details.content = ft.Column(
            [
                ft.Divider(height=1),
                ft.Row(
                    [
                        theme.muted(t("share.endpoint")),
                        self.endpoint,
                        ft.IconButton(
                            ft.Icons.COPY_OUTLINED,
                            icon_size=16,
                            tooltip=t("share.endpoint.copy"),
                            on_click=lambda _: self.copy_endpoint(),
                        ),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                theme.muted(f"{t('share.privacy')} {t('share.engines')}", 11),
                ft.Container(height=4),
                ft.Text(t("share.origins"), size=13, weight=ft.FontWeight.W_600),
                self.origin_rows,
                ft.Row(
                    [
                        self.new_origin,
                        ft.FilledTonalButton(
                            t("share.origin.add"),
                            icon=ft.Icons.ADD,
                            on_click=lambda _: self.add_origin(),
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                theme.muted(f"{t('share.origins.note')} {t('share.origins.browser')}", 11),
            ],
            spacing=8,
        )
        self.sync()
        return theme.card(
            ft.Column(
                [
                    ft.Row(
                        [
                            # 題と説明は上の見出しに出ている。ここではスイッチの名前だけ。
                            ft.Text(
                                t("share.switch"),
                                size=14,
                                weight=ft.FontWeight.W_600,
                                expand=True,
                            ),
                            self.switch,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                    # **状態は details の外に置く。** 中に入れると、閉じた
                    # 直後の一言(ポートが塞がっている等)が一緒に消えてしまう。
                    self.state_line.control,
                    self.details,
                ],
                spacing=10,
            ),
            padding=14,
        )

    # --- 表示の更新 -------------------------------------------------------
    def sync(self) -> None:
        self.switch.value = self.bridge.enabled
        self.switch.disabled = self.busy
        self.details.visible = self.bridge.enabled
        self.endpoint.value = self.bridge.endpoint
        self._sync_origins()
        if self.busy:
            return  # 動いている間の文面は、動かしている側が出している
        if self.report is not None:
            self.state_line.show(self.report)
        elif not self.bridge.enabled:
            self.state_line.hide()
        elif self.bridge.open:
            self.state_line.plain(t("share.state.open"))
        else:
            # 開けたままにしてあるのに立っていない(落ちた・取得を消した)。
            self.state_line.show(status.failed(t("share.state.down"), t("share.state.down.detail")))

    def _sync_origins(self) -> None:
        origins = self.bridge.origins
        if not origins:
            self.origin_rows.controls = [theme.muted(t("share.origins.empty"))]
            return
        self.origin_rows.controls = [self._origin_row(v) for v in origins]

    def _origin_row(self, origin: str) -> ft.Control:
        return ft.Row(
            [
                ft.Icon(ft.Icons.LANGUAGE, size=16, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(origin, size=13, expand=True, selectable=True),
                ft.IconButton(
                    ft.Icons.CLOSE,
                    icon_size=16,
                    tooltip=t("share.origin.remove"),
                    disabled=self.busy,
                    on_click=lambda _, v=origin: self.remove_origin(v),
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    # --- 接続先 -----------------------------------------------------------
    def copy_endpoint(self) -> None:
        # クリップボードは 0.86 では await が要る。
        self.page.run_task(self._copy_endpoint)

    async def _copy_endpoint(self) -> None:
        await self.page.clipboard.set(self.bridge.endpoint)
        self.view.ctx.notify(t("share.endpoint.copied"))

    # --- 開け閉め ---------------------------------------------------------
    def _on_toggle(self, event) -> None:
        if self.busy:
            # 動いている最中は受け付けない。見た目だけ戻す。
            self.switch.value = self.bridge.enabled
            self.page.update()
            return
        if event.control.value:
            self.page.run_task(self._open, t("share.state.opening"))
        else:
            self.page.run_task(self._close)

    async def _open(self, message: str) -> None:
        """開ける。重みの読み込みで 1 分ほどかかるので、待つのは糸(スレッド)の中。"""
        self.report = None
        # 待つ前に「開けにいく」と見せる。`turn_on` の中で立てると、
        # 1 分のあいだ接続先も相手の一覧も出てこない。
        bridge_core.set_enabled(True)
        self._working(message)
        try:
            await asyncio.to_thread(self.bridge.turn_on)
        except Exception as exc:  # noqa: BLE001 - 画面に出して続けられるようにする
            # 「取得がまだ」「起動できなかった」を、次の一手つきの文面に直す。
            self.report = status.explain(exc)
            traceback.print_exc()
        finally:
            self._done()

    async def _close(self) -> None:
        self.report = None
        self._working(t("share.state.closing"))
        try:
            await asyncio.to_thread(self.bridge.turn_off)
            # もう 1 つ開いたこのアプリが同じポートで待っていることがある。
            # 閉じたと言い切ると、繋がり続けている理由が分からなくなる。
            if await asyncio.to_thread(self.bridge.port_busy):
                self.report = status.failed(
                    t("share.state.other", port=self.bridge.port), t("share.state.down.detail")
                )
        finally:
            self._done()

    def _working(self, message: str) -> None:
        self.busy = True
        self.sync()
        self.state_line.show(status.loading(message))
        self.page.update()

    def _done(self) -> None:
        self.busy = False
        self.sync()
        self.page.update()

    # --- 繋いでよい相手 ---------------------------------------------------
    def add_origin(self) -> None:
        try:
            origin = bridge_core.normalize_origin(self.new_origin.value or "")
        except ValueError as exc:
            self.state_line.show(status.failed(t(f"share.origin.bad.{exc}"), ""))
            self.page.update()
            return
        self.new_origin.value = ""
        if origin in self.bridge.origins:
            self.sync()
            self.page.update()
            return
        self.bridge.add_origin(origin)
        self._reopen()

    def remove_origin(self, origin: str) -> None:
        self.bridge.remove_origin(origin)
        self._reopen()

    def _reopen(self) -> None:
        """変えた一覧を画面に出す。

        窓口(`core/gateway.py`)は呼ばれるたびに一覧を読むので、立て直さなくても
        その場で効く(前の版は llama-server を立て直していて、1 分ほど待たせた)。
        """
        self.sync()
        self.page.update()


def _section(title: str, note: str) -> ft.Control:
    return ft.Column(
        [ft.Text(title, size=13, weight=ft.FontWeight.W_600), theme.muted(note, 11)],
        spacing=1,
    )
