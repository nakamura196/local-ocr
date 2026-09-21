"""取得とサーバの起動・停止。画面から呼ばれる側で、Flet には依存しない。"""

from __future__ import annotations

import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections import deque

from . import assets, bridge, fetch, prefs
from .fetch import Progress
from .paths import data_dir, is_windows

DEFAULT_PORT = 8080


class Runtime:
    """取得済みかを見て、llama-server を起動・停止する。"""

    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None
        # 同じポートで既に動いているものを借りているか。前の版のアプリや、
        # もう 1 つ開いたこのアプリが立てたサーバがこれにあたる。
        self._borrowed = False
        # 画面の下に出す用。全部ためると長時間動かしたとき際限なく増える。
        self.log: deque[str] = deque(maxlen=400)
        self._lock = threading.Lock()

    # --- 設定 -------------------------------------------------------------
    @property
    def port(self) -> int:
        return int(prefs.get("port", DEFAULT_PORT))

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    # --- 取得 -------------------------------------------------------------
    def fetch_missing(self, on_progress: Progress) -> None:
        fetch.download_all(assets.missing(), on_progress)

    # --- サーバ -----------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def ready(self) -> bool:
        """読ませられる状態か。自分で立てたものでも、借りているものでもよい。"""
        return self.running or self._borrowed

    def start(self) -> None:
        with self._lock:
            if self.ready:
                return
            # **同じポートで既に動いていたら、立ち上げ直さない。**
            # 立てても bind に失敗して静かに死に、こちらは相手のサーバに
            # 投げ続けることになる(重みの二重読み込みで 2GB 無駄にもなる)。
            if self.health() != "down":
                self._borrowed = True
                return
            server = assets.server_path()
            if not server.is_file():
                raise RuntimeError("先に取得を済ませてください")
            d = data_dir()
            cmd = [
                str(server),
                "-m", str(d / "PaddleOCR-VL-1.6.gguf"),
                "--mmproj", str(d / "PaddleOCR-VL-1.6-mmproj.gguf"),
                "--host", "127.0.0.1",
                "--port", str(self.port),
                "-c", "8192",
                "-ngl", "99",
                # **省いてはいけない。** 既定は `*` で、その機械で開いている
                # どの頁からでも投げられる状態になる。閉じている間は誰も
                # 名乗れない相手が入る (core/bridge.py)。
                "--cors-origins", bridge.cors_value(),
            ]
            # Windows でコンソールの黒い窓が一瞬出るのを抑える。
            flags = subprocess.CREATE_NO_WINDOW if is_windows() else 0  # type: ignore[attr-defined]
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=flags,
            )
            threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            self.log.append(line.rstrip())

    def stop(self) -> None:
        with self._lock:
            # 借りているだけのサーバは、こちらの都合で止めない。
            self._borrowed = False
            proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    def health(self, timeout: float = 1.0) -> str:
        """'ready' / 'loading' / 'down'。

        llama-server は重みを読んでいる間 /health に 503 を返す。これは
        「起動していない」ではなく「起動途中」なので、分けて返す。
        """
        try:
            with urllib.request.urlopen(f"{self.endpoint}/health", timeout=timeout) as r:
                return "ready" if r.status == 200 else "loading"
        except urllib.error.HTTPError as e:
            return "loading" if e.code == 503 else "down"
        except OSError:
            return "down"

    def wait_ready(self, timeout: float = 180.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.health() == "ready":
                return True
            if not self.ready:
                return False
            time.sleep(1.0)
        return False
