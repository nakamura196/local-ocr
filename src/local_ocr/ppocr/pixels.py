"""画素の扱い。画像は高さ × 幅 × 3 の uint8（RGB）の配列で持つ。

OpenCV と同じ結果になるように書いてある。**Pillow の縮め方は使わない**:
PP-OCR の上流は OpenCV の INTER_LINEAR / INTER_CUBIC を使っていて、縮め方が
変わると検出も読みも変わる（NDL は上流が Pillow なので Pillow のまま）。
"""

from __future__ import annotations

import numpy as np

# 公式の検出・読み取りの正規化。**検出の平均は BGR の並びに RGB の ImageNet の値を
# そのまま当てている**（公式の癖。モデルがそれで学習されているので直さない）。
_DET_MEAN = (0.485 * 255, 0.456 * 255, 0.406 * 255)
_DET_STD = (0.229 * 255, 0.224 * 255, 0.225 * 255)


def _taps(src: int, dst: int, clamp: bool):
    """INTER_LINEAR の、出力 1 画素ごとの参照元 2 つと重み (1/2048 の整数)。

    OpenCV は float32 で位置を出す。同じ丸めになるよう float32 で計算する。
    """
    scale = src / dst
    d = np.arange(dst, dtype=np.float64)
    f = ((d + 0.5) * scale - 0.5).astype(np.float32)
    s = np.floor(f).astype(np.int64)
    f = (f - s.astype(np.float32)).astype(np.float32)
    if clamp:
        low = s < 0
        high = s >= src - 1
        f = np.where(low | high, np.float32(0), f)
        s = np.where(low, 0, np.where(high, src - 1, s))
    i0 = np.clip(s, 0, src - 1)
    i1 = np.clip(s + 1, 0, src - 1)
    # saturate_cast<short>(v * 2048) は偶数丸め（np.rint と同じ）
    a0 = np.rint((np.float32(1) - f) * np.float32(2048)).astype(np.int32)
    a1 = np.rint(f * np.float32(2048)).astype(np.int32)
    return i0, i1, a0, a1


def resize_linear_cv(img: np.ndarray, out_w: int, out_h: int) -> np.ndarray:
    """cv2.resize(INTER_LINEAR) の 8 ビット画素版。OpenCV と同じ固定小数点の式。

    **ビットまでは一致しない。** 手元の OpenCV（arm64）と比べると、縦に 3 倍ほど縮める
    ときに 25% ほどの画素が 1〜2 段階ずれる（ランダム画像 60 枚のうち 6 枚）。
    OpenCV は環境ごとに別の実装（SIMD など）を使うので、完全には追えない。読みへの
    影響は、英語の活字 1 ページで確かめて、行数も文字も変わらなかった。

    横は 1/2048 の重みで混ぜ、縦は OpenCV の SIMD の丸め
    ((a >> 4) * b0 >> 16) + ((c >> 4) * b1 >> 16) + 2) >> 2 に合わせる。
    横は端の参照元を端に寄せて重みを 0 にし、縦は行の番号だけを寄せる。
    """
    h, w = img.shape[:2]
    if w == out_w and h == out_h:
        return img
    xi0, xi1, xa0, xa1 = _taps(w, out_w, True)
    yi0, yi1, ya0, ya1 = _taps(h, out_h, False)
    src = img.astype(np.int32)
    rows = src[:, xi0, :] * xa0[None, :, None] + src[:, xi1, :] * xa1[None, :, None]
    top = ((rows[yi0] >> 4) * ya0[:, None, None]) >> 16
    bottom = ((rows[yi1] >> 4) * ya1[:, None, None]) >> 16
    return ((top + bottom + 2) >> 2).astype(np.uint8)


def bgr_tensor(img: np.ndarray, mean: tuple[float, ...], std: tuple[float, ...]) -> np.ndarray:
    """NCHW (1, 3, h, w) の float32。BGR の並びで (値 - 平均) / 標準偏差。"""
    bgr = img[:, :, ::-1].astype(np.float32)
    out = (bgr - np.asarray(mean, np.float32)) / np.asarray(std, np.float32)
    return np.ascontiguousarray(out.transpose(2, 0, 1)[None])


def det_tensor(img: np.ndarray) -> np.ndarray:
    """検出の入力。`img` はすでに検出の大きさ (dw × dh) に縮めてある。"""
    return bgr_tensor(img, _DET_MEAN, _DET_STD)


def rotate_left(img: np.ndarray) -> np.ndarray:
    """左へ 90 度倒す（PIL の ROTATE_90。縦書きの行を横長にする）。"""
    return np.ascontiguousarray(np.rot90(img))


def _cubic_weights(t: np.ndarray) -> list[np.ndarray]:
    """INTER_CUBIC（a = -0.75）の 4 つの重み。"""
    a = -0.75
    w0 = ((a * (t + 1) - 5 * a) * (t + 1) + 8 * a) * (t + 1) - 4 * a
    w1 = ((a + 2) * t - (a + 3)) * t * t + 1
    u = 1 - t
    w2 = ((a + 2) * u - (a + 3)) * u * u + 1
    return [w0, w1, w2, 1 - w0 - w1 - w2]


def bicubic_sample(img: np.ndarray, sx: np.ndarray, sy: np.ndarray) -> np.ndarray:
    """元画像の位置 (sx, sy)（小数）を 3 次補間で引く。外は端の画素を繰り返す。

    `sx`・`sy` は同じ形の配列で、返り値はその形 + (3,) の uint8。
    16 点の重み付き和を、配列まるごとの演算で一度に出す（画素ごとの繰り返しは遅い）。
    """
    h, w = img.shape[:2]
    ix = np.floor(sx).astype(np.int64)
    iy = np.floor(sy).astype(np.int64)
    wx = _cubic_weights(sx - ix)
    wy = _cubic_weights(sy - iy)
    flat = img.reshape(-1, img.shape[2]).astype(np.float64)
    acc = np.zeros(sx.shape + (img.shape[2],), np.float64)
    for j in range(4):
        y = np.clip(iy - 1 + j, 0, h - 1)
        row = np.zeros_like(acc)
        for i in range(4):
            x = np.clip(ix - 1 + i, 0, w - 1)
            row += wx[i][..., None] * flat[y * w + x]
        acc += wy[j][..., None] * row
    return np.clip(np.floor(acc + 0.5), 0, 255).astype(np.uint8)
