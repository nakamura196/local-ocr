"""Yigdzin(チベット語 OCR)のうち、モデルが無くても見られるところ。

**モデルは CI に無い**(GGUF 2 つと ONNX で合わせて 1.7GB)。ここで見るのは、
取得先の決め方と、行検出の幾何まわり(回転角の推定・輪郭の座標変換・
ノイズの足切り)といった、こちらが書いた部分。`test_ndl.py` と同じ方針。
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from local_ocr.core import yigdzin_assets
from local_ocr.engines import all_engines
from local_ocr.yigdzin import line_detection as ld

# --- 取得するもの -------------------------------------------------------------


def test_each_asset_has_its_own_place():
    assets = yigdzin_assets.required()
    assert len({a.key for a in assets}) == len(assets)
    assert len({a.dest for a in assets}) == len(assets)


def test_detector_files_sit_next_to_each_other():
    """.onnx と .onnx.data は ONNX ランタイムが同じフォルダで探す。分けて置かない。"""
    assets = {a.key: a for a in yigdzin_assets.required()}
    assert assets["detector"].dest.parent == assets["detector-data"].dest.parent


def test_urls_point_at_the_expected_repos():
    assets = {a.key: a for a in yigdzin_assets.required()}
    assert assets["model"].url.startswith("https://huggingface.co/nakamura196/yigdzin1-gguf/")
    assert assets["mmproj"].url.startswith("https://huggingface.co/nakamura196/yigdzin1-gguf/")
    assert assets["detector"].url.startswith("https://huggingface.co/BDRC/PhotiLines_v2/")
    assert assets["detector-data"].url.startswith("https://huggingface.co/BDRC/PhotiLines_v2/")


def test_engine_is_on_the_list():
    engines = {e.id: e for e in all_engines()}
    assert "yigdzin" in engines
    engine = engines["yigdzin"]
    assert engine.assets
    assert engine.available() == all(a.fetched() for a in engine.assets)


# --- 行検出の幾何 ---------------------------------------------------------------


def _rect_mask(size: tuple[int, int], boxes: list[tuple[int, int, int, int]]) -> np.ndarray:
    """`boxes` (x, y, w, h) を白く塗った 2 値マスクを作る。"""
    mask = np.zeros(size[::-1], dtype=np.uint8)
    for x, y, w, h in boxes:
        mask[y : y + h, x : x + w] = 255
    return mask


def test_rotation_angle_is_zero_for_straight_lines():
    """まっすぐな横長の矩形が並んでいれば、傾きは検出しない。"""
    mask = _rect_mask((400, 200), [(20, 30, 300, 20), (20, 80, 300, 20), (20, 130, 300, 20)])
    assert ld._rotation_angle(mask) == pytest.approx(0.0, abs=0.5)


def test_rotation_angle_detects_a_tilt():
    """5 度傾けた矩形を渡すと、その傾きを検出する(符号は cv2 の流儀どおり)。"""
    straight = _rect_mask((400, 200), [(20, 30, 300, 16), (20, 80, 300, 16), (20, 130, 300, 16)])
    matrix = cv2.getRotationMatrix2D((200, 100), 4.0, 1)
    tilted = cv2.warpAffine(straight, matrix, (400, 200))
    angle = ld._rotation_angle(tilted)
    assert angle != pytest.approx(0.0, abs=0.5)


def test_filter_by_size_drops_noise():
    mask = _rect_mask((1000, 200), [(20, 30, 300, 20), (500, 30, 3, 3)])
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    kept = ld._filter_by_size(mask, contours)
    assert len(kept) == 1
    x, y, w, h = cv2.boundingRect(kept[0])
    assert (x, y, w, h) == (20, 30, 300, 20)


def test_box_in_original_space_round_trips_without_rotation():
    """回転角 0 なら、輪郭の外接矩形は入れたときの座標に一致する。"""
    mask = _rect_mask((400, 200), [(20, 30, 100, 40)])
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    matrix = ld._rotation_matrix((400, 200), 0.0)
    inverse = cv2.invertAffineTransform(matrix)
    box = ld._box_in_original_space(contours[0], inverse, 400, 200)
    assert box == (20, 30, 100, 40)


def test_box_in_original_space_undoes_a_rotation():
    """回した画像上の輪郭を戻すと、回す前の矩形とだいたい重なる。"""
    original = (100, 60, 120, 30)
    mask = _rect_mask((400, 200), [original])
    matrix = ld._rotation_matrix((400, 200), 4.0)
    rotated_mask = cv2.warpAffine(mask, matrix, (400, 200))
    contours, _ = cv2.findContours(rotated_mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    inverse = cv2.invertAffineTransform(matrix)
    x, y, w, h = ld._box_in_original_space(contours[0], inverse, 400, 200)
    ox, oy, ow, oh = original
    # 回転・再ラスタ化の丸めがあるので、ぴったりではなく近さで見る。
    assert abs(x - ox) <= 3
    assert abs(y - oy) <= 3
    assert abs(w - ow) <= 6
    assert abs(h - oh) <= 6
