"""画像を読む芯。画面・端末・窓口(`core/gateway.py`)は、みなここを通して読む。

エンジンの `recognize` をそのまま呼ぶ代わりに、ここで 3 つを引き受ける。

- **範囲(`Region`)を切り出して読み、枠を元の画像の座標に戻す。** どのエンジンでも同じ。
  細長い範囲(縦 6:横 1 など)は、紙の色の余白を足してから渡す。PaddleOCR-VL は細長い画像で
  縦の座標が縮み、狭く切ると左の列に位置が付かなくなる(2026-09-26 に音釋の切り出しで実測)
- **読み方(`mode`)。** 道具ごとに持つ(`Engine.modes`、先頭が既定)。いまは 2 つの道具だけ。
  PaddleOCR-VL: "text"(文字だけ) / "lines"(行の位置も付ける = 「Spotting:」)。
  NDL の 2 つ: "layout"(版面から行を探して読む) / "line"(囲んだ範囲を 1 行として読む。
  行を探す段を飛ばす)。どれを使うかは設定画面で道具ごとに決める(`prefs` の "modes")
- **位置付きの読みの後始末。** Spotting の並びは横書きの並べ方(上端が高い順)で、割注の
  左右が入れ替わる。位置で並べ替える(`order_by_position`、調査の「方法 A」)。
  さらに位置なしでも読んで行数・字数をくらべ、崩れ(途中でやめる・同じ字の繰り返し)を
  `Check` に書く。**位置の付かなかった行も捨てない**(直前の行の後ろに置く)
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from itertools import pairwise

from PIL import Image, ImageStat

from ..engines.base import Check, Engine, Line, Result
from .ocr import Runaway

# 読み方の名前。道具が持つのはこのうちのいくつか(`Engine.modes`)。
MODES = ("text", "lines", "layout", "line")

# 細長い範囲に余白を足す目安。短い辺が長い辺のこれだけに満たなければ足す
# (音釋の切り出しで「横 ≥ 縦×0.4」にして、左の列にも位置が付いた)。
PAD_RATIO = 0.4
# 余白の色を取る縁の幅(画素)。
EDGE = 20

# 同じ字がこれだけ続いたら「繰り返し」とみなす(199-04 の「佛佛佛…」)。
REPEAT_CHARS = 10
# 同じ行がこれだけ続いたら「繰り返し」。
REPEAT_LINES = 5
# 位置付きの字数が、位置なしのこれ未満なら「途中でやめた」
# (137-03 は 41 行中 15 行、158-03 は 180 中 82。ふつうの面は 134 対 144 程度)。
STOPPED_RATIO = 0.8
# 字数の差がこれ未満なら、比が小さくても咎めない(数字の短い範囲で騒がない)。
STOPPED_MIN_CHARS = 10


# --- 範囲 -----------------------------------------------------------------


@dataclass(frozen=True)
class Region:
    """元の画像の画素座標での範囲 (x, y, w, h)。"""

    x: int
    y: int
    w: int
    h: int

    @classmethod
    def parse(cls, value: object) -> Region | None:
        """{x, y, w, h} の辞書か、"x,y,w,h" の文字列。無ければ None、形が違えば ValueError。"""
        if value is None or value == "":
            return None
        if isinstance(value, dict):
            try:
                nums = [value[k] for k in ("x", "y", "w", "h")]
            except KeyError as exc:
                raise ValueError("region") from exc
        elif isinstance(value, str):
            nums = value.split(",")
        elif isinstance(value, (list, tuple)):
            nums = list(value)
        else:
            raise ValueError("region")  # noqa: TRY004 - 呼び手は ValueError だけを見る
        if len(nums) != 4:
            raise ValueError("region")
        try:
            x, y, w, h = (round(float(v)) for v in nums)
        except (TypeError, ValueError) as exc:
            raise ValueError("region") from exc
        return cls(x, y, w, h)

    def clip(self, width: int, height: int) -> Region | None:
        """画像の中に収める。はみ出た分は落とし、重ならなければ None。"""
        x0, y0 = max(0, self.x), max(0, self.y)
        x1, y1 = min(width, self.x + self.w), min(height, self.y + self.h)
        if x1 - x0 < 1 or y1 - y0 < 1:
            return None
        return Region(x0, y0, x1 - x0, y1 - y0)

    def contains(self, box: tuple[int, int, int, int]) -> bool:
        """枠の中心がこの範囲に入っているか。"""
        cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
        return self.x <= cx <= self.x + self.w and self.y <= cy <= self.y + self.h

    def as_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


@dataclass
class _Cut:
    """切り出した画像と、元の画像の座標へ戻すための値。"""

    image: Image.Image
    region: Region
    pad_x: int = 0
    pad_y: int = 0

    def back(self, x: float, y: float) -> tuple[int, int]:
        """切り出しの座標 → 元の画像の座標。足した余白に掛かった分は範囲の縁に寄せる。"""
        r = self.region
        ox = min(max(x - self.pad_x, 0), r.w) + r.x
        oy = min(max(y - self.pad_y, 0), r.h) + r.y
        return round(ox), round(oy)


def cut(img: Image.Image, region: Region, pad: bool = True) -> _Cut:
    """範囲を切り出す。`pad` なら、細長いときに紙の色の余白を足す(`PAD_RATIO`)。"""
    piece = img.crop((region.x, region.y, region.x + region.w, region.y + region.h))
    piece = piece.convert("RGB")
    w, h = piece.size
    pad_x = round((PAD_RATIO * h - w) / 2) if pad and w < PAD_RATIO * h else 0
    pad_y = round((PAD_RATIO * w - h) / 2) if pad and h < PAD_RATIO * w else 0
    if not pad_x and not pad_y:
        return _Cut(piece, region)
    # 紙の色は、余白を足す側の縁の中央値。ページの地の色に揃えて、文字の縁と見間違わせない。
    edge = piece.crop((0, 0, min(EDGE, w), h)) if pad_x else piece.crop((0, 0, w, min(EDGE, h)))
    color = tuple(int(v) for v in ImageStat.Stat(edge).median)
    canvas = Image.new("RGB", (w + 2 * pad_x, h + 2 * pad_y), color)
    canvas.paste(piece, (pad_x, pad_y))
    return _Cut(canvas, region, pad_x, pad_y)


def _moved(line: Line, c: _Cut) -> Line:
    """切り出しで読んだ行を、元の画像の座標に戻す。"""
    if line.box is None:
        return Line(text=line.text)
    x, y, w, h = line.box
    x0, y0 = c.back(x, y)
    x1, y1 = c.back(x + w, y + h)
    poly = [c.back(px, py) for px, py in line.polygon] if line.polygon else None
    return Line(text=line.text, box=(x0, y0, x1 - x0, y1 - y0), polygon=poly)


# --- 読む -----------------------------------------------------------------


def spots(engine: Engine) -> bool:
    """行の位置を後から付ける道具か(PaddleOCR-VL)。並べ替えと点検が要るのはこれだけ。"""
    return callable(getattr(engine, "recognize_lines", None))


def modes(engine: Engine) -> tuple[str, ...]:
    """その道具が選べる読み方。先頭が既定。選べない道具は空。"""
    return tuple(getattr(engine, "modes", ()) or ())


def mode_for(engine: Engine, wanted: str | None) -> str:
    """使う読み方。選べない道具は ""、知らない名前は `ValueError`、無ければ既定。"""
    own = modes(engine)
    if not own:
        return ""
    if not wanted:
        return own[0]
    if wanted not in own:
        raise ValueError("mode")
    return wanted


def read(
    engine: Engine,
    img: Image.Image,
    *,
    region: Region | None = None,
    mode: str | None = None,
    check: bool = True,
) -> Result:
    """1 枚(またはその一部)を読む。枠はいつも元の画像の座標で返る。

    `mode` を省くと、その道具の既定の読み方。

    `check` は位置付きで読むとき、位置なしでも読んで抜けと崩れを調べるか。
    **時間は増える**(位置なしの読みは 1 面 4〜11 秒)が、崩れは位置付きの読みだけ
    見ても分からない。落とすのは、前からの呼び手(`gateway` の互換の道)だけ。
    """
    mode = mode_for(engine, mode)
    c: _Cut | None = None
    if region is not None:
        clipped = region.clip(*img.size)
        if clipped is None:
            raise ValueError("region")
        # 余白を足すのは PaddleOCR-VL だけ。NDL の「1 行として読む」は、余白があると
        # 行の画像が縮んで字が潰れる(決まった寸法に引き伸ばして読むため)。
        c = cut(img, clipped, pad=spots(engine))
    target = c.image if c is not None else img

    if mode == "lines" and spots(engine):
        result = _read_spotted(engine, target, check)
    elif mode == "line":
        result = engine.recognize_line(target)  # type: ignore[attr-defined]
    else:
        result = engine.recognize(target)

    if c is not None:
        result.lines = [_moved(ln, c) for ln in result.lines]
    return result


def _read_spotted(engine: Engine, img: Image.Image, check: bool) -> Result:
    problems: list[str] = []
    try:
        spotted = engine.recognize_lines(img)  # type: ignore[attr-defined]
        lines = order_by_position(spotted.lines)
    except Runaway:
        # 定規の数字などを数え続けた。位置付きの行は当てにならないので捨て、
        # 位置なしの読みを(位置の無い行として)返す。
        if not check:
            raise
        lines = []
        problems.append("runaway")
    if not check:
        return Result(text=_join(lines), lines=lines)

    plain = engine.recognize(img).text
    plain_lines = [s for s in plain.splitlines() if s.strip()]
    if not lines and "runaway" in problems:
        lines = [Line(text=s) for s in plain_lines]
    else:
        problems += find_problems(lines, plain)
    placed = sum(1 for ln in lines if ln.box is not None)
    return Result(
        text=_join(lines),
        lines=lines,
        plain=plain,
        check=Check(
            placed=placed if "runaway" not in problems else 0,
            unplaced=len(lines) - placed,
            plain_lines=len(plain_lines),
            plain_chars=_chars(plain),
            problems=problems,
        ),
    )


def _join(lines: list[Line]) -> str:
    return "\n".join(ln.text for ln in lines)


# --- 崩れの点検 -------------------------------------------------------------

_NOISE = re.compile(r"[、。，．\s・]")


def _chars(text: str) -> int:
    return len(_NOISE.sub("", text))


def find_problems(lines: list[Line], plain: str) -> list[str]:
    """位置付きの読みの崩れ。"repeat"(同じ字・同じ行の繰り返し)と "stopped_early"。"""
    out: list[str] = []
    texts = [ln.text for ln in lines]
    same_char = re.compile(rf"(.)\1{{{REPEAT_CHARS - 1},}}")
    streak = 1
    repeated = any(same_char.search(_NOISE.sub("", s)) for s in texts)
    for a, b in pairwise(texts):
        streak = streak + 1 if a == b else 1
        repeated = repeated or streak >= REPEAT_LINES
    if repeated:
        out.append("repeat")
    got, want = _chars(_join(lines)), _chars(plain)
    if got < STOPPED_RATIO * want and want - got >= STOPPED_MIN_CHARS:
        out.append("stopped_early")
    return out


# --- 位置で並べ替える(方法 A) ------------------------------------------------
#
# 縦書きの版面を前提にする。列は右から左、列の中は上から下。
# 割注(1 列に細い行が 2 本並ぶ)は、上下に重なる細い行を「帯」にまとめ、
# 帯の中は右の列 → 左の列の順に読む。
# 030-01 の 25 面(音釋)で、近くの行どうしの前後が 91% → 97%(正解は目視で確かめた
# 位置なしの読みの並び)。無作為抽出 14 面でも、割注・段組 9 面中 8 面で NDL を上回った。

# 列幅に対して、これより細い行を割注の行とみなす。
NARROW = 0.75


@dataclass
class _Col:
    left: float
    right: float
    items: list[Line] = field(default_factory=list)


def order_by_position(lines: list[Line]) -> list[Line]:
    """Spotting の行を読む順に並べ替える。位置の無い行は、元の並びで直前にあった行の後ろに置く。"""
    boxed = [ln for ln in lines if ln.box is not None]
    if len(boxed) < 2:
        return list(lines)
    ordered = _rule_order(boxed)

    # 位置の無い行を、元の並びで直前にあった(位置のある)行に結びつける。
    after: dict[int, list[Line]] = {}
    head: list[Line] = []
    prev: Line | None = None
    for ln in lines:
        if ln.box is None:
            (after.setdefault(id(prev), []) if prev is not None else head).append(ln)
        else:
            prev = ln
    out = list(head)
    for ln in ordered:
        out.append(ln)
        out += after.get(id(ln), [])
    return out


def _rule_order(lines: list[Line]) -> list[Line]:
    def box(ln: Line) -> tuple[int, int, int, int]:
        return ln.box  # type: ignore[return-value]

    # 字 1 つ分の幅(= 大字の列幅)。1〜2 字の、縦に長すぎない行の幅の中央値。
    singles = [
        box(ln)[2] for ln in lines if len(_NOISE.sub("", ln.text)) <= 2 and box(ln)[3] < 1.6 * box(ln)[2]
    ]
    width = statistics.median(singles or [box(ln)[2] for ln in lines])

    def narrow(ln: Line) -> bool:
        return box(ln)[2] < NARROW * width

    # 列: 幅のある行の横の範囲を、右から重ねて作る。
    cols: list[_Col] = []
    for ln in sorted((ln for ln in lines if not narrow(ln)), key=lambda ln: -(box(ln)[0] + box(ln)[2])):
        x, _, w, _ = box(ln)
        for c in cols:
            if min(c.right, x + w) - max(c.left, x) > 0.5 * min(w, c.right - c.left):
                c.left, c.right = min(c.left, x), max(c.right, x + w)
                break
        else:
            cols.append(_Col(x, x + w))

    def col_of(ln: Line) -> _Col | None:
        cx = box(ln)[0] + box(ln)[2] / 2
        found = None
        for c in cols:
            if c.left - 2 <= cx <= c.right + 2:
                found = c
        return found

    rest: list[Line] = []
    for ln in lines:
        c = col_of(ln)
        if c is None:
            rest.append(ln)
        else:
            c.items.append(ln)
    # 幅のある行が無い所(割注だけの列)の細い行は、1 本ずつ列にする。右の行が先に並ぶ。
    # 調査の試作は「2 本ずつ束ねる」つもりだったが、その枝は実際には一度も働いておらず、
    # 測った 97% はこの形での値(2026-09-26、試作と 15 面で並びが一致することを確かめた)。
    for ln in sorted(rest, key=lambda ln: -(box(ln)[0] + box(ln)[2])):
        x, _, w, _ = box(ln)
        cols.append(_Col(x, x + w, [ln]))

    out: list[Line] = []
    for c in sorted(cols, key=lambda c: -(c.left + c.right)):
        items = sorted(c.items, key=lambda ln: box(ln)[1])
        i = 0
        while i < len(items):
            first = items[i]
            if not narrow(first):
                out.append(first)
                i += 1
                continue
            # 縦に重なる細い行をまとめて帯にする。
            band = [first]
            bottom = box(first)[1] + box(first)[3]
            j = i + 1
            while (
                j < len(items)
                and narrow(items[j])
                and box(items[j])[1] < bottom - 0.3 * min(box(items[j])[3], box(first)[3])
            ):
                band.append(items[j])
                bottom = max(bottom, box(items[j])[1] + box(items[j])[3])
                j += 1
            mid = (min(box(o)[0] for o in band) + max(box(o)[0] + box(o)[2] for o in band)) / 2
            right = [o for o in band if box(o)[0] + box(o)[2] / 2 >= mid]
            left = [o for o in band if box(o)[0] + box(o)[2] / 2 < mid]
            out += sorted(right, key=lambda o: box(o)[1]) + sorted(left, key=lambda o: box(o)[1])
            i = j
    return out


# --- 範囲の読みを、前の読みに差し込む -------------------------------------------


def merge(old: list[Line], new: list[Line], region: Region) -> list[Line]:
    """範囲を読み直した結果を、ページ全体の前の読みに入れる。

    範囲の中にあった前の行(枠の中心が入るもの)を外し、その最初の場所に新しい行を置く。
    範囲の中に前の行が無ければ、末尾に足す。**位置の無い前の行は残す**(どこの行か分からない)。
    """
    kept: list[Line] = []
    at: int | None = None
    for ln in old:
        if ln.box is not None and region.contains(ln.box):
            if at is None:
                at = len(kept)
            continue
        kept.append(ln)
    if at is None:
        at = len(kept)
    return kept[:at] + list(new) + kept[at:]
