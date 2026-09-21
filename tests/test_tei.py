"""TEI/XML の形を確かめる。

形が tei-scanner とずれると、TEI/IIIF エディタが開けなくなる。ここで見るのは
「同じ形になっているか」と「開ける XML になっているか」の 2 つ。
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from local_ocr.core import export, tei
from local_ocr.engines import Line

NS = {"t": "http://www.tei-c.org/ns/1.0"}


def _page(lines, width=800, height=600, url="page.jpg") -> tei.Page:
    return tei.Page(lines=lines, width=width, height=height, image_url=url)


def _parse(xml: str) -> ET.Element:
    return ET.fromstring(xml)


def test_one_page_is_a_surface_with_a_graphic_and_a_zone_per_line():
    xml = tei.build(
        [_page([Line("一行目", (10, 20, 30, 40)), Line("二行目", (50, 60, 70, 80))])],
        tei.Meta(title="見本", engine="Apple Vision"),
    )
    root = _parse(xml)
    surfaces = root.findall("./t:facsimile/t:surface", NS)
    assert len(surfaces) == 1
    surface = surfaces[0]
    assert surface.get("{http://www.w3.org/XML/1998/namespace}id") == "f1"
    assert (surface.get("lrx"), surface.get("lry")) == ("800", "600")

    graphic = surface.find("t:graphic", NS)
    assert graphic.get("url") == "page.jpg"
    assert (graphic.get("width"), graphic.get("height")) == ("800px", "600px")

    zones = surface.findall("t:zone", NS)
    assert [z.get("{http://www.w3.org/XML/1998/namespace}id") for z in zones] == ["f1_l1", "f1_l2"]
    # (x, y, w, h) が四隅になっている。
    assert [zones[0].get(k) for k in ("ulx", "uly", "lrx", "lry")] == ["10", "20", "40", "60"]


def test_lines_are_lb_milestones_pointing_at_their_zone():
    xml = tei.build([_page([Line("あ", (0, 0, 10, 10)), Line("い", (0, 10, 10, 10))])], tei.Meta())
    root = _parse(xml)
    p = root.find("./t:text/t:body/t:p", NS)
    pb = p.find("t:pb", NS)
    assert (pb.get("n"), pb.get("facs")) == ("1", "#f1")

    lbs = p.findall("t:lb", NS)
    assert [lb.get("corresp") for lb in lbs] == ["#f1_l1", "#f1_l2"]
    assert [lb.get("n") for lb in lbs] == ["1", "2"]
    assert [lb.get("type") for lb in lbs] == ["line", "line"]
    # 行の文字は <lb/> の直後に置く。
    assert [lb.tail.strip() for lb in lbs] == ["あ", "い"]


def test_zones_are_omitted_when_the_engine_returns_no_boxes():
    """PaddleOCR-VL の版面読みのように、枠を返さない道具のとき。"""
    xml = tei.build([_page([Line("あ"), Line("い")])], tei.Meta())
    root = _parse(xml)
    assert root.findall("./t:facsimile/t:surface/t:zone", NS) == []
    # 版面そのもの(surface と graphic)は残す。
    assert root.find("./t:facsimile/t:surface/t:graphic", NS) is not None
    lbs = root.findall("./t:text/t:body/t:p/t:lb", NS)
    assert [lb.get("corresp") for lb in lbs] == [None, None]
    assert [lb.tail.strip() for lb in lbs] == ["あ", "い"]


def test_zone_ids_follow_the_line_number_even_when_some_lines_have_no_box():
    xml = tei.build([_page([Line("あ"), Line("い", (1, 2, 3, 4))])], tei.Meta())
    root = _parse(xml)
    zones = root.findall("./t:facsimile/t:surface/t:zone", NS)
    # 2 行目の枠なので f1_l2。詰めて f1_l1 にしない。
    assert [z.get("{http://www.w3.org/XML/1998/namespace}id") for z in zones] == ["f1_l2"]
    assert [lb.get("corresp") for lb in root.findall("./t:text/t:body/t:p/t:lb", NS)] == [
        None,
        "#f1_l2",
    ]


def test_boxes_are_clamped_to_the_page():
    """Vision の枠は割合からの丸めなので、1px はみ出ることがある。"""
    xml = tei.build([_page([Line("あ", (-5, -5, 2000, 2000))], width=100, height=80)], tei.Meta())
    zone = _parse(xml).find("./t:facsimile/t:surface/t:zone", NS)
    assert [zone.get(k) for k in ("ulx", "uly", "lrx", "lry")] == ["0", "0", "100", "80"]


def test_several_pages_get_their_own_surface():
    xml = tei.build([_page([Line("あ")]), _page([Line("い")])], tei.Meta())
    root = _parse(xml)
    ids = [
        s.get("{http://www.w3.org/XML/1998/namespace}id")
        for s in root.findall("./t:facsimile/t:surface", NS)
    ]
    assert ids == ["f1", "f2"]
    assert [pb.get("facs") for pb in root.findall("./t:text/t:body/t:p/t:pb", NS)] == ["#f1", "#f2"]


def test_markup_in_the_text_does_not_break_the_file():
    xml = tei.build([_page([Line('<b>a & b</b> "c"')], url='a&b".jpg')], tei.Meta(title="A & B"))
    root = _parse(xml)  # そもそも開けること
    assert root.find("./t:text/t:body/t:p/t:lb", NS).tail.strip() == '<b>a & b</b> "c"'
    assert root.find("./t:facsimile/t:surface/t:graphic", NS).get("url") == 'a&b".jpg'
    assert root.find(".//t:titleStmt/t:title", NS).text == "A & B"


def test_control_characters_are_dropped():
    """書けても開けない XML を作らない。"""
    xml = tei.build([_page([Line("あ\x0bい")])], tei.Meta())
    assert _parse(xml).find("./t:text/t:body/t:p/t:lb", NS).tail.strip() == "あい"


def test_header_names_the_engine():
    xml = tei.build([_page([Line("あ")])], tei.Meta(engine="PaddleOCR-VL", source="117_10.jpg"))
    root = _parse(xml)
    assert root.find(".//t:respStmt/t:name", NS).text == "PaddleOCR-VL"
    assert any("117_10.jpg" in (p.text or "") for p in root.findall(".//t:sourceDesc/t:p", NS))


# --- 書き出し -------------------------------------------------------------


def test_graphic_url_is_relative_to_the_tei(tmp_path: Path):
    """絶対の道を書くと、そのパソコンでしか開けない TEI になる。"""
    (tmp_path / "images").mkdir()
    image = tmp_path / "images" / "f1.jpg"
    image.touch()
    assert export.graphic_url(tmp_path / "out.xml", image) == "images/f1.jpg"
    assert export.graphic_url(tmp_path / "images" / "out.xml", image) == "f1.jpg"


def test_graphic_url_gives_up_when_the_image_is_far_away(tmp_path: Path):
    """`../../../../..` と書いても、人に渡した先では開けない。"""
    deep = tmp_path / "a" / "b" / "c" / "d"
    deep.mkdir(parents=True)
    far = tmp_path / "far.jpg"
    far.touch()
    assert export.graphic_url(deep / "out.xml", far) is None


def test_image_beside_copies_the_original_instead_of_re_encoding(tmp_path: Path):
    from PIL import Image

    source = tmp_path / "src" / "page.jpg"
    source.parent.mkdir()
    Image.new("RGB", (8, 8), "white").save(source, format="JPEG")
    with Image.open(source) as opened:
        out = export.image_beside(tmp_path / "out.xml", opened, source)
    assert out.name == "out.jpg"
    assert out.read_bytes() == source.read_bytes()


def test_image_beside_writes_a_png_when_there_is_no_original(tmp_path: Path):
    from PIL import Image

    out = export.image_beside(tmp_path / "out.xml", Image.new("RGB", (8, 8), "white"))
    assert out.name == "out.png"
    with Image.open(out) as written:
        assert written.size == (8, 8)


def test_writing_leaves_no_half_written_file(tmp_path: Path):
    dest = tmp_path / "out.txt"
    export.write_text(dest, "あ\nい")
    assert dest.read_text("utf-8") == "あ\nい\n"
    assert list(tmp_path.glob("*.part")) == []
