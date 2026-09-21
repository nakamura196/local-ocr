"""PaddleOCR-VL が要るもの（llama.cpp 本体とモデル）の定義。

**llama.cpp 本体は同梱する。ここには書かない。** 置き場所は `core/bundled.py`、
取ってくるのは `scripts/fetch-binaries.zsh` / `.ps1`（ビルド時に走らせる）。
初回起動時に取ってくる形はやめた。ストアの審査（審査が見たものと、実際に動く
ものが別になる）と正面からぶつかるため。

ここに残るのは初回に取得するモデル (.gguf) だけ。1.8GB あるが、中身はデータで
あって実行ファイルではないので、同梱しなくてよい。

版は固定する。上げるときはここだけ変える（取得スクリプトは LLAMA_BUILD を
このファイルから読む）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import bundled
from .paths import data_dir

# 同梱する llama.cpp の版。**取得スクリプトはこの行を sed / Select-String で
# 読んでいる。** 書き方（`LLAMA_BUILD = "..."`）を変えるときは両方を直すこと。
LLAMA_BUILD = "b10776"
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

    def fetched(self) -> bool:
        return self.dest.is_file() and self.dest.stat().st_size > 0

    def size_on_disk(self) -> int:
        """今ディスクにある大きさ。"""
        return self.dest.stat().st_size if self.dest.is_file() else 0


def server_path() -> Path | None:
    """同梱した llama-server。見つからなければ None（開発時に取得し忘れたとき）。"""
    return bundled.find("llama-server")


def required() -> list[Asset]:
    """初回に取得するもの。**llama.cpp 本体は入らない（同梱するため）。**"""
    d = data_dir()
    return [
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
