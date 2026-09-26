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
from .base import Line, Progress, Result

# llama-server を立てるポート。**8080 は窓口(`core/gateway.py`)が使う**ので、
# その後ろに隠す。8081 は Yigdzin(`engines/yigdzin.py`)。
PORT_PREF_KEY = "port_paddle"
DEFAULT_PORT = 8082


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
    # 読み方(`core/reading.py`)。先頭が既定。"lines" は「Spotting:」で行の位置も付け、
    # 位置で並べ替え、位置なしの読みとくらべて抜けを調べる。
    modes = ("text", "lines")

    def __init__(self) -> None:
        self._rt = Runtime(
            model_path=_dest("model"),
            mmproj_path=_dest("mmproj"),
            missing=paddle_assets.missing,
            port_pref_key=PORT_PREF_KEY,
            default_port=DEFAULT_PORT,
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

    def recognize_lines(self, img: Image.Image) -> Result:
        """行ごとの文字と位置(「Spotting:」)。並びはモデルが返したまま。

        並べ替えと点検は `core/reading.py` が行う。直接呼ばずに、そちらを通す。
        """
        if not self._rt.ready:
            raise RuntimeError("先に準備を済ませてください")
        lines: list[Line] = []
        for text, poly in ocr_call.spot(self._rt.endpoint, img):
            if poly is None:
                lines.append(Line(text=text))
                continue
            pts = [(round(x), round(y)) for x, y in poly]
            xs, ys = [x for x, _ in pts], [y for _, y in pts]
            box = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
            lines.append(Line(text=text, box=box, polygon=pts))
        return Result(text="\n".join(ln.text for ln in lines), lines=lines, raw=None)

    def shutdown(self) -> None:
        self._rt.stop()
