"""使えるエンジンの一覧。

**足すときはここに 1 行足すだけで済むようにしておく。** 画面側が
エンジンの名前を直接知ると、増やすたびに画面を直すことになる。
"""

from __future__ import annotations

from .apple_vision import AppleVisionEngine
from .base import Engine, Line, Progress, Result, runs_here
from .paddle_vl import PaddleVLEngine

__all__ = ["Engine", "Line", "Progress", "Result", "available_engines", "runs_here"]

# 並び順がそのまま画面の並び。取得の要らないものを上に置く。
_ALL: list[type] = [
    AppleVisionEngine,
    PaddleVLEngine,
]


def available_engines() -> list[Engine]:
    """この OS で動くエンジンを作って返す。取得済みかどうかは問わない。"""
    return [cls() for cls in _ALL if runs_here(cls())]
