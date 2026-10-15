# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = [
#     "huggingface_hub>=0.30",
#     "paddlepaddle>=3.0",
#     "paddle2onnx>=2.0",
#     "pyyaml>=6",
#     "onnxruntime>=1.22",
#     "setuptools",  # paddle が内部で使う。無いと import で落ちる
# ]
# ///
"""公式の Paddle のモデルを、ONNX に変換する（公式に `*_onnx` が無いモデルのときだけ使う）。

**アプリの依存には入れない。** このスクリプトは、自分用の使い捨ての環境で動く
（上の `dependencies` を uv が読んで、その場で用意する）。アプリの `uv sync` には何も足さない。

使い方（リポジトリの直下で。1 行で実行する）:

    uv run scripts/ppocr/convert.py PaddlePaddle/PP-OCRv5_mobile_rec --rev <40 桁の番号>

`--rev` を省くと、いまの最新の番号を使う（そのうえで、使った番号を表示する）。
出力は `--out`（既定 `./ppocr-out`）に、次の 2 つ。

- `<モデル名>.onnx` … 変換したモデル（重みは変えない）
- `<モデル名>.dict.json` … 認識モデルの文字の一覧（`inference.yml` の `character_dict`）。
  検出モデルには無いので出ない

最後に、`PpocrModel` に貼るデータの下書きと、ファイルの大きさを表示する。
**動作の確認は、変換が終わったあとに 1 回だけ行う**（onnxruntime で開き、入出力の形を表示する）。

**確かめたこと（2026-10-15、macOS arm64）**: PP-OCRv5_mobile_rec で動かし、できた ONNX が
nakamura196/ppocrv5-mobile-web-onnx のものと同じ大きさ（16,537,064 バイト）になった。
変換コマンドは、そのモデルカードに書いてあるものと同じ。Windows では動かしていない。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

OPSET = 14  # モデルカードの変換コマンドと同じ


def die(msg: str) -> None:
    print(f"エラー: {msg}", file=sys.stderr)
    raise SystemExit(1)


def download(repo: str, rev: str | None, dest: Path) -> tuple[Path, str]:
    """公式のモデルを取り出し、(置き場所, 40 桁の番号) を返す。"""
    from huggingface_hub import HfApi, snapshot_download

    sha = HfApi().model_info(repo, revision=rev).sha
    if not sha or not re.fullmatch(r"[0-9a-f]{40}", sha):
        die(f"{repo} の番号を調べられませんでした")
    path = snapshot_download(repo, revision=sha, local_dir=dest / "src")
    return Path(path), sha


def to_onnx(model_dir: Path, out_file: Path) -> None:
    # 新しい Paddle は inference.json、古いものは inference.pdmodel に入っている。
    if (model_dir / "inference.json").is_file():
        model_name = "inference.json"
    elif (model_dir / "inference.pdmodel").is_file():
        model_name = "inference.pdmodel"
    else:
        die("inference.json（または inference.pdmodel）が見つかりません。Paddle のモデルですか？")
    exe = shutil.which("paddle2onnx", path=str(Path(sys.executable).parent))
    cmd = [exe] if exe else [sys.executable, "-m", "paddle2onnx"]
    cmd += [
        "--model_dir", str(model_dir),
        "--model_filename", model_name,
        "--params_filename", "inference.pdiparams",
        "--save_file", str(out_file),
        "--opset_version", str(OPSET),
    ]  # fmt: skip
    print("実行:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def write_dict(model_dir: Path, out_file: Path) -> int | None:
    """inference.yml の character_dict を JSON の配列にして書く。無ければ None。"""
    import yaml

    yml_path = model_dir / "inference.yml"
    if not yml_path.is_file():
        return None
    cfg = yaml.safe_load(yml_path.read_text(encoding="utf-8"))
    chars = (cfg.get("PostProcess") or {}).get("character_dict")
    if not chars:
        return None
    chars = [str(c) for c in chars]
    out_file.write_text(
        json.dumps(chars, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    # アプリが自分で読む読み手（PyYAML を使わない）と同じ結果か確かめる。
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
        from local_ocr.ppocr.config import character_dict

        same = character_dict(yml_path.read_text(encoding="utf-8")) == chars
        print(
            "アプリの読み手との照合:",
            "一致" if same else "**不一致**（config.py を直す必要があります）",
        )
    except ImportError:
        print("アプリの読み手との照合: 飛ばしました（src/ が見つかりません）")
    return len(chars)


def check(onnx_file: Path) -> None:
    import onnxruntime

    onnxruntime.set_default_logger_severity(3)  # 変換物の「使わない部品」の警告を止める
    sess = onnxruntime.InferenceSession(str(onnx_file), providers=["CPUExecutionProvider"])
    print("入力:", [(i.name, i.shape) for i in sess.get_inputs()])
    print("出力:", [(o.name, o.shape) for o in sess.get_outputs()])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("repo", help="Hugging Face の名前（例: PaddlePaddle/PP-OCRv5_mobile_rec）")
    ap.add_argument("--rev", help="元のモデルの番号（40 桁）。省くと最新")
    ap.add_argument("--out", type=Path, default=Path("ppocr-out"))
    args = ap.parse_args()

    name = args.repo.rsplit("/", 1)[-1]
    args.out.mkdir(parents=True, exist_ok=True)
    model_dir, sha = download(args.repo, args.rev, args.out)
    onnx_file = args.out / f"{name}.onnx"
    to_onnx(model_dir, onnx_file)
    dict_file = args.out / f"{name}.dict.json"
    count = write_dict(model_dir, dict_file)

    try:
        check(onnx_file)
    except ImportError:
        print("onnxruntime が無いので、開いての確認は飛ばしました")

    print("\n--- 結果 ---")
    print(f"元のモデル: https://huggingface.co/{args.repo}  番号 {sha}")
    print(f"{onnx_file}  {onnx_file.stat().st_size:,} bytes")
    if count:
        print(f"{dict_file}  {dict_file.stat().st_size:,} bytes（{count:,} 字）")
    print(
        "\n次は、この 2 つ（あれば）を自分の Hugging Face の repo にアップロードし、"
        "その repo の番号（40 桁）を控えて、PpocrModel に書きます。"
        "手順は docs/adding-an-engine.md の「公式に ONNX が無いとき」。"
    )


if __name__ == "__main__":
    main()
