"""取得と削除。エンジンを問わず、Asset 1 件をどう落として、どう消すか。

**エンジンごとに書かない。** 設定画面はここだけを呼ぶので、エンジンを足しても
取得まわりの画面は直さずに済む。
"""

from __future__ import annotations

import shutil
import subprocess
import tarfile
import urllib.request
import zipfile
from collections.abc import Callable, Iterable
from pathlib import Path

from .assets import Asset
from .paths import is_windows

# (今なにをしているか, 0..1 または None)
Progress = Callable[[str, float | None], None]


def human(n: int) -> str:
    """1.8GB のような、人が読める大きさ。"""
    if n >= 1024**3:
        return f"{n / 1024**3:.1f}GB"
    if n >= 1024**2:
        return f"{round(n / 1024**2)}MB"
    return f"{max(1, round(n / 1024))}KB"


def total_bytes(assets: Iterable[Asset]) -> int:
    return sum(a.approx_bytes for a in assets)


def download(asset: Asset, on_progress: Progress) -> None:
    """1 件取得する。書庫なら展開まで済ませる。"""
    _download(asset.url, asset.dest, asset.approx_bytes, on_progress, asset.label)
    if asset.extract_to is not None:
        on_progress(f"{asset.label}を展開しています", None)
        _extract(asset.dest, asset.extract_to, asset.marker.name)


def download_all(assets: Iterable[Asset], on_progress: Progress) -> None:
    for a in assets:
        if not a.fetched():
            download(a, on_progress)


def remove(asset: Asset) -> None:
    """取得したものを消す。取り直せるので、確認は呼ぶ側の責任。"""
    asset.dest.unlink(missing_ok=True)
    part = asset.dest.with_suffix(asset.dest.suffix + ".part")
    part.unlink(missing_ok=True)
    if asset.extract_to is not None and asset.extract_to.is_dir():
        shutil.rmtree(asset.extract_to, ignore_errors=True)


def _download(url: str, dest: Path, approx: int, on_progress: Progress, label: str) -> None:
    """途中で落ちても部分ファイルを残さないよう、.part に書いてから差し替える。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "Local-OCR"})
    with urllib.request.urlopen(req) as res, open(part, "wb") as f:
        total = int(res.headers.get("Content-Length") or 0) or approx
        got = 0
        while chunk := res.read(1024 * 256):
            f.write(chunk)
            got += len(chunk)
            on_progress(label, min(got / total, 1.0) if total else None)
    part.replace(dest)


def _extract(archive: Path, into: Path, want: str) -> None:
    """書庫を展開する。`want` は展開後に必ず在るはずのファイル名。

    配布物によって、中身が 1 階層のフォルダに入っている版と、そのまま並んでいる
    版がある。展開後に `want` を探し直して、どちらでも動くようにする。
    """
    into.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(into)
    else:
        with tarfile.open(archive) as t:
            t.extractall(into)

    if not (into / want).is_file():
        found = next((p for p in into.rglob(want) if p.is_file()), None)
        if found is None:
            raise RuntimeError(f"展開しましたが {want} が見つかりません")
        # 実行ファイルと同じ階層の中身をまとめて 1 つ上へ移す(dylib を置き去りにしない)。
        for item in found.parent.iterdir():
            target = into / item.name
            if target.exists():
                continue
            shutil.move(str(item), str(target))

    if not is_windows():
        # ネットから取ったファイルに macOS が付ける印を外す。これが無いと起動できない。
        subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(into)], check=False)
        for p in into.glob("llama-*"):
            if p.is_file():
                p.chmod(0o755)
    archive.unlink(missing_ok=True)
