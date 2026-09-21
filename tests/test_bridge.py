"""ほかの道具に開く窓口。画面を出さずに確かめられるところを見る。

**いちばん見たいのは「閉じている間は誰も通さない」。** `--cors-origins` を
省くと llama-server の既定が `*` になり、閉じているつもりで全開になる。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from local_ocr.core import bridge, prefs


@pytest.fixture(autouse=True)
def settings(tmp_path: Path, monkeypatch):
    """本物の設定ファイル(利用者のホーム)を触らない。"""
    path = tmp_path / "settings.json"
    monkeypatch.setattr(prefs, "settings_file", lambda: path)
    return path


def test_closed_by_default_and_nobody_gets_through():
    assert bridge.enabled() is False
    # `*` でも空でもなく、誰も名乗れない相手が入る。
    assert bridge.cors_value() == bridge.DENY_ALL
    assert "*" not in bridge.cors_value()


def test_opening_lets_the_listed_pages_through():
    bridge.set_allowed_origins(["https://example.com", "http://localhost:3000"])
    bridge.set_enabled(True)
    assert bridge.cors_value() == "https://example.com,http://localhost:3000"


def test_an_empty_list_lets_nobody_through_even_while_open():
    bridge.set_enabled(True)
    bridge.set_allowed_origins([])
    # 空の一覧を既定で埋め戻さない(外したのに戻っては困る)。
    assert bridge.allowed_origins() == []
    assert bridge.cors_value() == bridge.DENY_ALL


def test_the_launch_script_setting_is_carried_over():
    """起動スクリプト版と、この窓口より前の版は 1 つだけ持っていた。"""
    prefs.save(origin="https://tei-iiif-editor.vercel.app")
    assert bridge.allowed_origins() == ["https://tei-iiif-editor.vercel.app"]


def test_the_default_is_the_proofreading_page():
    assert bridge.allowed_origins() == list(bridge.DEFAULT_ORIGINS)


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("https://example.com", "https://example.com"),
        ("  https://example.com/  ", "https://example.com"),
        ("http://localhost:3000", "http://localhost:3000"),
        # 頭を省いて書かれたら https として読む。
        ("example.com", "https://example.com"),
        ("localhost:3000", "https://localhost:3000"),
    ],
)
def test_origins_are_stored_the_way_a_browser_says_them(typed: str, expected: str):
    assert bridge.normalize_origin(typed) == expected


@pytest.mark.parametrize(
    ("typed", "reason"),
    [
        ("", "empty"),
        ("   ", "empty"),
        ("*", "wildcard"),
        ("https://*.example.com", "wildcard"),
        ("ftp://example.com", "scheme"),
        # 道(パス)まで書かれても落とす。ブラウザの Origin に道は入らないので、
        # 残すと一生一致しない。
        ("https://example.com/editor", "path"),
        ("https://example.com/?a=1", "path"),
    ],
)
def test_what_cannot_be_an_origin_is_refused(typed: str, reason: str):
    with pytest.raises(ValueError, match=reason):
        bridge.normalize_origin(typed)


def test_adding_and_removing_keeps_the_order_and_drops_duplicates():
    b = bridge.Bridge(_FakeRuntime())
    bridge.set_allowed_origins(["https://a.example"])
    b.add_origin("https://b.example")
    b.add_origin("https://a.example")
    assert b.origins == ["https://a.example", "https://b.example"]
    b.remove_origin("https://a.example")
    assert b.origins == ["https://b.example"]


def test_turning_on_stands_the_server_back_up_with_the_new_list():
    rt = _FakeRuntime()
    b = bridge.Bridge(rt)
    b.turn_on()
    # 閉じた状態で立っていたものは、繋いでよい相手を入れ替えるため立て直す。
    assert rt.calls == ["stop", "start", "wait"]
    assert b.enabled is True
    assert b.open is True
    b.turn_off()
    assert rt.calls[-1] == "stop"
    assert b.enabled is False


def test_a_server_that_will_not_come_up_leaves_the_setting_on():
    """黙って閉じない。開けるつもりで開いていないことを、画面に出させる。"""
    rt = _FakeRuntime(comes_up=False)
    b = bridge.Bridge(rt)
    with pytest.raises(RuntimeError):
        b.turn_on()
    assert b.enabled is True
    assert b.open is False


class _FakeRuntime:
    """llama-server は立てない。呼ばれた順だけ見る。"""

    def __init__(self, comes_up: bool = True) -> None:
        self.calls: list[str] = []
        self.ready = False
        self._comes_up = comes_up
        self.port = 8080
        self.endpoint = "http://127.0.0.1:8080"

    def start(self) -> None:
        self.calls.append("start")
        self.ready = self._comes_up

    def stop(self) -> None:
        self.calls.append("stop")
        self.ready = False

    def wait_ready(self, timeout: float = 180.0) -> bool:
        self.calls.append("wait")
        return self.ready

    def health(self, timeout: float = 1.0) -> str:
        return "ready" if self.ready else "down"
