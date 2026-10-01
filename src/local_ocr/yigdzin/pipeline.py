"""版面から行を見つけて、読んで、読み順に並べるところまでを 1 本につなぐ。

`ndl/pipeline.py` と同じ形(検出 → 並べ替え → 認識)。違うのは、認識を
ローカルの ONNX ではなく、常駐の llama-server(Yigdzin-1)に画像 1 枚ずつ
投げて行う点だけ。
"""

from __future__ import annotations

import re
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

# 1 行に書かせてよい長さ。写本の 1 行(約 120 音節)が 160 トークンほどで収まる。
# 4096 のままだと、止まらなくなった行が 1 行 1 分近く繰り返しを書き続ける。
LINE_MAX_TOKENS = 384

# 行の上下に足す余白(行の高さに対する割合)。検出器の切り出しは行の外を黒く
# 塗ってあり、写本の細長い行(横:縦が 20:1 を超える)だと Yigdzin-1 が
# 行の終わりを見失うことがある。元の画像から余白つきの長方形で切り直すと
# 止まる行がある(2026-10-01、東洋文庫・BDRC の写本カンギュルで実測)。
RETRY_MARGIN = 0.6

# 同じ並びがこの回数続いたら、繰り返しとみなして 1 回分だけ残す。
REPEAT_TIMES = 3
REPEAT_MAX_UNIT = 16  # 何音節(区切りの「།」も 1 つと数える)までの並びを見るか


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
            text, clean = self._read(line.crop)
            if not clean:
                again, clean_again = self._read(_rect_crop(img, line.box))
                if clean_again or len(again) > len(text):
                    text = again
            if not _is_tibetan(text):
                # 物差しや紙の端を行と見なしたもの。Yigdzin-1 は「empty page」と答えるか、
                # ローマ字の綴りを並べる(2026-10-01 実測)。本文ではないので捨てる
                continue
            reads.append(Read(text=text, box=line.box))
        return reads

    def _read(self, crop: Image.Image) -> tuple[str, bool]:
        """1 行を読む。返すのは (本文, 繰り返しに陥らず読み終えたか)。

        Yigdzin-1 は行の終わりで止まらず、改行してから同じ語を延々と続けることがある。
        出だしの 1 行はたいてい正しいので、最初の改行までを採り、残った繰り返しも切る。
        """
        raw, finished = ocr_call.complete(
            self.endpoint, crop, prompt=PROMPT, max_tokens=LINE_MAX_TOKENS
        )
        first = raw.strip().split("\n", 1)[0].strip()
        text = cut_repeats(first)
        return text, finished and text == first


def _is_tibetan(text: str) -> bool:
    """チベット文字(U+0F00〜U+0FFF)を 1 字でも含むか。"""
    return any("\u0f00" <= ch <= "\u0fff" for ch in text)


def _rect_crop(img: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    """検出した行の枠を、上下に余白を足して元の画像から長方形のまま切り出す。"""
    x, y, w, h = box
    m = int(h * RETRY_MARGIN)
    return img.crop((max(0, x), max(0, y - m), min(img.width, x + w), min(img.height, y + h + m)))


def cut_repeats(text: str) -> str:
    """同じ音節の並びが `REPEAT_TIMES` 回以上続いたら、そこから先を捨てて 1 回分だけ残す。

    例: 「ཆོས་དང་དང་དང་དང་…」→「ཆོས་དང་」。音節はツェク(་)と空白で区切る。
    本文で同じ語が 3 回続くことはまずないので、ここで切っても失うものはほぼ無い。
    """
    # 区切り記号ごと音節を取り出す(つなげ直すと元の文字列に戻る)
    sylls = re.findall(r"[^་\s]+[་\s]*|[་\s]+", text)
    n = len(sylls)
    for i in range(n):
        for k in range(1, REPEAT_MAX_UNIT + 1):
            unit = sylls[i : i + k]
            if i + k * REPEAT_TIMES > n:
                break
            if all(sylls[i + k * r : i + k * (r + 1)] == unit for r in range(1, REPEAT_TIMES)):
                return "".join(sylls[: i + k]).rstrip()
    return text


__all__ = ["YigdzinPipeline", "cut_repeats"]
