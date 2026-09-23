"""PaddleOCR-VL（llama.cpp 経由）。

画像と版面をまとめて読む視覚言語モデル。漢籍・多言語に強い。
常駐の llama-server を内側で立ち上げ、OpenAI 互換の窓口に投げる。
**利用者にサーバの存在は見せない**（起動・停止はこのエンジンが持つ）。
例外は設定の「ほかの道具から使えるようにする」で、そこだけは接続先を表に出す
（`core/bridge.py`。開けている間は、このサーバを立てたままにする）。
"""

from __future__ import annotations

from PIL import Image

from ..core import assets as paddle_assets
from ..core import ocr as ocr_call
from ..core.assets import Asset
from ..core.runtime import Runtime
from .base import Progress, Result


def _dest(key: str) -> object:
    """必要なファイルの置き場所を、`assets.required()` の定義から引く。

    ここで別にファイル名を書かない。1 か所(`core/assets.py`)だけを直せば済む。
    """
    return next(a.dest for a in paddle_assets.required() if a.key == key)


class PaddleVLEngine:
    id = "paddle-vl"
    label = "PaddleOCR-VL（漢籍・多言語）"
    note = "初回だけ 1.8GB ほど取得します。版面ごと読み、縦書きにも向きます。"
    platforms = frozenset({"darwin", "win32"})

    def __init__(self) -> None:
        self._rt = Runtime(
            model_path=_dest("model"),
            mmproj_path=_dest("mmproj"),
            missing=paddle_assets.missing,
        )

    @property
    def runtime(self) -> Runtime:
        """ほかの道具に開く窓口が見る(`core/bridge.py`)。

        **窓口にも同じサーバを使わせるため。** 別に立てると、同じポートを取り合い、
        重みを二度読むことになる。常駐のサーバを持つ道具はいまこれだけ。
        """
        return self._rt

    @property
    def assets(self) -> list[Asset]:
        return paddle_assets.required()

    def available(self) -> bool:
        return not paddle_assets.missing()

    def prepare(self, on_progress: Progress) -> None:
        # **取得より先に見る。** 同梱漏れに 1.8GB 落とし終わってから気づくのは遅い。
        if paddle_assets.server_path() is None:
            raise RuntimeError(
                "OCR の本体（llama-server）が同梱されていません。"
                "開発中は ./scripts/fetch-binaries.zsh を実行してください"
            )
        if paddle_assets.missing():
            self._rt.fetch_missing(on_progress)
        if not self._rt.ready:
            on_progress("OCR を起動しています（初回は少し待ちます）", None)
            self._rt.start()
            if not self._rt.wait_ready():
                raise RuntimeError("OCR を起動できませんでした")

    def recognize(self, img: Image.Image) -> Result:
        if not self._rt.ready:
            raise RuntimeError("先に準備を済ませてください")
        text = ocr_call.recognize(self._rt.endpoint, img)
        return Result(text=text, raw=None)

    def shutdown(self) -> None:
        self._rt.stop()
