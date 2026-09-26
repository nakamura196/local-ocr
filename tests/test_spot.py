"""PaddleOCR-VL の「Spotting:」の読み方と、写り込んだ定規の扱い。

見たいのは 3 つ。
- 本文は `content` から、位置は印の番号から拾う(漢字が複数トークンに割れても化けない)
- 位置の付かない行が続いたら打ち切る(定規の数字を数え続けるのを止める)
- 定規だけを塗りつぶし、本文の列や本の縁は塗らない
"""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import numpy as np
import pytest
from PIL import Image

from local_ocr.core import ocr, ruler

LOC0 = 1000  # 偽の llama-server での <|LOC_0|> の番号


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _loc(*values: int) -> list[dict]:
    return [{"content": "", "tokens": [LOC0 + v]} for v in values]


BOX = (100, 200, 300, 200, 300, 800, 100, 800)


class _Llama(BaseHTTPRequestHandler):
    chunks: ClassVar[list[dict]] = []

    def log_message(self, *args) -> None:
        pass

    def _json(self, obj: dict) -> None:
        out = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/apply-template":
            return self._json({"prompt": "PROMPT"})
        if self.path == "/tokenize":
            return self._json({"tokens": [LOC0, LOC0 + 999]})
        assert self.path == "/completion" and body["stream"] and body["return_tokens"]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        try:
            for c in self.chunks + [{"content": "", "tokens": [], "stop": True}]:
                self.wfile.write(b"data: " + json.dumps(c).encode() + b"\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # 打ち切りで呼び手が接続を切った


@pytest.fixture
def llama():
    port = _free_port()
    handler = type("Handler", (_Llama,), {"chunks": []})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}", handler
    server.shutdown()
    server.server_close()


def _page() -> Image.Image:
    return Image.new("RGB", (1000, 1000), (200, 190, 160))


def test_text_comes_from_content_and_positions_from_tokens(llama):
    endpoint, handler = llama
    handler.chunks = [
        # 「睨」は 3 トークン。llama-server は字がそろった回に最後の 1 つだけを載せる。
        {"content": "睨", "tokens": [3]},
        *_loc(*BOX),
        {"content": "\n", "tokens": [23]},
        {"content": "視也", "tokens": [7, 8]},
        *_loc(*BOX),
    ]
    lines = ocr.spot(endpoint, _page())
    assert [t for t, _ in lines] == ["睨", "視也"]
    corners = [v for xy in lines[0][1] for v in xy]
    assert corners == pytest.approx(
        [100.1, 200.2, 300.3, 200.2, 300.3, 800.8, 100.1, 800.8], abs=0.1
    )


def test_counting_without_positions_is_cut_short(llama):
    endpoint, handler = llama
    ok = [{"content": "本文", "tokens": [5]}, *_loc(*BOX), {"content": "\n", "tokens": [23]}]
    counting = [{"content": f"{n}\n", "tokens": [n % 10 + 4, 23]} for n in range(1, 400)]
    handler.chunks = ok + counting
    with pytest.raises(ocr.Runaway):
        ocr.spot(endpoint, _page())


def test_a_few_unplaced_lines_are_kept(llama):
    endpoint, handler = llama
    handler.chunks = [
        {"content": "170\n1\n2\n", "tokens": [4, 23, 4, 23, 5, 23]},
        {"content": "本文", "tokens": [5]},
        *_loc(*BOX),
    ]
    lines = ocr.spot(endpoint, _page())
    assert [t for t, _ in lines] == ["170", "1", "2", "本文"]
    assert [p is not None for _, p in lines] == [False, False, False, True]


# --- 定規 ---------------------------------------------------------------------
BG = 160


def _photo(ruler_at: str | None = "right", w: int = 2400, h: int = 1800) -> np.ndarray:
    """撮影台(無地)の上に本(縦の文字列)と定規を置いた合成画像。"""
    rng = np.random.default_rng(0)
    a = np.full((h, w), BG, dtype=np.float32) + rng.normal(0, 1.0, (h, w))
    # 本: 上下に余白のある紙、その中に縦の文字列(不規則な濃い点の並び)。
    a[100 : h - 100, 150 : w - 250] = 200
    for x in range(250, w - 350, 90):
        col = rng.random((h - 400, 50)) < 0.25
        a[200 : h - 200, x : x + 50][col] = 40
    # 定規: 白地に 1mm(6 画素)ごとの目盛り。
    if ruler_at == "right":
        a[:, w - 110 : w - 40] = np.where(np.arange(h) % 6 < 2, 30, 235)[:, None]
    elif ruler_at == "bottom":
        a[h - 80 : h - 20, :] = np.where(np.arange(w) % 6 < 2, 30, 235)
    return np.clip(a, 0, 255)


def _img(a: np.ndarray) -> Image.Image:
    return Image.fromarray(a.astype(np.uint8)).convert("RGB")


def test_a_ruler_on_the_edge_is_found():
    boxes = ruler.find_rulers(_img(_photo("right")))
    assert len(boxes) == 1
    x0, y0, x1, y1 = boxes[0]
    assert 2270 <= x0 <= 2295 and 2355 <= x1 <= 2380 and (y0, y1) == (0, 1800)


def test_a_ruler_along_the_bottom_is_found():
    boxes = ruler.find_rulers(_img(_photo("bottom")))
    assert len(boxes) == 1
    x0, y0, x1, y1 = boxes[0]
    assert (x0, x1) == (0, 2400) and 1710 <= y0 <= 1725 and 1775 <= y1 <= 1790


def test_no_ruler_no_change():
    img = _img(_photo(None))
    assert ruler.find_rulers(img) == []
    assert ruler.mask_rulers(img) is img


def test_text_running_to_the_edge_is_not_a_ruler():
    """本文を縁まで切り詰めた画像。端の列は上から下まで通るが、目盛りが無い。"""
    a = _photo(None)[200:1600, 250:2000]
    assert ruler.find_rulers(_img(a)) == []


def test_the_ruler_is_painted_with_the_background():
    out = np.asarray(ruler.mask_rulers(_img(_photo("right"))).convert("L"), dtype=np.float32)
    assert abs(out[:, 2300:2350].mean() - BG) < 3
    # 本の中は触らない。
    assert out[200:1600, 250:2000].mean() < 190
