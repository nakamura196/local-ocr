"""llama-server を立てる前の、ポートの選び方。

2026-10-03、宮崎さんの Mac で Yigdzin-1 だけが「OCR を起動できませんでした」になった。
決まったポート(8081)を別のアプリが使っていると、llama-server は bind に失敗して
すぐ終わる。手元で 8081 をふさぐと同じ文面が出た。ここでは本物は立てず、
立てようとしたコマンドのポートだけを見る。
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from local_ocr.core import assets, bundled, child, prefs, runtime


@pytest.fixture(autouse=True)
def settings(tmp_path: Path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(prefs, "settings_file", lambda: path)


class _Proc:
    stdout = None

    def poll(self) -> None:
        return None


@pytest.fixture
def spawned(monkeypatch, tmp_path: Path) -> list[list[str]]:
    cmds: list[list[str]] = []
    monkeypatch.setattr(assets, "server_path", lambda: tmp_path / "llama-server")
    monkeypatch.setattr(bundled, "ensure_executable", lambda _p: None)

    def spawn(cmd: list[str]) -> _Proc:
        cmds.append(cmd)
        return _Proc()

    monkeypatch.setattr(child, "spawn", spawn)
    return cmds


def _runtime(port: int) -> runtime.Runtime:
    return runtime.Runtime(
        model_path=Path("m.gguf"),
        mmproj_path=Path("p.gguf"),
        missing=list,
        port_pref_key="port_test",
        default_port=port,
    )


def _port_of(cmd: list[str]) -> int:
    return int(cmd[cmd.index("--port") + 1])


def _free() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_a_free_port_is_used_as_is(spawned):
    port = _free()
    rt = _runtime(port)
    rt.start()
    assert _port_of(spawned[0]) == port
    assert rt.endpoint == f"http://127.0.0.1:{port}"


def test_a_port_held_by_another_app_is_skipped(spawned):
    # llama-server ではない何か(/health に答えない)がふさいでいる。
    with socket.socket() as other:
        other.bind(("127.0.0.1", 0))
        other.listen()
        taken = other.getsockname()[1]
        rt = _runtime(taken)
        rt.start()
        moved = _port_of(spawned[0])
        assert moved != taken
        # 読ませる先も、移った先になっている。
        assert rt.endpoint == f"http://127.0.0.1:{moved}"
    # 移った先は保存しない。次の起動ではまた決まったポートから試す。
    assert prefs.get("port_test") is None


def test_the_last_error_lines_are_kept_for_the_screen():
    rt = _runtime(_free())
    rt.log.extend([
        "0.00.064 I cmn  common_params_print_info: verbosity = 3",
        "0.00.064 E srv  start: couldn't bind HTTP server socket, port: 8081",
        "0.00.064 I srv  operator(): cleaning up before exit...",
        "0.00.064 E srv  llama_server: exiting due to HTTP server error",
    ])
    said = rt.failure()
    assert "couldn't bind" in said
    assert "cleaning up" not in said
