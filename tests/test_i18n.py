"""画面の言語の決め方。"""

import sys

import pytest

from local_ocr.ui import i18n


@pytest.fixture(autouse=True)
def _no_saved_choice(monkeypatch):
    monkeypatch.setattr(i18n.prefs, "get", lambda key, default=None: None)


def test_os_setting_wins_without_lang(monkeypatch):
    """Finder から起動すると LANG が無い。それでも OS の設定が日本語なら日本語。"""
    monkeypatch.delenv("LANG", raising=False)
    monkeypatch.setattr(i18n.locale, "getlocale", lambda: ("en_US", "UTF-8"))
    monkeypatch.setattr(i18n, "_os_ui_language", lambda: "ja-JP")
    assert i18n.current() == "ja"


def test_os_setting_english(monkeypatch):
    monkeypatch.setenv("LANG", "ja_JP.UTF-8")
    monkeypatch.setattr(i18n, "_os_ui_language", lambda: "en-US")
    assert i18n.current() == "en"


def test_falls_back_to_lang(monkeypatch):
    monkeypatch.setattr(i18n, "_os_ui_language", lambda: "")
    monkeypatch.setattr(i18n.locale, "getlocale", lambda: (None, None))
    monkeypatch.setenv("LANG", "ja_JP.UTF-8")
    assert i18n.current() == "ja"


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS の設定を読む試験")
def test_reads_macos_setting_without_env(monkeypatch):
    monkeypatch.delenv("LANG", raising=False)
    assert i18n._os_ui_language() != ""
