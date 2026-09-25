"""ほかの道具に開く窓口(HTTP)。本物の HTTP を立て、読む道具は偽物にして確かめる。

見たいのは 3 つ。
- 一覧にない頁は断る(読ませる前に)。一覧にある頁には、読んだ結果が届く
- 行の位置(4 隅)が、元の画像の画素で返る
- 前からある 2 つの口(/health・/v1/chat/completions)が、PaddleOCR-VL へそのまま渡る
"""

from __future__ import annotations

import base64
import io
import json
import socket
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from PIL import Image

from local_ocr.core import bridge, gateway, ocr, prefs
from local_ocr.engines.base import Line, Result

EDITOR = "https://tei-iiif-editor.vercel.app"


@pytest.fixture(autouse=True)
def settings(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(prefs, "settings_file", lambda: tmp_path / "settings.json")
    bridge.set_enabled(True)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _FakeEngine:
    id = "paddle-vl"
    label = "Paddle"
    platforms = frozenset({"darwin", "win32", "linux"})

    def __init__(self, fetched: bool = True) -> None:
        self.fetched = fetched
        self.seen: list[tuple[int, int]] = []

    def available(self) -> bool:
        return self.fetched

    def prepare(self, on_progress) -> None:
        pass

    def recognize(self, img: Image.Image) -> Result:
        self.seen.append(img.size)
        return Result(text="文字だけ")

    def recognize_lines(self, img: Image.Image) -> Result:
        self.seen.append(img.size)
        line = Line(text="見相應受", box=(10, 20, 30, 400), polygon=[(10, 20), (40, 20), (40, 420), (10, 420)])
        return Result(text="見相應受", lines=[line])


class _Upstream(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    def do_GET(self) -> None:
        self.send_response(503)
        self.end_headers()
        self.wfile.write(b'{"error":"loading"}')

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers["Content-Length"]))
        out = json.dumps({"echo": json.loads(body)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)


@pytest.fixture
def served():
    engine = _FakeEngine()
    up_port = _free_port()
    upstream = ThreadingHTTPServer(("127.0.0.1", up_port), _Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    gw = gateway.Gateway(engines=lambda: [engine], upstream=lambda: f"http://127.0.0.1:{up_port}")
    port = _free_port()
    gw.start(port)
    yield f"http://127.0.0.1:{port}", engine
    gw.stop()
    upstream.shutdown()
    upstream.server_close()


def _image() -> str:
    buf = io.BytesIO()
    Image.new("RGB", (120, 480), "white").save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _call(url: str, body: dict | None = None, origin: str | None = EDITOR, method: str | None = None):
    headers = {"Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return res.status, dict(res.headers), res.read()
    except urllib.error.HTTPError as exc:
        with exc:
            return exc.code, dict(exc.headers), exc.read()


def test_the_editor_gets_lines_with_positions(served):
    base, _ = served
    status, headers, body = _call(f"{base}/v1/ocr", {"image": _image()})
    assert status == 200
    assert headers["Access-Control-Allow-Origin"] == EDITOR
    out = json.loads(body)
    assert out["engine"] == "paddle-vl"
    assert (out["width"], out["height"]) == (120, 480)
    assert out["lines"][0]["text"] == "見相應受"
    assert out["lines"][0]["box"] == {"x": 10, "y": 20, "w": 30, "h": 400}
    assert out["lines"][0]["polygon"][2] == [40, 420]


def test_text_only_when_lines_are_not_wanted(served):
    base, _ = served
    status, _, body = _call(f"{base}/v1/ocr", {"image": _image(), "lines": False})
    assert status == 200
    assert json.loads(body)["text"] == "文字だけ"


def test_a_page_not_on_the_list_is_refused_before_reading(served):
    base, engine = served
    status, headers, _ = _call(f"{base}/v1/ocr", {"image": _image()}, origin="https://evil.example")
    assert status == 403
    assert "Access-Control-Allow-Origin" not in headers
    assert engine.seen == []


def test_closing_refuses_even_the_editor(served):
    base, engine = served
    bridge.set_enabled(False)
    status, _, _ = _call(f"{base}/v1/ocr", {"image": _image()})
    assert status == 403
    assert engine.seen == []


def test_a_foreign_host_name_is_refused(served):
    """よその名前を 127.0.0.1 に向け直す手口(DNS リバインディング)。"""
    base, _ = served
    req = urllib.request.Request(f"{base}/v1/engines", headers={"Host": "evil.example"})
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(req, timeout=10)
    err.value.close()
    assert err.value.code == 403


def test_preflight_answers_the_editor(served):
    base, _ = served
    req = urllib.request.Request(
        f"{base}/v1/ocr",
        method="OPTIONS",
        headers={
            "Origin": EDITOR,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Private-Network": "true",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        assert res.status == 204
        assert res.headers["Access-Control-Allow-Origin"] == EDITOR
        assert "POST" in res.headers["Access-Control-Allow-Methods"]
        assert res.headers["Access-Control-Allow-Private-Network"] == "true"


def test_a_script_on_this_machine_needs_no_origin(served):
    base, _ = served
    status, _, body = _call(f"{base}/v1/engines", origin=None)
    assert status == 200
    assert json.loads(body)["engines"][0] == {"id": "paddle-vl", "label": "Paddle", "ready": True, "lines": True}


def test_an_engine_not_fetched_is_not_fetched_from_outside(served):
    base, engine = served
    engine.fetched = False
    status, _, body = _call(f"{base}/v1/ocr", {"image": _image()})
    assert status == 409
    assert json.loads(body)["error"] == "not_fetched"


def test_bad_input_is_answered_not_crashed(served):
    base, _ = served
    assert _call(f"{base}/v1/ocr", {"image": "not an image"})[0] == 400
    assert _call(f"{base}/v1/ocr", {"engine": "nope", "image": _image()})[0] == 404


def test_the_old_paths_are_relayed_to_paddle(served):
    """エディタはいまこの 2 つで話している。直さなくても動き続けること。"""
    base, _ = served
    status, headers, _ = _call(f"{base}/health")
    assert status == 503  # 読み込み中はそのまま 503(エディタは「起動中」と出す)
    assert headers["Access-Control-Allow-Origin"] == EDITOR
    status, _, body = _call(f"{base}/v1/chat/completions", {"messages": ["x"]})
    assert status == 200
    assert json.loads(body) == {"echo": {"messages": ["x"]}}


# --- 「Spotting:」の返事の読み方 --------------------------------------------
def test_spotting_output_becomes_pixel_polygons():
    content = (
        "567892801234<|LOC_945|><|LOC_12|><|LOC_966|><|LOC_12|><|LOC_966|><|LOC_981|><|LOC_945|><|LOC_981|>\n"
        "見相應受<|LOC_0|><|LOC_0|><|LOC_999|><|LOC_0|><|LOC_999|><|LOC_999|><|LOC_0|><|LOC_999|>\n"
        "途中で切れた行</s>"
    )
    lines = ocr.parse_spotting(content, 2000, 1000)
    assert [t for t, _ in lines] == ["567892801234", "見相應受", "途中で切れた行"]
    assert lines[1][1] == [(0.0, 0.0), (2000.0, 0.0), (2000.0, 1000.0), (0.0, 1000.0)]
    assert lines[2][1] is None
