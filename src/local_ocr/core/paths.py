"""どこに何を置くかを、OS ごとに 1 か所で決める。

配置先を各所に散らすと、片方の OS でしか通らない書き方が紛れ込む。
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

APP_DIR_NAME = "PaddleOCR Local"

# 2026-09 に東洋文庫へ配った起動スクリプト版の置き場所。すでに 1.8GB を
# 取得済みの方に再取得させないため、あればそちらを使う。
LEGACY_DIR_NAME = "PaddleOCR校正"


def is_windows() -> bool:
    return platform.system() == "Windows"


def data_dir() -> Path:
    """モデルと llama.cpp を置く場所。

    ホーム直下ではなく OS の作法に従う。ホーム直下はバックアップ対象に
    入りやすく、2GB 近い再取得可能なファイルを同期させてしまう。
    """
    legacy = Path.home() / LEGACY_DIR_NAME
    if legacy.is_dir():
        return legacy
    if is_windows():
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_DIR_NAME
    return Path.home() / "Library" / "Application Support" / APP_DIR_NAME


def settings_file() -> Path:
    return data_dir() / "settings.json"
