#!/usr/bin/env python3
"""アプリのアイコンを描いて、必要な形に書き出す。

Pillow だけで描く。外部の画像素材もネットワークも要らないので、
いつ実行しても同じものが出る（元絵の PSD/AI を管理しなくて済む）。
考え方は ~/git/kim/archival-packager/scripts/build_icons.py と同じ。

絵柄: 藍色の地に縦書きの頁を置き、その四隅を朱色の鉤括弧で囲む。
「手元にある紙面を、いま機械が読んでいる」という意味。
archival-packager（青緑＋箱）とは色も形も重ならないようにしてある。

書き出し先:
    assets/icon.png                     Flet がアプリのアイコンに使う（1024px）
    packaging/windows/Assets/*.png      MSIX（Microsoft Store）が使う

使い方:
    uv run python scripts/build_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent

MASTER = 1024

BG_TOP = (44, 68, 128)       # 藍。上が明るい
BG_BOTTOM = (18, 28, 62)     # 下は沈める
PAGE = (247, 246, 241)       # 生成りの紙
PAGE_EDGE = (206, 206, 196)  # 紙の縁の影
INK = (44, 52, 66)           # 墨
MARK = (232, 93, 58)         # 朱。読み取り枠


def _lerp(a: int, b: int, t: float) -> int:
    return int(round(a + (b - a) * t))


def _vertical_gradient(size: int, top: tuple, bottom: tuple) -> Image.Image:
    grad = Image.new("RGB", (1, size))
    px = grad.load()
    for y in range(size):
        t = y / max(1, size - 1)
        px[0, y] = (
            _lerp(top[0], bottom[0], t),
            _lerp(top[1], bottom[1], t),
            _lerp(top[2], bottom[2], t),
        )
    return grad.resize((size, size))


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=radius, fill=255
    )
    return mask


def _bracket(d: ImageDraw.ImageDraw, x: float, y: float, arm: float,
             sx: int, sy: int, width: int) -> None:
    """(x, y) を角として、sx/sy の向きに腕を伸ばした鉤括弧を 1 つ描く。"""
    d.line([(x, y + sy * arm), (x, y), (x + sx * arm, y)],
           fill=MARK, width=width, joint="curve")
    cap = width / 2
    for px_, py_ in ((x, y + sy * arm), (x + sx * arm, y), (x, y)):
        d.ellipse([px_ - cap, py_ - cap, px_ + cap, py_ + cap], fill=MARK)


def render_master() -> Image.Image:
    """MASTER の大きさで RGBA を描く。"""
    S = MASTER
    SS = 2                      # 一度 2 倍で描いて縮める（縁を滑らかに）
    W = S * SS

    radius = int(W * 0.22)      # Big Sur 風の丸み
    grad = _vertical_gradient(W, BG_TOP, BG_BOTTOM).convert("RGBA")
    canvas = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    canvas.paste(grad, (0, 0), _rounded_mask(W, radius))

    cx = W / 2
    cy = W * 0.505

    # --- 紙 ---------------------------------------------------------------
    page_w = W * 0.44
    page_h = W * 0.56
    page_left = cx - page_w / 2
    page_right = cx + page_w / 2
    page_top = cy - page_h / 2
    page_bottom = cy + page_h / 2
    r_page = W * 0.022

    shadow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [page_left, page_top, page_right, page_bottom],
        radius=r_page, fill=(0, 0, 0, 90),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(W * 0.016))
    drop = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    drop.paste(shadow, (0, int(W * 0.014)))
    canvas = Image.alpha_composite(canvas, drop)

    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle(
        [page_left, page_top, page_right, page_bottom],
        radius=r_page, fill=PAGE, outline=PAGE_EDGE,
        width=max(1, int(W * 0.003)),
    )

    # --- 縦書きの文字 -------------------------------------------------------
    # 右から左へ 4 行。角の丸い正方形を積む。大きく出せば文字に、
    # 小さく出せば縞に見える（44px でも潰れない）。
    # 最後の行（左端）だけ短くして、文章の終わりらしく見せる。
    glyph = W * 0.050          # 文字の一辺
    gap_y = W * 0.019          # 字間
    gap_x = W * 0.038          # 行間
    r_glyph = glyph * 0.24
    counts = (6, 6, 6, 4)

    block_w = len(counts) * glyph + (len(counts) - 1) * gap_x
    block_h = max(counts) * glyph + (max(counts) - 1) * gap_y
    first_cx = cx + block_w / 2 - glyph / 2     # 右端の行の中心
    col_top = cy - block_h / 2

    for i, n in enumerate(counts):
        gx = first_cx - i * (glyph + gap_x)
        for j in range(n):
            gy = col_top + j * (glyph + gap_y)
            d.rounded_rectangle(
                [gx - glyph / 2, gy, gx + glyph / 2, gy + glyph],
                radius=r_glyph, fill=INK,
            )

    # --- 読み取り枠（四隅の鉤括弧） -------------------------------------------
    inset = W * 0.030          # 紙より少し外側
    arm = W * 0.105
    stroke = max(3, int(W * 0.034))
    bl, br = page_left - inset, page_right + inset
    bt, bb = page_top - inset, page_bottom + inset
    _bracket(d, bl, bt, arm, +1, +1, stroke)
    _bracket(d, br, bt, arm, -1, +1, stroke)
    _bracket(d, bl, bb, arm, +1, -1, stroke)
    _bracket(d, br, bb, arm, -1, -1, stroke)

    return canvas.resize((S, S), Image.LANCZOS)


def emit() -> None:
    master = render_master()

    app_icon = ROOT / "assets" / "icon.png"
    app_icon.parent.mkdir(parents=True, exist_ok=True)
    master.save(app_icon)
    print(f"{app_icon.relative_to(ROOT)}  {MASTER}x{MASTER}")

    # MSIX 用。名前と大きさは AppxManifest.xml.in が参照するものと揃える。
    msix = ROOT / "packaging" / "windows" / "Assets"
    msix.mkdir(parents=True, exist_ok=True)
    for name, size in [
        ("Square44x44Logo", 44),
        ("Square150x150Logo", 150),
        ("Square310x310Logo", 310),
        ("StoreLogo", 50),
    ]:
        path = msix / f"{name}.png"
        master.resize((size, size), Image.LANCZOS).save(path)
        print(f"{path.relative_to(ROOT)}  {size}x{size}")

    # ワイドタイルだけ正方形ではないので、中央に置く。
    wide = Image.new("RGBA", (310, 150), (0, 0, 0, 0))
    glyph = master.resize((132, 132), Image.LANCZOS)
    wide.paste(glyph, ((310 - 132) // 2, (150 - 132) // 2), glyph)
    path = msix / "Wide310x150Logo.png"
    wide.save(path)
    print(f"{path.relative_to(ROOT)}  310x150")


if __name__ == "__main__":
    emit()
