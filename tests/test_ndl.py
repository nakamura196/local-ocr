"""NDL の 2 つ（ndl-lite / ndl-koten-lite）のうち、モデルが無くても見られるところ。

**モデルは CI に無い**（合わせて 230MB）。ここで見るのは、版面の組み立て・読み順・
取得先の決め方といった、こちらが書いた部分。モデルを通した結果が上流と合うことは、
`src/local_ocr/ndl/__init__.py` に書いたとおり手元で突き合わせて確かめてある。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from local_ocr.core import ndl_assets
from local_ocr.engines import all_engines
from local_ocr.ndl import classes, order
from local_ocr.ndl.detect import Detection
from local_ocr.ndl.layout import build_page
from local_ocr.ndl.recognize import load_charset

DATA = Path(__file__).parent / "data"


# --- 取得するもの -------------------------------------------------------------

def test_models_are_pinned_to_a_commit():
    """枝の名前で指していると、上流が差し替えた日に別のモデルが降ってくる。"""
    for asset in ndl_assets.koten() + ndl_assets.lite():
        commit = asset.url.split("/")[5]
        assert re.fullmatch(r"[0-9a-f]{40}", commit), asset.url
        assert asset.url.startswith("https://raw.githubusercontent.com/ndl-lab/")


def test_each_model_has_its_own_place():
    assets = ndl_assets.koten() + ndl_assets.lite()
    assert len({a.key for a in assets}) == len(assets)
    assert len({a.dest for a in assets}) == len(assets)


def test_paths_match_what_the_pipelines_ask_for():
    assert set(ndl_assets.paths(ndl_assets.koten())) == {"detector", "recognizer"}
    assert set(ndl_assets.paths(ndl_assets.lite())) == {
        "detector", "short", "medium", "long"
    }


def test_both_engines_are_on_the_list():
    engines = {e.id: e for e in all_engines()}
    assert {"ndl-lite", "ndl-koten-lite"} <= set(engines)
    for engine in (engines["ndl-lite"], engines["ndl-koten-lite"]):
        # 取得するものがあり、無いうちは使えない、と答えること。
        assert engine.assets
        assert engine.available() == all(a.fetched() for a in engine.assets)


# --- 文字の一覧 ---------------------------------------------------------------

@pytest.mark.parametrize("name", ["koten", "lite"])
def test_charset_matches_the_models(name: str):
    """モデルの出口は 7142 通り。0 が行の終わりなので、文字は 7141 個。"""
    charset = load_charset(name)
    assert len(charset) == 7141
    # **先頭は半角スペース。** 両端を削る書き方を入れると、以後 1 字ずつずれる。
    assert charset[0] == " "
    assert "\n" not in charset


def test_the_two_charsets_are_not_interchangeable():
    assert load_charset("koten") != load_charset("lite")


# --- 種類の一覧 ---------------------------------------------------------------

def test_taxonomies_differ_where_they_should():
    assert len(classes.KOTEN.names) == 16
    assert len(classes.LITE.names) == 17
    # 4 番の日本語名が違う。取り違えると、割注が注として出る。
    assert classes.KOTEN.org_name(4) == "注"
    assert classes.LITE.org_name(4) == "割注"
    # 古典籍には表組の種類が無い。
    assert classes.KOTEN.index("block_table") == -1
    assert classes.LITE.index("block_table") == 15


# --- 版面の組み立て -----------------------------------------------------------

def _line(taxonomy, name, box, conf=0.9, count=2.0):
    return Detection(taxonomy.index(name), conf, box, count)


def test_lines_go_inside_the_text_block_that_holds_them():
    t = classes.LITE
    page = build_page(
        1000, 1000, "x", t,
        [
            _line(t, "text_block", (100, 100, 400, 900)),
            _line(t, "line_main", (110, 120, 150, 880)),
            _line(t, "line_main", (160, 120, 200, 880)),
            _line(t, "line_main", (700, 120, 740, 880)),  # ブロックの外
        ],
        score_thr=0.1, use_block_ad=True,
    )
    block = page.find("TEXTBLOCK")
    assert block is not None
    assert len(block.findall("LINE")) == 2
    # ブロックに入らなかった行は、ページ直下に置かれる。
    assert len(page.findall("LINE")) == 1


def test_blocks_other_than_lines_are_kept_as_blocks():
    t = classes.LITE
    page = build_page(
        1000, 1000, "x", t,
        [_line(t, "block_fig", (10, 10, 90, 90)), _line(t, "line_main", (200, 10, 240, 900))],
        score_thr=0.1, use_block_ad=True,
    )
    assert [b.get("TYPE") for b in page.findall("BLOCK")] == ["図版"]
    assert len(page.findall(".//LINE")) == 1


def test_low_confidence_lines_are_dropped():
    t = classes.KOTEN
    page = build_page(
        1000, 1000, "x", t,
        [_line(t, "line_main", (10, 10, 50, 900), conf=0.2)],
        score_thr=0.3, use_block_ad=False,
    )
    assert page.findall(".//LINE") == []


# --- 読み順 -------------------------------------------------------------------

def _page_with(boxes, conf=0.9):
    page = ET.Element("PAGE", {"WIDTH": "1000", "HEIGHT": "1000"})
    for x, y, w, h in boxes:
        ET.SubElement(page, "LINE", {
            "TYPE": "本文", "X": str(x), "Y": str(y), "WIDTH": str(w), "HEIGHT": str(h),
            "CONF": f"{conf:0.3f}",
        })
    return page


def test_vertical_text_reads_right_to_left():
    page = _page_with([(100, 50, 40, 800), (200, 50, 40, 800), (300, 50, 40, 800)])
    order.apply(page, smoothing=False)
    assert [e.get("X") for e in page.findall("LINE")] == ["300", "200", "100"]


def test_horizontal_text_reads_top_to_bottom():
    page = _page_with([(50, 300, 800, 40), (50, 100, 800, 40), (50, 200, 800, 40)])
    order.apply(page, smoothing=False)
    assert [e.get("Y") for e in page.findall("LINE")] == ["100", "200", "300"]


def test_a_line_found_twice_is_kept_once():
    """同じ行が二重に見つかることがある。確からしさの高い方を残す。"""
    page = ET.Element("PAGE", {"WIDTH": "1000", "HEIGHT": "1000"})
    for x, y, w, h, conf in [(100, 50, 40, 800, 0.4), (101, 52, 39, 796, 0.9)]:
        ET.SubElement(page, "LINE", {
            "TYPE": "本文", "X": str(x), "Y": str(y), "WIDTH": str(w), "HEIGHT": str(h),
            "CONF": f"{conf:0.3f}",
        })
    order.apply(page, smoothing=False)
    kept = page.findall("LINE")
    assert len(kept) == 1
    assert kept[0].get("CONF") == "0.900"


def test_an_empty_page_does_not_fall_over():
    page = _page_with([])
    order.apply(page, smoothing=True)
    assert page.findall("LINE") == []


def test_one_line_does_not_fall_over():
    page = _page_with([(100, 50, 40, 800)])
    order.apply(page, smoothing=True)
    assert len(page.findall("LINE")) == 1


def test_a_real_page_keeps_its_reading_order():
    """上流の試し画像（表のあるページ）の版面を、そのまま並べ直してみる。

    入力は上流が組み立てたものをそのまま置いてある。期待する並びはこちらの出力。
    **読み順に手を入れたら、ここが必ず動く。** 動いたときは、直したのか
    壊したのかを、版面を見て確かめてから期待値を更新する。
    """
    page = ET.parse(DATA / "ndl_lite_layout.xml").getroot()
    order.apply(page, smoothing=True)
    got = [
        f"{e.get('X')},{e.get('Y')},{e.get('WIDTH')},{e.get('HEIGHT')}"
        for e in page.findall(".//LINE")
    ]
    want = (DATA / "ndl_lite_order.txt").read_text(encoding="utf-8").split()
    assert got == want
