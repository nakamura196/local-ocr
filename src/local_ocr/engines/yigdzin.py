"""Yigdzin-1（チベット語 OCR）。

行を見つけてから 1 行ずつ読む、という流れは NDL の 2 つと同じ
（`yigdzin/pipeline.py`）。違うのは、行を読む部分が ONNX ではなく、常駐の
llama-server（PaddleOCR-VL と同じ仕組み）である点。**別の GGUF を別のポートで
動かすので、PaddleOCR-VL とは別に自分の `Runtime` を持つ**（`core/runtime.py`）。

`.runtime` は持たせていない。「ほかの道具から使えるようにする」窓口
（`core/bridge.py`）は、いまのところ `Runtime` を 1 つしか受け取れない作りに
なっており、PaddleOCR-VL がそれを使っている。両方を出せるようにするのは
窓口側の改修が要るので、必要になったら別途行う。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from ..core import assets as core_assets
from ..core import yigdzin_assets
from ..core.assets import Asset
from ..core.runtime import Runtime
from ..yigdzin.pipeline import YigdzinPipeline
from .base import Line, Progress, Result

# PaddleOCR-VL(既定 8080、core/runtime.py の DEFAULT_PORT)と衝突しないよう、
# 別の設定キー・別の既定ポートを使う。2 つの llama-server を同時に立てられる。
PORT_PREF_KEY = "port_yigdzin"
DEFAULT_PORT = 8081


def _dest(key: str) -> Path:
    """必要なファイルの置き場所を `yigdzin_assets.required()` の定義から引く。

    ここで別にファイル名を書かない。1 か所(`core/yigdzin_assets.py`)だけを
    直せば済む。
    """
    return next(a.dest for a in yigdzin_assets.required() if a.key == key)


class YigdzinEngine:
    id = "yigdzin"
    label = "Yigdzin-1（チベット語）"
    note = "初回だけ 1.7GB ほど取得します。行を見つけてから読みます。"
    platforms = frozenset({"darwin", "win32"})

    def __init__(self) -> None:
        self._rt = Runtime(
            model_path=_dest("model"),
            mmproj_path=_dest("mmproj"),
            missing=yigdzin_assets.missing,
            port_pref_key=PORT_PREF_KEY,
            default_port=DEFAULT_PORT,
        )
        self._pipeline: YigdzinPipeline | None = None

    @property
    def assets(self) -> list[Asset]:
        return yigdzin_assets.required()

    def available(self) -> bool:
        return not yigdzin_assets.missing()

    def prepare(self, on_progress: Progress) -> None:
        # **取得より先に見る。** 同梱漏れに 1.6GB 落とし終わってから気づくのは遅い。
        if core_assets.server_path() is None:
            raise RuntimeError(
                "OCR の本体（llama-server）が同梱されていません。"
                "開発中は ./scripts/fetch-binaries.zsh を実行してください"
            )
        if yigdzin_assets.missing():
            self._rt.fetch_missing(on_progress)
        if not self._rt.ready:
            on_progress("OCR を起動しています（初回は少し待ちます）", None)
            self._rt.start()
            if not self._rt.wait_ready():
                raise RuntimeError("OCR を起動できませんでした")
        if self._pipeline is None:
            # 行検出の ONNX を開くのに時間がかかる。開いたままにして、
            # 2 枚目からは待たせない(NDL の Pipeline と同じ考え方)。
            on_progress("行を見つける部分を読み込んでいます", None)
            self._pipeline = YigdzinPipeline(_dest("detector"), self._rt.endpoint)

    def recognize(self, img: Image.Image) -> Result:
        if self._pipeline is None:
            raise RuntimeError("先に準備を済ませてください")
        reads = self._pipeline.run(img)
        lines = [Line(text=r.text, box=r.box) for r in reads]
        return Result(text="\n".join(line.text for line in lines), lines=lines)

    def shutdown(self) -> None:
        self._rt.stop()
        self._pipeline = None
