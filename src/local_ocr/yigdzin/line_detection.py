"""版面のどこに行があるかを見つける部分。BDRC/PhotiLines_v2(ONNX)を使う。

BDRC純正アプリ(`buda-base/tibetan-ocr-app`)の `BDRC/line_detection.py` /
`BDRC/Utils.py` / `BDRC/Inference.py`(`LineDetection`)を下敷きにした移植。
**上流と考え方は同じだが、そのまま持ってきてはいない。**

- 版面ぜんたいのレイアウト解析(表・図版・キャプションの分類)はしない。
  PhotiLines_v2 は「行かどうか」の 1 クラスしか返さないので、その必要がない
- 読み順の並べ替えはしない。それは `ndl/order.py` の XY カットに任せる
  (`yigdzin/pipeline.py` 側でやる。座標だけを見る汎用のロジックで、
  NDL 固有ではない)
- 歪み補正(TPS)はしない。**傾き(回転)の補正だけ入れる。** BDRC純正でも
  TPS は既定オフの上級機能
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt
import onnxruntime
from PIL import Image

# BDRC純正アプリ・PhotiLines_v2 の config.json (`patch_size: "512"`) と同じ既定値。
PATCH_SIZE = 512
CLASS_THRESHOLD = 0.9
# 版面を大きすぎる/小さすぎるまま渡さない。BDRC純正の既定値。縮めないと、
# タイル 1 枚に収まる行が太くなりすぎ、モデルが学習時に見ていない大きさになる。
CLAMP_WIDTH = 4096
CLAMP_HEIGHT = 2048
# 行を切り出すときの膨張の大きさと、切り直しを始める高さの倍率。
#
# **BDRC純正アプリの既定値(`ocr_settings.json` の `k_factor=2.5` /
# `bbox_tolerance=3.0`)ではなく、関数の引数の既定値(1.7 / 2.5)を使う。**
# 実測で試した結果、アプリの既定値のほうが余白を広く残し、Yigdzin-1 に渡すと
# 隣の行を読み込んで続きを作文する(同じ語句の繰り返しループに陥ることもある)。
# BDRC純正の認識器(小さな CTC モデル)は多少の余白があっても行の外を無視できるが、
# Yigdzin-1 は VLM(自己回帰生成)なので、渡した絵の中に読める文字があれば
# 読み進めてしまう。よってここだけ、値を詰めた側(1.7 / 2.5)を採用する。
CROP_K_FACTOR = 1.7
CROP_BBOX_TOLERANCE = 2.5


@dataclass
class Line:
    """検出した行 1 つ。

    `box` は**元の画像**(回転させる前)の画素座標で (x, y, w, h)。傾きを補正
    したあと切り出しているので、`crop` はまっすぐな行の絵になる。
    """

    box: tuple[int, int, int, int]
    crop: Image.Image


def _resize_to_width(img: npt.NDArray, width: int) -> npt.NDArray:
    scale = width / img.shape[1]
    return cv2.resize(img, (width, max(1, int(img.shape[0] * scale))), interpolation=cv2.INTER_LINEAR)


def _resize_to_height(img: npt.NDArray, height: int) -> npt.NDArray:
    scale = height / img.shape[0]
    return cv2.resize(img, (max(1, int(img.shape[1] * scale)), height), interpolation=cv2.INTER_LINEAR)


def _clamp(img: npt.NDArray) -> npt.NDArray:
    h, w = img.shape[:2]
    if w > h and w > CLAMP_WIDTH:
        return _resize_to_width(img, CLAMP_WIDTH)
    if h > w and h > CLAMP_HEIGHT:
        return _resize_to_height(img, CLAMP_HEIGHT)
    if h < PATCH_SIZE:
        return _resize_to_height(img, PATCH_SIZE)
    return img


def _pad_to_tiles(img: npt.NDArray, patch_size: int = PATCH_SIZE) -> tuple[npt.NDArray, int, int]:
    """タイル分割できる大きさまで、白(255)で余白を足す。"""
    h, w = img.shape[:2]
    pad_x = math.ceil(w / patch_size) * patch_size - w
    pad_y = math.ceil(h / patch_size) * patch_size - h
    padded = np.pad(img, ((0, pad_y), (0, pad_x), (0, 0)), mode="constant", constant_values=255)
    return padded, pad_x, pad_y


def _tile(img: npt.NDArray, patch_size: int = PATCH_SIZE) -> tuple[list[npt.NDArray], int]:
    y_steps = img.shape[0] // patch_size
    x_steps = img.shape[1] // patch_size
    rows = np.split(img, y_steps, axis=0)
    tiles = [tile for row in rows for tile in np.split(row, x_steps, axis=1)]
    return tiles, y_steps


def _binarize(tile: npt.NDArray) -> npt.NDArray:
    gray = cv2.cvtColor(tile, cv2.COLOR_RGB2GRAY)
    bw = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 51, 13
    )
    return cv2.cvtColor(bw, cv2.COLOR_GRAY2RGB)


def _stitch(mask: npt.NDArray, y_steps: int) -> npt.NDArray:
    rows = np.split(mask, y_steps, axis=0)
    return np.vstack([np.hstack(row) for row in rows])


def _sigmoid(x: npt.NDArray) -> npt.NDArray:
    """大きく負の値で `exp` があふれて警告が出るのを避ける(結果は変わらない)。"""
    return np.where(x >= 0, 1 / (1 + np.exp(-x)), np.exp(x) / (1 + np.exp(x)))


def _line_orientation(contour: npt.NDArray) -> float:
    """1 つの輪郭が、水平から何度傾いているか。長い辺を基準にする。(-90, 90] で返す。

    **BDRC純正のコードは angle をそのまま使っているが、それは古い OpenCV の
    角度の付け方(0=横、90=縦)を前提にしている。** 今の OpenCV(4.5 以降)は
    `minAreaRect` の角度の付け方を変えていて、同じ「まっすぐ横」の矩形でも
    `size` の並びと `angle` の組み合わせが変わる(例: 実測で `angle=-90` が
    返る)。ここでは `size` の大小で長い辺がどちらかを見てから正規化するので、
    OpenCV の版に依らない。
    """
    (_, _), (w, h), angle = cv2.minAreaRect(contour)
    if w < h:
        angle += 90
    return ((angle + 90) % 180) - 90


def _rotation_angle(mask: npt.NDArray, max_angle: float = 5.0) -> float:
    """行の傾きから、ページ全体の回転角を推定する(BDRC純正と同じ考え方)。

    版面に対して十分大きい輪郭だけを見て、それぞれの傾き(`_line_orientation`)
    を集め、水平から `max_angle` 度以内に収まっているものの平均を取る
    (横書きの行は、page が大きく傾いていない限り、ほぼ水平のはずなので)。
    """
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    threshold = mask.shape[0] * mask.shape[1] * 0.001
    contours = [c for c in contours if cv2.contourArea(c) > threshold]
    if not contours:
        return 0.0
    angles = [a for a in (_line_orientation(c) for c in contours) if abs(a) <= max_angle]
    return float(np.mean(angles)) if angles else 0.0


def _rotation_matrix(size: tuple[int, int], angle: float) -> npt.NDArray:
    w, h = size
    return cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1)


def _rotate(img: npt.NDArray, matrix: npt.NDArray, border: int | tuple[int, int, int]) -> npt.NDArray:
    h, w = img.shape[:2]
    return cv2.warpAffine(img, matrix, (w, h), borderValue=border)


def _filter_by_size(mask: npt.NDArray, contours: list, width_ratio: float = 0.01) -> list:
    """細すぎる・小さすぎる輪郭(ノイズ)を落とす。BDRC純正の既定値と同じ。"""
    out = []
    for c in contours:
        _, _, w, h = cv2.boundingRect(c)
        if w > mask.shape[1] * width_ratio and h > 10:
            out.append(c)
    return out


def _dilate_and_crop(rot_img: npt.NDArray, contour: npt.NDArray, k: float) -> npt.NDArray:
    mask = np.zeros(rot_img.shape[:2], dtype=np.uint8)
    cv2.drawContours(mask, [contour], -1, 255, -1)
    k_size = max(1, round(k))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_size, max(1, int(k_size * CROP_K_FACTOR))))
    dilated = cv2.dilate(mask, kernel, iterations=1)
    masked = cv2.bitwise_and(rot_img, rot_img, mask=dilated)
    rows, cols = np.any(dilated, axis=1), np.any(dilated, axis=0)
    if not rows.any() or not cols.any():
        return np.zeros((1, 1, 3), dtype=np.uint8)
    y0, y1 = np.where(rows)[0][[0, -1]]
    x0, x1 = np.where(cols)[0][[0, -1]]
    return masked[y0 : y1 + 1, x0 : x1 + 1]


def _crop_line(
    rot_img: npt.NDArray, contour: npt.NDArray, box_h: int, bbox_tolerance: float = CROP_BBOX_TOLERANCE
) -> npt.NDArray:
    """行 1 本を切り出す。輪郭のまま矩形で切ると隣の行の文字が混ざることがあるので、
    輪郭を膨張させたマスクで隠してから切る(BDRC純正と同じ考え方)。

    マスクの外は黒になる(白紙ではない)。BDRC純正の学習・評価データが同じ形で
    作られているため、モデルが見慣れた入力に合わせている。

    **膨張の大きさは固定しない。** 行と行の間隔が狭いと、既定の膨張(行の高さの
    `CROP_K_FACTOR` 倍)だけで隣の行まで飲み込んでしまう(実測: 密な版面で
    7 行のはずが、隣り合う行の文字が混ざって出た)。切り出した高さが元の行の
    高さの `bbox_tolerance` 倍を超える間、膨張を少しずつ弱めて切り直す
    (BDRC純正 `get_line_image` と同じ考え方)。
    """
    k = box_h * CROP_K_FACTOR
    for _ in range(10):
        crop = _dilate_and_crop(rot_img, contour, k)
        if crop.shape[0] <= box_h * bbox_tolerance or k <= box_h * 0.2:
            return crop
        k -= box_h * 0.1
    return crop


def _box_in_original_space(
    contour: npt.NDArray, inverse: npt.NDArray, img_w: int, img_h: int
) -> tuple[int, int, int, int]:
    """回転させた画像上の輪郭を、回転させる前の画像の (x, y, w, h) に戻す。

    行検出も切り出しも回転させた画像の上で行うが、`Line.box` は利用者が渡した
    元の画像に対する座標でなければならない(TEI の facsimile 出力・版面への
    枠の重ね描きは、元の画像のまま行うため)。

    輪郭の全点を逆変換してから、軸に揃えた外接矩形を取る。**先に回転後の画像
    上で `cv2.boundingRect` を取ってから戻す形にはしない。** 回転で斜めに
    なった矩形を、さらに軸に揃えた矩形で包むと本来より大きくなり、それを
    逆変換すると余分な幅がずれた向きに乗って戻る(実測で数 px 単位のずれ)。
    輪郭点を直接戻す方が、回った矩形の実際の形をそのまま運べる。

    輪郭の画素座標は「その画素の位置」を指す。幅を出すには
    `右端 - 左端 + 1` が要る(`cv2.boundingRect` と同じ数え方)。
    """
    pts = contour.reshape(-1, 2).astype(np.float64)
    ones = np.ones((pts.shape[0], 1))
    orig = np.hstack([pts, ones]) @ inverse.T
    x0, y0 = orig[:, 0].min(), orig[:, 1].min()
    x1, y1 = orig[:, 0].max(), orig[:, 1].max()
    x0, y0 = max(0, math.floor(x0)), max(0, math.floor(y0))
    x1, y1 = min(img_w, math.ceil(x1) + 1), min(img_h, math.ceil(y1) + 1)
    return x0, y0, max(0, x1 - x0), max(0, y1 - y0)


class LineDetector:
    """PhotiLines_v2 (ONNX): 版面のどこに行があるかを 2 値のマスクで見つける。"""

    def __init__(self, model_path: Path) -> None:
        self.session = onnxruntime.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name

    def _mask(self, img: npt.NDArray) -> npt.NDArray:
        padded, pad_x, pad_y = _pad_to_tiles(img)
        tiles, y_steps = _tile(padded)
        batch = np.array([_binarize(t).astype(np.float32) / 255.0 for t in tiles])
        batch = batch.transpose(0, 3, 1, 2).astype(np.float32)
        pred = self.session.run([self.output_name], {self.input_name: batch})[0]
        pred = np.squeeze(pred, axis=1)
        pred = _sigmoid(pred)
        pred = np.where(pred > CLASS_THRESHOLD, 1.0, 0.0).astype(np.uint8)
        mask = _stitch(pred, y_steps)
        if pad_y:
            mask = mask[:-pad_y, :]
        if pad_x:
            mask = mask[:, :-pad_x]
        return (mask * 255).astype(np.uint8)

    def detect(self, img: Image.Image) -> list[Line]:
        original = np.asarray(img.convert("RGB"))
        work = _clamp(original)
        scale_x, scale_y = original.shape[1] / work.shape[1], original.shape[0] / work.shape[0]
        mask = self._mask(work)

        angle = _rotation_angle(mask)
        matrix = _rotation_matrix((work.shape[1], work.shape[0]), angle)
        inverse = cv2.invertAffineTransform(matrix)
        rot_mask = _rotate(mask, matrix, 0)
        rot_img = _rotate(work, matrix, (255, 255, 255))

        contours, _ = cv2.findContours(rot_mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contours = [c for c in contours if cv2.contourArea(c) > 10]
        contours = _filter_by_size(rot_mask, contours)

        lines: list[Line] = []
        for contour in contours:
            _, _, _, box_h = cv2.boundingRect(contour)
            crop = _crop_line(rot_img, contour, box_h)
            # `work` の縮小分を元に戻してから、`original` の座標系に直す。
            box = _box_in_original_space(contour, inverse, work.shape[1], work.shape[0])
            x, y, w, h = box
            box = (round(x * scale_x), round(y * scale_y), round(w * scale_x), round(h * scale_y))
            lines.append(Line(box=box, crop=Image.fromarray(crop)))
        return lines
