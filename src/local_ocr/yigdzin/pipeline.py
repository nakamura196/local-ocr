"""版面から行を見つけて、読んで、読み順に並べるところまでを 1 本につなぐ。

`ndl/pipeline.py` と同じ形(検出 → 並べ替え → 認識)。違うのは、認識を
ローカルの ONNX ではなく、常駐の llama-server(Yigdzin-1)に画像 1 枚ずつ
投げて行う点だけ。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from ..core import ocr as ocr_call
from ..ndl import order
from ..ndl.pipeline import Read
from .line_detection import LineDetector

# 行クロップに特化した指示文。1 行クロップなら sequential/grid どちらの
# 位置エンコーディングでも差が出ないことを検証済み(docs/design.md)なので、
# 本家の llama.cpp(grid のみ)で足りる — 独自パッチは要らない。
PROMPT = "Extract all Tibetan text. Preserve line breaks."


class YigdzinPipeline:
    def __init__(self, detector_path: Path, endpoint: str) -> None:
        self.detector = LineDetector(detector_path)
        self.endpoint = endpoint

    def run(self, img: Image.Image) -> list[Read]:
        lines = self.detector.detect(img)
        if not lines:
            return []

        # 読み順は座標だけで決める(NDL と同じ XY カット)。PhotiLines_v2 は
        # 「行かどうか」の 1 クラスしか返さないので、NDL のような本文ブロック/
        # 表/図版といった種類ごとの組み立て(`ndl/layout.py`)は要らない。
        boxes = np.array(
            [[x, y, x + w, y + h] for x, y, w, h in (line.box for line in lines)],
            dtype=np.int64,
        )
        ranks = order.solve(boxes)
        ordered = [line for _, line in sorted(zip(ranks, lines, strict=True), key=lambda p: p[0])]

        reads = []
        for line in ordered:
            text = ocr_call.recognize(self.endpoint, line.crop, prompt=PROMPT)
            reads.append(Read(text=text, box=line.box))
        return reads


__all__ = ["YigdzinPipeline"]
