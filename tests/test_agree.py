"""読む道具どうしの食い違いの探し方。"""

import pytest

from local_ocr.core import agree


def test_identical_texts_agree_fully():
    bad, rate = agree.compare("勸學篇\n天地玄黃", "勸學篇\n天地玄黃")
    assert bad == set()
    assert rate == 1.0


def test_only_line_breaks_and_spaces_differ():
    """行の切り方や空白が違うだけなら、全部一致。"""
    a = "天地玄黃\n宇宙洪荒"
    b = "天地\n玄黃宇宙 洪荒\n"
    assert agree.compare(a, b) == (set(), 1.0)
    assert agree.compare(b, a) == (set(), 1.0)


def test_single_substitution_marks_only_that_char():
    bad, rate = agree.compare("勸學篇", "勤學篇")
    assert bad == {0}
    assert rate == pytest.approx(2 / 3)


def test_variant_characters_count_as_different_for_now():
    assert agree.compare("眞", "真")[0] == {0}


def test_insertion_in_other_leaves_no_char_to_mark():
    """相手に余分な字があるとき、こちらには印を付ける字が無い。一致率には出る。"""
    bad, rate = agree.compare("天地玄黃", "天地玄之黃")
    assert bad == set()
    assert rate == pytest.approx(4 / 5)


def test_deletion_in_other_marks_the_extra_char():
    bad, rate = agree.compare("天地玄之黃", "天地玄黃")
    assert bad == {3}
    assert rate == pytest.approx(4 / 5)


def test_empty_texts():
    assert agree.compare("", "") == (set(), 1.0)
    assert agree.compare(" \n", "\n") == (set(), 1.0)
    assert agree.compare("天地", "") == ({0, 1}, 0.0)
    assert agree.compare("", "天地") == (set(), 0.0)


def test_positions_point_into_the_original_text():
    """改行・空白を含む元の文字列の位置で返す。"""
    text = "天地\n玄 黃\n宇宙"
    other = "天地玄黄宇宙"  # 黃 だけ違う
    bad, _ = agree.compare(text, other)
    assert {text[i] for i in bad} == {"黃"}
    assert bad == {text.index("黃")}


def test_rate_is_about_the_longer_text():
    assert agree.rate("天地", "天地玄黃") == pytest.approx(0.5)
    assert agree.rate("天地玄黃", "天地") == pytest.approx(0.5)


def test_disputed_is_the_union_over_other_engines():
    primary = "天地玄黃宇宙洪荒"
    others = ["天地玄黃宇宙洪荒", "天地玄黄宇宙洪荒", "天地玄黃宇宙洪茫"]
    bad = agree.disputed(primary, others)
    assert {primary[i] for i in bad} == {"黃", "荒"}


def test_disputed_with_no_others_is_empty():
    assert agree.disputed("天地", []) == set()


def test_long_texts_are_compared_in_chunks_and_still_find_the_difference():
    base = "".join(chr(0x4E00 + (i * 7919) % 3000) for i in range(agree.CHUNK * 2 + 500))
    changed = base[:6000] + "X" + base[6001:]
    bad, rate = agree.compare(base, changed)
    assert bad == {6000}
    assert rate == pytest.approx(1 - 1 / len(base))
