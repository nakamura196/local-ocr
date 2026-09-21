"""端末から使う口。画面を開かずに確かめられる(flet を取り込まない作りなので)。"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from PIL import Image

from local_ocr import cli
from local_ocr.engines import Line, Result

NS = {"t": "http://www.tei-c.org/ns/1.0"}


class FakeEngine:
    """読む中身は問わない。渡し方と出し方だけを見る。"""

    id = "fake"
    label = "Fake"
    note = ""
    platforms = frozenset({sys.platform})
    assets: list = []

    def __init__(self) -> None:
        self.prepared = 0
        self.stopped = 0

    def available(self) -> bool:
        return True

    def prepare(self, on_progress) -> None:
        self.prepared += 1

    def recognize(self, img: Image.Image) -> Result:
        return Result(text="あ\nい", lines=[Line("あ", (0, 0, 4, 4)), Line("い", (0, 4, 4, 4))])

    def shutdown(self) -> None:
        self.stopped += 1


@pytest.fixture
def engine(monkeypatch) -> FakeEngine:
    fake = FakeEngine()
    monkeypatch.setattr(cli, "all_engines", lambda: [fake])
    return fake


def _image(path: Path) -> Path:
    Image.new("RGB", (8, 8), "white").save(path)
    return path


def test_reads_one_image_to_standard_output(engine, tmp_path: Path, capsys):
    assert cli.main([str(_image(tmp_path / "a.png")), "-q"]) == 0
    assert capsys.readouterr().out == "あ\nい\n"
    # 常駐するものを持つ道具のために、必ず後始末する。
    assert engine.stopped == 1


def test_a_folder_becomes_every_image_in_it(engine, tmp_path: Path, capsys):
    _image(tmp_path / "b.png")
    _image(tmp_path / "a.png")
    (tmp_path / "notes.txt").write_text("画像ではない", encoding="utf-8")
    assert cli.main([str(tmp_path), "-q", "--format", "tei", "--out", str(tmp_path / "o.xml")]) == 0
    root = ET.parse(tmp_path / "o.xml").getroot()
    # 名前の順に 1 ページずつ。
    assert [g.get("url") for g in root.findall(".//t:graphic", NS)] == ["a.png", "b.png"]
    assert len(root.findall("./t:text/t:body/t:p/t:pb", NS)) == 2


def test_tei_keeps_the_boxes_the_engine_returned(engine, tmp_path: Path):
    out = tmp_path / "o.xml"
    assert (
        cli.main([str(_image(tmp_path / "a.png")), "-q", "--format", "tei", "--out", str(out)]) == 0
    )
    root = ET.parse(out).getroot()
    assert len(root.findall(".//t:zone", NS)) == 2
    assert root.find("./t:text/t:body/t:p/t:lb", NS).get("corresp") == "#f1_l1"


def test_an_unknown_engine_stops_before_reading(engine, tmp_path: Path, capsys):
    assert cli.main([str(_image(tmp_path / "a.png")), "--engine", "nope"]) == 1
    assert engine.prepared == 0


def test_nothing_to_read_is_an_error(engine, capsys):
    assert cli.main(["-q"]) == 1


def test_list_engines_does_not_start_anything(engine, capsys):
    assert cli.main(["--list-engines"]) == 0
    assert "fake" in capsys.readouterr().out
    assert engine.prepared == 0


# --- IIIF マニフェスト ----------------------------------------------------


@pytest.fixture
def manifest(monkeypatch):
    """取り寄せには行かせない。渡し方と、TEI がどこを指すかだけを見る。"""
    from local_ocr.core import iiif

    fetched: list[str] = []

    def fake_load(url: str, lang: str = "", **_kw):
        return iiif.Manifest(
            label="酉蓮社本",
            canvases=[
                iiif.Canvas(label="1 オ", image_url="https://example.org/iiif/1/full/800,/0/default.jpg"),
                iiif.Canvas(label="1 ウ", image_url="https://example.org/iiif/2/full/800,/0/default.jpg"),
            ],
        )

    def fake_image(url: str, **_kw):
        fetched.append(url)
        return Image.new("RGB", (8, 8), "white")

    monkeypatch.setattr(iiif, "load", fake_load)
    monkeypatch.setattr(iiif, "image", fake_image)
    return fetched


def test_a_manifest_url_becomes_every_canvas(engine, manifest, tmp_path: Path):
    out = tmp_path / "o.xml"
    assert (
        cli.main(
            ["https://example.org/manifest.json", "-q", "--format", "tei", "--out", str(out)]
        )
        == 0
    )
    root = ET.parse(out).getroot()
    # **TEI は IIIF の URL をそのまま指す。** どのパソコンでも開ける道になる。
    assert [g.get("url") for g in root.findall(".//t:graphic", NS)] == [
        "https://example.org/iiif/1/full/800,/0/default.jpg",
        "https://example.org/iiif/2/full/800,/0/default.jpg",
    ]
    assert len(root.findall("./t:text/t:body/t:p/t:pb", NS)) == 2
    # 取り寄せるのは、読むページのぶんだけ。
    assert len(manifest) == 2


def test_a_manifest_that_cannot_be_read_stops_before_the_engine(engine, monkeypatch, capsys):
    from local_ocr.core import iiif

    def fake_load(url: str, lang: str = "", **_kw):
        raise iiif.ManifestError("iiif.error.collection")

    monkeypatch.setattr(iiif, "load", fake_load)
    from local_ocr.ui.i18n import t

    assert cli.main(["https://example.org/collection.json", "-q"]) == 1
    assert engine.prepared == 0
    # 鍵のまま出さず、意味の分かる文面にして出す。
    assert t("iiif.error.collection") in capsys.readouterr().err
