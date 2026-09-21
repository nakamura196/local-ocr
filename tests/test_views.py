"""画面の組み立てだけを、窓を開かずに通す。

**中身が正しいかまでは見ない。** 見るのは「組み立てで落ちないこと」。
Flet 0.86 は書き方の作法が変わっているところが多く(ボタンのラベルは `content`、
`ft.Icons` の名前など)、落ちるとしたら組み立ての時点なので、そこだけ機械に見張らせる。
"""

from __future__ import annotations

import flet as ft
import pytest

from local_ocr.core import prefs
from local_ocr.engines import Result
from local_ocr.ui import work
from local_ocr.ui.landing import LandingView
from local_ocr.ui.state import AppState, Doc, Job, Run
from local_ocr.ui.work import WorkView


class FakeWindow:
    width = 1180.0
    height = 780.0


class FakePage:
    """窓の代わり。寸法を聞かれるのと、更新を無視するだけ。"""

    def __init__(self) -> None:
        self.window = FakeWindow()
        self.tasks: list[object] = []

    def update(self) -> None:
        pass

    def run_task(self, fn, *args) -> None:
        self.tasks.append(fn)


class FakeCtx:
    def __init__(self, state: AppState) -> None:
        self.page = FakePage()
        self.state = state

    def engine_dropdown(self, width: int = 240, on_change=None) -> ft.Dropdown:
        return ft.Dropdown(options=[], width=width)

    def go(self, name: str) -> None:
        pass


@pytest.fixture
def ctx(monkeypatch) -> FakeCtx:
    # 利用者の設定(前回の続き・選んでいる道具)に左右されないようにする。
    monkeypatch.setattr(prefs, "load", dict)
    return FakeCtx(AppState())


def test_the_landing_screen_builds(ctx: FakeCtx):
    assert isinstance(LandingView(ctx).build(), ft.Control)


def test_the_work_screen_builds_for_one_page(ctx: FakeCtx):
    ctx.state.open_job(Job(source="a.png"))
    view = WorkView(ctx)
    assert isinstance(view.build(), ft.Control)
    # 1 枚だけのときは、ページを行き来する帯を出さない。
    assert view.pager is None


def test_the_work_screen_shows_a_pager_for_a_bundle(ctx: FakeCtx):
    jobs = [Job(source=f"{i}.jpg") for i in range(3)]
    jobs[0].record(Run("fake", Result(text="あ")), prefer=True)
    ctx.state.open(Doc(title="束", jobs=jobs, index=1))

    view = WorkView(ctx)
    view.build()
    assert view.pager is not None
    assert "2" in view.page_label.value and "3" in view.page_label.value
    assert view.page_name.value == "1.jpg"
    # 端では行き止まりにする。真ん中なので、どちらにも行ける。
    assert view.prev_button.disabled is False
    assert view.next_button.disabled is False
    # 読み終えた数を出す。
    assert view.done_chip.content is not None


def test_the_pager_stops_at_both_ends(ctx: FakeCtx):
    ctx.state.open(Doc(title="束", jobs=[Job(source="1"), Job(source="2")]))
    view = WorkView(ctx)
    view.build()
    assert view.prev_button.disabled is True
    assert view.next_button.disabled is False


def test_the_save_menu_offers_the_whole_bundle_only_when_there_is_one(ctx: FakeCtx):
    ctx.state.open_job(Job(source="a.png"))
    assert len(WorkView(ctx)._save_items()) == 2
    ctx.state.open(Doc(title="束", jobs=[Job(source="1"), Job(source="2")]))
    assert len(WorkView(ctx)._save_items()) == 4


def test_the_page_image_gets_room_taken_off_for_the_pager(ctx: FakeCtx):
    """帯のぶんだけ、版面に使える高さが減ること(はみ出させない)。"""
    ctx.state.open_job(Job(source="a.png"))
    alone = WorkView(ctx)
    alone.build()
    alone_height = alone._budget()[1]

    ctx.state.open(Doc(title="束", jobs=[Job(source="1"), Job(source="2")]))
    bundled = WorkView(ctx)
    bundled.build()
    assert alone_height - bundled._budget()[1] == work.PAGER


def test_a_name_that_cannot_be_a_file_name_is_tidied():
    from local_ocr.ui.work import _safe_name

    assert _safe_name("酉蓮社/所蔵: 阿毗達磨") == "酉蓮社_所蔵_ 阿毗達磨"
    assert _safe_name("   ") == "ocr"
