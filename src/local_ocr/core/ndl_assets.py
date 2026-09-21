"""NDL の 2 つが取得するもの（ONNX のモデル）の定義。

**取り出し先は上流の repo の、動かない番号（コミット）を指している。** 枝の名前で
指すと、上流が差し替えた日に、手元のコードと合わないモデルが降ってくる。
上げるときはここの番号と大きさだけを変え、`src/local_ocr/ndl/charset/` の
文字の一覧も同じ番号から取り直す（モデルと文字の一覧は組で使う）。
"""

from __future__ import annotations

from pathlib import Path

from .assets import Asset
from .paths import data_dir

KOTEN_COMMIT = "ede4283845cdc0ba2bda8b7ebfc3dc80b33c92c8"
LITE_COMMIT = "d25e0d415b607ad44459ca6b95c7512a54363935"
RAW = "https://raw.githubusercontent.com/ndl-lab"


def _dir() -> Path:
    return data_dir() / "ndl"


def _asset(key: str, label: str, repo: str, commit: str, name: str, size: int) -> Asset:
    return Asset(
        key=key,
        label=label,
        url=f"{RAW}/{repo}/{commit}/src/model/{name}",
        dest=_dir() / name,
        approx_bytes=size,
    )


def koten() -> list[Asset]:
    """NDL古典籍OCR Lite。版面を見る 1 つと、字を読む 1 つ。"""
    return [
        _asset("koten-detector", "版面を見る部分", "ndlkotenocr-lite", KOTEN_COMMIT,
               "rtmdet-s-1280x1280.onnx", 40_188_733),
        _asset("koten-recognizer", "字を読む部分", "ndlkotenocr-lite", KOTEN_COMMIT,
               "parseq-ndl-32x384-tiny-10.onnx", 42_442_247),
    ]


def lite() -> list[Asset]:
    """NDLOCR Lite。字を読む部分は、行の長さ別に 3 つある。"""
    return [
        _asset("lite-detector", "版面を見る部分", "ndlocr-lite", LITE_COMMIT,
               "deim-s-1024x1024.onnx", 40_256_763),
        _asset("lite-short", "字を読む部分（短い行）", "ndlocr-lite", LITE_COMMIT,
               "parseq-ndl-24x256-30-tiny-189epoch-tegaki3-r8data-202604.onnx", 36_457_393),
        _asset("lite-medium", "字を読む部分（中くらいの行）", "ndlocr-lite", LITE_COMMIT,
               "parseq-ndl-24x384-50-tiny-300epoch-tegaki3-r8data-202604.onnx", 37_808_553),
        _asset("lite-long", "字を読む部分（長い行）", "ndlocr-lite", LITE_COMMIT,
               "parseq-ndl-24x768-100-tiny-153epoch-tegaki3-r8data-202604.onnx", 42_588_187),
    ]


def paths(assets: list[Asset]) -> dict[str, Path]:
    """エンジンが読み込むときの「役割 → 置き場所」。key の接頭辞は落とす。"""
    return {asset.key.split("-", 1)[1]: asset.dest for asset in assets}
