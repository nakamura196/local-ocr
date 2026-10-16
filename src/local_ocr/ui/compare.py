"""くらべるときの 1 列。読む道具 1 つ分の結果を受け持つ。

列は作業画面(`work.py`)が並べる。ここが持つのは「1 つの道具の結果をどう見せるか」だけ。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from . import status, theme
from .i18n import engine_short, t

if TYPE_CHECKING:
    from ..engines import Engine
    from .work import WorkView

# くらべるときの 1 列の幅。
COLUMN = 300


class ResultColumn:
    def __init__(self, view: WorkView, engine: Engine) -> None:
        self.view = view
        self.engine = engine
        self.state = view.state
        self.meta = theme.muted("")
        # 一致率・異同の数は統計とは別の行に出す。同じ行に足すと、列の幅(300)では
        # 「異同 7 字」の「字」だけが次の行に落ちる。
        self.agree = theme.muted("")
        self.agree.visible = False
        self.status = status.Inline(bar_width=120)
        self.status.hide()
        self.badge = ft.Container()
        self.list = ft.ListView(expand=True, spacing=2, padding=ft.Padding.all(8))
        self._rows: list[ft.Container] = []

    def build(self) -> ft.Control:
        self.sync()
        return ft.Container(
            width=COLUMN,
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Text(
                                            engine_short(self.engine),
                                            size=13,
                                            weight=ft.FontWeight.W_600,
                                            no_wrap=True,
                                            overflow=ft.TextOverflow.ELLIPSIS,
                                            expand=True,
                                        ),
                                        self.badge,
                                    ],
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                self.meta,
                                self.agree,
                                self.status.control,
                            ],
                            spacing=4,
                        ),
                        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                        border=ft.Border.only(
                            bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)
                        ),
                    ),
                    self.list,
                ],
                spacing=0,
                expand=True,
            ),
        )

    # --- 表示の更新 -------------------------------------------------------
    def sync(self) -> None:
        job = self.state.job
        run = job.runs.get(self.engine.id) if job else None
        primary = bool(job and job.primary == self.engine.id)

        bad, rate = self.view.agreement(self.engine.id)
        self.agree.value = ""
        if run and run.result is not None:
            self.meta.value = t(
                "compare.stats", count=len(run.lines), chars=len(run.text), timing=run.timing
            )
            if rate is not None:
                # 切り捨てる。100% と出るのは本当に異同が無いときだけ。
                self.agree.value = t("compare.match", rate=int(rate * 100))
            elif primary and bad:
                self.agree.value = t("compare.disputed", n=len(bad))
            self.status.hide()
        elif run and run.error:
            self.meta.value = ""
        else:
            self.meta.value = ""

        self.agree.visible = bool(self.agree.value)

        # 「使用中」= コピーと保存に使う結果。画像に枠が出るのは行の位置がある結果だけ
        # (PaddleOCR-VL の既定の読み方は位置を返さない)。無いときは、そう添える。
        showing = t("compare.showing")
        if run and run.result is not None and not any(ln.box for ln in run.lines):
            showing = t("compare.showing.nopos")
        self.badge.content = (
            theme.chip(ft.Icons.CHECK_CIRCLE_OUTLINE, showing, ft.Colors.PRIMARY)
            if primary
            else (
                ft.TextButton(
                    t("compare.use"),
                    on_click=lambda _: self.view.use_result(self.engine.id),
                )
                if run and run.result is not None
                else None
            )
        )

        lines = run.lines if run else []
        self._rows = []
        start = 0
        for i, ln in enumerate(lines):
            self._rows.append(self._row(i, ln.text, primary, bad, start))
            start += len(ln.text) + 1  # 行は改行でつないだ文字列として比べている
        self.list.controls = self._rows or [
            ft.Container(
                content=theme.muted(
                    run.error if run and run.error else t("compare.empty")
                ),
                padding=ft.Padding.all(8),
            )
        ]

    def set_status(self, report: status.Report) -> None:
        self.status.show(report)

    def paint(self) -> None:
        """選ばれている行の色を塗り直す。枠と連動するのは版面に出している列だけ。"""
        job = self.state.job
        primary = bool(job and job.primary == self.engine.id)
        for i, row in enumerate(self._rows):
            row.bgcolor = self._color(i, primary)

    def _color(self, index: int, primary: bool) -> str | None:
        if not primary or index != self.view.selected:
            return None
        return ft.Colors.with_opacity(0.14, ft.Colors.PRIMARY)

    def _row(
        self, index: int, text: str, primary: bool, bad: set[int], start: int
    ) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Text(
                            str(index + 1), size=11, color=ft.Colors.ON_SURFACE_VARIANT
                        ),
                        width=22,
                    ),
                    _text(text, bad, start),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.Padding.symmetric(horizontal=6, vertical=5),
            border_radius=ft.BorderRadius.all(8),
            bgcolor=self._color(index, primary),
            on_click=lambda _, i=index: self._on_row(i),
        )

    def _on_row(self, index: int) -> None:
        """版面に出していない列の行を押したら、まずその列を版面に出す。"""
        job = self.state.job
        if job and job.primary != self.engine.id and self.engine.id in job.runs:
            self.view.use_result(self.engine.id)
        self.view.select(index)


def _text(text: str, bad: set[int], start: int) -> ft.Text:
    """1 行の文字。異同のある文字(`bad` は列ぜんたいでの位置、この行は `start` から)に印を付ける。

    **色だけに頼らない。** 背景の色に加えて下線も引く(色の違いが分かりにくい人や、
    白黒で刷るときのため)。色は theme の名前から取るので、明暗どちらでも読める。
    """
    if not bad:
        return ft.Text(text, size=13, expand=True, selectable=True)
    spans: list[ft.TextSpan] = []
    i = 0
    while i < len(text):
        flag = (start + i) in bad
        j = i
        while j < len(text) and ((start + j) in bad) == flag:
            j += 1
        spans.append(ft.TextSpan(text[i:j], style=theme.DIFF_STYLE if flag else None))
        i = j
    return ft.Text(spans=spans, size=13, expand=True, selectable=True)
