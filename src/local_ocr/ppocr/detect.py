"""文字の検出（DB）。確からしさの地図から、行の四角形を取り出す。

公式の DBPostProcess（thresh 0.3・box_thresh 0.6・unclip 1.5・四角形）の手順。
OpenCV の輪郭抽出（findContours）の代わりに、つながった画素のかたまりを取る。
最小外接矩形はそれで同じになる（凸包は、行ごとの左端と右端だけで決まる）。
"""

from __future__ import annotations

import numpy as np

from .config import DEFAULT, Params

# しきい値（thresh: これを超えた画素が「文字」、box_thresh: 四角形の中の平均がこれ未満なら
# 捨てる、unclip_ratio・max_candidates）はモデルごとに違うので `Params` が持つ。
MIN_SIZE = 3
# 入力の大きさ（公式の limit_type: min）。短い辺をこれまで引き上げ、長い辺は上限で抑える。
DET_MIN_SIDE = 64
DET_MAX_SIDE = 4000

XY = tuple[float, float]


def det_size(w: int, h: int) -> tuple[int, int]:
    """検出に入れる大きさ (dw, dh)。32 の倍数にする（公式の DetResizeForTest）。"""
    ratio = DET_MIN_SIDE / min(w, h) if min(w, h) < DET_MIN_SIDE else 1.0
    if max(w, h) * ratio > DET_MAX_SIDE:
        ratio = DET_MAX_SIDE / max(w, h)

    def r32(n: int) -> int:
        # JS の Math.round は .5 を上へ丸める。Python の round は偶数へ丸めるので使わない。
        return max(int(np.floor(int(n * ratio) / 32 + 0.5)) * 32, 32)

    return r32(w), r32(h)


def _cross(o: XY, a: XY, b: XY) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def convex_hull(pts: list[XY]) -> list[XY]:
    """凸包（Andrew の方法）。y が下向きの画素座標で反時計回り。"""
    p = sorted(set(pts))
    if len(p) < 3:
        return p
    lower: list[XY] = []
    for q in p:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], q) <= 0:
            lower.pop()
        lower.append(q)
    upper: list[XY] = []
    for q in reversed(p):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], q) <= 0:
            upper.pop()
        upper.append(q)
    return lower[:-1] + upper[:-1]


# 回転した矩形: (中心 x, 中心 y, 辺 u の長さ, 辺 v の長さ, u の向き x, u の向き y)
Rect = tuple[float, float, float, float, float, float]


def min_area_rect(pts: list[XY]) -> Rect:
    """点をすべて囲む、面積が最小の矩形（cv2.minAreaRect）。1 辺は凸包の辺の上に載る。"""
    hull = convex_hull(pts)
    # 1 画素だけのかたまり（頂点がすべて同じ点）は、大きさ 0
    best: Rect = (hull[0][0], hull[0][1], 0.0, 0.0, 1.0, 0.0)
    if len(hull) < 2:
        return best
    h = np.asarray(hull, np.float64)
    edge = np.roll(h, -1, axis=0) - h
    length = np.hypot(edge[:, 0], edge[:, 1])
    keep = length > 0
    if not keep.any():
        return best
    ux = edge[keep, 0] / length[keep]
    uy = edge[keep, 1] / length[keep]
    # 辺ごとに、全頂点をその向き (u) と直角 (v) に射影して、はみ出す幅を出す。
    u = ux[:, None] * h[None, :, 0] + uy[:, None] * h[None, :, 1]
    v = -uy[:, None] * h[None, :, 0] + ux[:, None] * h[None, :, 1]
    min_u, max_u = u.min(axis=1), u.max(axis=1)
    min_v, max_v = v.min(axis=1), v.max(axis=1)
    area = (max_u - min_u) * (max_v - min_v)
    k = int(np.argmin(area))  # 同点なら先の辺（JS の「<」と同じ）
    cu = (min_u[k] + max_u[k]) / 2
    cv = (min_v[k] + max_v[k]) / 2
    return (
        float(cu * ux[k] - cv * uy[k]),
        float(cu * uy[k] + cv * ux[k]),
        float(max_u[k] - min_u[k]),
        float(max_v[k] - min_v[k]),
        float(ux[k]),
        float(uy[k]),
    )


def rect_corners(r: Rect) -> list[XY]:
    """矩形の四隅。get_mini_boxes と同じ並び: 左上・右上・右下・左下。"""
    cx, cy, w, h, ux, uy = r
    ax, ay = ux * w / 2, uy * w / 2
    bx, by = -uy * h / 2, ux * h / 2
    p = sorted(
        [
            (cx - ax - bx, cy - ay - by),
            (cx + ax - bx, cy + ay - by),
            (cx + ax + bx, cy + ay + by),
            (cx - ax + bx, cy - ay + by),
        ],
        key=lambda q: q[0],
    )
    tl, bl = (p[0], p[1]) if p[1][1] > p[0][1] else (p[1], p[0])
    tr, br = (p[2], p[3]) if p[3][1] > p[2][1] else (p[3], p[2])
    return [tl, tr, br, bl]


def box_score(prob: np.ndarray, box: list[XY]) -> float:
    """四角形の中の確からしさの平均（公式の box_score_fast）。

    公式は、四角形の外接する範囲に、四角形を塗って平均を取る。塗るときは頂点を
    整数に切り捨てる。
    """
    h, w = prob.shape
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    x0 = int(min(max(np.floor(min(xs)), 0), w - 1))
    x1 = int(min(max(np.ceil(max(xs)), 0), w - 1))
    y0 = int(min(max(np.floor(min(ys)), 0), h - 1))
    y1 = int(min(max(np.ceil(max(ys)), 0), h - 1))
    q = [(int(x - x0) + x0, int(y - y0) + y0) for x, y in box]
    # 向きをそろえる（どちら回りでも内側を正にする）
    sign = -1 if _cross(q[0], q[1], q[2]) < 0 else 1
    gx, gy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
    inside = np.ones(gx.shape, bool)
    for k in range(4):
        a, b = q[k], q[(k + 1) % 4]
        c = (b[0] - a[0]) * (gy - a[1]) - (b[1] - a[1]) * (gx - a[0])
        inside &= sign * c >= 0
    n = int(inside.sum())
    return float(prob[y0 : y1 + 1, x0 : x1 + 1][inside].sum() / n) if n else 0.0


def _runs(mask: np.ndarray):
    """各行の「続いている区間」（行・左端・右端。右端も含む）を、上の行から順に返す。"""
    h, w = mask.shape
    padded = np.zeros((h, w + 2), np.int8)
    padded[:, 1:-1] = mask
    d = np.diff(padded, axis=1)
    sy, sx = np.nonzero(d == 1)  # 区間の左端（d は 1 つ右にずれる分、そのまま列番号）
    _, ex = np.nonzero(d == -1)
    # 行ごとに左端と右端は同じ数だけ、同じ順で並ぶ（np.nonzero は行優先）。
    return sy, sx, ex - 1


def components(mask: np.ndarray) -> list[np.ndarray]:
    """つながった画素（8 近傍）のかたまりを、走査の順（上から、左から）に返す。

    1 画素ずつ幅優先で調べると、2000px のページで何秒もかかる。そこで
    「行ごとの続いた区間（ラン）」を単位にし、上の行と重なる区間を
    素集合（union-find）でつなぐ。重なりの探し方は配列の二分探索でまとめて行う。
    返り値は、かたまりごとの (行, 左端, 右端) の 3 列の配列。
    """
    ry, rs, re_ = _runs(mask)
    n = len(ry)
    if n == 0:
        return []
    width = mask.shape[1]
    k = width + 3  # 行をまたいで並べるための幅（行の境目で混ざらない大きさ）
    ends = ry * k + re_ + 1
    starts = ry * k + rs + 1
    # 8 近傍では、区間 [s, e] は、1 つ上の行の [s' , e'] と s' <= e + 1 かつ e' >= s - 1 で
    # つながる。上の行の候補は、並びの中の連続した範囲になる。
    lo = np.searchsorted(ends, (ry - 1) * k + rs, side="left")
    hi = np.searchsorted(starts, (ry - 1) * k + re_ + 2, side="right")
    # 上の行に区間が無いときは hi <= lo になる（鍵の幅 k が行の混ざりを防ぐ）。
    count = np.maximum(hi - lo, 0)
    me = np.repeat(np.arange(n), count)
    offset = np.arange(int(count.sum())) - np.repeat(np.cumsum(count) - count, count)
    other = np.repeat(lo, count) + offset

    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b in zip(me.tolist(), other.tolist(), strict=True):
        ra, rb = find(a), find(b)
        if ra != rb:
            # 小さい番号を根にする（= 根が、そのかたまりで最初に走査される区間）
            if ra < rb:
                parent[rb] = ra
            else:
                parent[ra] = rb
    roots = np.fromiter((find(i) for i in range(n)), np.int64, n)
    order = np.argsort(roots, kind="stable")
    sorted_roots = roots[order]
    cuts = np.nonzero(np.diff(sorted_roots))[0] + 1
    groups = np.split(order, cuts)
    runs = np.stack([ry, rs, re_], axis=1)
    return [runs[g] for g in groups]


def _round_half_up(v: float) -> int:
    return int(np.floor(v + 0.5))


def find_boxes(
    prob: np.ndarray, out_w: int, out_h: int, params: Params = DEFAULT
) -> list[tuple[list[tuple[int, int]], float]]:
    """確からしさの地図 (dh × dw) から、行の四角形を取り出す。

    四角形は画像 (out_w × out_h) の画素座標で、左上・右上・右下・左下の整数。
    読み順（上から下、同じ行なら左から右。公式の SortQuadBoxes）に並べて返す。
    """
    dh, dw = prob.shape
    out: list[tuple[list[tuple[int, int]], float]] = []
    # 公式と同じく、最初の max_candidates 個のかたまりで打ち切る（捨てたものも数える）。
    for runs in components(prob > params.thresh)[: params.max_candidates]:
        pts: list[XY] = []
        ys = runs[:, 0].tolist()
        for y, a, b in zip(ys, runs[:, 1].tolist(), runs[:, 2].tolist(), strict=True):
            pts.append((float(a), float(y)))
            pts.append((float(b), float(y)))
        rect = min_area_rect(pts)
        if min(rect[2], rect[3]) < MIN_SIZE:
            continue
        score = box_score(prob, rect_corners(rect))
        if score < params.box_thresh:
            continue
        cx, cy, w, h, ux, uy = rect
        # 広げる幅は、面積 × 1.5 ÷ 周囲の長さ
        d = (w * h * params.unclip_ratio) / (2 * (w + h))
        big = (cx, cy, w + 2 * d, h + 2 * d, ux, uy)
        if min(big[2], big[3]) < MIN_SIZE + 2:
            continue
        quad = [
            (
                min(max(_round_half_up(x / dw * out_w), 0), out_w),
                min(max(_round_half_up(y / dh * out_h), 0), out_h),
            )
            for x, y in rect_corners(big)
        ]
        out.append((quad, score))
    return order_boxes(out)


def sort_boxes(boxes):
    """上から下へ。左上の y の差が 10px 未満なら、左から右へ（公式の SortQuadBoxes）。"""
    out = sorted(boxes, key=lambda b: (b[0][0][1], b[0][0][0]))
    for i in range(len(out) - 1):
        for j in range(i, -1, -1):
            a, b = out[j][0][0], out[j + 1][0][0]
            if abs(b[1] - a[1]) < 10 and b[0] < a[0]:
                out[j], out[j + 1] = out[j + 1], out[j]
            else:
                break
    return out


def is_vertical(quad: list[tuple[int, int]]) -> bool:
    """縦長の箱か。切り出しで左へ倒す条件（高さが幅の 1.5 倍以上）と同じ。"""
    w = max(
        np.hypot(quad[1][0] - quad[0][0], quad[1][1] - quad[0][1]),
        np.hypot(quad[2][0] - quad[3][0], quad[2][1] - quad[3][1]),
    )
    h = max(
        np.hypot(quad[3][0] - quad[0][0], quad[3][1] - quad[0][1]),
        np.hypot(quad[2][0] - quad[1][0], quad[2][1] - quad[1][1]),
    )
    return w > 0 and h / w >= 1.5


def sort_boxes_vertical(boxes):
    """縦書きの並べ方: 右の列から左へ。同じ列（中心の x の差が 10px 未満）なら上から下へ。

    公式の SortQuadBoxes の左右・上下を入れ替えたもの。
    """

    def cx(b):
        return sum(p[0] for p in b[0]) / 4

    def top(b):
        return min(p[1] for p in b[0])

    out = sorted(boxes, key=lambda b: (-cx(b), top(b)))
    for i in range(len(out) - 1):
        for j in range(i, -1, -1):
            a, b = out[j], out[j + 1]
            if abs(cx(b) - cx(a)) < 10 and top(b) < top(a):
                out[j], out[j + 1] = b, a
            else:
                break
    return out


def order_boxes(boxes):
    """読み順に並べる。縦長の箱が過半なら縦書きの順、そうでなければ公式の順。

    **公式の PaddleOCR にあるのは横書きの並べ替え（SortQuadBoxes）だけ。** 縦書きの
    ページをそれで並べると、列が左から右へ出てしまい、東アジアの縦書き（右から左）と
    逆になる。そこで、縦長の箱が半分より多いページだけ、列を右から左へ並べる。
    """
    if boxes and sum(is_vertical(b[0]) for b in boxes) * 2 > len(boxes):
        return sort_boxes_vertical(boxes)
    return sort_boxes(boxes)
