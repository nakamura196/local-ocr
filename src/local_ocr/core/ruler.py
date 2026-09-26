"""画像に写り込んだ定規を見つけて、背景の色で塗りつぶす。

所蔵機関の撮影では、寸法を示す定規(目盛りと数字)が版面の横や下に写っていることが多い。
PaddleOCR-VL の「Spotting:」は右端から読み始めるので、右に定規があると
「1, 2, 3, …」と数を数え続け、出力の上限まで本文に届かない
(2026-09-25、candra 酉蓮社 030_01_025 で 1,041 行・枠 0。定規を消すと 140 行すべて枠つき)。
公式の PaddleOCR-VL は読む前に版面の区分け(PP-DocLayout)を通すが、
Local OCR は読むモデルだけを動かしているので、この前処理で代わりをする。

見つけ方は画素の並びだけで、モデルは使わない。

- 撮影台の背景は無地なので、縦(横)1 列の中で隣り合う画素の差がほとんど無い。
  この「無地の列」で画像を塊に分ける。
- 細く、背景の帯で本体と離れていて、画像の端から端まで通り、
  **目盛りが一定の間隔で並んでいる**塊を定規とみなす。
  最後の条件が決め手で、本文の列・柱・表紙の縁・本の小口はここで外れる
  (実測で目盛りの強さは定規 0.15〜0.25、それ以外 0.02〜0.06)。

見つからなければ何もしない。本体と定規が接して写っている場合は見つけられない
(そのときは `ocr.spot` が数を数え始めたところで打ち切る)。
位置は変えずに塗るだけなので、読んだ行の座標はそのまま元の画像で使える。
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

# 塊に分けるときの大きさ。細部は要らないので縮めて速くする。
_SIDE = 1000
# 目盛りの間隔を測るときの大きさ。1mm が数画素になる程度は要る。
_FINE_SIDE = 2400
# 隣り合う画素の差の平均がこれ未満なら「無地」。JPEG の揺らぎで 1〜2 ある。
_QUIET = 4.0
# 定規とみなす塊の幅(画像の幅に対する割合)。下限は本の影や縁の 1〜2 画素を拾わないため。
_MIN_WIDTH = 0.01
_MAX_WIDTH = 0.10
# 本体との間に要る背景の帯の幅。
_MIN_GAP = 0.004
# 塊が端から端まで通っているとみなす割合。
_SPAN = 0.85
# 目盛りの強さ(いちばん強い周期が、細かい揺れ全体に占める割合)の下限。
_TICKS = 0.10

Box = tuple[int, int, int, int]


def _runs(mask: np.ndarray, min_gap: int) -> list[tuple[int, int]]:
    """True が続く区間 [始め, 終わり)。min_gap 未満の切れ目はつなぐ。"""
    runs: list[tuple[int, int]] = []
    start = None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    merged: list[tuple[int, int]] = []
    for s, e in runs:
        if merged and s - merged[-1][1] < min_gap:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged


def _spans(part: np.ndarray, background: float) -> bool:
    """塊が上から下まで(背景でない画素として)通っているか。"""
    busy = (part.std(axis=1) > _QUIET * 2) | (np.abs(part.mean(axis=1) - background) > 12)
    return busy.mean() >= _SPAN


def tick_strength(profile: np.ndarray) -> float:
    """明るさの並び 1 本に、目盛りのような一定間隔の繰り返しがどれだけ強いか(0〜1)。"""
    # ゆるやかな明暗(照明のむら・紙の色)を引いて、細かい揺れだけにする。
    smooth = np.convolve(profile, np.ones(31) / 31, mode="same")
    x = (profile - smooth)[20:-20]
    if len(x) < 100:
        return 0.0
    power = np.abs(np.fft.rfft(x)) ** 2
    freq = np.arange(len(power)) / len(x)
    power = power[freq > 1 / 40]
    total = power.sum()
    return float(power.max() / total) if total > 0 else 0.0


def _find(small: np.ndarray, fine: np.ndarray) -> list[tuple[int, int]]:
    """縦の定規の列の範囲 [始め, 終わり)(small の画素)。横は転置して同じ関数で見る。"""
    w = small.shape[1]
    activity = np.abs(np.diff(small, axis=0)).mean(axis=0)
    quiet = activity < _QUIET
    if not quiet.any():
        return []
    runs = _runs(~quiet, max(1, round(w * _MIN_GAP)))
    if len(runs) < 2:
        return []
    # 背景の明るさは無地の列から取る(紙の色と取り違えないため)。
    background = float(np.median(small[:, quiet]))
    k = fine.shape[1] / w
    found = []
    for s, e in runs:
        if not (w * _MIN_WIDTH <= e - s <= w * _MAX_WIDTH):
            continue
        # 通っているかも目盛りも、細かいほうの画像で見る。縮めた画像では 1mm の目盛りが
        # ならされて背景と同じ灰色になり、通っていないように見える。
        part = fine[:, round(s * k) : max(round(e * k), round(s * k) + 1)]
        if not _spans(part, background):
            continue
        if tick_strength(part.mean(axis=1)) >= _TICKS:
            found.append((s, e))
    return found


def _gray(img: Image.Image, side: int) -> np.ndarray:
    w, h = img.size
    scale = min(1.0, side / max(w, h))
    g = img.convert("L")
    if scale < 1.0:
        g = g.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.BILINEAR)
    return np.asarray(g, dtype=np.float32)


def find_rulers(img: Image.Image) -> list[Box]:
    """定規の範囲 (左, 上, 右, 下) の並び。元の画像の画素で返す。"""
    w, h = img.size
    small = _gray(img, _SIDE)
    fine = _gray(img, _FINE_SIDE)
    sx, sy = w / small.shape[1], h / small.shape[0]
    boxes: list[Box] = []
    for s, e in _find(small, fine):
        boxes.append((round(s * sx), 0, round(e * sx), h))
    for s, e in _find(small.T, fine.T):
        boxes.append((0, round(s * sy), w, round(e * sy)))
    return boxes


def mask_rulers(img: Image.Image) -> Image.Image:
    """定規を背景の色で塗りつぶした画像。見つからなければ元の画像をそのまま返す。"""
    boxes = find_rulers(img)
    if not boxes:
        return img
    out = img.convert("RGB")
    # 塗る色は、定規のすぐ外側(背景の帯)の色の中央値。
    a = np.asarray(out)
    w, h = out.size
    pad = max(2, round(max(w, h) * _MIN_GAP))
    samples = []
    for x0, y0, x1, y1 in boxes:
        if y0 == 0 and y1 == h:  # 縦の定規
            for xs in (slice(max(0, x0 - pad), x0), slice(x1, min(w, x1 + pad))):
                samples.append(a[:, xs].reshape(-1, 3))
        else:
            for ys in (slice(max(0, y0 - pad), y0), slice(y1, min(h, y1 + pad))):
                samples.append(a[ys, :].reshape(-1, 3))
    color = tuple(int(v) for v in np.median(np.concatenate(samples), axis=0))
    draw = ImageDraw.Draw(out)
    for x0, y0, x1, y1 in boxes:
        draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=color)
    return out
