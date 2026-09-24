"""見た目の決めごとを 1 か所に集める。

**色は必ず意味の名前(ON_SURFACE_VARIANT など)で持つ。** 直の色を書くと、
明るいテーマか暗いテーマのどちらかで必ず読めなくなる。
"""

from __future__ import annotations

import flet as ft

from ..core import prefs
from .i18n import t

# 余白と角。画面をまたいで同じ値を使う。
PAD = 24
GAP = 12
RADIUS = 14
# 作業画面の右側(読んだ行)の幅。版面の表示寸法もここから逆算する。
RIGHT_PANE = 380
TOP_BAR = 60

SEED = ft.Colors.INDIGO

_MODES = {
    "system": ft.ThemeMode.SYSTEM,
    "light": ft.ThemeMode.LIGHT,
    "dark": ft.ThemeMode.DARK,
}


# **スクロールバーは濃く、太く、溝も見せる。** 既定の薄い灰色では、くらべる画面で
# 右の列が隠れていることに気づけなかった。色は意味の名前で持つので明暗どちらでも読める。
SCROLLBAR = ft.ScrollbarTheme(
    thickness=10,
    radius=5,
    thumb_color={
        ft.ControlState.HOVERED: ft.Colors.ON_SURFACE,
        ft.ControlState.DEFAULT: ft.Colors.OUTLINE,
    },
    track_visibility=True,
    track_color=ft.Colors.SURFACE_CONTAINER_HIGHEST,
    track_border_color=ft.Colors.TRANSPARENT,
)


def setup(page: ft.Page) -> None:
    page.theme = ft.Theme(color_scheme_seed=SEED, scrollbar_theme=SCROLLBAR)
    page.dark_theme = ft.Theme(color_scheme_seed=SEED, scrollbar_theme=SCROLLBAR)
    page.theme_mode = theme_mode()
    page.bgcolor = ft.Colors.SURFACE
    # 余白は各画面が持つ。ページ側に付けると全面に敷く投入エリアが作れない。
    page.padding = 0
    page.spacing = 0


def theme_mode() -> ft.ThemeMode:
    return _MODES.get(str(prefs.get("theme", "system")), ft.ThemeMode.SYSTEM)


def set_theme_mode(page: ft.Page, key: str) -> None:
    prefs.save(theme=key)
    page.theme_mode = _MODES.get(key, ft.ThemeMode.SYSTEM)
    page.update()


# --- 文字 -----------------------------------------------------------------


def heading(text: str, size: int = 20) -> ft.Text:
    return ft.Text(text, size=size, weight=ft.FontWeight.W_600)


def muted(text: str, size: int = 12) -> ft.Text:
    return ft.Text(text, size=size, color=ft.Colors.ON_SURFACE_VARIANT)


# --- 入れ物 ---------------------------------------------------------------


def card(content: ft.Control, padding: int = 16) -> ft.Container:
    return ft.Container(
        content=content,
        padding=ft.Padding.all(padding),
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=ft.BorderRadius.all(RADIUS),
    )


def chip(icon: str, text: str, color: str = ft.Colors.ON_SURFACE_VARIANT) -> ft.Container:
    """小さな札。状態(取得済み・この OS では使えません)や注意書きに使う。"""
    return ft.Container(
        content=ft.Row(
            [ft.Icon(icon, size=14, color=color), ft.Text(text, size=12, color=color)],
            spacing=6,
            tight=True,
        ),
        padding=ft.Padding.symmetric(horizontal=10, vertical=5),
        bgcolor=ft.Colors.with_opacity(0.10, color),
        border_radius=ft.BorderRadius.all(999),
    )


def top_bar(left: list[ft.Control], right: list[ft.Control] | None = None) -> ft.Container:
    """どの画面でも同じ高さ・同じ区切り線の上帯。"""
    return ft.Container(
        content=ft.Row(
            [
                ft.Row(left, spacing=GAP, tight=True),
                ft.Container(expand=True),
                ft.Row(right or [], spacing=8, tight=True),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        height=TOP_BAR,
        padding=ft.Padding.symmetric(horizontal=16),
        border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
    )


def menu_button(label: str, icon: str, items: list[ft.PopupMenuItem]) -> ft.PopupMenuButton:
    """押すと選べる一覧が出る箱。見た目は OutlinedButton に合わせる。

    **中に本物のボタンを入れない。** 中のボタンが先に押されて、一覧が開かない
    ことがある。押せない Container で見た目だけ作る。
    """
    color = ft.Colors.PRIMARY
    return ft.PopupMenuButton(
        content=ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon, size=18, color=color),
                    ft.Text(label, size=14, color=color),
                    ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=18, color=color),
                ],
                spacing=8,
                tight=True,
            ),
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            border=ft.Border.all(1, ft.Colors.OUTLINE),
            border_radius=ft.BorderRadius.all(20),
        ),
        items=items,
        padding=0,
    )


def back_button(on_click) -> ft.IconButton:
    return ft.IconButton(ft.Icons.ARROW_BACK, tooltip=t("common.back"), on_click=on_click)
