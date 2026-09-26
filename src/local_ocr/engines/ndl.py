"""国立国会図書館の 2 つ（NDLOCR Lite / NDL古典籍OCR Lite）。

どちらも手元で動く。初回だけモデルを取得し、あとはネットに出ない。
読み取りの中身は `local_ocr/ndl/` にある（上流の実装を写したもの）。
**どちらも CC BY 4.0 なので、表示が要る。** 文面は repo の `NOTICE`。
"""

from __future__ import annotations

from PIL import Image

from ..core import fetch, ndl_assets
from ..core.assets import Asset
from ..ndl.pipeline import KotenPipeline, LitePipeline
from .base import Line, Progress, Result


class _NdlEngine:
    """取得と読み込みの段取りは 2 つで同じ。違うのは何を取るかと、何を作るか。"""

    platforms = frozenset({"darwin", "win32"})
    # 読み方(`core/reading.py`)。先頭が既定。"line" は行を探す段を飛ばし、
    # 渡された画像(囲んだ範囲)を 1 行として読む。
    modes = ("layout", "line")

    def __init__(self) -> None:
        self._pipeline = None

    def _assets(self) -> list[Asset]:
        raise NotImplementedError

    def _build(self, models: dict) -> object:
        raise NotImplementedError

    @property
    def assets(self) -> list[Asset]:
        return self._assets()

    def available(self) -> bool:
        return all(asset.fetched() for asset in self._assets())

    def prepare(self, on_progress: Progress) -> None:
        assets = self._assets()
        missing = [asset for asset in assets if not asset.fetched()]
        if missing:
            fetch.download_all(missing, on_progress)
        if self._pipeline is None:
            # モデルを開くのに数秒かかる。開いたままにして 2 枚目からは待たせない。
            on_progress("OCR を読み込んでいます（初回は少し待ちます）", None)
            self._pipeline = self._build(ndl_assets.paths(assets))

    def recognize(self, img: Image.Image) -> Result:
        if self._pipeline is None:
            raise RuntimeError("先に準備を済ませてください")
        reads = self._pipeline.run(img.convert("RGB"))
        lines = [Line(text=read.text, box=read.box) for read in reads]
        return Result(text="\n".join(line.text for line in lines), lines=lines)

    def recognize_line(self, img: Image.Image) -> Result:
        """画像全体を 1 行として読む。枠は画像全体。"""
        if self._pipeline is None:
            raise RuntimeError("先に準備を済ませてください")
        rgb = img.convert("RGB")
        text = self._pipeline.read_line(rgb)
        lines = [Line(text=text, box=(0, 0, rgb.width, rgb.height))] if text else []
        return Result(text=text, lines=lines)

    def shutdown(self) -> None:
        # ONNX Runtime の読み込み分を離す。常駐するものは持たない。
        self._pipeline = None


class NdlKotenLiteEngine(_NdlEngine):
    id = "ndl-koten-lite"
    label = "NDL古典籍OCR Lite（くずし字）"
    note = "初回だけ 83MB ほど取得します。古典籍・くずし字に向きます。"

    def _assets(self) -> list[Asset]:
        return ndl_assets.koten()

    def _build(self, models: dict) -> KotenPipeline:
        return KotenPipeline(models)


class NdlLiteEngine(_NdlEngine):
    id = "ndl-lite"
    label = "NDLOCR Lite（近代の活字）"
    note = "初回だけ 157MB ほど取得します。近代資料の活字・手書きに向きます。"

    def _assets(self) -> list[Asset]:
        return ndl_assets.lite()

    def _build(self, models: dict) -> LitePipeline:
        return LitePipeline(models)
