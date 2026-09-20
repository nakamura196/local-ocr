"""画像を 1 枚渡して、読んだ文字を受け取る。

llama-server の OpenAI 互換の窓口に投げているだけ。画面側はこの関数しか使わない。
"""

from __future__ import annotations

import base64
import io
import json
import urllib.request
from pathlib import Path

from PIL import Image, ImageGrab

# 長辺の上限。大きいまま渡すと視覚トークンが文脈長を食い潰し、
# 読みの途中で切れる。1600 は A4 相当の版面で本文が潰れない下限あたり(実測)。
MAX_SIDE = 1600
# 出力の上限。1 ページの版面でも足りる長さにしている。
MAX_TOKENS = 4096
PROMPT = "OCR:"


def from_clipboard() -> Image.Image | None:
    """クリップボードの画像。文字しか入っていなければ None。

    ImageGrab は macOS と Windows の両方で使える。Linux は対象外。
    """
    try:
        data = ImageGrab.grabclipboard()
    except (OSError, NotImplementedError):
        return None
    if isinstance(data, Image.Image):
        return data
    # Finder / エクスプローラでファイルをコピーした場合はパスの一覧で返る。
    if isinstance(data, list) and data:
        try:
            return Image.open(data[0])
        except (OSError, ValueError):
            return None
    return None


def load(path: str | Path) -> Image.Image:
    return Image.open(path)


def to_data_url(img: Image.Image) -> str:
    img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > MAX_SIDE:
        scale = MAX_SIDE / max(w, h)
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def recognize(endpoint: str, img: Image.Image, timeout: float = 300.0) -> str:
    body = json.dumps(
        {
            "model": "paddleocr-vl",
            "temperature": 0,
            "max_tokens": MAX_TOKENS,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": to_data_url(img)}},
                        {"type": "text", "text": PROMPT},
                    ],
                }
            ],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{endpoint}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        payload = json.loads(res.read().decode("utf-8"))
    return (payload.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
