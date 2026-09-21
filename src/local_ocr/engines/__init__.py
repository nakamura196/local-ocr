"""使えるエンジンの一覧。

**足すときはここに 1 行足すだけで済むようにしておく。** 画面側が
エンジンの名前を直接知ると、増やすたびに画面を直すことになる。
"""

from __future__ import annotations

from .apple_vision import AppleVisionEngine
from .base import Engine, Line, Progress, Result, runs_here
from .ndl import NdlKotenLiteEngine, NdlLiteEngine
from .paddle_vl import PaddleVLEngine

__all__ = [
    "Engine",
    "Line",
    "Progress",
    "Result",
    "all_engines",
    "available_engines",
    "runs_here",
]

# 並び順がそのまま画面の並び。取得の要らないものを上に置く。
_ALL: list[type] = [
    AppleVisionEngine,
    NdlKotenLiteEngine,
    NdlLiteEngine,
    PaddleVLEngine,
]


def available_engines() -> list[Engine]:
    """この OS で動くエンジンを作って返す。取得済みかどうかは問わない。"""
    return [e for e in all_engines() if runs_here(e)]


def all_engines() -> list[Engine]:
    """OS を問わず全部。設定画面は「この OS では使えません」も並べて見せる。"""
    return [cls() for cls in _ALL]
