"""使えるエンジンの一覧。

**足すときはここに 1 行足すだけで済むようにしておく。** 画面側が
エンジンの名前を直接知ると、増やすたびに画面を直すことになる。
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from .apple_vision import AppleVisionEngine
from .base import Check, Engine, Line, Progress, Result, runs_here
from .ndl import NdlKotenLiteEngine, NdlLiteEngine
from .paddle_vl import PaddleVLEngine
from .ppocr import MODELS as PPOCR_MODELS
from .ppocr import PpocrEngine
from .yigdzin import YigdzinEngine

__all__ = [
    "Check",
    "Engine",
    "Line",
    "Progress",
    "Result",
    "all_engines",
    "available_engines",
    "runs_here",
]

# 並び順がそのまま画面の並び。取得の要らないものを上に置く。
# エンジンのクラス、または引数なしで 1 つ作る関数。PP-OCR の仲間は `ppocr.MODELS` の
# データから作るので、モデルを足しても、ここは直さない。
_ALL: list[Callable[[], Engine]] = [
    AppleVisionEngine,
    NdlKotenLiteEngine,
    NdlLiteEngine,
    *[partial(PpocrEngine, model) for model in PPOCR_MODELS],
    PaddleVLEngine,
    YigdzinEngine,
]


def available_engines() -> list[Engine]:
    """この OS で動くエンジンを作って返す。取得済みかどうかは問わない。"""
    return [e for e in all_engines() if runs_here(e)]


def all_engines() -> list[Engine]:
    """OS を問わず全部。設定画面は「この OS では使えません」も並べて見せる。"""
    return [make() for make in _ALL]
