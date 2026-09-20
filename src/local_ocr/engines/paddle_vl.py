"""PaddleOCR-VL（llama.cpp 経由）。

画像と版面をまとめて読む視覚言語モデル。漢籍・多言語に強い。
常駐の llama-server を内側で立ち上げ、OpenAI 互換の窓口に投げる。
利用者にサーバの存在は見せない（起動・停止はこのエンジンが持つ）。
"""

from __future__ import annotations

from PIL import Image

from ..core import assets as paddle_assets
from ..core import ocr as ocr_call
from ..core.assets import Asset
from ..core.runtime import Runtime
from .base import Progress, Result


class PaddleVLEngine:
    id = "paddle-vl"
    label = "PaddleOCR-VL（漢籍・多言語）"
    note = "初回だけ 1.8GB ほど取得します。版面ごと読み、縦書きにも向きます。"
    platforms = frozenset({"darwin", "win32"})

    def __init__(self) -> None:
        self._rt = Runtime()

    @property
    def assets(self) -> list[Asset]:
        return paddle_assets.required()

    def available(self) -> bool:
        return not paddle_assets.missing()

    def prepare(self, on_progress: Progress) -> None:
        if paddle_assets.missing():
            self._rt.fetch_missing(on_progress)
        if not self._rt.running:
            on_progress("OCR を起動しています", None)
            self._rt.start()
            if not self._rt.wait_ready():
                raise RuntimeError("OCR を起動できませんでした")

    def recognize(self, img: Image.Image) -> Result:
        if not self._rt.running:
            raise RuntimeError("先に準備を済ませてください")
        text = ocr_call.recognize(self._rt.endpoint, img)
        return Result(text=text, raw=None)

    def shutdown(self) -> None:
        self._rt.stop()
