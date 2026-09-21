"""データの置き場所。

見張りたいのは、**前の名前のフォルダを取り残さないこと**。中身はモデルで
1.8GB あり、取り残すと利用者が黙って取り直すことになる（気づけない）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from local_ocr.core import paths


@pytest.fixture
def home(tmp_path, monkeypatch):
    """ホームを tmp に向け、macOS 側の道だけを見るようにする。"""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(paths, "is_windows", lambda: False)
    return tmp_path


def _support(home: Path, name: str) -> Path:
    return home / "Library" / "Application Support" / name


def test_uses_the_current_name_when_nothing_exists(home):
    assert paths.data_dir() == _support(home, paths.APP_DIR_NAME)


def test_moves_the_folder_from_the_former_name(home):
    former = _support(home, paths.FORMER_DIR_NAME)
    (former / "models").mkdir(parents=True)
    (former / "settings.json").write_text("{}")

    got = paths.data_dir()

    assert got == _support(home, paths.APP_DIR_NAME)
    assert (got / "models").is_dir()          # 中身ごと移っている
    assert (got / "settings.json").read_text() == "{}"
    assert not former.exists()                # 取り残していない


def test_keeps_the_current_folder_when_both_exist(home):
    """移したあとに前の名前が作られても、いま使っている方を壊さない。"""
    current = _support(home, paths.APP_DIR_NAME)
    current.mkdir(parents=True)
    (current / "settings.json").write_text('{"keep": true}')
    _support(home, paths.FORMER_DIR_NAME).mkdir(parents=True)

    got = paths.data_dir()

    assert got == current
    assert (got / "settings.json").read_text() == '{"keep": true}'


def test_the_launcher_script_folder_still_wins(home):
    """東洋文庫へ配った起動スクリプト版が残っている機械では、そちらを使う。"""
    legacy = home / paths.LEGACY_DIR_NAME
    legacy.mkdir()
    _support(home, paths.APP_DIR_NAME).mkdir(parents=True)

    assert paths.data_dir() == legacy
