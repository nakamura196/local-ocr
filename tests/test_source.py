"""入口。渡されたものが、どうページの並びになるか。"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from local_ocr.core import iiif, source


def _image(path: Path) -> Path:
    Image.new("RGB", (8, 8), "white").save(path)
    return path


def test_a_folder_opens_into_the_images_in_it(tmp_path: Path):
    _image(tmp_path / "b.png")
    _image(tmp_path / "a.png")
    (tmp_path / "notes.txt").write_text("画像ではない", encoding="utf-8")
    (tmp_path / "下位").mkdir()
    _image(tmp_path / "下位" / "c.png")

    bundle = source.expand(str(tmp_path))
    # 中のフォルダまでは潜らない。
    assert [item.label for item in bundle.items] == ["a.png", "b.png"]
    assert all(item.path is not None and item.url == "" for item in bundle.items)
    # 束の題と出どころはフォルダの名前。**絶対の道は持ち回らない。**
    assert bundle.title == tmp_path.name
    assert bundle.origin == tmp_path.name


def test_pages_come_out_in_the_order_a_person_would_expect(tmp_path: Path):
    """`10.jpg` が `2.jpg` より前に来ないこと(桁の揃っていない連番は珍しくない)。"""
    for name in ("2.jpg", "10.jpg", "1.jpg"):
        _image(tmp_path / name)
    assert [i.label for i in source.expand(str(tmp_path)).items] == ["1.jpg", "2.jpg", "10.jpg"]


def test_one_image_is_one_page(tmp_path: Path):
    path = _image(tmp_path / "a.png")
    assert [item.path for item in source.expand(str(path)).items] == [path]


def test_something_that_is_not_there(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        source.expand(str(tmp_path / "nope.png"))


def test_a_url_goes_to_the_manifest(monkeypatch):
    seen: list[tuple[str, str]] = []

    def fake_load(url: str, lang: str = "", **_kw) -> iiif.Manifest:
        seen.append((url, lang))
        return iiif.Manifest(
            label="題",
            canvases=[iiif.Canvas(label="1 オ", image_url="https://example.org/1.jpg")],
        )

    monkeypatch.setattr(iiif, "load", fake_load)
    bundle = source.expand("https://example.org/manifest.json", lang="ja")
    assert seen == [("https://example.org/manifest.json", "ja")]
    assert bundle.items == [source.Item(label="1 オ", url="https://example.org/1.jpg")]
    # 題はマニフェストのもの、出どころはその URL。
    assert bundle.title == "題"
    assert bundle.origin == "https://example.org/manifest.json"


def test_the_opened_image_comes_from_the_right_place(tmp_path: Path, monkeypatch):
    """手元のファイルはそのまま開き、取り寄せるページは IIIF 側に任せる。"""
    path = _image(tmp_path / "a.png")
    with source.open_image(source.Item("a.png", path=path)) as img:
        assert img.size == (8, 8)

    asked: list[str] = []
    monkeypatch.setattr(
        iiif, "image", lambda url, **_kw: asked.append(url) or Image.new("RGB", (4, 4))
    )
    assert source.open_image(source.Item("1", url="https://example.org/1.jpg")).size == (4, 4)
    assert asked == ["https://example.org/1.jpg"]
