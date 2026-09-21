"""読み順を決める部分。

上流の `src/reading_order/` を写したもの。やっていることは 3 段。

1. **版面を空白で切り分ける（XY カット）。** 行の枠を粗い格子に落として、
   一番広い空白で縦か横に切る。これを繰り返して木を作り、深さ優先で番号を振る
2. **ブロックの中で座標順に並べ直す。** 縦書きなら右の列から、横書きなら上の行から
3. **仕上げ（近代資料だけ）。** 行やブロックの並びを、行き来の短い順に入れ替える

上流との違いは、3 の最短経路を networkx ではなく深さ優先で解いている点だけ。
つながりが「隣」と「1 つ飛ばし」しかない細い形なので、これで足りる。
"""

from __future__ import annotations

import functools
import math
import xml.etree.ElementTree as ET

import numpy as np

# ---------------------------------------------------------------- XY カット


class _Node:
    def __init__(self, x0: int, y0: int, x1: int, y1: int) -> None:
        self.x0, self.y0, self.x1, self.y1 = int(x0), int(y0), int(x1), int(y1)
        self.children: list[_Node] = []
        self.line_idx: list[int] = []
        self.num_lines = 0
        self.num_vertical_lines = 0

    def coords(self) -> tuple[int, int, int, int]:
        return self.x0, self.y0, self.x1, self.y1

    def is_x_split(self) -> bool:
        return all(child.coords()[1::2] == (self.y0, self.y1) for child in self.children)

    def is_vertical(self) -> bool:
        return self.num_lines < self.num_vertical_lines * 2


def _min_span(hist: np.ndarray) -> tuple[int, int, float]:
    """一番長く続く「一番空いているところ」を返す。"""
    if hist.size == 1:
        return 0, 1, float(hist[0])
    min_val, max_val = hist.min(), hist.max()
    diff = np.diff(np.concatenate(([0], hist == min_val, [0])))
    start_idx = np.where(diff == 1)[0]
    end_idx = np.where(diff == -1)[0]
    i = np.argmax(end_idx - start_idx)
    return start_idx[i], end_idx[i], -min_val / max_val if max_val > 0 else 0.0


def _cut(table: np.ndarray, node: _Node) -> None:
    x0, y0, x1, y1 = node.coords()
    x_beg, x_end, x_val = _min_span(table[y0:y1, x0:x1].sum(axis=0))
    y_beg, y_end, y_val = _min_span(table[y0:y1, x0:x1].sum(axis=1))
    x_beg, x_end, y_beg, y_end = x_beg + x0, x_end + x0, y_beg + y0, y_end + y0
    if (x0, x1, y0, y1) == (x_beg, x_end, y_beg, y_end):
        return

    def add(nx0: int, ny0: int, nx1: int, ny1: int) -> None:
        if not (nx0 < nx1 and ny0 < ny1) or (nx0, ny0, nx1, ny1) == node.coords():
            return
        child = _Node(nx0, ny0, nx1, ny1)
        node.children.append(child)
        _cut(table, child)

    split_x = y_val < x_val or (x_val == y_val and (x_end - x_beg) >= (y_end - y_beg))
    if split_x:
        add(x0, y0, x_beg, y1)
        add(x_beg, y0, x_end, y1)
        add(x_end, y0, x1, y1)
    else:
        add(x0, y0, x1, y_beg)
        add(x0, y_beg, x1, y_end)
        add(x0, y_end, x1, y1)


def _normalize(bboxes: np.ndarray, grid: float, scale: float, tolerance: float = 0.25) -> np.ndarray:
    bboxes[:, 2] = np.where(bboxes[:, 0] < bboxes[:, 2], bboxes[:, 2], bboxes[:, 0])
    bboxes[:, 3] = np.where(bboxes[:, 1] < bboxes[:, 3], bboxes[:, 3], bboxes[:, 1])
    if scale != 1.0:
        w = bboxes[:, 2] - bboxes[:, 0]
        h = bboxes[:, 3] - bboxes[:, 1]
        m = np.median(np.minimum(w, h))
        lower, upper = m * (1.0 - tolerance), m * (1.0 + tolerance)
        _x = np.logical_and(w < h, lower <= w, w < upper)
        _y = np.logical_and(h < w, lower <= h, h < upper)
        bboxes[_x, 0] -= ((scale - 1.0) * w[_x] // 2).astype(np.int64)
        bboxes[_x, 2] += ((scale - 1.0) * w[_x] // 2).astype(np.int64)
        bboxes[_y, 1] -= ((scale - 1.0) * h[_y] // 2).astype(np.int64)
        bboxes[_y, 3] += ((scale - 1.0) * h[_y] // 2).astype(np.int64)
    x_min, y_min = bboxes[:, 0].min(), bboxes[:, 1].min()
    # 行が 1 本だけ、あるいは一直線に並んでいると 0 になる。0 で割らせない。
    w_page = max(int(bboxes[:, 2].max() - x_min), 1)
    h_page = max(int(bboxes[:, 3].max() - y_min), 1)
    x_grid = grid if w_page < h_page else grid * (w_page / h_page)
    y_grid = grid if h_page < w_page else grid * (h_page / w_page)
    bboxes[:, 0] = (bboxes[:, 0] - x_min) * x_grid // w_page
    bboxes[:, 1] = (bboxes[:, 1] - y_min) * y_grid // h_page
    bboxes[:, 2] = (bboxes[:, 2] - x_min) * x_grid // w_page
    bboxes[:, 3] = (bboxes[:, 3] - y_min) * y_grid // h_page
    return np.where(bboxes < 0, 0, bboxes)


def _iou(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    x0 = np.maximum(box[0], boxes[:, 0])
    y0 = np.maximum(box[1], boxes[:, 1])
    x1 = np.minimum(box[2], boxes[:, 2])
    y1 = np.minimum(box[3], boxes[:, 3])
    inter = np.maximum(0, x1 - x0 + 1) * np.maximum(0, y1 - y0 + 1)
    box_area = (box[2] - boxes[:, 0] + 1) * (box[3] - boxes[:, 1] + 1)
    boxes_area = (boxes[:, 2] - box[0] + 1) * (boxes[:, 3] - box[1] + 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return inter / (box_area + boxes_area - inter)


def _assign(root: _Node, bboxes: np.ndarray) -> None:
    """一番重なる葉に、それぞれの行を預ける。"""
    leaves: list[_Node] = []

    def collect(node: _Node) -> None:
        if not node.children:
            leaves.append(node)
        for child in node.children:
            collect(child)

    collect(root)
    coords = np.array([leaf.coords() for leaf in leaves])
    for i, bbox in enumerate(bboxes):
        leaves[int(np.nanargmax(_iou(bbox, coords)))].line_idx.append(i)


def _sort_nodes(node: _Node, bboxes: np.ndarray) -> tuple[int, int]:
    """上下に切ったところは必ず上から。左右に切ったところは、縦書きなら右から。

    **ここだけ上流と結果が変わる。** 上流は下の `is_vertical` を呼び忘れていて
    (`node.is_vertical` と書いてある。すぐ下の同じ判定には `()` が付いている)、
    横書きでも必ず「右の列から」並べてしまう。空白で切り分けきれずに 1 つの
    まとまりに 2 本以上残ったとき — 表のます目がこれにあたる — だけ効く。
    実測: 上流の試し画像 `digidepo_3048008_0025.jpg`(表のあるページ)で、
    上流は行が入り乱れるが、呼ぶようにすると表の見出しが上から順に並ぶ。
    他の 5 枚では結果は変わらない。戻すなら `node.is_vertical()` を `True` にする。
    """
    if node.line_idx:
        w = bboxes[node.line_idx, 2] - bboxes[node.line_idx, 0]
        h = bboxes[node.line_idx, 3] - bboxes[node.line_idx, 1]
        node.num_lines = len(node.line_idx)
        node.num_vertical_lines = int((w < h).sum())
        if node.num_lines > 1:
            x0, y0 = bboxes[node.line_idx, 0], bboxes[node.line_idx, 1]
            perm = np.lexsort((y0, -x0) if node.is_vertical() else (x0, y0))
            node.line_idx[:] = [node.line_idx[i] for i in perm]
    else:
        for child in node.children:
            num, v_num = _sort_nodes(child, bboxes)
            node.num_lines += num
            node.num_vertical_lines += v_num
        if node.is_x_split() and node.is_vertical():
            node.children = node.children[::-1]
    return node.num_lines, node.num_vertical_lines


def solve(bboxes: np.ndarray, scale: float = 1.0) -> list[int]:
    """行の枠の並びから、それぞれが何番目に読まれるかを返す。"""
    if len(bboxes) == 0:
        return []
    grid = 100 * math.sqrt(len(bboxes))
    bboxes = _normalize(np.array(bboxes, dtype=np.int64), grid, scale)
    x_grid = int(bboxes[:, 2].max()) + 1
    y_grid = int(bboxes[:, 3].max()) + 1
    table = np.zeros((y_grid, x_grid), dtype=np.int32)
    for x0, y0, x1, y1 in bboxes:
        table[y0:y1, x0:x1] = 1
    root = _Node(0, 0, x_grid, y_grid)
    _cut(table, root)
    _assign(root, bboxes)
    _sort_nodes(root, bboxes)

    ranks = [-1] * len(bboxes)

    def number(node: _Node, rank: int) -> int:
        for i in node.line_idx:
            ranks[i] = rank
            rank += 1
        for child in node.children:
            rank = number(child, rank)
        return rank

    number(root, 0)
    return ranks


# ------------------------------------------------- ブロックの中での並べ直し

_LINE_TAGS = ("LINE", "WARICHUBLOCK")


def _attr(elem: ET.Element, name: str, default: float = -1.0) -> float:
    value = elem.get(name)
    return default if value is None else float(value)


def _overlaps(a: list[float], b: list[float]) -> bool:
    """2 つの枠がほぼ同じ場所か。小さい方の 8 割が隠れていれば同じとみなす。"""
    a_area = (a[2] - a[0]) * (a[3] - a[1])
    b_area = (b[2] - b[0]) * (b[3] - b[1])
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    smaller = min(a_area, b_area)
    return smaller > 0 and (w * h) / smaller > 0.8


def _remove_duplicates(children: list[ET.Element]) -> list[ET.Element]:
    """隣り合う重なった行を 1 つに減らす。確からしさの高い方を残す。"""
    kept: list[ET.Element] = []
    boxes: list[list[float]] = []
    for elem in children:
        if elem.tag not in _LINE_TAGS:
            kept.append(elem)
            continue
        x, y = _attr(elem, "X"), _attr(elem, "Y")
        box = [x, y, x + _attr(elem, "WIDTH"), y + _attr(elem, "HEIGHT"), _attr(elem, "CONF")]
        if kept and kept[-1].tag in _LINE_TAGS and _overlaps(boxes[-1], box):
            if boxes[-1][4] >= box[4]:
                continue
            kept.pop()
            boxes.pop()
        kept.append(elem)
        boxes.append(box)
    return kept


def _sort_local(root: ET.Element) -> float:
    """ブロックの中の行を座標で並べ直し、そのブロックの順番（行の中央値）を返す。"""
    lines: list[tuple[float, float, float, ET.Element]] = []
    others: list[ET.Element] = []
    widths: list[float] = []
    heights: list[float] = []
    vertical = 0
    for elem in root:
        if elem.tag not in _LINE_TAGS:
            others.append(elem)
            continue
        w, h = _attr(elem, "WIDTH"), _attr(elem, "HEIGHT")
        vertical += 1 if w < h else 0
        widths.append(w)
        heights.append(h)
        lines.append(
            (_attr(elem, "X") + w / 2, _attr(elem, "Y") + h / 2, _attr(elem, "ORDER", np.nan), elem)
        )
    if not widths:
        return -1.0

    is_vertical = len(lines) < vertical * 2
    margin = float(np.median(widths if is_vertical else heights)) * 0.3

    def compare(a: tuple, b: tuple) -> float:
        # 縦書きは右の列が先で、同じ列とみなせる範囲では上から。横書きはその逆。
        if is_vertical:
            if margin < b[0] - a[0]:
                return 1.0
            if margin < a[0] - b[0]:
                return -1.0
            return a[1] - b[1]
        if margin < a[1] - b[1]:
            return 1.0
        if margin < b[1] - a[1]:
            return -1.0
        return a[0] - b[0]

    lines.sort(key=functools.cmp_to_key(compare))
    sorted_lines = _remove_duplicates([elem for _, _, _, elem in lines])

    orders = sorted(order for _, _, order, _ in lines if not np.isnan(order))
    median = orders[len(orders) // 2] if orders else float("nan")
    root[:] = sorted_lines + others
    return median


def _sort_page(page: ET.Element) -> None:
    to_sort: list[tuple[float, ET.Element]] = []
    unsorted: list[ET.Element] = []
    for elem in page:
        if elem.tag == "TEXTBLOCK":
            for wari in elem.findall("./WARICHUBLOCK"):
                _sort_local(wari)
            to_sort.append((_sort_local(elem), elem))
        elif elem.tag == "LINE":
            to_sort.append((_attr(elem, "ORDER", np.nan), elem))
        elif elem.tag == "WARICHUBLOCK":
            to_sort.append((_sort_local(elem), elem))
        elif elem.tag in ("BLOCK", "PAGE"):
            _sort_page(elem)
            unsorted.append(elem)
        else:
            unsorted.append(elem)
    ordered = [elem for _, elem in sorted(to_sort, key=lambda pair: pair[0])]
    page[:] = _remove_duplicates(ordered) + unsorted


# ------------------------------------------------------------------ 割注

def _group_warichu(page: ET.Element) -> None:
    """並んだ割注をひとまとまりにする。2 行 1 組で書かれるので、別々に並べると崩れる。"""
    parents: dict[int, ET.Element] = {}
    for parent in page.iter("*"):
        for child in parent:
            parents[id(child)] = parent

    items = []
    for line in page.findall(".//LINE[@TYPE='割注']"):
        x, y = _attr(line, "X"), _attr(line, "Y")
        w, h = _attr(line, "WIDTH"), _attr(line, "HEIGHT")
        step = min(w, h) * 0.1 / 2
        grown = (x - step, y, x + w + step, y + h) if w < h else (x, y - step, x + w, y + h + step)
        items.append(
            {"box": (x, y, x + w, y + h), "grown": grown, "elem": line,
             "order": _attr(line, "ORDER", np.nan), "parent": parents.get(id(line))}
        )

    def touches(a: tuple, b: tuple) -> bool:
        return (min(a[2], b[2]) - max(a[0], b[0])) > 0 and (min(a[3], b[3]) - max(a[1], b[1])) > 0

    grouped: set[int] = set()
    for i, first in enumerate(items):
        if i in grouped:
            continue
        group = [first]
        grouped.add(i)
        for j, other in enumerate(items):
            if j not in grouped and touches(first["grown"], other["grown"]):
                group.append(other)
                grouped.add(j)

        x0 = min(item["box"][0] for item in group)
        y0 = min(item["box"][1] for item in group)
        x1 = max(item["box"][2] for item in group)
        y1 = max(item["box"][3] for item in group)
        block = ET.Element(
            "WARICHUBLOCK",
            {"X": str(x0), "Y": str(y0), "WIDTH": str(x1 - x0), "HEIGHT": str(y1 - y0),
             "ORDER": str(np.median([item["order"] for item in group]))},
        )
        anchor = next(
            (item for item in group if item["parent"] is not None
             and item["parent"].tag == "TEXTBLOCK"),
            group[0],
        )
        parent = anchor["parent"]
        if parent is None:
            continue
        parent.insert(list(parent).index(anchor["elem"]), block)
        for item in group:
            block.append(item["elem"])
            item["parent"].remove(item["elem"])


def _ungroup_warichu(root: ET.Element) -> None:
    for child in list(root):
        _ungroup_warichu(child)
    flat: list[ET.Element] = []
    for child in root:
        if child.tag == "WARICHUBLOCK":
            flat.extend(child)
        else:
            flat.append(child)
    root[:] = flat


# ------------------------------------------------------------------ 仕上げ

def _shortest_hamiltonian(num: int, weight, max_step: int) -> list[int] | None:
    """0 から num-1 まで、全部を 1 回ずつ通る道のうち、いちばん短いもの。

    つながりは「隣」と（数が少ないときだけ）「1 つ飛ばし」だけなので、
    深さ優先で全部たどっても数は増えない。上流は networkx で同じことをしている。
    """
    if num == 1:
        return [0]
    best: list[list[int]] = []
    best_cost = [math.inf]
    visited = [False] * num
    path: list[int] = []

    def walk(node: int, cost: float) -> None:
        if cost >= best_cost[0]:
            return
        path.append(node)
        visited[node] = True
        if node == num - 1:
            if len(path) == num:
                best_cost[0] = cost
                best[:] = [list(path)]
        else:
            for step in range(1, max_step):
                for nxt in (node - step, node + step):
                    if 0 <= nxt < num and not visited[nxt]:
                        walk(nxt, cost + weight(node, nxt))
        visited[node] = False
        path.pop()

    walk(0, 0.0)
    return best[0] if best else None


def _smooth_page(page: ET.Element) -> None:
    w, h = _attr(page, "WIDTH"), _attr(page, "HEIGHT")
    diameter = math.hypot(w, h)

    def traverse(parent: ET.Element) -> None:
        entries: list[tuple[float, tuple, tuple, ET.Element]] = []
        unsorted: list[ET.Element] = []
        for elem in parent:
            if elem.tag == "TEXTBLOCK":
                lines = elem.findall("./LINE")
                if not lines:
                    continue
                orders = [_attr(line, "ORDER", np.nan) for line in lines]
                spans = [
                    (_attr(line, "X") + _attr(line, "WIDTH") / 2, _attr(line, "Y"),
                     _attr(line, "Y") + _attr(line, "HEIGHT"))
                    for line in lines
                ]
                entries.append(
                    (orders[len(orders) // 2], (spans[0][0], spans[0][1]),
                     (spans[-1][0], spans[-1][2]), elem)
                )
            elif elem.tag == "LINE":
                x, y = _attr(elem, "X"), _attr(elem, "Y")
                cx = x + _attr(elem, "WIDTH") / 2
                entries.append(
                    (_attr(elem, "ORDER", np.nan), (cx, y), (cx, y + _attr(elem, "HEIGHT")), elem)
                )
            elif elem.tag == "BLOCK":
                traverse(elem)
                unsorted.append(elem)
            else:
                unsorted.append(elem)

        num = len(entries)
        if num == 0:
            return
        orders = [entry[0] for entry in entries]
        span = max(orders) - min(orders)

        def weight(i: int, j: int) -> float:
            # 前の行の終わりから次の行の始まりまでの距離と、番号の飛び方の和。
            x0, y0 = entries[i][2]
            x1, y1 = entries[j][1]
            gap = 0.0 if span == 0 else abs(entries[i][0] - entries[j][0]) / span
            return math.hypot(x1 - x0, y1 - y0) / diameter + gap

        path = _shortest_hamiltonian(num, weight, max_step=3 if num < 20 else 2)
        if path:
            parent[:] = [entries[i][3] for i in path] + unsorted

    traverse(page)


# ------------------------------------------------------------------- 入口

def apply(page: ET.Element, *, smoothing: bool) -> None:
    """`layout.build_page` が作った木に読み順を付けて、その順に並べ替える。"""
    lines = page.findall(".//LINE")
    boxes = np.array(
        [
            [
                int(_attr(line, "X")),
                int(_attr(line, "Y")),
                int(_attr(line, "X")) + int(_attr(line, "WIDTH")),
                int(_attr(line, "Y")) + int(_attr(line, "HEIGHT")),
            ]
            for line in lines
        ],
        dtype=np.int64,
    ).reshape(-1, 4)
    for line, rank in zip(lines, solve(boxes), strict=True):
        line.set("ORDER", str(rank))

    _group_warichu(page)
    try:
        _sort_page(page)
    finally:
        _ungroup_warichu(page)
    if smoothing:
        _smooth_page(page)
