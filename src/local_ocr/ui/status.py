"""状態の見せ方。空・読み込み中・取得中・失敗の 4 つを、どの画面でも同じ形で出す。

**失敗は「何が起きたか」だけで終わらせない。** 次に何をすればよいかを必ず添える。
文面をここに集めておくと、画面ごとに言い回しがぶれない。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

import flet as ft

from . import theme
from .i18n import t


class Kind(Enum):
    EMPTY = "empty"
    LOADING = "loading"
    FETCHING = "fetching"
    FAILED = "failed"


_ICON = {
    Kind.EMPTY: ft.Icons.IMAGE_OUTLINED,
    Kind.FETCHING: ft.Icons.DOWNLOADING,
    Kind.FAILED: ft.Icons.ERROR_OUTLINE,
}


@dataclass
class Report:
    """今なにが起きているか。`detail` は失敗のときの「次にすること」。"""

    kind: Kind
    message: str
    detail: str = ""
    # 0..1。取得中で長さが分からないときは None(不定の帯になる)。
    ratio: float | None = None
    action: tuple[str, Callable] | None = None

    @property
    def color(self) -> str:
        return ft.Colors.ERROR if self.kind is Kind.FAILED else ft.Colors.ON_SURFACE_VARIANT


def empty(message: str, detail: str = "", action=None) -> Report:
    return Report(Kind.EMPTY, message, detail, action=action)


def loading(message: str) -> Report:
    return Report(Kind.LOADING, message)


def fetching(message: str, ratio: float | None) -> Report:
    return Report(Kind.FETCHING, message, ratio=ratio)


def failed(message: str, detail: str) -> Report:
    return Report(Kind.FAILED, message, detail)


def explain(exc: Exception) -> Report:
    """例外を、利用者に意味の分かる文面と次の一手に翻訳する。"""
    text = str(exc)
    if "起動できませんでした" in text:
        # 取り直しても直らないときは、たいてい他のアプリが同じポートを使っている。
        return failed(t("error.server.title"), t("error.server.detail"))
    if isinstance(exc, OSError) and "画像" not in text:
        return failed(t("error.file.title", error=text), t("error.file.detail"))
    if "先に取得" in text:
        return failed(t("error.not_fetched.title"), t("error.not_fetched.detail"))
    return failed(t("error.other.title", error=text), t("error.other.detail"))


class Panel:
    """画面の真ん中に大きく出す版。中身が無いときの受け皿にもなる。"""

    def __init__(self, visible: bool = False) -> None:
        self._icon = ft.Icon(ft.Icons.INFO_OUTLINE, size=40, color=ft.Colors.ON_SURFACE_VARIANT)
        self._spinner = ft.ProgressRing(width=34, height=34, stroke_width=3, visible=False)
        self._message = ft.Text(size=14, weight=ft.FontWeight.W_500, text_align=ft.TextAlign.CENTER)
        self._detail = ft.Text(
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
            text_align=ft.TextAlign.CENTER,
            visible=False,
        )
        self._bar = ft.ProgressBar(width=260, visible=False)
        # ボタンは必要になってから作る。Flet 0.86 は中身の無いボタンを弾く。
        self._action = ft.Container(visible=False)
        self.control = ft.Container(
            content=ft.Column(
                [self._icon, self._spinner, self._message, self._detail, self._bar, self._action],
                spacing=10,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                tight=True,
            ),
            alignment=ft.Alignment.CENTER,
            padding=ft.Padding.all(theme.PAD),
            expand=True,
            visible=visible,
        )

    def show(self, r: Report) -> None:
        spinning = r.kind in (Kind.LOADING, Kind.FETCHING)
        self._spinner.visible = r.kind is Kind.LOADING
        self._icon.visible = not spinning
        self._icon.icon = _ICON.get(r.kind, ft.Icons.INFO_OUTLINE)
        self._icon.color = r.color
        self._message.value = r.message
        self._message.color = r.color
        self._detail.value = r.detail
        self._detail.visible = bool(r.detail)
        self._bar.visible = r.kind is Kind.FETCHING
        self._bar.value = r.ratio
        if r.action:
            label, callback = r.action
            self._action.content = ft.FilledTonalButton(
                label, on_click=_ignore_event(callback)
            )
            self._action.visible = True
        else:
            self._action.content = None
            self._action.visible = False
        self.control.visible = True

    def hide(self) -> None:
        self.control.visible = False


class Inline:
    """1 行に収める版。カードの中や画面の下に、同じ語彙のまま差し込む。"""

    def __init__(self, bar_width: int = 180) -> None:
        self._icon = ft.Icon(ft.Icons.INFO_OUTLINE, size=16, visible=False)
        self._spinner = ft.ProgressRing(width=14, height=14, stroke_width=2, visible=False)
        self._text = ft.Text(size=12, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS)
        self._detail = ft.Text(size=12, color=ft.Colors.ON_SURFACE_VARIANT, visible=False)
        self._bar = ft.ProgressBar(width=bar_width, visible=False)
        self.control = ft.Row(
            [self._icon, self._spinner, self._text, self._bar, self._detail],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def show(self, r: Report) -> None:
        spinning = r.kind in (Kind.LOADING, Kind.FETCHING)
        self._spinner.visible = spinning
        self._icon.visible = not spinning
        self._icon.icon = _ICON.get(r.kind, ft.Icons.INFO_OUTLINE)
        self._icon.color = r.color
        pct = f"  {r.ratio * 100:.0f}%" if r.kind is Kind.FETCHING and r.ratio is not None else ""
        self._text.value = f"{r.message}{pct}"
        self._text.color = r.color
        self._bar.visible = r.kind is Kind.FETCHING
        self._bar.value = r.ratio
        self._detail.value = r.detail
        self._detail.visible = bool(r.detail)
        self.control.visible = True

    def plain(self, message: str) -> None:
        """状態ではない、ただの一言。"""
        self.show(Report(Kind.EMPTY, message))
        self._icon.visible = False

    def hide(self) -> None:
        self.control.visible = False


class Strip(Inline):
    """画面の下に細く出す版。作業中の進みぐあいはここに出す。"""

    def __init__(self) -> None:
        super().__init__()
        self.control = ft.Container(
            content=self.control,
            height=40,
            padding=ft.Padding.symmetric(horizontal=16),
            border=ft.Border.only(top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        )


def _ignore_event(fn: Callable):
    """引数を取らない関数を、Flet のイベントハンドラとして使えるようにする。"""

    def handler(_event=None):
        fn()

    return handler
