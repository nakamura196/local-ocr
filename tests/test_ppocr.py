"""PP-OCR の仲間（ppocrv5 / ppocrv5-latin / ppocrv6-small）のうち、モデルが無くても見られるところ。

**モデルは CI に無い**（各 13〜31MB）。ここで見るのは、こちらが書いた部分:
文字の一覧と設定の読み出し、CTC の復号、検出の後処理、取得先の決め方、登録の仕方。
モデルを通した結果は、末尾の統合試験が、モデルが手元にあるときだけ確かめる。
"""

from __future__ import annotations

import re

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from local_ocr.core import fetch
from local_ocr.engines import all_engines
from local_ocr.engines.ppocr import MODELS, PpocrEngine, PpocrFile, PpocrModel
from local_ocr.ppocr import config, detect, pixels, recognize
from local_ocr.ppocr.pipeline import crop_line, quad_box
from local_ocr.ui import i18n

# --- 登録と取得先 -------------------------------------------------------------

# 変換して自前の repo に置いたモデル（dictionary= の道）と、公式の ONNX（yml の道）の見本。
# 登録には入れず、試験の中だけで使う。
_REPO = "https://huggingface.co/example/converted-onnx"
_REV = "0123456789abcdef0123456789abcdef01234567"
_DET = PpocrFile(_REPO, _REV, "det.onnx", 1000)
LOCAL_A = PpocrModel(
    id="local-a",
    label="甲",
    label_en="A",
    hint="h",
    hint_en="h",
    detector=_DET,
    recognizer=PpocrFile(_REPO, _REV, "rec_a.onnx", 2000),
    dictionary=PpocrFile(_REPO, _REV, "rec_a.dict.json", 300),
)
LOCAL_B = PpocrModel(
    id="local-b",
    label="乙（ラテン文字）",
    label_en="B (Latin script)",
    hint="h",
    hint_en="h",
    detector=_DET,
    recognizer=PpocrFile(_REPO, _REV, "rec_b.onnx", 2000),
    dictionary=PpocrFile(_REPO, _REV, "rec_b.dict.json", 300),
)


def test_only_v6_small_is_registered():
    assert [m.id for m in MODELS] == ["ppocrv6-small"]
    assert "ppocrv6-small" in [e.id for e in all_engines()]


def test_all_engines_returns_fresh_instances():
    assert all_engines()[0] is not all_engines()[0]


def test_models_are_pinned_to_a_commit():
    """枝の名前で指していると、差し替えられた日に別のモデルが降ってくる。"""
    for m in [*MODELS, LOCAL_A, LOCAL_B]:
        for _, _, f in m.roles():
            assert re.fullmatch(r"[0-9a-f]{40}", f.rev), (m.id, f)
            assert f.url == f"{f.repo}/resolve/{f.rev}/{f.name}"


def test_same_file_name_from_different_repos_does_not_collide():
    """公式の repo はどれも inference.onnx。repo と番号で置き場所を分ける。"""
    dests: dict = {}
    for m in [*MODELS, LOCAL_A, LOCAL_B]:
        for _, _, f in m.roles():
            dests.setdefault(f.dest(), f.url)
            assert dests[f.dest()] == f.url, f.dest()
    v6 = MODELS[0]
    assert v6.detector.dest() != v6.recognizer.dest()


def test_the_v5_detector_is_shared():
    assert LOCAL_A.detector.dest() == LOCAL_B.detector.dest()
    assert LOCAL_A.recognizer.dest() != LOCAL_B.recognizer.dest()


def test_each_model_has_a_way_to_get_its_characters():
    for m in [*MODELS, LOCAL_A, LOCAL_B]:
        assert m.dictionary is not None or m.rec_config is not None, m.id


def test_note_shows_the_real_size_in_both_languages():
    for e in [*all_engines(), PpocrEngine(LOCAL_A)]:
        if not isinstance(e, PpocrEngine):
            continue
        size = fetch.human(fetch.total_bytes(e.assets))
        assert size in e.note and size in e.note_en
        assert e.available() == all(a.fetched() for a in e.assets)


def test_label_en_is_used_in_english_only(monkeypatch):
    monkeypatch.setattr(i18n.prefs, "get", lambda key, default=None: None)
    engine = PpocrEngine(LOCAL_B)
    monkeypatch.setattr(i18n, "current", lambda: "en")
    assert i18n.engine_label(engine) == "B (Latin script)"
    assert i18n.engine_note(engine) == engine.note_en
    monkeypatch.setattr(i18n, "current", lambda: "ja")
    assert i18n.engine_label(engine) == "乙（ラテン文字）"
    assert i18n.engine_note(engine) == engine.note


def test_existing_engines_keep_their_own_translation(monkeypatch):
    monkeypatch.setattr(i18n, "current", lambda: "en")
    ndl = next(e for e in all_engines() if e.id == "ndl-lite")
    assert i18n.engine_label(ndl) == "NDL OCR Lite (modern print)"


# --- inference.yml の読み出し -------------------------------------------------

YML = """\
Global:
  model_name: x
PostProcess:
  name: CTCLabelDecode
  character_dict:
  - '!'
  - '"'
  - $
  - ''''
  - \\
  - '#'
  - '''x'''
  - "\\u00e9\\\\\\"\\x41"
  - あ
  - 　
  - a b
  - 'it''s' # 注釈
  - ''
"""


def test_character_dict_reads_every_quoting_style():
    chars = config.character_dict(YML)
    assert chars == [
        "!",
        '"',
        "$",
        "'",
        "\\",
        "#",
        "'x'",
        'é\\"A',
        "あ",
        "　",
        "a b",
        "it's",
        "",
    ]


def test_character_dict_keeps_the_ideographic_space():
    """全角スペースは字。両端を削ると一覧の番号が 1 つずれて、全部が別の字になる。"""
    assert config.character_dict("PostProcess:\n  character_dict:\n  - 　\n  - 一\n") == [
        "　",
        "一",
    ]


def test_character_dict_stops_at_the_next_key():
    yml = "PostProcess:\n  character_dict:\n  - a\n  - b\n  use_space_char: true\nOther:\n  - z\n"
    assert config.character_dict(yml) == ["a", "b"]


@pytest.mark.parametrize("bad", ["no dict here", "character_dict:\n", "character_dict:\n  - [a]\n"])
def test_character_dict_refuses_what_it_cannot_read(bad):
    with pytest.raises(ValueError):
        config.character_dict(bad)


def test_params_default_to_v5_and_yml_overrides():
    assert config.params_from(None, None) == config.Params()
    det = "PostProcess:\n  box_thresh: 0.45\n  max_candidates: 3000\n  thresh: 0.2\n  unclip_ratio: 1.4\n"
    rec = "PreProcess:\n  transform_ops:\n  - RecResizeImg:\n      image_shape:\n      - 3\n      - 32\n      - 480\n"
    p = config.params_from(det, rec)
    assert (p.thresh, p.box_thresh, p.unclip_ratio, p.max_candidates) == (0.2, 0.45, 1.4, 3000)
    assert (p.rec_height, p.rec_min_width) == (32, 480)


def test_a_yml_without_the_items_keeps_the_defaults():
    assert config.params_from("PostProcess:\n  name: X\n", "Global:\n  a: 1\n") == config.Params()


# --- 読み取り -----------------------------------------------------------------


def test_ctc_decode_merges_repeats_and_drops_blanks():
    chars = ["a", "b"]  # 番号 1 = a、2 = b、3 = 最後 = 空白
    steps = [0, 1, 1, 0, 1, 2, 2, 3, 0]
    prob = np.zeros((len(steps), 4), np.float32)
    for t, k in enumerate(steps):
        prob[t, k] = 0.9
    text, score = recognize.decode_ctc(prob, chars)
    assert text == "aab "
    assert score == pytest.approx(0.9)


def test_ctc_decode_of_only_blanks_is_empty():
    prob = np.zeros((5, 4), np.float32)
    prob[:, 0] = 1
    assert recognize.decode_ctc(prob, ["a", "b"]) == ("", 0.0)


def test_rec_tensor_pads_on_the_right_to_the_minimum_width():
    img = np.full((24, 96, 3), 255, np.uint8)  # 縦横比 4 → 幅 192 に伸ばす。最小は 320
    t = recognize.rec_tensor(img)
    assert t.shape == (1, 3, 48, 320)
    assert t[0, :, :, :192].max() == pytest.approx(1.0)
    assert not t[0, :, :, 192:].any()


def test_rec_tensor_caps_the_width():
    t = recognize.rec_tensor(np.zeros((10, 5000, 3), np.uint8))
    assert t.shape[3] == recognize.REC_MAX_W


# --- 検出 ---------------------------------------------------------------------


def test_det_size_is_a_multiple_of_32():
    for w, h in [(1234, 2048), (100, 40), (5000, 300), (2048, 2048)]:
        dw, dh = detect.det_size(w, h)
        assert dw % 32 == 0 and dh % 32 == 0 and min(dw, dh) >= 32


def test_det_size_raises_a_thin_page_and_caps_a_huge_one():
    assert detect.det_size(1234, 2048) == (1248, 2048)
    # 短い辺が 64 未満なら 64 まで引き上げる（長い辺もその比で伸びる）
    assert detect.det_size(640, 32) == (1280, 64)
    # 長い辺が 4000 を超えるなら 4000 に収める
    assert max(detect.det_size(8000, 100)) <= 4000


def test_box_order_is_top_down_then_left_right_within_10px():
    def box(x, y):
        return ([(x, y), (x + 50, y), (x + 50, y + 20), (x, y + 20)], 1.0)

    out = detect.sort_boxes([box(200, 104), box(10, 108), box(10, 300), box(100, 100)])
    assert [b[0][0] for b in out] == [(10, 108), (100, 100), (200, 104), (10, 300)]


def _col(x, y, h=200, w=30):
    return ([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], 1.0)


def test_vertical_page_is_ordered_right_to_left_then_top_down():
    # 同じ列（x の差 10px 未満）は上から下。列は右から左。
    boxes = [_col(100, 0), _col(300, 220), _col(305, 0), _col(102, 220)]
    out = detect.order_boxes(boxes)
    assert [b[0][0] for b in out] == [(305, 0), (300, 220), (100, 0), (102, 220)]


def test_mostly_horizontal_page_keeps_the_official_order():
    wide = ([(200, 0), (400, 0), (400, 20), (200, 20)], 1.0)
    wide2 = ([(10, 40), (210, 40), (210, 60), (10, 60)], 1.0)
    tall = _col(500, 0)
    out = detect.order_boxes([wide2, wide, tall])  # 縦長は 1/3 だけ
    assert out == [wide, tall, wide2]  # 上から下、左から右（公式の順）


def _rotated_rect_points(cx, cy, w, h, deg):
    a = np.deg2rad(deg)
    u = np.array([np.cos(a), np.sin(a)])
    v = np.array([-np.sin(a), np.cos(a)])
    pts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            p = np.array([cx, cy]) + sx * u * w / 2 + sy * v * h / 2
            pts.append((float(p[0]), float(p[1])))
    return pts


@pytest.mark.parametrize("deg", [0, 17, 45])
def test_min_area_rect_finds_a_rotated_rectangle(deg):
    pts = _rotated_rect_points(100, 80, 60, 20, deg)
    cx, cy, w, h, _, _ = detect.min_area_rect(pts)
    assert (cx, cy) == pytest.approx((100, 80), abs=1e-6)
    assert sorted([w, h]) == pytest.approx([20, 60], abs=1e-6)


def test_min_area_rect_of_a_single_pixel_has_no_size():
    assert detect.min_area_rect([(5.0, 5.0), (5.0, 5.0)])[2:4] == (0.0, 0.0)


def test_rect_corners_start_at_the_top_left():
    corners = detect.rect_corners(
        detect.min_area_rect([(0.0, 0.0), (40.0, 0.0), (40.0, 10.0), (0.0, 10.0)])
    )
    assert corners == pytest.approx([(0, 0), (40, 0), (40, 10), (0, 10)])


def _brute_labels(mask):
    """素朴な幅優先（8 近傍）。速い版の答え合わせ用。"""
    h, w = mask.shape
    seen = np.zeros_like(mask, bool)
    out = []
    for y in range(h):
        for x in range(w):
            if not mask[y, x] or seen[y, x]:
                continue
            stack, comp = [(y, x)], set()
            seen[y, x] = True
            while stack:
                cy, cx = stack.pop()
                comp.add((cy, cx))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((ny, nx))
            out.append(comp)
    return out


@pytest.mark.parametrize("density", [0.3, 0.5, 0.6])
def test_components_match_a_plain_flood_fill(density):
    rng = np.random.default_rng(1)
    mask = rng.random((40, 60)) < density
    fast = detect.components(mask)
    slow = _brute_labels(mask)
    assert len(fast) == len(slow)
    # 走査の順（先頭の画素が上・左のものが先）も同じ
    fast_sets = [{(int(y), int(x)) for y, a, b in c for x in range(a, b + 1)} for c in fast]
    assert fast_sets == slow


def test_components_of_an_empty_mask():
    assert detect.components(np.zeros((10, 10), bool)) == []


def test_find_boxes_on_a_synthetic_map():
    prob = np.zeros((96, 320), np.float32)
    prob[20:40, 30:250] = 0.9  # 太い横の帯 = 1 行
    prob[60:62, 30:60] = 0.9  # 細すぎる（3 未満）ものは捨てる
    prob[70:90, 10:50] = 0.4  # 0.3 は超えるが、平均が 0.6 に届かない
    boxes = detect.find_boxes(prob, 640, 192)
    assert len(boxes) == 1
    quad, score = boxes[0]
    assert score == pytest.approx(0.9)
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    # 画像は地図の 2 倍。広げた分だけ、帯 (60..500 × 40..80) より外へ出る
    assert min(xs) < 60 and max(xs) > 500 and min(ys) < 40 and max(ys) > 80


def test_quad_box_reports_a_polygon_only_when_turned():
    flat = [(10, 10), (60, 10), (60, 30), (10, 30)]
    assert quad_box(flat) == ((10, 10, 50, 20), None)
    tilted = [(10, 12), (60, 10), (60, 30), (10, 32)]
    box, polygon = quad_box(tilted)
    assert box == (10, 10, 50, 22) and polygon == tilted


# --- 画素 ---------------------------------------------------------------------


def test_resize_matches_opencv_within_two_levels():
    cv2 = pytest.importorskip("cv2")
    rng = np.random.default_rng(0)
    for _ in range(20):
        h, w = (int(v) for v in rng.integers(8, 200, 2))
        out_w = int(rng.integers(8, 400))
        img = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
        ours = pixels.resize_linear_cv(img, out_w, 48)
        theirs = cv2.resize(img, (out_w, 48), interpolation=cv2.INTER_LINEAR)
        assert np.abs(ours.astype(int) - theirs).max() <= 2


def test_resize_to_the_same_size_is_a_no_op():
    img = np.arange(24, dtype=np.uint8).reshape(2, 4, 3)
    assert pixels.resize_linear_cv(img, 4, 2) is img


def test_bgr_tensor_swaps_channels():
    img = np.zeros((1, 1, 3), np.uint8)
    img[0, 0] = (10, 20, 30)  # RGB
    t = pixels.bgr_tensor(img, (0, 0, 0), (1, 1, 1))
    assert t[0, :, 0, 0].tolist() == [30, 20, 10]


def test_rotate_left_matches_pil():
    rng = np.random.default_rng(2)
    img = rng.integers(0, 256, (7, 11, 3), dtype=np.uint8)
    want = np.asarray(Image.fromarray(img).transpose(Image.Transpose.ROTATE_90))
    assert (pixels.rotate_left(img) == want).all()


def test_crop_line_straightens_and_turns_vertical_text_left():
    img = np.zeros((200, 200, 3), np.uint8)
    img[50:70, 40:140] = 255
    flat = crop_line(img, [(40, 50), (140, 50), (140, 70), (40, 70)])
    assert flat.shape[:2] == (20, 100) and flat.mean() > 240
    tall = crop_line(img, [(40, 50), (60, 50), (60, 150), (40, 150)])
    assert tall.shape[:2] == (20, 100)  # 縦長は左へ倒して横長にする
    assert crop_line(img, [(5, 5), (5, 5), (5, 5), (5, 5)]) is None


# --- モデルを通す（手元にあるときだけ） ---------------------------------------


def _text_image(lines: list[str]) -> Image.Image:
    font = ImageFont.load_default(size=40)
    img = Image.new("RGB", (900, 120 * len(lines)), "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((30, 30 + 120 * i), line, font=font, fill="black")
    return img


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.id)
def test_reads_a_rendered_page_when_the_model_is_at_hand(model):
    engine = PpocrEngine(model)
    if not engine.available():
        pytest.skip(
            f"{model.id} のモデルが手元に無い（アプリで取得するか LOCAL_OCR_DATA_DIR を指す）"
        )
    engine.prepare(lambda *_: None)
    try:
        result = engine.recognize(_text_image(["Origin of Species", "natural selection"]))
        assert [line.text for line in result.lines] == ["Origin of Species", "natural selection"]
        assert all(line.box and line.box[2] > 100 for line in result.lines)
        # 「行として読む」は、行の枠で切った画像を渡す使い方（枠の余白が広いと読めない）
        page = _text_image(["Origin of Species", "natural selection"])
        x, y, w, h = result.lines[1].box
        one = engine.recognize_line(page.crop((x, y, x + w, y + h)))
        assert one.text == "natural selection"
    finally:
        engine.shutdown()
