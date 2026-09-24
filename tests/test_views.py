"""画面の組み立てだけを、窓を開かずに通す。

**中身が正しいかまでは見ない。** 見るのは「組み立てで落ちないこと」。
Flet 0.86 は書き方の作法が変わっているところが多く(ボタンのラベルは `content`、
`ft.Icons` の名前など)、落ちるとしたら組み立ての時点なので、そこだけ機械に見張らせる。
"""

from __future__ import annotations

import asyncio
import sys

import flet as ft
import pytest

from local_ocr.core import prefs
from local_ocr.engines import Result
from local_ocr.ui import work
from local_ocr.ui.landing import LandingView
from local_ocr.ui.settings import SettingsView
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

    def go_back(self) -> None:
        pass

    def notify(self, message: str) -> None:
        pass


@pytest.fixture
def ctx(monkeypatch) -> FakeCtx:
    # 利用者の設定(前回の続き・選んでいる道具)に左右されないようにする。
    monkeypatch.setattr(prefs, "load", dict)
    # 配布先は macOS と Windows だけ。CI (Linux) では動く道具が 1 つも無く、
    # 既定の道具を選べずに AppState が作れない。そこでは Windows のふりをする
    # (NDL 2 種と PaddleOCR-VL が並ぶ。未取得のままでも組み立てには足りる)。
    if sys.platform not in ("darwin", "win32"):
        monkeypatch.setattr(sys, "platform", "win32")
    return FakeCtx(AppState())


def test_the_landing_screen_builds(ctx: FakeCtx):
    assert isinstance(LandingView(ctx).build(), ft.Control)


def test_the_settings_screen_builds(ctx: FakeCtx):
    """読む道具・ほかの道具に開く窓口・IIIF の置き場が、1 つの画面に同居する。

    **この 3 つは別々に足されたので、ここで一度に組んでおく。** 組み立てで
    落ちるかどうかは、窓を開けるまで分からない。
    """
    view = SettingsView(ctx)
    # 窓口の節は、常駐のサーバを持つ道具があるときだけ出る (PaddleOCR-VL)。
    # 出ない側だけを組んで通してしまわないように、出ていることを見ておく。
    assert view.bridge_card is not None
    assert isinstance(view.build(), ft.Control)


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


# --- 読んだあとの版面と、くらべる画面 -------------------------------------
#
# 組み立てで落ちないことに加えて、**読んだ結果が版面の枠になっているか**まで見る。
# 「1 つで読んだら枠が出ない」「これを使うで枠が替わらない」は、
# 画面を見るまで気づけないので、ここで機械に見張らせる。


class FakeEngine:
    """すぐ読み終わる道具。道具ごとに枠の横位置をずらし、どれが版面に出ているか見分ける。"""

    platforms = frozenset({sys.platform})
    assets: tuple = ()
    note = ""

    def __init__(self, n: int) -> None:
        self.n = n
        self.id = f"fake{n}"
        self.label = f"Fake {n}"

    def available(self) -> bool:
        return True

    def prepare(self, on_progress) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def boxes(self) -> list[tuple[int, int, int, int]]:
        return [(100 + self.n * 200, 100 + i * 300, 80, 250) for i in range(3)]

    def recognize(self, img) -> Result:
        from local_ocr.engines import Line

        lines = [Line(f"{self.n}-{i}", box) for i, box in enumerate(self.boxes())]
        return Result(text="\n".join(ln.text for ln in lines), lines=lines)


@pytest.fixture
def fakes(monkeypatch) -> tuple[FakeCtx, list[FakeEngine]]:
    monkeypatch.setattr(prefs, "load", dict)
    # 読み終えると「前回の続き」をしまいに行く。利用者の設定を書き換えない。
    monkeypatch.setattr(prefs, "save", lambda **kw: None)
    engines = [FakeEngine(i) for i in range(6)]
    return FakeCtx(AppState(engines=engines)), engines


def _page(ctx: FakeCtx, size=(2000, 1500)) -> Job:
    from PIL import Image

    job = Job(source="p.png", image=Image.new("RGB", size, "white"))
    ctx.state.open_job(job)
    return job


def _lefts(view: WorkView) -> list[float]:
    return [box.left for box in view._boxes]


def _expected_lefts(view: WorkView, engine: FakeEngine) -> list[float]:
    return [x * view._scale for x, _, _, _ in engine.boxes()]


def test_reading_with_one_engine_puts_its_boxes_on_the_page(fakes):
    ctx, engines = fakes
    job = _page(ctx)
    ctx.state.set_engine(engines[2].id)
    view = WorkView(ctx)
    view.build()
    assert view._boxes == []

    asyncio.run(view._run_all(job, [engines[2]]))

    assert job.primary == engines[2].id
    assert len(view._boxes) == 3
    assert _lefts(view) == pytest.approx(_expected_lefts(view, engines[2]))


def test_reading_again_with_another_engine_moves_the_boxes(fakes):
    """道具を替えて読み直したら、版面の枠も新しい道具のものになる。"""
    ctx, engines = fakes
    job = _page(ctx)
    view = WorkView(ctx)
    view.build()
    asyncio.run(view._run_all(job, [engines[0]]))
    asyncio.run(view._run_all(job, [engines[3]]))

    assert job.primary == engines[3].id
    assert _lefts(view) == pytest.approx(_expected_lefts(view, engines[3]))


def test_use_this_puts_the_chosen_engines_boxes_on_the_page(fakes):
    ctx, engines = fakes
    job = _page(ctx)
    ctx.state.compare = True
    ctx.state.compare_ids = {e.id for e in engines}
    view = WorkView(ctx)
    view.build()
    asyncio.run(view._run_all(job, engines))
    assert len(job.runs) == len(engines)

    last = engines[-1]
    assert job.primary != last.id
    view.use_result(last.id)

    assert job.primary == last.id
    assert _lefts(view) == pytest.approx(_expected_lefts(view, last))
    # 「版面に表示中」は選んだ列だけ。ほかの列には「これを使う」が出る。
    for col in view.columns:
        shown = col.engine.id == last.id
        assert isinstance(col.badge.content, ft.TextButton) is not shown


def test_many_engines_to_compare_can_be_scrolled_sideways(fakes):
    """列が右の枠に収まらないときは、横に送って見られること。バーは常に出す。"""
    ctx, engines = fakes
    _page(ctx)
    ctx.state.compare = True
    ctx.state.compare_ids = {e.id for e in engines}
    view = WorkView(ctx)
    view.build()

    pane = view.body.content.controls[2]
    columns_row = pane.content.controls[1]
    assert len(view.columns) == len(engines)
    # 6 列は窓(1180)の右側に収まらない。収まらないから、送れる必要がある。
    assert len(engines) * work.COLUMN > pane.width
    assert columns_row.scroll == ft.ScrollMode.ALWAYS


def test_many_engines_to_pick_wrap_instead_of_running_off_the_right(fakes):
    """道具が多いとき、上のチェックボックスは折り返す。右で切れると押せない道具が出る。"""
    ctx, engines = fakes
    _page(ctx)
    ctx.state.compare = True
    ctx.state.compare_ids = {e.id for e in engines}
    view = WorkView(ctx)
    view.build()

    pane = view.body.content.controls[2]
    header = pane.content.controls[0].content
    picks = header.controls[1]
    # 横並びの中では、expand で幅をもらわないと wrap しても折り返さない。
    assert picks.wrap and picks.expand
    # 1 つずつ名前の幅に縮めておかないと、1 行に 1 つずつになる。
    assert len(picks.controls) == len(engines)
    for pick in picks.controls:
        assert pick.tight and isinstance(pick.controls[0], ft.Checkbox)


def test_the_page_image_is_shrunk_before_it_is_sent_to_the_screen():
    """8000 画素の撮影画像を、そのまま画面へ送らない(1 回 80MB になり画面が止まる)。"""
    import io

    from PIL import Image

    big = Image.new("RGB", (8000, 6000), "white")
    data = work._preview(big, 600, 450)
    sent = Image.open(io.BytesIO(data))
    assert sent.size == (1200, 900)
    assert len(data) < 1_000_000

    # 小さな切り抜きは引き伸ばさない(引き伸ばしは画面側の拡大に任せる)。
    small = Image.new("RGB", (300, 200), "white")
    assert Image.open(io.BytesIO(work._preview(small, 600, 400))).size == (300, 200)


def test_the_page_image_is_redone_when_the_window_changes_size(fakes):
    ctx, _ = fakes
    _page(ctx, size=(4000, 3000))
    view = WorkView(ctx)
    view.build()
    before = view._picture_for

    ctx.page.window.width = 1600
    view._render()
    assert view._picture_for != before
    assert view._picture_for[0] > before[0]
