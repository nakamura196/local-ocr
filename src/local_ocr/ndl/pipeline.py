"""版面を見つけて、読んで、読み順に並べるところまでを 1 本につなぐ。

古典籍と近代資料で、使うモデルと細かい決めごとが違うだけで、流れは同じ。
モデルの読み込みは重い（近代資料は 4 つある）ので、1 度作ったら使い回す。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from . import classes, order
from .detect import DEIM, Detection, RTMDet
from .layout import build_page
from .recognize import Parseq, load_charset, read_cascade, read_single


@dataclass
class Read:
    """読んだ 1 行。`box` は元画像の画素座標で (x, y, w, h)。"""

    text: str
    box: tuple[int, int, int, int]


def _crop(img: Image.Image, line: ET.Element) -> tuple[Image.Image, tuple[int, int, int, int]]:
    x, y = int(line.get("X", "0")), int(line.get("Y", "0"))
    w, h = int(line.get("WIDTH", "0")), int(line.get("HEIGHT", "0"))
    # 枠が画像からはみ出すことがある（検出は上下を 2% のばして返す）。
    # 削らずに負のまま切ると、反対の端が紛れ込む。
    left, top = max(x, 0), max(y, 0)
    right, bottom = min(x + w, img.width), min(y + h, img.height)
    if right <= left or bottom <= top:
        return Image.new("RGB", (1, 1)), (x, y, w, h)
    return img.crop((left, top, right, bottom)), (x, y, w, h)


class KotenPipeline:
    """古典籍・くずし字向け。RTMDet で行を見つけ、1 つの PARSeq で読む。"""

    def __init__(self, models: dict[str, Path]) -> None:
        self.detector = RTMDet(models["detector"], classes.KOTEN)
        self.recognizer = Parseq(
            models["recognizer"], load_charset("koten"), resample=Image.Resampling.BICUBIC
        )

    def run(self, img: Image.Image) -> list[Read]:
        detections = self.detector.detect(img)
        page = build_page(
            img.width, img.height, "image", classes.KOTEN, detections,
            score_thr=0.3, use_block_ad=False,
        )
        order.apply(page, smoothing=False)
        lines = page.findall(".//LINE")
        crops, boxes = zip(*(_crop(img, line) for line in lines), strict=True) if lines else ((), ())
        texts = read_single(self.recognizer, crops)
        return [Read(text, box) for text, box in zip(texts, boxes, strict=True)]

    def read_line(self, img: Image.Image) -> str:
        """画像全体を 1 行として読む(行を探す段を飛ばす)。"""
        return self.recognizer.read(img)


class LitePipeline:
    """近代資料・活字向け。DEIMv2 で版面を読み解き、長さ違いの PARSeq 3 つで読む。"""

    def __init__(self, models: dict[str, Path]) -> None:
        charset = load_charset("lite")
        self.detector = DEIM(models["detector"], classes.LITE)
        self.short = Parseq(models["short"], charset, resample=Image.Resampling.BILINEAR)
        self.medium = Parseq(models["medium"], charset, resample=Image.Resampling.BILINEAR)
        self.long = Parseq(models["long"], charset, resample=Image.Resampling.BILINEAR)

    def run(self, img: Image.Image) -> list[Read]:
        detections = self.detector.detect(img)
        page = build_page(
            img.width, img.height, "image", classes.LITE, detections,
            score_thr=0.1, use_block_ad=True,
        )
        order.apply(page, smoothing=True)
        lines = page.findall(".//LINE")
        if not lines:
            return []
        crops, boxes = zip(*(_crop(img, line) for line in lines), strict=True)
        hints = [float(line.get("PRED_CHAR_CNT", "100")) for line in lines]
        texts = read_cascade(self.short, self.medium, self.long, crops, hints)
        return [Read(text, box) for text, box in zip(texts, boxes, strict=True)]

    def read_line(self, img: Image.Image) -> str:
        """画像全体を 1 行として読む(行を探す段を飛ばす)。

        文字数の見当が無いので、短いモデルから始め、入りきらなければ長い方へ送る。
        """
        return read_cascade(self.short, self.medium, self.long, [img], [3])[0]


__all__ = ["Detection", "KotenPipeline", "LitePipeline", "Read"]
