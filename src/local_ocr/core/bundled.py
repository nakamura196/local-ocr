"""同梱した実行ファイルの置き場所。

llama-server は開発時とパッケージ後で置き場所が変わる。その差をここに閉じ込める。

## なぜ同梱するのか

0.1.0 までは初回起動時に GitHub から取ってきていた。これはストアの審査
（審査が見たものと、実際に動くものが別になる）と正面からぶつかる。ビルド時に
取り込み、アプリと一緒に署名する。取ってくる手順は `scripts/fetch-binaries.zsh`
（macOS）と `scripts/fetch-binaries.ps1`（Windows / CI から呼ぶ）。

## 置き場所

    macOS     <アプリ>.app/Contents/Resources/bin/
              sys.executable が <アプリ>.app/Contents/MacOS/<実行ファイル> なので
              parent.parent / "Resources" / "bin"

    Windows   <実行ファイルと同じ階層>/bin/

    開発時     リポジトリ直下の binaries/<os>/

**Python 側（app.zip に入る場所）に置いてはいけない。** 起動自体はできるが、
公証で必ず弾かれる。Apple の審査は app.zip の中まで降りて署名を要求するが、
zip の中のファイルは署名できないため原理的に通せない。
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

from .paths import is_windows


def _candidate_dirs() -> list[Path]:
    exe = Path(sys.executable).resolve()
    if is_windows():
        candidates = [exe.parent / "bin"]
    else:
        candidates = [exe.parent.parent / "Resources" / "bin"]
    # 開発時（uv run / pytest）。core/ から 3 つ上がリポジトリ直下。
    repo_root = Path(__file__).resolve().parents[3]
    candidates.append(repo_root / "binaries" / ("windows" if is_windows() else "macos"))
    return candidates


def bin_dir() -> Path | None:
    """同梱物の置き場所。見つからなければ None。"""
    return next((d for d in _candidate_dirs() if d.is_dir()), None)


def find(name: str) -> Path | None:
    """同梱した実行ファイルを返す。見つからなければ None。

    Args:
        name: 拡張子を含まない名前（例: "llama-server"）。Windows では .exe を補う。
    """
    directory = bin_dir()
    if directory is None:
        return None
    tool = directory / (f"{name}.exe" if is_windows() else name)
    return tool if tool.is_file() else None


def ensure_executable(tool: Path) -> None:
    """実行ビットが落ちていれば付け直す。

    macOS のパッケージ経路では保たれるが、zip を経由した配置では落ちることがある。
    付けられなければ例外をそのまま上げる（黙って起動に失敗させるより、原因が
    分かる形で落とす方がよい）。
    """
    if is_windows() or os.access(tool, os.X_OK):
        return
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
