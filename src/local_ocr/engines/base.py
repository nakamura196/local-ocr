"""エンジンの共通の口。

エンジンごとに違うのは「何を取得するか」と「どう読ませるか」だけ。
取得・キャッシュ・進捗・失敗時の文面は共通側が持ち、ここには書かない。
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from PIL import Image

from ..core.assets import Asset

# (今なにをしているか, 0..1 または None)
Progress = Callable[[str, float | None], None]


@dataclass
class Line:
    """読んだ 1 行。`box` は元画像の画素座標で (x, y, w, h)。

    `polygon` は 4 隅 (傾いた行や縦書きの列をそのまま囲める)。返せる道具だけが入れる。
    """

    text: str
    box: tuple[int, int, int, int] | None = None
    polygon: list[tuple[int, int]] | None = None


@dataclass
class Result:
    text: str
    lines: list[Line] = field(default_factory=list)
    # エンジンが返した生の値。書き出しや不具合調べのために残す。
    raw: object | None = None


@runtime_checkable
class Engine(Protocol):
    id: str
    label: str
    note: str
    # 動く OS。sys.platform の値で持つ ("darwin" / "win32")。
    platforms: frozenset[str]
    assets: list[Asset]

    def available(self) -> bool:
        """この機械で使えるか（OS と、取得済みかどうか）。"""

    def prepare(self, on_progress: Progress) -> None:
        """使える状態にする。取得の要らないエンジンは何もしない。"""

    def recognize(self, img: Image.Image) -> Result:
        """画像 1 枚を読む。"""

    def shutdown(self) -> None:
        """後始末。常駐するものを持たないエンジンは何もしない。"""


def runs_here(engine: Engine) -> bool:
    return sys.platform in engine.platforms
