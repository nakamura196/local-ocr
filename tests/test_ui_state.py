"""画面を出さずに確かめられるところだけを見る(Flet の窓は開かない)。"""

from __future__ import annotations

from local_ocr.engines import Line, Result
from local_ocr.ui import i18n
from local_ocr.ui.state import Job, Run


def test_job_keeps_one_result_per_engine():
    job = Job(source="x")
    job.record(Run("apple-vision", Result(text="あ\nい", lines=[])))
    job.record(Run("paddle-vl", Result(text="う", lines=[Line("う", (0, 0, 1, 1))])))
    # 先に読み終えたものが版面に出る。
    assert job.primary == "apple-vision"
    assert [ln.text for ln in job.lines] == ["あ", "い"]
    # くらべた相手の結果も残っている。
    assert set(job.runs) == {"apple-vision", "paddle-vl"}
    job.primary = "paddle-vl"
    assert job.text == "う"
    assert job.lines[0].box == (0, 0, 1, 1)


def test_lines_fall_back_to_splitting_text():
    """枠を返さないエンジンでも、右側の並びは同じ形にする。"""
    run = Run("paddle-vl", Result(text="一行目\n\n二行目", lines=[]))
    assert [ln.text for ln in run.lines] == ["一行目", "二行目"]
    assert all(ln.box is None for ln in run.lines)


def test_reading_again_with_another_engine_replaces_what_is_shown():
    """道具を変えて読み直したのに、前の道具の結果が出たままにならないこと。"""
    job = Job(source="x")
    job.record(Run("apple-vision", Result(text="定規の数字", lines=[])), prefer=True)
    job.record(Run("paddle-vl", Result(text="阿毗達磨", lines=[])), prefer=True)
    assert job.primary == "paddle-vl"
    assert job.text == "阿毗達磨"


def test_comparing_does_not_swap_the_page_under_the_user():
    """くらべるときは、先に読み終えたものを出したままにする。"""
    job = Job(source="x")
    job.record(Run("apple-vision", Result(text="あ", lines=[])))
    job.record(Run("paddle-vl", Result(text="い", lines=[])))
    assert job.primary == "apple-vision"


def test_a_failed_run_does_not_take_over_the_page():
    job = Job(source="x")
    job.record(Run("apple-vision", Result(text="あ", lines=[])), prefer=True)
    job.record(Run("paddle-vl", error="起動できませんでした"), prefer=True)
    assert job.primary == "apple-vision"


def test_editing_the_whole_text_carries_the_boxes_along():
    """「まとめて」で直した文字が、行の一覧にも TEI にも効く。"""
    run = Run(
        "apple-vision",
        Result(text="あ\nい", lines=[Line("あ", (0, 0, 9, 9)), Line("い", (0, 9, 9, 9))]),
    )
    run.result.text = "亜\n伊"
    assert [ln.text for ln in run.lines] == ["亜", "伊"]
    assert [ln.box for ln in run.lines] == [(0, 0, 9, 9), (0, 9, 9, 9)]


def test_boxes_survive_when_the_line_count_changes():
    """行を足されると枠との対応が付かない。直す前の姿を出し、枠は捨てない。"""
    run = Run(
        "apple-vision",
        Result(text="あ\nい", lines=[Line("あ", (0, 0, 9, 9)), Line("い", (0, 9, 9, 9))]),
    )
    run.result.text = "あ\nい\nう"
    assert [ln.text for ln in run.lines] == ["あ", "い"]
    assert run.lines[0].box == (0, 0, 9, 9)


def test_timing_separates_preparation():
    plain = Run("x", Result(text="a"), seconds=0.8)
    slow = Run("x", Result(text="a"), seconds=0.8, prepare_seconds=41.2)
    assert "準備" not in plain.timing
    assert "41" in slow.timing


def test_every_string_has_both_languages():
    for key, pair in i18n._STRINGS.items():
        assert len(pair) == 2, key
        assert all(isinstance(v, str) and v for v in pair), key


def test_placeholders_match_between_languages():
    """{...} の名前が言語でずれていると、その言語だけ落ちる。"""
    import re

    for key, (ja, en) in i18n._STRINGS.items():
        assert set(re.findall(r"{(\w+)}", ja)) == set(re.findall(r"{(\w+)}", en)), key
