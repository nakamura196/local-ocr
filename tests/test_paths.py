"""データの置き場所。

見張りたいのは 2 つ。

1. **前の名前のフォルダを取り残さないこと**。中身はモデルで 1.8GB あり、
   取り残すと利用者が黙って取り直すことになる（気づけない）
2. **環境変数での指定が、確実にいちばん強いこと**。これは空きが無い機械の
   逃げ道なので、効かなければ案内する意味がない
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
    # 動かす機械で設定されていると、ほかの試験がその場所を見てしまう。
    monkeypatch.delenv(paths.DATA_DIR_ENV, raising=False)
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


# --- 環境変数での指定 ---------------------------------------------------------

def test_the_environment_variable_wins_over_everything(home, monkeypatch):
    """ほかの候補がどう在ろうと、指定された場所を使う。

    この口は「C: に空きが無い」ような機械の逃げ道なので、ほかの候補に
    負けては意味がない。起動スクリプト版のフォルダ（いちばん強かったもの）が
    在っても勝つことを見る。
    """
    (home / paths.LEGACY_DIR_NAME).mkdir()
    _support(home, paths.APP_DIR_NAME).mkdir(parents=True)
    elsewhere = home / "somewhere" / "else"
    monkeypatch.setenv(paths.DATA_DIR_ENV, str(elsewhere))

    assert paths.data_dir() == elsewhere


def test_the_environment_variable_need_not_exist_yet(home, monkeypatch):
    """まだ無い場所を指してよい。作るのは使う側。

    案内するときに「先にフォルダを作ってください」と言わずに済む。
    """
    elsewhere = home / "not" / "created" / "yet"
    monkeypatch.setenv(paths.DATA_DIR_ENV, str(elsewhere))

    assert paths.data_dir() == elsewhere
    assert not elsewhere.exists()


def test_a_tilde_in_the_environment_variable_is_expanded(home, monkeypatch):
    """`~/Models` のような書き方をそのまま受ける。

    シェルが展開してくれるとは限らない（Windows はしない。値を引用符で
    囲んだときもしない）。展開しないと `./~/Models` を掘ることになる。

    `expanduser()` が見るのは環境変数 HOME（Windows では USERPROFILE）で、
    `Path.home()` の差し替えでは届かない。ここだけ両方を向け直す。
    """
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv(paths.DATA_DIR_ENV, "~/Models")

    assert paths.data_dir() == home / "Models"


def test_an_empty_environment_variable_is_ignored(home, monkeypatch):
    """空のまま export されていても、変な場所を掘らない。

    空文字を Path に渡すと `.`（いまいる場所）になる。アプリを起動した場所に
    1.8GB を置くことになり、気づきにくい。
    """
    for value in ("", "   "):
        monkeypatch.setenv(paths.DATA_DIR_ENV, value)
        assert paths.data_dir() == _support(home, paths.APP_DIR_NAME)
