"""Yigdzin(チベット語 OCR)が要るものの定義。

PaddleOCR-VL と同じ形(GGUF ペア)に、行検出の ONNX ペアが 1 つ加わる。

  - GGUF (model / mmproj): BDRC/tibetan-ocr(Apache-2.0)を、このプロジェクトが
    自分で GGUF に変換して公開したもの(誰も公開していなかったため。詳しい経緯は
    NOTICE)。**上げるときはここの URL を差し替える。**
  - 行検出 (detector / detector-data): BDRC/PhotiLines_v2(CC BY 4.0)そのまま。
    2 ファイルに分かれている(.onnx は入口だけで、重みは .onnx.data 側)ので、
    ONNX ランタイムが読めるよう **同じフォルダに置く**(assets.py の Asset には
    このつながりを守る仕組みが無いので、ここで dest を揃えて守る)。
"""

from __future__ import annotations

from pathlib import Path

from .assets import Asset
from .paths import data_dir

GGUF_REPO = "https://huggingface.co/nakamura196/yigdzin1-gguf/resolve/main"
PHOTILINES_REPO = "https://huggingface.co/BDRC/PhotiLines_v2/resolve/main"


def _dir() -> Path:
    return data_dir() / "yigdzin"


def required() -> list[Asset]:
    d = _dir()
    return [
        Asset(
            key="model",
            label="文字を読む部分",
            url=f"{GGUF_REPO}/yigdzin1.gguf",
            dest=d / "yigdzin1.gguf",
            approx_bytes=750_993_408,
        ),
        Asset(
            key="mmproj",
            label="画像を見る部分",
            url=f"{GGUF_REPO}/yigdzin1-mmproj.gguf",
            dest=d / "yigdzin1-mmproj.gguf",
            approx_bytes=880_415_008,
        ),
        Asset(
            key="detector",
            label="行を見つける部分",
            url=f"{PHOTILINES_REPO}/photilines_v2.onnx",
            dest=d / "photilines_v2.onnx",
            approx_bytes=287_436,
        ),
        Asset(
            key="detector-data",
            label="行を見つける部分(重み)",
            url=f"{PHOTILINES_REPO}/photilines_v2.onnx.data",
            dest=d / "photilines_v2.onnx.data",
            approx_bytes=89_718_784,
        ),
    ]


def missing() -> list[Asset]:
    return [a for a in required() if not a.fetched()]
