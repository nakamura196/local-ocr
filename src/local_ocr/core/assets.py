"""取得するもの（llama.cpp 本体とモデル）の定義。

版は固定する。上げるときはここだけ変える。
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path

from .paths import data_dir, is_windows

# llama.cpp の版。起動スクリプト版 (scripts/paddle/local/) と同じものに揃えている。
LLAMA_BUILD = "b10776"
LLAMA_RELEASE = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_BUILD}"
HF = "https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6-GGUF/resolve/main"


@dataclass(frozen=True)
class Asset:
    """取得物 1 件。`label` は画面にそのまま出す。"""

    key: str
    label: str
    url: str
    dest: Path
    # 進捗バーのため。サーバが Content-Length を返さないときの目安にも使う。
    approx_bytes: int
    # tar.gz / zip なら、展開先。None ならそのまま置く。
    extract_to: Path | None = None
    # 「取得済み」と見なす目印。書庫を展開するものは、展開後の実行ファイルを指す
    # (書庫そのものは展開後に消すので、dest の有無では判定できない)。
    installed_marker: Path | None = None

    @property
    def marker(self) -> Path:
        return self.installed_marker or self.dest

    def fetched(self) -> bool:
        p = self.marker
        return p.is_file() and p.stat().st_size > 0

    def size_on_disk(self) -> int:
        """今ディスクにある大きさ。展開するものは展開先のフォルダ全体を数える。"""
        if self.extract_to is not None and self.extract_to.is_dir():
            return sum(f.stat().st_size for f in self.extract_to.rglob("*") if f.is_file())
        return self.dest.stat().st_size if self.dest.is_file() else 0


def llama_asset_name() -> str:
    """この機械向けの llama.cpp 配布物の名前。"""
    if is_windows():
        # Vulkan 版を使う。CPU 版だと画像を見る部分が 1 行 93 秒かかる (実測)。
        return f"llama-{LLAMA_BUILD}-bin-win-vulkan-x64.zip"
    arch = platform.machine()
    if arch == "arm64":
        return f"llama-{LLAMA_BUILD}-bin-macos-arm64.tar.gz"
    if arch == "x86_64":
        return f"llama-{LLAMA_BUILD}-bin-macos-x64.tar.gz"
    raise RuntimeError(f"対応していない CPU です: {arch}")


def bin_dir() -> Path:
    return data_dir() / f"llama-{LLAMA_BUILD}"


def server_path() -> Path:
    name = "llama-server.exe" if is_windows() else "llama-server"
    return bin_dir() / name


def required() -> list[Asset]:
    d = data_dir()
    name = llama_asset_name()
    return [
        Asset(
            key="llama",
            label="OCR の本体",
            url=f"{LLAMA_RELEASE}/{name}",
            dest=d / name,
            approx_bytes=120 * 1024 * 1024,
            extract_to=bin_dir(),
            installed_marker=server_path(),
        ),
        Asset(
            key="model",
            label="文字を読む部分",
            url=f"{HF}/PaddleOCR-VL-1.6-GGUF.gguf",
            dest=d / "PaddleOCR-VL-1.6.gguf",
            approx_bytes=935_769_056,
        ),
        Asset(
            key="mmproj",
            label="画像を見る部分",
            url=f"{HF}/PaddleOCR-VL-1.6-GGUF-mmproj.gguf",
            dest=d / "PaddleOCR-VL-1.6-mmproj.gguf",
            approx_bytes=881_770_560,
        ),
    ]


def missing() -> list[Asset]:
    """まだ取得していないもの。"""
    return [a for a in required() if not a.fetched()]
