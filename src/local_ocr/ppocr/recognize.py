"""1 行を文字にする部分（CTC）。

CTC は、時間方向の各位置で「いちばん確からしい字」を選び、同じ字の連続を 1 つに
詰め、空白（番号 0）を捨てて文字列にする方式。
"""

from __future__ import annotations

import numpy as np

from .config import DEFAULT, Params
from .pixels import bgr_tensor, resize_linear_cv

REC_MAX_W = 3200


def rec_tensor(img: np.ndarray, params: Params = DEFAULT) -> np.ndarray:
    """読み取りの入力: 高さは 48 など、幅は縦横比のまま（320 以上、右は 0 で埋める）。"""
    rec_h = params.rec_height
    h, w = img.shape[:2]
    ratio = w / h
    width = int(rec_h * max(params.rec_min_width / rec_h, ratio))
    if width > REC_MAX_W:
        width = rw = REC_MAX_W
    else:
        rw = min(int(np.ceil(rec_h * ratio)), width)
    small = resize_linear_cv(img, rw, rec_h)
    t = bgr_tensor(small, (127.5,) * 3, (127.5,) * 3)
    if rw == width:
        return t
    out = np.zeros((1, 3, rec_h, width), np.float32)
    out[:, :, :, :rw] = t
    return out


def decode_ctc(prob: np.ndarray, chars: list[str]) -> tuple[str, float]:
    """[T, C] の確からしさを文字にする。返り値は (文字列, 採った字の確からしさの平均)。"""
    best = prob.argmax(axis=1)
    top = prob.max(axis=1)
    prev = np.concatenate(([-1], best[:-1]))
    keep = (best != 0) & (best != prev)
    ids = best[keep].tolist()
    text = "".join(chars[i - 1] if i - 1 < len(chars) else " " for i in ids)
    return text, float(top[keep].mean()) if ids else 0.0
