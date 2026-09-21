"""前回の状態と好みの置き場。settings.json を読み書きするのはここだけ。

書き込みは読んでから混ぜる。別の場所が書いた項目(ポートなど)を消さないため。
"""

from __future__ import annotations

import json
from typing import Any

from .paths import settings_file


def load() -> dict[str, Any]:
    try:
        return json.loads(settings_file().read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def get(key: str, default: Any = None) -> Any:
    return load().get(key, default)


def save(**kv: Any) -> None:
    merged = load() | kv
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), "utf-8")
