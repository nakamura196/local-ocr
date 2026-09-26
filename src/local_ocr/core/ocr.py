"""画像を 1 枚渡して、読んだ文字を受け取る。

llama-server の OpenAI 互換の窓口に投げているだけ。画面側は `recognize` しか使わない。
行の位置まで欲しいときは `spot`(PaddleOCR-VL 1.5 以降の「Spotting:」)。
"""

from __future__ import annotations

import base64
import io
import json
import re
import urllib.request
from pathlib import Path

from PIL import Image, ImageGrab

from .ruler import mask_rulers

# 受け付ける画像の拡張子。入口(選ぶ・フォルダ・端末)で共通に使う。
IMAGE_SUFFIXES = ("png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp")

# 長辺の上限。大きいまま渡すと視覚トークンが文脈長を食い潰し、
# 読みの途中で切れる。1600 は A4 相当の版面で本文が潰れない下限あたり(実測)。
MAX_SIDE = 1600
# 出力の上限。1 ページの版面でも足りる長さにしている。
MAX_TOKENS = 4096
PROMPT = "OCR:"
# 行ごとに文字と位置(4 隅)を返させる指示。PaddleOCR-VL 1.5 で入った。
SPOT_PROMPT = "Spotting:"
# 位置は画像の幅・高さを 0〜999 に割った目盛りで返る。
LOC_SCALE = 999
_LOC = re.compile(r"<\|LOC_(\d+)\|>")
# 位置の付かない行がこれだけ続いたら、読みが崩れたとみなして打ち切る。
# 本文の行には必ず位置が付く。崩れるのは定規の数字を「1, 2, 3, …」と数え続けるとき
# (2026-09-25 に 030_01_025 で実測。上限の 4096 まで 40 秒ほど数え続けた)。
RUNAWAY_LINES = 20
# 位置以外の特殊な印(終わりの </s> など)。本文には残さない。
_SPECIAL = re.compile(r"</s>|<\|[^|>]*\|>")


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


def _jpeg_base64(img: Image.Image) -> str:
    img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > MAX_SIDE:
        scale = MAX_SIDE / max(w, h)
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def to_data_url(img: Image.Image) -> str:
    return "data:image/jpeg;base64," + _jpeg_base64(img)


def _post(url: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


Polygon = list[tuple[float, float]]


def parse_spotting(content: str, width: int, height: int) -> list[tuple[str, Polygon | None]]:
    """「Spotting:」の返事を、(文字, 4 隅の画素座標) の並びにする。

    1 行が `本文<|LOC_x1|><|LOC_y1|>…<|LOC_x4|><|LOC_y4|>`。座標は 0〜999 の目盛りで、
    縮めて渡した画像でも縦横比は同じなので、元の画像の幅・高さを掛ければ戻る。
    位置の付かない行(途中で切れたなど)は、文字だけ返す。
    """
    out: list[tuple[str, Polygon | None]] = []
    for raw in content.splitlines():
        locs = [int(v) for v in _LOC.findall(raw)]
        text = _SPECIAL.sub("", raw).strip()
        if not text:
            continue
        poly: Polygon | None = None
        if len(locs) >= 8:
            v = locs[:8]
            poly = [
                (v[i] / LOC_SCALE * width, v[i + 1] / LOC_SCALE * height) for i in range(0, 8, 2)
            ]
        out.append((text, poly))
    return out


class Runaway(RuntimeError):
    """位置の付かない行が続き、読みが崩れたので打ち切った。

    画像に定規などが写っていて、`ruler.mask_rulers` で消せなかったときに起きる。
    範囲を切って読み直してもらうしかない。
    """


def _loc_ids(endpoint: str, timeout: float) -> range:
    """位置の印 `<|LOC_0|>`〜`<|LOC_999|>` のトークン番号(連番)。"""
    got = _post(
        f"{endpoint}/tokenize",
        {"content": f"<|LOC_0|><|LOC_{LOC_SCALE}|>", "parse_special": True},
        timeout,
    )["tokens"]
    return range(got[0], got[-1] + 1)


def _stream(endpoint: str, body: dict, loc: range, timeout: float) -> str:
    """`/completion` を少しずつ受け取り、位置の印を `<|LOC_n|>` に戻した全文を返す。

    **本文はトークンではなく `content` から取る。** 漢字 1 字が複数のトークンに分かれると、
    llama-server は字がそろうまで送らず、そろった回にはトークンを最後の 1 つしか載せない
    (2026-09-25 に実測。「睨」の 3 トークンのうち 1 つしか届かず、文字化けした)。
    位置の印は 1 つで完結したトークンなので、番号から `<|LOC_n|>` に戻せる。

    位置の付かない行が `RUNAWAY_LINES` 続いたら、接続を切って `Runaway` を投げる
    (接続が切れると llama-server も生成をやめる)。
    """
    req = urllib.request.Request(
        f"{endpoint}/completion",
        data=json.dumps({**body, "stream": True, "return_tokens": True}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    out: list[str] = []
    line, placed, unplaced = "", False, 0
    with urllib.request.urlopen(req, timeout=timeout) as res:
        for raw in res:
            if not raw.startswith(b"data: "):
                continue
            chunk = json.loads(raw[6:])
            text = chunk.get("content", "")
            out.append(text)
            for tok in chunk.get("tokens") or []:
                if tok in loc:
                    out.append(f"<|LOC_{tok - loc.start}|>")
                    placed = True
            line += text
            while "\n" in line:
                done, line = line.split("\n", 1)
                if done.strip():
                    unplaced = 0 if placed else unplaced + 1
                placed = False
                if unplaced >= RUNAWAY_LINES:
                    raise Runaway(f"{unplaced} lines without a position")
            if chunk.get("stop"):
                break
    return "".join(out)


def spot(
    endpoint: str, img: Image.Image, timeout: float = 300.0
) -> list[tuple[str, Polygon | None]]:
    """行ごとの文字と位置を返す(PaddleOCR-VL 1.5 以降)。

    **`/v1/chat/completions` は使えない。** 位置は `<|LOC_n|>` という特殊な印で返り、
    llama-server の OpenAI 互換の窓口はそれを消して本文だけにする(2026-09-25 に実測。
    位置が無いように見えて、「Paddle は行の位置を返さない」と誤解していた)。
    そこで、会話の型を文字列にしてから下の窓口 `/completion` に投げ、
    返った印の番号(トークン)から位置を拾う(`_stream`)。

    読む前に定規を背景の色で塗りつぶす(`ruler.py`)。位置は動かさないので座標はそのまま。
    それでも崩れたら `Runaway`。
    """
    data = _jpeg_base64(mask_rulers(img))
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + data}},
                {"type": "text", "text": SPOT_PROMPT},
            ],
        }
    ]
    prompt = _post(f"{endpoint}/apply-template", {"messages": messages}, timeout)["prompt"]
    content = _stream(
        endpoint,
        {
            "prompt": {"prompt_string": prompt, "multimodal_data": [data]},
            "temperature": 0,
            "n_predict": MAX_TOKENS,
        },
        _loc_ids(endpoint, timeout),
        timeout,
    )
    w, h = img.size
    return parse_spotting(content, w, h)


def recognize(
    endpoint: str, img: Image.Image, timeout: float = 300.0, *, prompt: str = PROMPT
) -> str:
    """llama-server(PaddleOCR-VL 系のアーキテクチャ全般)に画像 1 枚を投げる。

    `prompt` は既定で PaddleOCR-VL のもの。Yigdzin は行クロップに特化した別の
    指示文を渡す(`yigdzin/pipeline.py`)。`model` の値は llama-server 側では
    無視される(`-m` で読み込んだものを常に使う)ので、ここでは固定のままでよい。
    """
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
                        {"type": "text", "text": prompt},
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
