"""見つけた枠を、版面の組み立て（どの行がどのブロックの中か）に直す部分。

上流の `src/ndl_parser.py` の `convert_to_xml_string3` とその周りを写したもの。
上流は文字列で XML を組み立ててから読み直しているが、ここでは木を直に作る。
**タグと属性の名前は上流のまま。** 読み順の処理（`order.py`）がこの形を前提にしている。

本文ブロックの形は常に長方形なので、上流の一般の多角形あたり判定は
長方形あたり判定に置き換えてある（同じ答えになる）。
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections.abc import Sequence

from .classes import Taxonomy
from .detect import Detection

Rect = tuple[float, float, float, float]

MIN_BBOX_SIZE = 5


def _contains(rect: Rect, x: float, y: float) -> bool:
    x0, y0, x1, y1 = rect
    return x0 <= x <= x1 and y0 <= y <= y1


def _signed_distance(rect: Rect, x: float, y: float) -> float:
    """長方形の縁までの距離。中なら正、外なら負。"""
    x0, y0, x1, y1 = rect
    if _contains(rect, x, y):
        return min(x - x0, x1 - x, y - y0, y1 - y)
    return -math.hypot(max(x0 - x, 0.0, x - x1), max(y0 - y, 0.0, y - y1))


def _center(rect: Rect) -> tuple[float, float]:
    x0, y0, x1, y1 = rect
    return (x0 + x1) // 2, (y0 + y1) // 2


def _set_box(elem: ET.Element, rect: Rect) -> None:
    x0, y0, x1, y1 = rect
    elem.set("X", str(int(x0)))
    elem.set("Y", str(int(y0)))
    elem.set("WIDTH", str(int(x1 - x0)))
    elem.set("HEIGHT", str(int(y1 - y0)))


class _Page:
    """検出の結果を、上流と同じ入れ物に並べ替えたもの。"""

    def __init__(self, taxonomy: Taxonomy, detections: Sequence[Detection]) -> None:
        self.taxonomy = taxonomy
        self.tb_id = taxonomy.index("text_block")
        # 種類ごとの [x0, y0, x1, y1, 確からしさ, 文字数の見当]。
        self.by_class: list[list[list[float]]] = [[] for _ in taxonomy.names]
        for det in detections:
            if not 0 <= det.class_index < len(taxonomy.names):
                continue
            x0, y0, x1, y1 = det.box
            count = 0.0 if det.pred_char_count is None else det.pred_char_count
            self.by_class[det.class_index].append([x0, y0, x1, y1, det.confidence, count])

    def blocks(self, name: str) -> list[list[float]]:
        index = self.taxonomy.index(name)
        return self.by_class[index] if index >= 0 else []

    def text_blocks(self) -> list[Rect | None]:
        """本文ブロックの長方形。小さすぎるものは None（番号をずらさないため）。"""
        out: list[Rect | None] = []
        for x0, y0, x1, y1, *_ in self.by_class[self.tb_id]:
            too_small = x1 - x0 < MIN_BBOX_SIZE and y1 - y0 < MIN_BBOX_SIZE
            out.append(None if too_small else (x0, y0, x1, y1))
        return out


def _relationships(
    page: _Page, rects: Sequence[Rect | None], score_thr: float, use_block_ad: bool
) -> tuple[list, list, list, list]:
    """どの行がどのブロックの中に入るかを決める。

    戻り値は（本文ブロックごとの行, 広告ごとの行, 表組ごとの行, どこにも入らなかった行）。
    行の中心がブロックの中にあるかどうかだけで決める（上流と同じ）。
    """
    tb_info: list[list[list[int]] | None] = [[] for _ in rects]
    tables = page.blocks("block_table")
    ads = page.blocks("block_ad") if use_block_ad else []
    table_info: list[list[list[int]]] = [[] for _ in tables]
    ad_info: list[list[list[int]]] = [[] for _ in ads]
    loose: list[list[int]] = []

    for c, name in enumerate(page.taxonomy.names):
        if not name.startswith("line_"):
            continue
        for j, line in enumerate(page.by_class[c]):
            if line[4] < score_thr:
                continue
            cx, cy = _center((line[0], line[1], line[2], line[3]))
            for i, rect in enumerate(rects):
                if rect is None:
                    tb_info[i] = None
                    continue
                if _contains(rect, cx, cy):
                    tb_info[i].append([c, j])  # type: ignore[union-attr]
                    break
            else:
                for i, ad in enumerate(ads):
                    if _contains((ad[0], ad[1], ad[2], ad[3]), cx, cy):
                        ad_info[i].append([c, j])
                        break
                else:
                    for i, table in enumerate(tables):
                        if _contains((table[0], table[1], table[2], table[3]), cx, cy):
                            table_info[i].append([c, j])
                            break
                    else:
                        loose.append([c, j])

    return tb_info, ad_info, table_info, loose  # type: ignore[return-value]


def _merge_nested(page: _Page, rects: Sequence[Rect | None], tb_info: list, margin: int = 50) -> None:
    """本文ブロックが入れ子になっていたら、中の行を外側へ移す。

    中に行が 1 つも無いブロックは、外側のブロックの「行」として引き取られる
    （そのブロック全体が 1 行だった、という扱い）。
    """
    for child_i, child in enumerate(rects):
        if child is None or tb_info[child_i] is None:
            continue
        for parent_i, parent in enumerate(rects):
            if child_i == parent_i or parent is None or tb_info[parent_i] is None:
                continue
            corners = ((child[0], child[1]), (child[0], child[3]),
                       (child[2], child[3]), (child[2], child[1]))
            if any(_signed_distance(parent, x, y) < -margin for x, y in corners):
                continue
            if tb_info[child_i]:
                tb_info[parent_i].extend(tb_info[child_i])
            else:
                tb_info[parent_i].append([page.tb_id, child_i])
            tb_info[child_i] = None
            break

    # 中身が本文ブロックだけになったものは、空として扱う。
    for i, info in enumerate(tb_info):
        if info is not None and info and all(c_id == page.tb_id for c_id, _ in info):
            tb_info[i] = []


def _add_line(parent: ET.Element, page: _Page, c: int, j: int, rects: Sequence) -> None:
    line = page.by_class[c][j]
    rect: Rect
    if c == page.tb_id:
        # 中に行の無かった本文ブロック。ブロックの枠をそのまま 1 行として書く。
        if rects[j] is None:
            return
        rect = rects[j]
        if rect[2] - rect[0] < MIN_BBOX_SIZE or rect[3] - rect[1] < MIN_BBOX_SIZE:
            return
        type_name = page.taxonomy.org_name(page.taxonomy.index("line_main"))
    else:
        rect = (line[0], line[1], line[2], line[3])
        type_name = page.taxonomy.org_name(c)
    elem = ET.SubElement(parent, "LINE")
    elem.set("TYPE", type_name)
    _set_box(elem, rect)
    elem.set("CONF", f"{line[4]:0.3f}")
    elem.set("PRED_CHAR_CNT", f"{line[5]:0.3f}")


def _add_text_block(parent: ET.Element, rect: Rect, conf: float) -> ET.Element:
    block = ET.SubElement(parent, "TEXTBLOCK", {"CONF": f"{conf:0.3f}"})
    x0, y0, x1, y1 = (int(v) for v in rect)
    points = f"{x0},{y0},{x0},{y1},{x1},{y1},{x1},{y0}"
    ET.SubElement(ET.SubElement(block, "SHAPE"), "POLYGON", {"POINTS": points})
    return block


def build_page(
    img_w: int,
    img_h: int,
    img_name: str,
    taxonomy: Taxonomy,
    detections: Sequence[Detection],
    *,
    score_thr: float,
    use_block_ad: bool,
) -> ET.Element:
    """検出の結果を 1 ページ分の木にする。読み順はまだ付いていない。"""
    page = _Page(taxonomy, detections)
    rects = page.text_blocks()
    tb_info, ad_info, table_info, loose = _relationships(page, rects, score_thr, use_block_ad)
    _merge_nested(page, rects, tb_info)

    root = ET.Element(
        "PAGE", {"IMAGENAME": img_name, "WIDTH": str(img_w), "HEIGHT": str(img_h)}
    )

    def fill_container(container: ET.Element, members: Sequence[Sequence[int]]) -> None:
        for c, j in members:
            if page.by_class[c][j][4] >= score_thr:
                _add_line(container, page, c, j, rects)

    for i, table in enumerate(page.blocks("block_table")):
        elem = ET.SubElement(root, "BLOCK", {"TYPE": "表組", "CONF": f"{table[4]:0.3f}"})
        _set_box(elem, (table[0], table[1], table[2], table[3]))
        fill_container(elem, table_info[i])

    if use_block_ad:
        for i, ad in enumerate(page.blocks("block_ad")):
            elem = ET.SubElement(root, "BLOCK", {"TYPE": "広告", "CONF": f"{ad[4]:0.3f}"})
            _set_box(elem, (ad[0], ad[1], ad[2], ad[3]))
            fill_container(elem, ad_info[i])

    for j, rect in enumerate(rects):
        if rect is None or tb_info[j] is None:
            continue
        block = _add_text_block(root, rect, page.by_class[page.tb_id][j][4])
        if not tb_info[j]:
            # 行が 1 つも入っていない本文ブロックは、まるごと 1 行として読ませる。
            x0, y0, x1, y1 = rect
            if x1 - x0 >= MIN_BBOX_SIZE and y1 - y0 >= MIN_BBOX_SIZE:
                elem = ET.SubElement(block, "LINE", {"TYPE": taxonomy.org_name(1)})
                _set_box(elem, rect)
        else:
            fill_container(block, tb_info[j])

    fill_container(root, loose)

    for c, name in enumerate(taxonomy.names):
        if not name.startswith("block_") or name in ("block_table", "block_ad"):
            continue
        for block in page.by_class[c]:
            if block[4] < score_thr:
                continue
            elem = ET.SubElement(
                root, "BLOCK", {"TYPE": taxonomy.org_name(c), "CONF": f"{block[4]:0.3f}"}
            )
            _set_box(elem, (block[0], block[1], block[2], block[3]))

    return root
