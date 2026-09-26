"""読む芯(`core/reading.py`)。範囲・読み方・並べ替え・崩れの点検。

見たいのは 5 つ。
- 範囲で切って読んだ枠が、元の画像の座標に戻る(細長い範囲に足した余白の分も)
- 読み方は道具ごと。PaddleOCR-VL の "lines" は位置付き + 位置なしの 2 回読み、NDL の "line" は 1 行読み
- 割注(1 列に細い行が 2 本)は右の行 → 左の行。Spotting はここを逆に返す
- 途中でやめた読み・同じ字の繰り返しを見つける。位置の付かない行は捨てない
- 範囲の読み直しを、前の読みの同じ場所に差し込む
"""

from __future__ import annotations

import pytest
from PIL import Image

from local_ocr.core import ocr, reading
from local_ocr.core.reading import Region
from local_ocr.engines.base import Line, Result


def _line(text: str, x: int, y: int, w: int, h: int) -> Line:
    return Line(text=text, box=(x, y, w, h), polygon=[(x, y), (x + w, y), (x + w, y + h), (x, y + h)])


class _Paddle:
    id = "paddle-vl"
    modes = ("text", "lines")

    def __init__(self, spotted: list[Line], plain: str) -> None:
        self.spotted = spotted
        self.plain = plain
        self.sizes: list[tuple[int, int]] = []

    def recognize(self, img: Image.Image) -> Result:
        self.sizes.append(img.size)
        return Result(text=self.plain)

    def recognize_lines(self, img: Image.Image) -> Result:
        self.sizes.append(img.size)
        return Result(text="\n".join(ln.text for ln in self.spotted), lines=list(self.spotted))


class _Ndl:
    id = "ndl-koten-lite"
    modes = ("layout", "line")

    def recognize(self, img: Image.Image) -> Result:
        return Result(text="版面", lines=[_line("版面", 1, 1, 5, 5)])

    def recognize_line(self, img: Image.Image) -> Result:
        return Result(text="一行", lines=[Line(text="一行", box=(0, 0, *img.size))])


# --- 範囲 -----------------------------------------------------------------
def test_region_is_parsed_and_clipped():
    assert Region.parse({"x": 10, "y": 20, "w": 30, "h": 40}) == Region(10, 20, 30, 40)
    assert Region.parse("10,20,30.4,40") == Region(10, 20, 30, 40)
    assert Region.parse(None) is None
    with pytest.raises(ValueError):
        Region.parse({"x": 1})
    assert Region(-5, -5, 20, 20).clip(100, 100) == Region(0, 0, 15, 15)
    assert Region(200, 0, 10, 10).clip(100, 100) is None


def test_a_thin_region_gets_paper_margins_and_boxes_come_back():
    """縦 6:横 1 の範囲には左右に余白が付く。読んだ枠は元の画像の座標に戻る。"""
    img = Image.new("RGB", (1000, 1000), (230, 220, 200))
    c = reading.cut(img, Region(500, 100, 100, 600))
    assert c.image.size == (240, 600)  # 横 ≥ 縦 × 0.4
    assert c.image.getpixel((0, 300)) == (230, 220, 200)  # 余白は紙の色
    # 切り出しの (70, 0)〜(170, 600) は、元の (500, 100)〜(600, 700)
    assert c.back(70, 0) == (500, 100)
    assert c.back(170, 600) == (600, 700)
    # 余白に掛かった分は範囲の縁に寄せる
    assert c.back(0, 0) == (500, 100)


def test_a_region_is_read_and_placed_back_on_the_page():
    img = Image.new("RGB", (1000, 1000), "white")
    spotted = [_line("甲乙", 10, 20, 50, 200)]
    engine = _Paddle(spotted, plain="甲乙")
    result = reading.read(engine, img, region=Region(300, 400, 300, 300), mode="lines")
    assert engine.sizes == [(300, 300), (300, 300)]  # 位置付きと位置なしで 2 回
    assert result.lines[0].box == (310, 420, 50, 200)
    assert result.lines[0].polygon[0] == (310, 420)


def test_modes_belong_to_each_engine():
    img = Image.new("RGB", (400, 100), "white")
    engine = _Paddle([_line("甲", 0, 0, 10, 10)], plain="甲")
    assert reading.read(engine, img).lines == []  # 既定は「文字だけ」
    assert reading.mode_for(engine, None) == "text"
    with pytest.raises(ValueError):
        reading.mode_for(engine, "line")
    ndl = _Ndl()
    assert reading.read(ndl, img).text == "版面"
    one = reading.read(ndl, img, mode="line", region=Region(100, 0, 200, 100))
    # 1 行読みには余白を足さない(行の画像が縮んで字が潰れる)
    assert one.lines[0].box == (100, 0, 200, 100)


# --- 並べ替え ---------------------------------------------------------------
def test_warichu_is_read_right_then_left():
    """右の列: 大字「經」の下に割注 2 行。Spotting は上端がそろう割注を左から返す。"""
    W = 100
    spotted = [
        _line("經", 800, 0, W, W),
        _line("左の割注", 800, 110, 45, 400),  # 左が先に来ている
        _line("右の割注", 855, 110, 45, 400),
        _line("文", 800, 520, W, W),
        _line("次の列", 600, 0, W, 900),
    ]
    got = [ln.text for ln in reading.order_by_position(spotted)]
    assert got == ["經", "右の割注", "左の割注", "文", "次の列"]


def test_lines_without_a_position_are_kept_after_their_neighbour():
    spotted = [
        _line("左の列", 100, 0, 100, 900),
        Line(text="位置なし"),
        _line("右の列", 600, 0, 100, 900),
    ]
    got = [ln.text for ln in reading.order_by_position(spotted)]
    assert got == ["右の列", "左の列", "位置なし"]


# --- 崩れの点検 -------------------------------------------------------------
def test_a_reading_that_stopped_early_is_flagged():
    img = Image.new("RGB", (400, 400), "white")
    spotted = [_line("一二三", 300, 0, 50, 300)]
    engine = _Paddle(spotted, plain="一二三\n四五六七八九\n十百千萬億兆\n京垓")
    result = reading.read(engine, img, mode="lines")
    assert result.check.problems == ["stopped_early"]
    assert (result.check.placed, result.check.plain_lines) == (1, 4)
    assert result.plain.startswith("一二三")


def test_repeated_characters_are_flagged():
    assert "repeat" in reading.find_problems([Line("佛" * 12)], "佛")
    assert "repeat" in reading.find_problems([Line("南無")] * 5, "南無" * 5)
    assert reading.find_problems([Line("如是我聞")], "如是我聞") == []


def test_a_runaway_falls_back_to_the_plain_reading():
    img = Image.new("RGB", (400, 400), "white")
    engine = _Paddle([], plain="甲\n乙")

    def runaway(_img):
        raise ocr.Runaway("20 lines without a position")

    engine.recognize_lines = runaway
    result = reading.read(engine, img, mode="lines")
    assert [ln.text for ln in result.lines] == ["甲", "乙"]
    assert all(ln.box is None for ln in result.lines)
    assert result.check.problems == ["runaway"]
    with pytest.raises(ocr.Runaway):
        reading.read(engine, img, mode="lines", check=False)


# --- 範囲の読み直しを差し込む ---------------------------------------------------
def test_merge_replaces_the_lines_inside_the_region():
    old = [_line("一", 800, 0, 100, 900), _line("二", 600, 0, 100, 900), Line("位置なし"), _line("三", 400, 0, 100, 900)]
    new = [_line("二a", 600, 0, 50, 400), _line("二b", 650, 0, 50, 400)]
    got = reading.merge(old, new, Region(580, 0, 140, 1000))
    assert [ln.text for ln in got] == ["一", "二a", "二b", "位置なし", "三"]
    assert [ln.text for ln in reading.merge(old[:1], new, Region(0, 0, 10, 10))] == ["一", "二a", "二b"]
