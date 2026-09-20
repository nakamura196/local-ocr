"""取得とサーバの起動・停止。画面から呼ばれる側で、Flet には依存しない。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from collections import deque
from collections.abc import Callable
from pathlib import Path

from . import assets
from .paths import data_dir, is_windows, settings_file

DEFAULT_PORT = 8080
# 起動スクリプト版と同じ既定。校正の画面からしか呼べないようにしている。
DEFAULT_ORIGIN = "https://tei-iiif-editor.vercel.app"

Progress = Callable[[str, float | None], None]


def _download(url: str, dest: Path, approx: int, on_progress: Progress, label: str) -> None:
    """途中で落ちても部分ファイルを残さないよう、.part に書いてから差し替える。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "PaddleOCR-Local"})
    with urllib.request.urlopen(req) as res, open(part, "wb") as f:
        total = int(res.headers.get("Content-Length") or 0) or approx
        got = 0
        while chunk := res.read(1024 * 256):
            f.write(chunk)
            got += len(chunk)
            on_progress(label, min(got / total, 1.0) if total else None)
    part.replace(dest)


def _extract(archive: Path, into: Path) -> None:
    """llama.cpp の配布物を展開する。

    配布物によって、中身が 1 階層のフォルダに入っている版と、そのまま並んでいる
    版がある。展開後に llama-server を探し直して、どちらでも動くようにする。
    """
    into.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(into)
    else:
        with tarfile.open(archive) as t:
            t.extractall(into)

    want = assets.server_path().name
    if not (into / want).is_file():
        found = next((p for p in into.rglob(want) if p.is_file()), None)
        if found is None:
            raise RuntimeError(f"展開しましたが {want} が見つかりません")
        # 実行ファイルと同じ階層の中身をまとめて 1 つ上へ移す(dylib を置き去りにしない)。
        for item in found.parent.iterdir():
            target = into / item.name
            if target.exists():
                continue
            shutil.move(str(item), str(target))

    if not is_windows():
        # ネットから取ったファイルに macOS が付ける印を外す。これが無いと起動できない。
        subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(into)], check=False)
        for p in into.glob("llama-*"):
            if p.is_file():
                p.chmod(0o755)
    archive.unlink(missing_ok=True)


class Runtime:
    """取得済みかを見て、llama-server を起動・停止する。"""

    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None
        # 画面の下に出す用。全部ためると長時間動かしたとき際限なく増える。
        self.log: deque[str] = deque(maxlen=400)
        self._lock = threading.Lock()

    # --- 設定 -------------------------------------------------------------
    def load_settings(self) -> dict:
        try:
            return json.loads(settings_file().read_text("utf-8"))
        except (OSError, ValueError):
            return {}

    def save_settings(self, **kv) -> None:
        s = self.load_settings() | kv
        settings_file().parent.mkdir(parents=True, exist_ok=True)
        settings_file().write_text(json.dumps(s, ensure_ascii=False, indent=2), "utf-8")

    @property
    def port(self) -> int:
        return int(self.load_settings().get("port", DEFAULT_PORT))

    @property
    def origin(self) -> str:
        return str(self.load_settings().get("origin", DEFAULT_ORIGIN))

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    # --- 取得 -------------------------------------------------------------
    def fetch_missing(self, on_progress: Progress) -> None:
        for a in assets.missing():
            _download(a.url, a.dest, a.approx_bytes, on_progress, a.label)
            if a.extract_to is not None:
                on_progress(f"{a.label}を展開しています", None)
                _extract(a.dest, a.extract_to)

    # --- サーバ -----------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        with self._lock:
            if self.running:
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
                "--cors-origins", self.origin,
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
            if not self.running:
                return False
            time.sleep(1.0)
        return False
