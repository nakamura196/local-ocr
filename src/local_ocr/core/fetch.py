"""取得と削除。エンジンを問わず、Asset 1 件をどう落として、どう消すか。

**エンジンごとに書かない。** 設定画面はここだけを呼ぶので、エンジンを足しても
取得まわりの画面は直さずに済む。
"""

from __future__ import annotations

import urllib.request
from collections.abc import Callable, Iterable
from pathlib import Path

from .assets import Asset

# (今なにをしているか, 0..1 または None)
Progress = Callable[[str, float | None], None]


def human(n: int) -> str:
    """1.8GB のような、人が読める大きさ。

    **1000 で割る (Finder と同じ)。** 1024 で割っていたころは、同じモデルが
    画面の札では「1.7GB」、説明文では「1.8GB」と食い違っていた。
    """
    if n >= 1000**3:
        return f"{n / 1000**3:.1f}GB"
    if n >= 1000**2:
        return f"{round(n / 1000**2)}MB"
    return f"{max(1, round(n / 1000))}KB"


def total_bytes(assets: Iterable[Asset]) -> int:
    return sum(a.approx_bytes for a in assets)


def download(asset: Asset, on_progress: Progress) -> None:
    """1 件取得する。

    取得するのはモデル (.onnx / .gguf) だけで、どれも 1 ファイルそのまま。
    **書庫を展開する道は持たない。** 唯一の使い手だった llama.cpp が同梱に
    変わったので落とした (core/bundled.py)。必要になったら戻す。
    """
    _download(asset.url, asset.dest, asset.approx_bytes, on_progress, asset.label)


def download_all(assets: Iterable[Asset], on_progress: Progress) -> None:
    for a in assets:
        if not a.fetched():
            download(a, on_progress)


def to_file(
    url: str,
    dest: Path,
    on_progress: Progress | None = None,
    label: str = "",
    timeout: float | None = None,
) -> None:
    """URL を 1 つのファイルに落とすだけ(展開もしない)。IIIF の版面がこれを使う。

    **取得の書き方を 2 か所に書かない。** 途中で落ちたときに部分ファイルを
    残さない作法も、ここを通せば同じになる。
    """
    _download(url, dest, 0, on_progress or _quiet, label, timeout)


def _quiet(_label: str, _ratio: float | None) -> None:
    pass


def remove(asset: Asset) -> None:
    """取得したものを消す。取り直せるので、確認は呼ぶ側の責任。"""
    asset.dest.unlink(missing_ok=True)
    asset.dest.with_suffix(asset.dest.suffix + ".part").unlink(missing_ok=True)


def _download(
    url: str,
    dest: Path,
    approx: int,
    on_progress: Progress,
    label: str,
    timeout: float | None = None,
) -> None:
    """途中で落ちても部分ファイルを残さないよう、.part に書いてから差し替える。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "Local-OCR"})
    with urllib.request.urlopen(req, timeout=timeout) as res, open(part, "wb") as f:
        total = int(res.headers.get("Content-Length") or 0) or approx
        got = 0
        while chunk := res.read(1024 * 256):
            f.write(chunk)
            got += len(chunk)
            on_progress(label, min(got / total, 1.0) if total else None)
    part.replace(dest)
