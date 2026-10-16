"""読む道具どうしの異同を探す。画面を知らない純粋な計算だけを置く。

校正する人は、2 つの道具が同じに読んだ所はたいてい正しいと見て、
異同のある所だけを確かめたい。その「異同のある所」を文字の位置で返す。

**空白と改行は無視して比べる。** 道具によって行の切り方が違う(縦書きの 1 列を
2 行に割る道具もある)ので、行ごとに比べると、文字は同じでも異同だらけになる。
一方、返す位置は **元の文字列の位置**(改行や空白を含む)。画面は行をそのまま
見せたいので、位置を元に戻して返す。

**異体字(眞 と 真 など)は、いまは別の字として扱う。** 将来、対応表を作れば
`_key()` で字を寄せるだけで入れられる(比べる前の 1 文字ごとの変換)。
"""

from __future__ import annotations

from difflib import SequenceMatcher

# 1 回に比べる長さ。SequenceMatcher は似ていない長い文章どうしだと急に遅くなるので、
# 上限を超えたら塊に切って比べる。実測は tests ではなく docs/design.md に書いた
# (5,000 字どうしで 5% 違うとき 0.1 秒未満)。
CHUNK = 4000


def _strip(text: str) -> tuple[str, list[int]]:
    """空白を除いた文字列と、各文字の元の位置。"""
    chars: list[str] = []
    where: list[int] = []
    for i, ch in enumerate(text):
        if not ch.isspace():
            chars.append(ch)
            where.append(i)
    return "".join(chars), where


def _matched(a: str, b: str) -> list[bool]:
    """a の各文字が b と対応したか。長すぎるときは塊ごとに比べる。"""
    flags = [False] * len(a)
    if len(a) <= CHUNK and len(b) <= CHUNK:
        _fill(flags, a, b, 0)
        return flags
    # 先頭から同じ割合の位置で区切る。挿入や欠落でずれても、塊の中では
    # 合うので、ずれの影響は塊の境目に限られる。
    n = max(1, -(-max(len(a), len(b)) // CHUNK))
    for k in range(n):
        a0, a1 = len(a) * k // n, len(a) * (k + 1) // n
        b0, b1 = len(b) * k // n, len(b) * (k + 1) // n
        _fill(flags, a[a0:a1], b[b0:b1], a0)
    return flags


def _fill(flags: list[bool], a: str, b: str, offset: int) -> None:
    sm = SequenceMatcher(None, a, b, autojunk=False)
    for block in sm.get_matching_blocks():
        for i in range(block.a, block.a + block.size):
            flags[offset + i] = True


def compare(text: str, other: str) -> tuple[set[int], float]:
    """text の中で other と合わない文字の位置(元の位置)と、一致率。

    一致率 = 合った文字数 / 長いほうの文字数(どちらも空白を除いた長さ)。
    **両方が空なら 1.0**(比べるものが無いのは異同ではない)。
    片方だけが空なら 0.0。
    """
    a, where = _strip(text)
    b, _ = _strip(other)
    if not a and not b:
        return set(), 1.0
    flags = _matched(a, b)
    off = {where[i] for i, ok in enumerate(flags) if not ok}
    return off, sum(flags) / max(len(a), len(b))


def rate(a: str, b: str) -> float:
    """2 つの文章の一致率。向きによらない(a と b を替えても近い値)。"""
    return compare(a, b)[1]


def disputed(primary: str, others: list[str]) -> set[int]:
    """primary の中で、他の道具のどれか 1 つでも合わない文字の位置。"""
    out: set[int] = set()
    for other in others:
        out |= compare(primary, other)[0]
    return out
