"""入口。渡されたものを「読む 1 ページ」の並びに開く。

画像 1 枚・フォルダ・IIIF マニフェストの URL を、同じ形 (`Item` の並び) にして返す。
**画面と端末で入口の書き方を分けない。** 分けると、フォルダの並び順や
マニフェストの読み方が 2 通りに割れて、出てくる TEI が食い違う。

版面(画像そのもの)は、ここでは開かない。何百ページもあるとき、全部を
一度に開くと机の上に載らないため。開くのは読む直前に `open_image` で 1 枚ずつ。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from . import iiif, ocr


@dataclass
class Item:
    """読む 1 ページ。中身はまだ開いていない。

    `path` は手元のファイル、`url` は取り寄せる先(IIIF)。どちらか一方が入る。
    """

    label: str
    path: Path | None = None
    url: str = ""


@dataclass
class Bundle:
    """ひとまとまりで開いたもの。題と、読むページの並び。

    `origin` は TEI の「出どころ」に書く文字。フォルダ名か、マニフェストの URL。
    **絶対の道は入れない**(利用者の名前がファイルに残る)。
    """

    title: str
    items: list[Item]
    origin: str = ""


def is_url(raw: str) -> bool:
    return raw.startswith(("http://", "https://"))


def expand(raw: str, lang: str = "") -> Bundle:
    """渡された 1 つを、読むページの並びに開く。

    - 画像のファイル → 1 ページ
    - フォルダ → 中の画像(**中のフォルダまでは潜らない**)
    - `http(s)://…` → IIIF マニフェストのカンバス

    見つからないときは `FileNotFoundError`。マニフェストが読めないときは
    `iiif.ManifestError`。どちらも呼ぶ側が文面を付ける。
    """
    if is_url(raw):
        return from_manifest(raw, lang)
    path = Path(raw).expanduser()
    if path.is_dir():
        name = path.name or str(path)
        return Bundle(
            title=name,
            items=[Item(label=p.name, path=p) for p in images_in(path)],
            origin=name,
        )
    if path.is_file():
        return Bundle(title=path.stem, items=[Item(label=path.name, path=path)], origin=path.name)
    raise FileNotFoundError(raw)


def images_in(folder: Path) -> list[Path]:
    """フォルダの中の画像。**人が見て自然な順に並べる。**

    ただの文字の順だと `10.jpg` が `2.jpg` より前に来る。連番の桁が
    揃っていない資料は珍しくないので、数字は数として見る。
    """
    return sorted(
        (
            child
            for child in folder.iterdir()
            if child.is_file() and child.suffix.lower().lstrip(".") in ocr.IMAGE_SUFFIXES
        ),
        key=lambda p: natural_key(p.name),
    )


def natural_key(name: str) -> list[object]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def from_manifest(url: str, lang: str = "") -> Bundle:
    manifest = iiif.load(url, lang=lang)
    return Bundle(
        title=manifest.label or url,
        items=[Item(label=c.label, url=c.image_url) for c in manifest.canvases],
        origin=url,
    )


def open_image(item: Item) -> Image.Image:
    """版面を 1 枚開く。取り寄せ(IIIF)もここを通る。**糸(スレッド)の中から呼ぶ。**"""
    if item.path is not None:
        return ocr.load(item.path)
    if item.url:
        return iiif.image(item.url)
    raise ValueError("版面がありません")
