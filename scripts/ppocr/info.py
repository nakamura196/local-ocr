"""Hugging Face の repo から、`PpocrFile` に書く値（番号・大きさ）を調べて表示する。

公式の `PaddlePaddle/<名前>_onnx` を足すときに使う。**標準の Python だけで動く**
（何も入れなくてよい）。

    python3 scripts/ppocr/info.py PaddlePaddle/PP-OCRv6_small_det_onnx PaddlePaddle/PP-OCRv6_small_rec_onnx

repo ごとに、いまの最新の番号（40 桁）と、使うファイル（inference.onnx と inference.yml）の
大きさを出し、そのまま貼れる `PpocrFile(...)` の行を表示する。
**番号は、動かない値として控える。** あとで公式が更新しても、こちらは控えた番号の版を使い続ける。
"""

from __future__ import annotations

import json
import sys
import urllib.request

HF = "https://huggingface.co"
FILES = ("inference.onnx", "inference.yml")


def get(url: str, method: str = "GET"):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": "Local-OCR"})
    return urllib.request.urlopen(req, timeout=30)


def main(repos: list[str]) -> None:
    if not repos:
        raise SystemExit(__doc__)
    for repo in repos:
        with get(f"{HF}/api/models/{repo}") as res:
            info = json.load(res)
        sha = info["sha"]
        print(f"\n# {repo}")
        print(f"# 番号: {sha}")
        print(f"# ライセンス: {info.get('cardData', {}).get('license', '（書かれていません）')}")
        name = repo.rsplit("/", 1)[-1]
        for f in FILES:
            try:
                with get(f"{HF}/{repo}/resolve/{sha}/{f}", "HEAD") as res:
                    size = int(
                        res.headers.get("X-Linked-Size") or res.headers.get("Content-Length")
                    )
            except Exception as e:  # noqa: BLE001 - 何が起きても、その旨を表示して続ける
                print(f"# {f}: 見つかりません（{e}）")
                continue
            print(f'PpocrFile("{HF}/{repo}", "{sha}", "{f}", {size:_}),  # {name}')


if __name__ == "__main__":
    main(sys.argv[1:])
