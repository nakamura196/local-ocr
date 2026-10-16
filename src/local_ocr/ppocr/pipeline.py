"""検出 → 切り出し → 読み取りを 1 本につなぐ。

モデルを開くのは重い（数百 ms）ので、1 度作ったら使い回す。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime
from PIL import Image

from . import detect, pixels, recognize
from .config import DEFAULT, Params


@dataclass
class Read:
    """読んだ 1 行。`box` は元画像の画素座標で (x, y, w, h)。

    `polygon` は行が傾いているときだけ入る（4 隅）。`score` は検出の確からしさ、
    `text_score` は読んだ字の確からしさの平均。
    """

    text: str
    box: tuple[int, int, int, int]
    polygon: list[tuple[int, int]] | None = None
    score: float = 0.0
    text_score: float = 0.0


def _session(path: Path) -> onnxruntime.InferenceSession:
    opts = onnxruntime.SessionOptions()
    opts.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
    # 公式の変換物は使わない部品を持っていて、開くたびに警告が何十行も出る。
    opts.log_severity_level = 3
    return onnxruntime.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])


def crop_line(img: np.ndarray, quad: list[tuple[int, int]]) -> np.ndarray | None:
    """四角形の中を、まっすぐな 1 枚に切り出す（公式の get_rotate_crop_image）。

    公式（get_minarea_rect_crop）と同じく、整数にした四隅の最小外接矩形を取り直して
    から切り出す。縦に細長い（高さが幅の 1.5 倍以上）ものは、左へ倒して横長にする。
    小さすぎて切れなければ None。
    """
    p0, p1, p2, p3 = detect.rect_corners(
        detect.min_area_rect([(float(x), float(y)) for x, y in quad])
    )

    def dist(a, b):
        return float(np.hypot(a[0] - b[0], a[1] - b[1]))

    w = int(max(dist(p0, p1), dist(p2, p3)))
    h = int(max(dist(p0, p3), dist(p1, p2)))
    if w <= 0 or h <= 0:
        return None
    u, v = np.meshgrid(np.arange(w, dtype=np.float64), np.arange(h, dtype=np.float64))
    ax, ay = (p1[0] - p0[0]) / w, (p1[1] - p0[1]) / w
    bx, by = (p3[0] - p0[0]) / h, (p3[1] - p0[1]) / h
    out = pixels.bicubic_sample(img, p0[0] + u * ax + v * bx, p0[1] + u * ay + v * by)
    return pixels.rotate_left(out) if h / w >= 1.5 else out


def quad_box(quad: list[tuple[int, int]]):
    """四角形を囲む軸に沿った枠と、傾いているときだけ四角形そのもの。"""
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    x, y = min(xs), min(ys)
    # 軸から 0.5px より多くずれていたら「傾いている」
    turned = abs(quad[0][1] - quad[1][1]) > 0.5 or abs(quad[0][0] - quad[3][0]) > 0.5
    return (x, y, max(xs) - x, max(ys) - y), (list(quad) if turned else None)


class PpocrPipeline:
    def __init__(
        self,
        detector: Path,
        recognizer: Path,
        chars: list[str],
        params: Params = DEFAULT,
        *,
        det_long_side: int = 2048,
    ) -> None:
        self.det = _session(detector)
        self.rec = _session(recognizer)
        self.chars = chars
        self.params = params
        self.det_long_side = det_long_side
        self._det_in = self.det.get_inputs()[0].name
        self._rec_in = self.rec.get_inputs()[0].name

    def detect(self, img: Image.Image) -> list[tuple[list[tuple[int, int]], float]]:
        """行の四角形を読み順に返す。`img` は RGB。"""
        W, H = img.size
        # 長辺を上限に縮めてから検出する（公式は原寸。違いは `__init__.py` の 3 番）
        scale = min(1.0, self.det_long_side / max(W, H))
        small = (
            img
            if scale == 1.0
            else img.resize(
                (max(round(W * scale), 1), max(round(H * scale), 1)), Image.Resampling.BICUBIC
            )
        )
        dw, dh = detect.det_size(*small.size)
        arr = pixels.resize_linear_cv(np.asarray(small), dw, dh)
        prob = self.det.run(None, {self._det_in: pixels.det_tensor(arr)})[0][0, 0]
        return detect.find_boxes(prob, W, H, self.params)

    def read_crop(self, crop: np.ndarray) -> tuple[str, float]:
        out = self.rec.run(None, {self._rec_in: recognize.rec_tensor(crop, self.params)})[0][0]
        return recognize.decode_ctc(out, self.chars)

    def run(self, img: Image.Image) -> list[Read]:
        rgb = np.asarray(img.convert("RGB"))
        reads: list[Read] = []
        for quad, score in self.detect(img.convert("RGB")):
            crop = crop_line(rgb, quad)
            if crop is None:
                continue
            text, text_score = self.read_crop(crop)
            if text.strip():
                box, polygon = quad_box(quad)
                reads.append(Read(text, box, polygon, score, text_score))
        return reads

    def read_line(self, img: Image.Image) -> str:
        """画像全体を 1 行として読む（検出を飛ばす）。縦長なら左へ倒す。"""
        arr = np.asarray(img.convert("RGB"))
        h, w = arr.shape[:2]
        if w == 0 or h == 0:
            return ""
        if h / w >= 1.5:
            arr = pixels.rotate_left(arr)
        return self.read_crop(arr)[0]
