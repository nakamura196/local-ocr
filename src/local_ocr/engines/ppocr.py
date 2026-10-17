"""PaddleOCR PP-OCR の読む道具（いま入っているのは PP-OCRv6 medium）。**モデルを足すときはデータを 1 件足すだけ。**

PP-OCR の仲間は、行を探す部分（検出）と、1 行を読む部分（読み取り）と、文字の一覧が
1 組になっている。検出は共通で、読み取りと一覧だけがモデルごとに違う。
そこで、モデル 1 つを `PpocrModel` というデータで書き、エンジンのクラスは 1 つに
している。足し方は `docs/adding-an-engine.md`。

- モデルは ONNX。公式（PaddlePaddle）が `*_onnx` として出しているものは、そのまま指す。
  無いものだけ、公式の重みを ONNX に変えて自前の repo に置く（重みは変えていない）。
  **どちらも、repo の動かない番号（コミット）を指している。** 枝の名前で指すと、
  差し替えられた日に別のモデルが降ってくる（`core/ndl_assets.py` と同じ考え）
- 読み取りの中身は `local_ocr/ppocr/`。Apache-2.0 なので表示が要る → repo の `NOTICE`
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from ..core import fetch
from ..core.assets import Asset
from ..core.paths import data_dir
from ..ppocr import config
from ..ppocr.pipeline import PpocrPipeline
from .base import Line, Progress, Result

HF = "https://huggingface.co"


@dataclass(frozen=True)
class PpocrFile:
    """取得するファイル 1 件。`repo` と `rev`（動かない番号）で、取り出し先が決まる。

    手元では `ppocr/<repo の名前>/<rev の頭 7 文字>/<ファイル名>` に置く。公式の repo は
    どれも `inference.onnx` という同じ名前なので、repo と番号で分けないとぶつかる。
    """

    repo: str
    rev: str
    name: str
    approx_bytes: int

    @property
    def url(self) -> str:
        return f"{self.repo}/resolve/{self.rev}/{self.name}"

    def dest(self) -> Path:
        return _dir() / self.repo.rstrip("/").rsplit("/", 1)[-1] / self.rev[:7] / self.name


@dataclass(frozen=True)
class PpocrModel:
    """PP-OCR のモデル 1 つ分の定義。画面に出す文字もここに持つ。"""

    id: str
    label: str
    label_en: str
    # 画面の説明の、取得量のあとに続く文。取得量はファイルの大きさから自動で入れる。
    hint: str
    hint_en: str
    detector: PpocrFile
    recognizer: PpocrFile
    # 文字の一覧。JSON の配列のファイルがあればそれを使う。無ければ `rec_config`
    # （公式の inference.yml）の character_dict を読む。
    dictionary: PpocrFile | None = None
    # 公式の inference.yml。あれば、しきい値や入力の高さを読む（`ppocr/config.py`）。
    # 無い項目は `Params` の既定（PP-OCRv5 の公式の値）になる。
    det_config: PpocrFile | None = None
    rec_config: PpocrFile | None = None
    # 表示（NOTICE に書く文面と合わせる）
    license: str = "Apache-2.0"
    credit: str = "PaddlePaddle"
    homepage: str = "https://github.com/PaddlePaddle/PaddleOCR"
    # 検出に入れる前に、長辺をここまで縮める（px）。公式は縮めない。
    det_long_side: int = 2048
    platforms: frozenset[str] = field(default_factory=lambda: frozenset({"darwin", "win32"}))

    def roles(self) -> list[tuple[str, str, PpocrFile]]:
        """(役割, 画面に出す名前, ファイル)。無いものは入らない。"""
        parts = [
            ("detector", "行を探す部分", self.detector),
            ("recognizer", "字を読む部分", self.recognizer),
            ("dictionary", "文字の一覧", self.dictionary),
            ("det-config", "行を探す部分の設定", self.det_config),
            ("rec-config", "字を読む部分の設定", self.rec_config),
        ]
        return [p for p in parts if p[2] is not None]


# 公式が出している ONNX（PaddlePaddle/<名前>_onnx）。**変換も再配布も要らない。**
# 中身は inference.onnx と inference.yml（しきい値・入力・文字の一覧）。
# 0.1.11 は small（31MB）だった。漢籍 28 頁で PaddleOCR-VL と違う字が small 167 → medium 148 に
# 減ったので medium に置き換えた（1 頁 3 秒 → 6 秒、docs/notes/ppocr.md の 2026-10-17）。
V6_MEDIUM_DET = f"{HF}/PaddlePaddle/PP-OCRv6_medium_det_onnx"
V6_MEDIUM_DET_REV = "61323801669c338b7891481ec7bac61ce31b576a"
V6_MEDIUM_REC = f"{HF}/PaddlePaddle/PP-OCRv6_medium_rec_onnx"
V6_MEDIUM_REC_REV = "50c7eacafc52fa7bcf4194e8cd08e46f8558504b"

# 並び順がそのまま画面の並び。**足すときはここに 1 件書く。**
# 同じ言語を読むモデルは 2 つ並べない（新しい版が上回るなら置き換える）。
MODELS: list[PpocrModel] = [
    PpocrModel(
        id="ppocrv6-medium",
        label="PP-OCRv6（活字・多言語）",
        label_en="PP-OCRv6 (print, multilingual)",
        hint="活字を行ごとに読みます。中国語・英語・日本語のほか、ラテン文字の言語にも向きます。",
        hint_en="Reads print line by line. Chinese, English, Japanese, and Latin-script languages.",
        detector=PpocrFile(V6_MEDIUM_DET, V6_MEDIUM_DET_REV, "inference.onnx", 62_032_837),
        recognizer=PpocrFile(V6_MEDIUM_REC, V6_MEDIUM_REC_REV, "inference.onnx", 76_554_979),
        det_config=PpocrFile(V6_MEDIUM_DET, V6_MEDIUM_DET_REV, "inference.yml", 886),
        rec_config=PpocrFile(V6_MEDIUM_REC, V6_MEDIUM_REC_REV, "inference.yml", 150_580),
    ),
]


def _dir() -> Path:
    return data_dir() / "ppocr"


class PpocrEngine:
    """モデル 1 つ分のエンジン。取得と読み込みの段取りは全モデルで同じ。"""

    # 読み方(`core/reading.py`)。先頭が既定。"line" は行を探す段を飛ばし、
    # 渡された画像(囲んだ範囲)を 1 行として読む。
    modes = ("layout", "line")

    def __init__(self, model: PpocrModel) -> None:
        self.model = model
        self.id = model.id
        self.label = model.label
        self.label_en = model.label_en
        self.platforms = model.platforms
        size = fetch.human(fetch.total_bytes(self.assets))
        self.note = f"初回だけ {size} ほど取得します。{model.hint}"
        self.note_en = f"Downloads about {size} the first time. {model.hint_en}"
        self._pipeline: PpocrPipeline | None = None

    @property
    def assets(self) -> list[Asset]:
        return [
            Asset(
                key=f"{self.model.id}-{role}",
                label=label,
                url=f.url,
                dest=f.dest(),
                approx_bytes=f.approx_bytes,
            )
            for role, label, f in self.model.roles()
        ]

    def available(self) -> bool:
        return all(asset.fetched() for asset in self.assets)

    def prepare(self, on_progress: Progress) -> None:
        assets = self.assets
        missing = [asset for asset in assets if not asset.fetched()]
        if missing:
            fetch.download_all(missing, on_progress)
        if self._pipeline is None:
            on_progress("OCR を読み込んでいます（初回は少し待ちます）", None)
            self._pipeline = self._build()

    def _build(self) -> PpocrPipeline:
        m = self.model

        def read(f: PpocrFile | None) -> str | None:
            return f.dest().read_text(encoding="utf-8") if f else None

        params = config.params_from(read(m.det_config), read(m.rec_config))
        chars = config.load_chars(
            m.dictionary.dest() if m.dictionary else None,
            m.rec_config.dest() if m.rec_config else None,
        )
        return PpocrPipeline(
            m.detector.dest(),
            m.recognizer.dest(),
            chars,
            params,
            det_long_side=m.det_long_side,
        )

    def recognize(self, img: Image.Image) -> Result:
        if self._pipeline is None:
            raise RuntimeError("先に準備を済ませてください")
        reads = self._pipeline.run(img.convert("RGB"))
        lines = [Line(text=r.text, box=r.box, polygon=r.polygon) for r in reads]
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
        # ONNX Runtime の読み込み分を離す。
        self._pipeline = None
