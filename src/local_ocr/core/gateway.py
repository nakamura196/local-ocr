"""ほかの道具に開く窓口の本体(HTTP)。設定の「ほかの道具から使えるようにする」で開く。

待つのは 127.0.0.1 の 1 つのポート(既定 8080)だけ。出すものは 3 つ。

    GET  /v1/engines            読む道具の一覧(取得済みか、行の位置を返せるか)
    POST /v1/ocr                {engine, image, lines} → {text, lines:[{text, box, polygon}], …}
    GET  /health                PaddleOCR-VL の状態(下の 2 つと合わせて、前からある口)
    POST /v1/chat/completions   PaddleOCR-VL の llama-server へそのまま渡す

**特定の相手に合わせない。** 中身は `engines/base.py` の `recognize` をそのまま外に出すだけ。
PaddleOCR-VL は、`lines` を付けると「Spotting:」で行の位置まで返す(`engines/paddle_vl.py`)。
読みが崩れて打ち切ったとき(定規など、`ocr.Runaway`)は 422 `{"error": "runaway"}`。

下の 2 つは、この窓口より前の作り(llama-server を 8080 にそのまま立てていた)との互換のため。
TEI/IIIF エディタはいまこの 2 つで話しているので、エディタを直さなくても動き続ける。

繋いでよい相手はここで見る(`core/bridge.py` の一覧)。llama-server 自身は誰も通さない。
一覧は毎回読むので、相手を足したり外したりしても**立て直さなくてよい**。
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image, UnidentifiedImageError

from ..engines.base import Engine, Result, runs_here
from . import bridge
from .ocr import Runaway

DEFAULT_ENGINE = "paddle-vl"
# 受け取る大きさの上限。ページ画像 1 枚なら十分で、取り違えた巨大なものは断る。
MAX_BODY = 64 * 1024 * 1024


def decode_image(value: str) -> Image.Image:
    """`data:image/...;base64,…` でも、base64 の中身だけでも受ける。"""
    if value.startswith("data:"):
        value = value.split(",", 1)[-1]
    try:
        raw = base64.b64decode(value, validate=False)
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (binascii.Error, UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("image") from exc
    return img


def result_json(engine: Engine, img: Image.Image, result: Result, seconds: float) -> dict:
    w, h = img.size
    return {
        "engine": engine.id,
        "width": w,
        "height": h,
        "seconds": round(seconds, 3),
        "text": result.text,
        "lines": [
            {
                "text": ln.text,
                "box": (
                    {"x": ln.box[0], "y": ln.box[1], "w": ln.box[2], "h": ln.box[3]}
                    if ln.box
                    else None
                ),
                "polygon": [list(p) for p in ln.polygon] if ln.polygon else None,
            }
            for ln in result.lines
        ],
    }


class Gateway:
    """窓口の立ち上げ・停止。読む道具そのものは持たず、渡されたものを使う。

    `engines` は画面と同じ道具の一覧を返す関数。**別に作らない。** PaddleOCR-VL は
    サーバを 1 つしか立てないので、別に作ると同じ重みを二度読むことになる。
    `upstream` は PaddleOCR-VL の llama-server の宛先(前からある 2 つの口の渡し先)。
    """

    def __init__(
        self,
        engines: Callable[[], list[Engine]],
        upstream: Callable[[], str | None],
    ) -> None:
        self._engines = engines
        self._upstream = upstream
        self._server: ThreadingHTTPServer | None = None
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    @property
    def running(self) -> bool:
        return self._server is not None

    def start(self, port: int) -> None:
        """立てる。ポートが塞がっていたら `OSError`(ほかのプログラムが使っている)。"""
        if self._server is not None:
            return
        handler = _handler_for(self)
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        server.daemon_threads = True
        self._server = server
        threading.Thread(target=server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            server.shutdown()
            server.server_close()

    # --- 読む -------------------------------------------------------------
    def engine_list(self) -> list[dict]:
        return [
            {
                "id": e.id,
                "label": e.label,
                "ready": e.available(),
                # 行の位置を返せるか。Apple Vision・NDL・Yigdzin は元から、
                # PaddleOCR-VL は「Spotting:」(`recognize_lines`)で返す。
                "lines": True,
            }
            for e in self._engines()
            if runs_here(e)
        ]

    def _lock(self, engine_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(engine_id, threading.Lock())

    def ocr(self, body: dict) -> tuple[int, dict]:
        engine_id = str(body.get("engine") or DEFAULT_ENGINE)
        engine = next((e for e in self._engines() if e.id == engine_id and runs_here(e)), None)
        if engine is None:
            return 404, {"error": "unknown_engine", "engine": engine_id}
        if not engine.available():
            # 取得(数百 MB〜2GB)を、よそからの呼び出しで勝手に始めない。
            return 409, {"error": "not_fetched", "engine": engine_id}
        try:
            img = decode_image(str(body.get("image") or ""))
        except ValueError:
            return 400, {"error": "bad_image"}
        want_lines = body.get("lines", True) is not False
        with self._lock(engine_id):
            started = time.monotonic()
            engine.prepare(lambda _msg, _frac: None)
            reader = getattr(engine, "recognize_lines", None) if want_lines else None
            try:
                result = reader(img) if reader else engine.recognize(img)
            except Runaway:
                # 定規などに引っかかって読みが崩れた。呼び手には「範囲を切って読み直して」と
                # 案内してもらう(500 の「失敗」とは分ける)。
                return 422, {"error": "runaway", "engine": engine_id}
            seconds = time.monotonic() - started
        return 200, result_json(engine, img, result, seconds)

    # --- 前からある口 -------------------------------------------------------
    def relay(self, method: str, path: str, data: bytes | None) -> tuple[int, bytes, str]:
        target = self._upstream()
        if not target:
            return 503, b'{"error":"paddle_unavailable"}', "application/json"
        req = urllib.request.Request(
            target + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if data is not None else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as res:
                return res.status, res.read(), res.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), exc.headers.get("Content-Type", "application/json")
        except OSError:
            # 立ち上がる途中(または止まっている)。エディタは 503 を「起動中」と読む。
            return 503, b'{"error":"paddle_unavailable"}', "application/json"


def _handler_for(gateway: Gateway) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "LocalOCR"

        def log_message(self, format: str, *args: object) -> None:
            pass  # 画面の無いところに出しても誰も読まない

        # --- 繋いでよい相手 -----------------------------------------------
        def _origin_ok(self) -> bool:
            """通してよい呼び出しか。

            - **Host が 127.0.0.1 / localhost でなければ断る。** よその名前を 127.0.0.1 に
              向け直して頁と同じ出どころに見せかける手口(DNS リバインディング)を防ぐ
            - Origin の無い呼び出し(同じ機械の端末・スクリプト)は通す。待っているのは
              127.0.0.1 だけなので、同じ機械の中からに限られる。ブラウザは POST には
              必ず Origin を付けるので、頁から読ませる呼び出しは一覧で絞れる
            """
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
            if host not in ("127.0.0.1", "localhost", "::1"):
                return False
            origin = self.headers.get("Origin")
            return origin is None or bridge.allows(origin)

        def _cors_headers(self) -> None:
            origin = self.headers.get("Origin")
            if origin is not None and bridge.allows(origin):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")

        def _send(self, status: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(status)
            self._cors_headers()
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: dict | list) -> None:
            self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"))

        def _refuse(self) -> None:
            self._json(403, {"error": "origin_not_allowed"})

        def _body(self) -> bytes | None:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                return None
            return self.rfile.read(length) if length else b""

        # --- 口 -----------------------------------------------------------
        def do_OPTIONS(self) -> None:
            if not self._origin_ok():
                self._refuse()
                return
            self.send_response(204)
            self._cors_headers()
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            # Chrome が https の頁から 127.0.0.1 へ繋ぐときに尋ねてくることがある。
            if self.headers.get("Access-Control-Request-Private-Network"):
                self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:
            if not self._origin_ok():
                self._refuse()
                return
            path = self.path.split("?", 1)[0]
            if path == "/v1/engines":
                self._json(200, {"engines": gateway.engine_list()})
            elif path == "/health":
                status, body, ctype = gateway.relay("GET", "/health", None)
                self._send(status, body, ctype)
            else:
                self._json(404, {"error": "not_found"})

        def do_POST(self) -> None:
            if not self._origin_ok():
                self._refuse()
                return
            path = self.path.split("?", 1)[0]
            data = self._body()
            if data is None:
                self._json(413, {"error": "too_large"})
                return
            if path == "/v1/ocr":
                try:
                    body = json.loads(data.decode("utf-8") or "{}")
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._json(400, {"error": "bad_json"})
                    return
                try:
                    status, payload = gateway.ocr(body if isinstance(body, dict) else {})
                except Exception as exc:  # noqa: BLE001 - 読み手の失敗は文面にして返す
                    status, payload = 500, {"error": "failed", "detail": str(exc)}
                self._json(status, payload)
            elif path == "/v1/chat/completions":
                status, out, ctype = gateway.relay("POST", path, data)
                self._send(status, out, ctype)
            else:
                self._json(404, {"error": "not_found"})

    return Handler
