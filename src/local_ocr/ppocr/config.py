"""モデルごとに違う設定（しきい値・入力の大きさ・文字の一覧）を、公式の inference.yml から読む。

**PyYAML は入れない。** 配布物が 1 つ増えるごとに .app と .msix が重くなるので、
NDL でも要らなくした（`ndl/__init__.py`）。ここで要るのは YAML のごく一部
（数値の項目と、文字の一覧の並び）だけなので、その形だけを読む小さな読み手を書いた。
**読める形は、公式が出力する inference.yml の形に限る。** 見慣れない形に出会ったら、
黙って間違えずに `ValueError` で止める。

公式の PP-OCRv6 の rec は、文字の一覧が 18,708 件ある。字は次の 3 通りで書かれる
（実物で確かめた）。

- そのまま: `- あ`
- 一重引用符: `- '!'`。中の引用符は 2 つ重ねる（`- ''''` が `'`）
- 二重引用符: `- "\\u3000"`（逆スラッシュで書く字。公式の出力にはまだ無いが、書き方としてある）
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Params:
    """検出と読み取りの設定。既定は PP-OCRv5 の公式の値。yml があれば上書きする（v6 small は yml で上書きされる）。"""

    # 検出の後処理（DB）
    thresh: float = 0.3
    box_thresh: float = 0.6
    unclip_ratio: float = 1.5
    max_candidates: int = 1000
    # 読み取りの入力 (高さ, 最小の幅)
    rec_height: int = 48
    rec_min_width: int = 320


DEFAULT = Params()

_ESCAPES = {
    "0": "\0", "a": "\a", "b": "\b", "t": "\t", "\t": "\t", "n": "\n", "v": "\v",
    "f": "\f", "r": "\r", "e": "\x1b", " ": " ", '"': '"', "/": "/", "\\": "\\",
    "N": "\x85", "_": "\xa0", "L": " ", "P": " ",
}  # fmt: skip


def _double_quoted(body: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(body):
        c = body[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        k = body[i + 1]
        if k in "xuU":
            n = {"x": 2, "u": 4, "U": 8}[k]
            out.append(chr(int(body[i + 2 : i + 2 + n], 16)))
            i += 2 + n
        elif k in _ESCAPES:
            out.append(_ESCAPES[k])
            i += 2
        else:
            raise ValueError(f"読めない書き方です: {body!r}")
    return "".join(out)


def scalar(text: str) -> str:
    """YAML の 1 つの値（文字列）を読む。両端の空白は ASCII のスペースとタブだけ削る。

    **全角スペース（U+3000）は字として残す**（文字の一覧に入っている）。
    """
    s = text.strip(" \t")
    if s.startswith("'"):
        # 閉じの引用符は、重なった '' を飛ばした最後の ' 。後ろは空か注釈だけ。
        m = re.fullmatch(r"'((?:[^']|'')*)'\s*(#.*)?", s)
        if not m:
            raise ValueError(f"読めない書き方です: {text!r}")
        return m.group(1).replace("''", "'")
    if s.startswith('"'):
        m = re.fullmatch(r'"((?:[^"\\]|\\.)*)"\s*(#.*)?', s)
        if not m:
            raise ValueError(f"読めない書き方です: {text!r}")
        return _double_quoted(m.group(1))
    if s[:1] in "[{|>&*!%@`":
        raise ValueError(f"読めない書き方です: {text!r}")
    # 引用符なしの値は、「空白 + #」から後ろが注釈
    return re.split(r"[ \t]#", s, maxsplit=1)[0].rstrip(" \t")


def character_dict(yml: str) -> list[str]:
    """inference.yml の PostProcess.character_dict（文字の並び）を取り出す。"""
    lines = yml.split("\n")
    for n, line in enumerate(lines):
        m = re.fullmatch(r"( *)character_dict:\s*", line)
        if not m:
            continue
        indent = len(m.group(1))
        items: list[str] = []
        for rest in lines[n + 1 :]:
            if not rest.strip():
                continue
            m2 = re.match(r"( *)- ?(.*)", rest)
            # 並びは、キーと同じ深さか、それより深い位置の「- 」で続く。
            if not m2 or len(m2.group(1)) < indent:
                break
            items.append(scalar(m2.group(2)))
        if not items:
            raise ValueError("character_dict が空です")
        return items
    raise ValueError("character_dict が見つかりません（inference.yml ではない？）")


def number(yml: str, key: str) -> float | None:
    """`key: 0.3` のような数値の項目を探す（最初に見つかったもの）。無ければ None。"""
    m = re.search(rf"^ *{re.escape(key)}: *([-+0-9.eE]+) *(#.*)?$", yml, re.MULTILINE)
    return float(m.group(1)) if m else None


def rec_image_shape(yml: str) -> tuple[int, int, int] | None:
    """RecResizeImg の image_shape（チャンネル, 高さ, 最小の幅）。"""
    m = re.search(r"RecResizeImg:\s*\n\s*image_shape:\s*\n\s*- (\d+)\n\s*- (\d+)\n\s*- (\d+)", yml)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def params_from(det_yml: str | None, rec_yml: str | None) -> Params:
    """既定（PP-OCRv5 の値）に、yml にある項目だけを上書きする。"""
    base = Params()
    kw: dict[str, float | int] = {}
    if det_yml:
        for field, cast in (
            ("thresh", float),
            ("box_thresh", float),
            ("unclip_ratio", float),
            ("max_candidates", int),
        ):
            v = number(det_yml, field)
            if v is not None:
                kw[field] = cast(v)
    if rec_yml:
        shape = rec_image_shape(rec_yml)
        if shape:
            kw["rec_height"], kw["rec_min_width"] = shape[1], shape[2]
    return Params(**{**base.__dict__, **kw})


def load_chars(dict_json: Path | None, rec_yml: Path | None) -> list[str]:
    """文字の一覧。JSON の配列があればそれを、無ければ rec の inference.yml から読む。

    番号 0 は CTC の空白、番号 k + 1 が一覧の k 番目、最後の番号は半角スペース
    （一覧に入っていない）。**両端を削らない**（先頭が全角スペースの版がある）。
    """
    if dict_json is not None:
        return json.loads(dict_json.read_text(encoding="utf-8"))
    if rec_yml is None:
        raise ValueError("文字の一覧がありません（dict.json か inference.yml が要ります）")
    return character_dict(rec_yml.read_text(encoding="utf-8"))
