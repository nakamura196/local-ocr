"""作業画面。左に版面(枠の重ね描きつき)、右に読んだ行。

行を選ぶと対応する枠が光る(tei-scanner と同じ操作感)。枠を返さないエンジンでも
右側の並びは同じにして、画面の作りが読む道具によって変わらないようにする。

**「くらべる」に切り替えると、読む道具ごとの結果を横に並べる。** どれを版面に
重ねるかは利用者が選ぶ(`Job.primary`)。
"""

from __future__ import annotations

import asyncio
import io
import re
import time
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

import flet as ft

from ..core import export, fetch
from . import status, theme
from .compare import COLUMN, ResultColumn
from .i18n import engine_label, engine_short, t
from .state import Doc, Job, Run

if TYPE_CHECKING:
    from ..app import App
    from ..engines import Engine

# 版面の拡大の上限。小さな切り抜きを無闇に引き伸ばしても粗くなるだけ。
MAX_ZOOM = 2.0
# ページを行き来する帯の高さ。2 ページ以上のときだけ、版面の下に出す。
PAGER = 44


class WorkView:
    def __init__(self, ctx: App) -> None:
        self.ctx = ctx
        self.page = ctx.page
        self.state = ctx.state
        self.selected = -1
        self._png: bytes | None = None
        self._boxes: list[ft.Container] = []
        # 束を読んでいる途中で「中止」が押されたか。次のページに移る前に見る。
        self._cancel = False
        # いま束を読んでいる最中か。「くらべる」で読んでいるだけのときに
        # 帯のボタンが「中止」になってしまわないよう、別に持つ。
        self._reading_doc = False
        # ページを行き来する帯。1 枚だけのときは作らない。
        self.pager: ft.Container | None = None
        # 版面をどれだけ縮めて(拡げて)出しているか。枠の線の太さに使う。
        self._scale = 1.0
        self._rows: list[ft.Container] = []

        self.strip = status.Strip()
        self.panel = status.Panel()
        # 版面に重ねるので、下の絵が透けて文字が読みにくくならないよう幕を敷く。
        self.panel.control.bgcolor = ft.Colors.with_opacity(0.88, ft.Colors.SURFACE)
        self.stage = ft.Container(expand=True, alignment=ft.Alignment.CENTER, padding=16)
        self.body = ft.Container(expand=True)

        # 単独で読むときの右側。
        self.lines_list = ft.ListView(expand=True, spacing=2, padding=ft.Padding.all(8))
        # **「まとめて」は読みながら直す場所なので、行の一覧より広く取る。**
        # 枠を消しただけだと文字が縁にぴたりと付いて読みにくい。
        # 余白は content_padding で内側に入れる(外の Container だけだと、
        # 文字の折り返しが縁に触れる)。行間は 1.7 まで開ける。
        self.whole_text = ft.TextField(
            multiline=True,
            expand=True,
            border=ft.InputBorder.NONE,
            text_size=14,
            text_style=ft.TextStyle(height=1.7),
            content_padding=ft.Padding.symmetric(horizontal=16, vertical=12),
            on_change=self._on_text_edit,
        )
        self.count = theme.muted("")
        self.text_mode = ft.SegmentedButton(
            segments=[
                ft.Segment(value="lines", label=ft.Text(t("work.view.lines"), size=12)),
                ft.Segment(value="whole", label=ft.Text(t("work.view.whole"), size=12)),
            ],
            selected=["lines"],
            show_selected_icon=False,
            on_change=self._on_text_mode,
        )

        self.columns: list[ResultColumn] = []

    @property
    def doc(self) -> Doc | None:
        return self.state.doc

    @property
    def many(self) -> bool:
        """2 ページ以上の束か。ページを行き来する帯を出すかどうかが、これで決まる。"""
        return bool(self.doc and self.doc.many)

    @property
    def compare(self) -> bool:
        return self.state.compare

    @property
    def compare_ids(self) -> set[str]:
        return self.state.compare_ids

    # --- 組み立て ---------------------------------------------------------
    def build(self) -> ft.Control:
        job = self.state.job
        doc = self.doc
        self.title = ft.Text(
            # 束のときは束の名前(フォルダ名・マニフェストの題)。
            # 1 ページごとの名前は、下の帯に出す。
            (doc.title if doc and doc.many else (job.source if job else "")),
            size=13,
            weight=ft.FontWeight.W_500,
            no_wrap=True,
            overflow=ft.TextOverflow.ELLIPSIS,
            max_lines=1,
        )
        self.engine_dd = self.ctx.engine_dropdown(width=265, on_change=self._on_engine)
        self.mode = ft.SegmentedButton(
            segments=[
                ft.Segment(value="one", label=ft.Text(t("work.mode.one"), size=12)),
                ft.Segment(value="compare", label=ft.Text(t("work.mode.compare"), size=12)),
            ],
            selected=["compare" if self.compare else "one"],
            show_selected_icon=False,
            on_change=self._on_mode,
        )
        self.engine_dd.visible = not self.compare
        self.run_button = ft.FilledButton(
            t("work.run.compare") if self.compare else t("work.run"),
            icon=ft.Icons.PLAY_ARROW,
            on_click=(lambda _: self.start_compare()) if self.compare else (lambda _: self.start()),
        )
        self.copy_button = ft.OutlinedButton(
            t("work.copy"), icon=ft.Icons.CONTENT_COPY, on_click=lambda _: self.copy()
        )

        self._build_body()
        if job is not None and job.image is None and (job.path is not None or job.url):
            # 前回の続きや、版面を手放したページ。画面が出てから開きに行く。
            self.page.run_task(self._ensure_image)
        return ft.Column(
            [
                theme.top_bar(
                    [
                        theme.back_button(lambda _: self.ctx.go("landing")),
                        ft.Container(content=self.title, width=170),
                        self.mode,
                        self.engine_dd,
                    ],
                    [
                        self.run_button,
                        self.copy_button,
                        theme.menu_button(
                            t("work.save"), ft.Icons.SAVE_OUTLINED, self._save_items()
                        ),
                        ft.IconButton(
                            ft.Icons.SETTINGS_OUTLINED,
                            tooltip=t("common.settings"),
                            on_click=lambda _: self.ctx.go("settings"),
                        ),
                    ],
                ),
                self.body,
                self.strip.control,
            ],
            spacing=0,
            expand=True,
        )

    def _save_items(self) -> list[ft.PopupMenuItem]:
        """保存の選び方。束のときだけ「このページ / すべてのページ」に分ける。

        **枚数を品書きに書かない。** 読み進めるたびに数が変わるので、
        作ったときの数が残っていると嘘になる。
        """
        if not self.many:
            return [
                ft.PopupMenuItem(
                    content=t("work.save.text"),
                    icon=ft.Icons.DESCRIPTION_OUTLINED,
                    on_click=lambda _: self.save("text"),
                ),
                ft.PopupMenuItem(
                    content=t("work.save.tei"),
                    icon=ft.Icons.CODE,
                    on_click=lambda _: self.save("tei"),
                ),
            ]
        return [
            ft.PopupMenuItem(
                content=t("work.save.text.page"),
                icon=ft.Icons.DESCRIPTION_OUTLINED,
                on_click=lambda _: self.save("text", "page"),
            ),
            ft.PopupMenuItem(
                content=t("work.save.text.all"),
                icon=ft.Icons.LIBRARY_BOOKS_OUTLINED,
                on_click=lambda _: self.save("text", "all"),
            ),
            ft.PopupMenuItem(
                content=t("work.save.tei.page"),
                icon=ft.Icons.CODE,
                on_click=lambda _: self.save("tei", "page"),
            ),
            ft.PopupMenuItem(
                content=t("work.save.tei.all"),
                icon=ft.Icons.CODE,
                on_click=lambda _: self.save("tei", "all"),
            ),
        ]

    def _build_body(self) -> None:
        """左(版面)と右(結果)を組み立てる。束のときは版面の下にページの帯。"""
        right = self._compare_pane() if self.compare else self._single_pane()
        stage = ft.Stack([self.stage, self.panel.control], expand=True)
        self.pager = None
        left: ft.Control = (
            ft.Column([stage, self._pager()], spacing=0, expand=True) if self.many else stage
        )
        self.body.content = ft.Row(
            [left, ft.VerticalDivider(width=1), right],
            spacing=0,
            expand=True,
        )
        self._render()

    def _single_pane(self) -> ft.Control:
        self.pane_body = ft.Container(content=self.lines_list, expand=True)
        self.whole_pane = ft.Container(
            content=self.whole_text,
            expand=True,
            padding=ft.Padding.only(top=4, bottom=8),
        )
        return ft.Container(
            width=theme.RIGHT_PANE,
            content=ft.Column(
                [
                    _pane_header(
                        [
                            ft.Text(t("work.lines"), size=13, weight=ft.FontWeight.W_600),
                            self.count,
                            ft.Container(expand=True),
                            self.text_mode,
                        ]
                    ),
                    self.pane_body,
                ],
                spacing=0,
                expand=True,
            ),
        )

    def _compare_pane(self) -> ft.Control:
        self.columns = [
            ResultColumn(self, e) for e in self.state.usable if e.id in self.compare_ids
        ]
        picks: list[ft.Control] = []
        for engine in self.state.usable:
            ready = self._ready(engine)
            picks.append(
                ft.Checkbox(
                    label=engine_short(engine),
                    value=engine.id in self.compare_ids and ready,
                    disabled=not ready,
                    tooltip=None if ready else t("compare.not_fetched.detail"),
                    data=engine.id,
                    on_change=self._on_pick,
                )
            )
        columns: list[ft.Control] = []
        for i, col in enumerate(self.columns):
            if i:
                columns.append(ft.VerticalDivider(width=1))
            columns.append(col.build())
        if not columns:
            columns = [
                ft.Container(
                    content=theme.muted(t("compare.pick")),
                    padding=ft.Padding.all(16),
                )
            ]
        return ft.Container(
            width=self._right_width(),
            content=ft.Column(
                [
                    _pane_header(
                        [
                            ft.Text(t("work.mode.compare"), size=13, weight=ft.FontWeight.W_600),
                            ft.Row(picks, spacing=4, tight=True, wrap=True),
                        ]
                    ),
                    ft.Row(columns, spacing=0, expand=True, scroll=ft.ScrollMode.AUTO),
                ],
                spacing=0,
                expand=True,
            ),
        )

    # --- ページの帯(束のときだけ) -----------------------------------------
    #
    # **版面の下に置く。** 上帯に足すと、狭い窓(920px)で読む・コピー・保存が
    # 押し出される。ページの行き来は版面に付いている方が、目も動かさずに済む。

    def _pager(self) -> ft.Container:
        self.page_label = ft.Text("", size=12, weight=ft.FontWeight.W_500)
        self.page_name = theme.muted("", 11)
        self.page_name.no_wrap = True
        self.page_name.overflow = ft.TextOverflow.ELLIPSIS
        self.prev_button = ft.IconButton(
            ft.Icons.CHEVRON_LEFT,
            icon_size=20,
            tooltip=t("work.page.prev"),
            on_click=lambda _: self.show_page(self.doc.index - 1 if self.doc else 0),
        )
        self.next_button = ft.IconButton(
            ft.Icons.CHEVRON_RIGHT,
            icon_size=20,
            tooltip=t("work.page.next"),
            on_click=lambda _: self.show_page(self.doc.index + 1 if self.doc else 0),
        )
        self.done_chip = ft.Container()
        self.all_button = ft.FilledTonalButton(
            t("work.read.all"),
            icon=ft.Icons.PLAYLIST_PLAY,
            on_click=lambda _: self.toggle_all(),
        )
        bar = ft.Container(
            content=ft.Row(
                [
                    self.prev_button,
                    self.page_label,
                    self.next_button,
                    ft.Container(content=self.page_name, expand=True),
                    self.done_chip,
                    self.all_button,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=6,
            ),
            height=PAGER,
            padding=ft.Padding.only(left=6, right=12),
            border=ft.Border.only(top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        )
        # **先に持たせてから同期する。** `_sync_pager` は帯が無いときに何もしない
        # 作りなので、順を逆にすると、出来たての帯が空のまま画面に出る。
        self.pager = bar
        self._sync_pager()
        return bar

    def _sync_pager(self) -> None:
        """帯の表示を、いまのページと読み終えた数に合わせる。"""
        doc = self.doc
        if self.pager is None or doc is None:
            return
        self.page_label.value = t("work.page", index=doc.index + 1, total=doc.total)
        self.page_name.value = doc.current.source if doc.current else ""
        self.prev_button.disabled = doc.index <= 0 or self.state.busy
        self.next_button.disabled = doc.index >= doc.total - 1 or self.state.busy
        done = len(doc.read())
        self.done_chip.content = (
            theme.chip(
                ft.Icons.CHECK_CIRCLE_OUTLINE,
                t("work.read.done.count", done=done, total=doc.total),
                ft.Colors.PRIMARY if done >= doc.total else ft.Colors.ON_SURFACE_VARIANT,
            )
            if done
            else None
        )
        # 束を読んでいる間は「中止」になる。押せないボタンにすると、
        # 200 ページの途中で止める手立てが無くなる。
        running = self._reading_doc
        self.all_button.content = t("work.read.stop") if running else t("work.read.all")
        self.all_button.icon = ft.Icons.STOP if running else ft.Icons.PLAYLIST_PLAY
        # ほかの読み取り(1 つで読む・くらべる)の最中は、押せなくしておく。
        self.all_button.disabled = self.state.busy and not running

    def show_page(self, index: int) -> None:
        """ページを移る。版面が手元に無ければ、移ってから開きに行く。"""
        doc = self.doc
        if doc is None or self.state.busy or not 0 <= index < doc.total or index == doc.index:
            return
        doc.go(index)
        self.selected = -1
        self._png = None
        self._render()
        self._sync_pager()
        self.page.update()
        self.page.run_task(self._ensure_image)

    async def _ensure_image(self) -> None:
        """いま出ているページの版面を用意する。取り寄せ(IIIF)もここを通る。

        **移った先で待たせない。** 版面が来るまでは「読み込んでいます」を出し、
        来たら描き直す。待っている間に別のページへ移られたら、その結果は捨てる。
        """
        job = self.state.job
        doc = self.doc
        if job is None or doc is None or job.image is not None:
            return
        if job.path is None and not job.url:
            return  # 貼り付けた画像を手放したあと。開き直す当てが無い
        index = doc.index
        self.panel.show(status.loading(t("work.loading.page")))
        self.page.update()
        try:
            await asyncio.to_thread(job.load)
        except Exception as exc:  # noqa: BLE001 - 画面に出して続けられるようにする
            traceback.print_exc()
            if self.doc is doc and doc.index == index:
                self.panel.show(status.explain(exc))
                self.page.update()
            return
        if self.doc is not doc or doc.index != index:
            # 待っている間に別のページへ移っている。いまの画面は触らない。
            job.release()
            return
        doc.keep_only(index)
        self._png = None
        self._render()
        self.panel.hide()
        self.page.update()

    def _right_width(self) -> int:
        if not self.compare:
            return theme.RIGHT_PANE
        window = int(self.page.window.width or 1180)
        wanted = max(1, len(self.compare_ids)) * (COLUMN + 1)
        # 版面が細切れにならないよう、右側は窓の 6 割までに抑える。
        return max(COLUMN, min(wanted, int(window * 0.62)))

    # --- 描き直し ---------------------------------------------------------
    def _render(self) -> None:
        """job の中身から、版面・行・件数を作り直す。"""
        job = self.state.job
        self.stage.content = self._stage_content(job)
        lines = job.lines if job else []
        self.count.value = t("work.lines.count", count=len(lines)) if lines else ""
        self.whole_text.value = job.text if job else ""
        self._rows = [self._row(i, ln.text) for i, ln in enumerate(lines)]
        self.lines_list.controls = self._rows or [
            ft.Container(
                content=theme.muted(t("work.empty.lines")),
                padding=ft.Padding.all(12),
            )
        ]
        for col in self.columns:
            col.sync()

    def _stage_content(self, job: Job | None) -> ft.Control:
        self._boxes = []
        if job is None or job.image is None:
            if job is not None and (job.path is not None or job.url):
                # 開き直す当てがある。`_ensure_image` が持ってくるまでの受け皿。
                message = t("work.loading.page")
            else:
                message = t("work.text_only") if job is not None else t("work.no_image")
            return ft.Container(
                content=theme.muted(message),
                alignment=ft.Alignment.CENTER,
            )

        img = job.image
        bw, bh = self._budget()
        scale = min(bw / img.width, bh / img.height, MAX_ZOOM)
        self._scale = scale
        sw, sh = max(1, round(img.width * scale)), max(1, round(img.height * scale))

        if self._png is None:
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            self._png = buf.getvalue()

        for i, line in enumerate(job.lines):
            if not line.box:
                continue
            x, y, w, h = line.box
            self._boxes.append(
                ft.Container(
                    left=x * scale,
                    top=y * scale,
                    width=max(2.0, w * scale),
                    height=max(2.0, h * scale),
                    border_radius=ft.BorderRadius.all(2),
                    tooltip=line.text,
                    on_click=self._select_handler(i),
                    data=i,
                )
            )
        self._paint_boxes()

        return ft.Container(
            content=ft.Stack(
                [
                    ft.Image(
                        src=self._png,
                        width=sw,
                        height=sh,
                        fit=ft.BoxFit.FILL,
                        border_radius=ft.BorderRadius.all(6),
                    ),
                    *self._boxes,
                ],
                width=sw,
                height=sh,
            ),
            alignment=ft.Alignment.CENTER,
        )

    def _budget(self) -> tuple[int, int]:
        """版面に使える大きさ。窓の寸法から引き算して決める。

        Flet 0.86 には「置かれた後の実寸」を教わる手立てが無いので、
        こちらで決めた寸法に版面を合わせる。少なめに見積もって、はみ出させない。
        """
        w = (self.page.window.width or 1180) - self._right_width() - 1 - 40
        h = (self.page.window.height or 780) - theme.TOP_BAR - 40 - 40 - 28
        if self.many:
            h -= PAGER  # ページを行き来する帯のぶん
        return max(260, int(w)), max(220, int(h))

    def _row(self, index: int, text: str) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Text(
                            str(index + 1), size=11, color=ft.Colors.ON_SURFACE_VARIANT
                        ),
                        width=26,
                    ),
                    ft.Text(text, size=13, expand=True, selectable=True),
                    # **1 行だけ持ち出せるようにする。** 校正は 1 行ずつ直すので、
                    # 全文をコピーして要る所を探す手間をここで省く。
                    ft.IconButton(
                        ft.Icons.CONTENT_COPY,
                        icon_size=14,
                        icon_color=ft.Colors.ON_SURFACE_VARIANT,
                        tooltip=t("work.copy.line"),
                        padding=ft.Padding.all(4),
                        on_click=self._copy_line_handler(text),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=6),
            border_radius=ft.BorderRadius.all(8),
            bgcolor=self._row_color(index),
            on_click=self._select_handler(index),
            data=index,
        )

    def _row_color(self, index: int) -> str | None:
        return ft.Colors.with_opacity(0.14, ft.Colors.PRIMARY) if index == self.selected else None

    def _stroke(self) -> float:
        """枠の線の太さ。

        **線の太さは画面の点で決まるので、元画像の画素数では変わらない。**
        細く見えるのは、版面を縮めて出しているぶん枠が小さく詰まるため。
        大きく引き伸ばしているとき(小さな切り抜き)は、逆に線が頼りなくなるので、
        縮尺に合わせて少しだけ太くする。
        """
        return min(3.0, max(2.0, self._scale * 2.0))

    def _paint_boxes(self) -> None:
        stroke = self._stroke()
        for box in self._boxes:
            on = box.data == self.selected
            box.border = ft.Border.all(
                stroke + 1.5 if on else stroke,
                ft.Colors.PRIMARY if on else ft.Colors.with_opacity(0.75, ft.Colors.PRIMARY),
            )
            box.bgcolor = ft.Colors.with_opacity(0.22 if on else 0.06, ft.Colors.PRIMARY)

    # --- 操作 -------------------------------------------------------------
    def _select_handler(self, index: int):
        def handler(_event=None) -> None:
            self.select(index)

        return handler

    def select(self, index: int) -> None:
        self.selected = -1 if self.selected == index else index
        for i, row in enumerate(self._rows):
            row.bgcolor = self._row_color(i)
        self._paint_boxes()
        for col in self.columns:
            col.paint()
        self.page.update()

    def _on_mode(self, _event=None) -> None:
        self.state.compare = "compare" in (self.mode.selected or ["one"])
        # **画面ごと作り直す。** 同じ部品を別の親に入れ直すと、
        # それ以降の書き換えが画面に届かなくなる(Flet 0.86 で実測)。
        self.ctx.go("work")

    def _on_pick(self, event) -> None:
        engine_id = event.control.data
        if event.control.value:
            self.compare_ids.add(engine_id)
        else:
            self.compare_ids.discard(engine_id)
        self.ctx.go("work")

    def _on_text_mode(self, _event=None) -> None:
        whole = "whole" in (self.text_mode.selected or ["lines"])
        self.pane_body.content = self.whole_pane if whole else self.lines_list
        # 「まとめて」で直した分を、行の一覧にも映す。
        self._render()
        self.page.update()

    def _on_text_edit(self, _event=None) -> None:
        """まとめて直した文字を、コピーの元に反映する。"""
        result = self.state.job.result if self.state.job else None
        if result is not None:
            result.text = self.whole_text.value or ""

    def _on_engine(self, _event=None) -> None:
        self.strip.plain(t("work.engine.changed", engine=engine_label(self.state.engine)))
        self.page.update()

    def use_result(self, engine_id: str) -> None:
        """くらべた中から、版面に重ねる 1 つを選ぶ。"""
        job = self.state.job
        if job is None or engine_id not in job.runs:
            return
        job.primary = engine_id
        self.selected = -1
        self._render()
        self.state.remember(job)
        self.page.update()

    def copy(self) -> None:
        job = self.state.job
        text = (job.text if job else "").strip()
        if not text:
            self.strip.plain(t("work.copy.empty"))
            self.page.update()
            return
        self.page.run_task(self._copy_async, text)

    def _copy_line_handler(self, text: str):
        def handler(_event=None) -> None:
            self.page.run_task(self._copy_line, text)

        return handler

    async def _copy_line(self, text: str) -> None:
        await self.page.clipboard.set(text)
        self.strip.plain(t("work.copy.line.done", chars=len(text)))
        self.page.update()

    async def _copy_async(self, text: str) -> None:
        await self.page.clipboard.set(text)
        self.strip.plain(t("work.copy.done", chars=len(text)))
        self.page.update()

    # --- 保存 -------------------------------------------------------------
    #
    # 対象は **いま版面に出ている結果**(`Job.primary`)。くらべているときは、
    # 「これを使う」で選んだものが保存される。コピーと同じ決まりにしてある。

    def save(self, kind: str, scope: str = "page") -> None:
        """`kind` は "text"(.txt) か "tei"(.xml)、`scope` は "page" か "all"。

        **書き出すのは読み終えたページだけ。** まだ読んでいないページを
        空のまま並べると、「読んだが何も無かった」ページと見分けが付かない。
        """
        doc = self.doc
        if scope == "all" and doc is not None:
            jobs = [job for job in doc.read() if job.text.strip()]
            empty_note = t("work.save.none_read")
        else:
            job = self.state.job
            jobs = [job] if job is not None and job.text.strip() else []
            empty_note = t("work.save.empty")
        if not jobs:
            self.strip.plain(empty_note)
            self.page.update()
            return
        if kind == "tei":
            # TEI は行の枠を版面の座標で書くので、版面の寸法が要る。
            jobs = [job for job in jobs if job.width and job.height]
            if not jobs:
                self.strip.show(
                    status.failed(t("work.save.no_image"), t("work.save.no_image.detail"))
                )
                self.page.update()
                return
        self.page.run_task(self._save_async, kind, jobs)

    async def _save_async(self, kind: str, jobs: list[Job]) -> None:
        suffix = export.TEI_SUFFIX if kind == "tei" else export.TEXT_SUFFIX
        doc = self.doc
        if len(jobs) > 1 and doc is not None:
            stem = doc.title or "ocr"
        else:
            stem = jobs[0].path.stem if jobs[0].path else (jobs[0].source or "ocr")
        chosen = await self.ctx.picker.save_file(
            dialog_title=t(f"save.dialog.{kind}"),
            file_name=_safe_name(stem) + suffix,
            initial_directory=export.last_dir(),
        )
        if not chosen:
            return
        dest = Path(chosen)
        if dest.suffix.lower() != suffix:
            # 拡張子を選ばずに閉じられることがある。こちらで揃える。
            dest = dest.with_suffix(suffix)
        try:
            note = await asyncio.to_thread(self._write, kind, dest, jobs)
        except Exception as exc:  # noqa: BLE001 - 画面に出して続けられるようにする
            traceback.print_exc()
            self.strip.show(status.explain(exc))
            self.page.update()
            return
        export.remember_dir(dest)
        self.strip.plain(note)
        self.page.update()

    def _write(self, kind: str, dest: Path, jobs: list[Job]) -> str:
        """糸(スレッド)の中で書く。返すのは、画面の下に出す一言。"""
        many = len(jobs) > 1
        if kind == "text":
            # ページの切れ目は空行 1 つ。端末から使ったときと同じ形にする。
            export.write_text(dest, "\n\n".join(job.text.rstrip("\n") for job in jobs))
            return self._saved_note(dest, len(jobs), None)

        beside = None
        pages: list[tuple[Job, str]] = []
        for job in jobs:
            url, made = self._graphic(dest, job, many)
            beside = beside or made
            pages.append((job, url))
        doc = self.doc
        export.write_tei(
            dest,
            self.state.tei(
                pages,
                title=doc.title if doc and doc.many else "",
                origin=doc.origin if doc else "",
            ),
        )
        return self._saved_note(dest, len(jobs), beside)

    def _graphic(self, dest: Path, job: Job, many: bool) -> tuple[str, Path | None]:
        """`<graphic url="…">` に書く道と、隣に置いた版面(置いたときだけ)。

        - 取り寄せたページ(IIIF)は、**その URL をそのまま指す**。どのパソコンでも開ける
        - 手元のファイルは、TEI から見た相対の道
        - 相対にできない(遠い・別のドライブ)ときは、1 枚なら隣に写す。
          **束のときは写さない**(何百枚も増やさない)。端末から使ったときと同じく、
          そのままの道を書く
        """
        if job.url:
            return job.url, None
        source = job.path if job.path is not None and job.path.is_file() else None
        if source is not None:
            url = export.graphic_url(dest, source)
            if url is not None:
                return url, None
            if many:
                return source.resolve().as_posix(), None
        if job.image is None:
            # 版面を手放したあと。隣に写せないので、道だけでも書く
            # (`<graphic>` の無い TEI より、開ける当てのある道の方がまし)。
            return (source.resolve().as_posix() if source is not None else ""), None
        made = export.image_beside(dest, job.image, source)
        return made.name, made

    def _saved_note(self, dest: Path, pages: int, beside: Path | None) -> str:
        if beside is not None:
            return t("work.save.done.with_image", name=dest.name, image=beside.name)
        if pages > 1:
            return t("work.save.done.pages", name=dest.name, pages=pages)
        return t("work.save.done", name=dest.name)

    def opened(self) -> None:
        """束(フォルダ・IIIF)を開いた直後。1 ページ目を出して、次にすることを言う。

        **黙って全部を読み始めない。** 何百ページの取り寄せと読み取りは、
        押してから始まる方がよい。1 枚だけのときは、これまでどおりすぐ読む。
        """
        doc = self.doc
        if doc is None:
            return
        # 版面を開きに行くのは `build()` が済ませている。ここで二重に頼まない
        # (IIIF では同じページを二度取り寄せることになる)。
        self.strip.plain(t("work.opened", count=doc.total))
        self.page.update()

    # --- 読み取り(1 つで読む) ---------------------------------------------
    def start(self, allow_fetch: bool = False) -> None:
        job = self._runnable_job()
        if job is None or self.state.busy:
            return
        engine = self.state.engine
        if not allow_fetch and self._needs_consent(engine):
            self._ask_consent(engine, lambda: self.start(allow_fetch=True))
            return
        self.page.run_task(self._run_all, job, [engine])

    # --- 読み取り(束をまとめて) -------------------------------------------
    #
    # **黙って始めない・途中で止められる・見ているページから先に出す。**
    # 200 ページの束では、この 3 つが無いと使い物にならない。

    def toggle_all(self) -> None:
        if self._reading_doc:
            self.stop()
        elif not self.state.busy:
            self.start_all()

    def stop(self) -> None:
        """いま読んでいるページまでで止める。押した 1 枚は最後まで読む。"""
        self._cancel = True
        self.strip.plain(t("work.read.stopping"))
        self.page.update()

    def start_all(self, allow_fetch: bool = False) -> None:
        doc = self.doc
        if doc is None or not doc.jobs or self.state.busy:
            return
        engine = self.state.engine
        if not allow_fetch and self._needs_consent(engine):
            self._ask_consent(engine, lambda: self.start_all(allow_fetch=True))
            return
        self.page.run_task(self._run_doc, doc, engine)

    async def _run_doc(self, doc: Doc, engine: Engine) -> None:
        # まだこの道具で読んでいないページだけを読む。読み直したいときのために、
        # 全部が読み終わっているときは、もう一度ぜんぶ読む。
        targets = [(i, job) for i, job in enumerate(doc.jobs) if engine.id not in job.runs]
        if not targets:
            targets = list(enumerate(doc.jobs))

        def on_progress(label: str, ratio: float | None) -> None:
            # 糸の中から呼ばれる。run_task は糸をまたいでも安全。
            self.page.run_task(self._show, engine.id, status.fetching(label, ratio), False)

        self.state.busy = True
        self._reading_doc = True
        self._cancel = False
        self.run_button.disabled = True
        self._sync_pager()
        self.panel.show(status.loading(t("work.preparing")))
        self.strip.show(status.loading(t("work.preparing")))
        self.page.update()

        done = failed = 0
        try:
            try:
                await asyncio.to_thread(engine.prepare, on_progress)
            except Exception as exc:  # noqa: BLE001 - 画面に出して続けられるようにする
                traceback.print_exc()
                report = status.explain(exc)
                self.panel.show(report)
                self.strip.show(report)
                return
            self.panel.hide()

            for index, job in targets:
                if self._cancel:
                    break
                self.strip.show(
                    status.loading(
                        t(
                            "work.read.progress",
                            index=index + 1,
                            total=doc.total,
                            name=job.source,
                        )
                    )
                )
                self.page.update()
                try:
                    image = await asyncio.to_thread(job.load)
                    started = time.monotonic()
                    result = await asyncio.to_thread(engine.recognize, image)
                except Exception as exc:  # noqa: BLE001 - 1 ページこけても残りは読む
                    traceback.print_exc()
                    job.record(Run(engine_id=engine.id, error=status.explain(exc).message))
                    failed += 1
                    continue
                job.record(
                    Run(engine.id, result=result, seconds=time.monotonic() - started),
                    prefer=True,
                )
                done += 1
                if index == doc.index:
                    # 見ているページが読み終わったら、その場で出す。待たせない。
                    self.selected = -1
                    self._render()
                    self.panel.hide()
                else:
                    # 見ていないページの版面は抱えない(読んだ文字と枠は残る)。
                    job.release()
                self._sync_pager()
                self.page.update()
        finally:
            stopped = self._cancel
            self.state.busy = False
            self._reading_doc = False
            self._cancel = False
            self.run_button.disabled = False
            self._sync_pager()
            self.strip.plain(self._doc_report(done, failed, stopped))
            if self.state.job is not None and self.state.job.result is not None:
                self.state.remember(self.state.job)
            self.page.update()

    def _doc_report(self, done: int, failed: int, stopped: bool) -> str:
        if stopped:
            return t("work.read.all.stopped", count=done)
        if failed:
            return t("work.read.all.done.failed", count=done, failed=failed)
        return t("work.read.all.done", count=done)

    # --- 読み取り(くらべる) -----------------------------------------------
    def start_compare(self) -> None:
        job = self._runnable_job()
        if job is None or self.state.busy:
            return
        engines = [e for e in self.state.usable if e.id in self.compare_ids]
        if not engines:
            self.strip.plain(t("compare.pick"))
            self.page.update()
            return
        for col in self.columns:
            col.set_status(status.loading(t("work.waiting")))
        self.page.run_task(self._run_all, job, engines)

    def _runnable_job(self) -> Job | None:
        """読ませられるページ。**版面はまだ手元に無くてよい**(開く当てがあればよい)。

        束のページは、見ていない間は版面を手放してある。ここで「画像がありません」と
        突き放すと、戻ってきたページが読めなくなる。
        """
        job = self.state.job
        if job is not None and (job.image is not None or job.path is not None or job.url):
            return job
        self.panel.show(
            status.empty(
                t("work.no_image.title"),
                t("work.no_image.detail"),
                action=(t("work.no_image.action"), lambda: self.ctx.go("landing")),
            )
        )
        self.page.update()
        return None

    def _ready(self, engine: Engine) -> bool:
        return not engine.assets or engine.available()

    def _needs_consent(self, engine: Engine) -> bool:
        return bool(engine.assets) and not engine.available()

    def _ask_consent(self, engine: Engine, proceed) -> None:
        size = fetch.human(fetch.total_bytes(engine.assets))
        self.panel.show(
            status.empty(
                t("work.consent.title", engine=engine_label(engine), size=size),
                t("work.consent.detail"),
                action=(t("work.consent.action", size=size), proceed),
            )
        )
        self.page.update()

    # --- 動かす -----------------------------------------------------------
    #
    # **重い処理は糸(スレッド)へ、画面の書き換えはこのコルーチンの中で行う。**
    # 自前の糸から page.update() を呼ぶと、画面が途中の姿で止まる(0.86 で実測)。
    # 道具どうしは待ち合わせない。速い道具の結果は、遅い道具を待たずに出る。

    async def _run_all(self, job: Job, engines: list[Engine]) -> None:
        many = len(engines) > 1
        self.state.busy = True
        self.run_button.disabled = True
        opening = status.loading(
            t("work.reading.many", count=len(engines)) if many else t("work.preparing")
        )
        self.panel.show(opening)
        self.strip.show(opening)
        self.page.update()
        try:
            # **版面はここで 1 回だけ用意する。** 道具ごとに開きに行かせると、
            # くらべるときに同じページを人数ぶん取り寄せることになる。
            if job.image is None:
                try:
                    await asyncio.to_thread(job.load)
                    self._png = None
                except Exception as exc:  # noqa: BLE001 - 画面に出して続けられるようにする
                    traceback.print_exc()
                    report = status.explain(exc)
                    self.panel.show(report)
                    self.strip.show(report)
                    return
            await asyncio.gather(*(self._run_one(job, e, many) for e in engines))
            self.selected = -1
            self._render()
            self.panel.hide()
            self._report(job, engines)
        finally:
            self.state.busy = False
            self.run_button.disabled = False
            self.page.update()

    async def _run_one(self, job: Job, engine: Engine, many: bool) -> None:
        col = self._column(engine.id)

        def on_progress(label: str, ratio: float | None) -> None:
            # 糸の中から呼ばれる。run_task は糸をまたいでも安全。
            self.page.run_task(self._show, engine.id, status.fetching(label, ratio), many)

        if many and self._needs_consent(engine):
            # くらべるときに 1.8GB を黙って落とし始めない。
            note = status.failed(t("compare.not_fetched"), t("compare.not_fetched.detail"))
            job.record(Run(engine_id=engine.id, error=note.message))
            if col:
                col.set_status(note)
                col.sync()
            self.page.update()
            return

        working = status.loading(
            t("work.reading.with", engine=engine_label(engine)) if many else t("work.reading")
        )
        await self._show(engine.id, working, many)

        started = time.monotonic()
        try:
            await asyncio.to_thread(engine.prepare, on_progress)
            # 下ごしらえの分は読んだ時間に混ぜない(1 回目だけ何十秒もかかるため)。
            prepared = time.monotonic()
            result = await asyncio.to_thread(engine.recognize, job.image)
        except Exception as exc:  # noqa: BLE001 - 1 つ失敗しても残りは読む
            report = status.explain(exc)
            job.record(Run(engine_id=engine.id, error=report.message))
            traceback.print_exc()
            if col:
                col.set_status(report)
                col.sync()
            else:
                self.panel.show(report)
            self.strip.show(report)
            self.page.update()
            return

        job.record(
            Run(
                engine.id,
                result=result,
                seconds=time.monotonic() - prepared,
                prepare_seconds=prepared - started,
            ),
            # 1 つで読んだときは、いま読んだ道具の結果を版面に出す。
            prefer=not many,
        )
        if col:
            col.sync()  # 結果が入れば、その列の状態表示は sync が引っ込める
        if not job.primary or job.primary == engine.id:
            # 最初に読み終えた道具を版面に出す。待たせない。
            self._render()
            self.panel.hide()
        self.page.update()

    async def _show(self, engine_id: str, report: status.Report, many: bool) -> None:
        """状態を、その道具の列(くらべるとき)か、画面ぜんたい(1 つで読むとき)に出す。"""
        col = self._column(engine_id)
        if col:
            col.set_status(report)
        if not many:
            self.panel.show(report)
        self.strip.show(report)
        self.page.update()

    def _column(self, engine_id: str) -> ResultColumn | None:
        return next((c for c in self.columns if c.engine.id == engine_id), None)

    def _report(self, job: Job, engines: list[Engine]) -> None:
        """読み終わりの一言。くらべたときは道具ごとの行数を並べる。"""
        if len(engines) > 1:
            parts = []
            for engine in engines:
                run = job.runs.get(engine.id)
                short = engine_short(engine)
                if run and run.result is not None:
                    parts.append(
                        t("compare.summary", engine=short, count=len(run.lines), timing=run.timing)
                    )
                else:
                    parts.append(f"{short} ―")
            self.strip.plain("　".join(parts))
            if job.result is not None:
                self.state.remember(job)
            return

        count = len(job.lines)
        run = job.run
        if count:
            timing = f" / {run.timing}" if run else ""
            self.strip.plain(
                t("work.done", count=count, chars=len(job.text), timing=timing)
            )
            self.state.remember(job)
        else:
            self.strip.show(
                status.empty(t("work.nothing_found"), t("work.nothing_found.detail"))
            )


def _safe_name(stem: str) -> str:
    """保存ダイアログに出す既定の名前。

    フォルダ名やマニフェストの題をそのまま使うので、ファイル名に使えない字
    (`/` など)が混ざる。OS に断られる前にこちらで落とす。
    """
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", stem).strip(" .")
    return (cleaned or "ocr")[:80]


def _pane_header(controls: list[ft.Control]) -> ft.Control:
    return ft.Container(
        content=ft.Row(controls, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
    )
