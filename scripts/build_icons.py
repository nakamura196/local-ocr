#!/usr/bin/env python3
"""アプリのアイコンを描いて、必要な形に書き出す。

絵柄はスマホ版（nakamura196/local-ocr-ios の scripts/make_app_icon.py）と同じ。
藍の地に、太い明朝の「読」を 1 字置き、四隅を朱の括弧（読み取り枠）で囲む。
背景にいくつかの文字（文・字・書・A・g・R）を薄く置く。
KotenOCR（生成りの地・朱の括弧・「典」）と同じ組み方にして、姉妹のアプリだと分かるようにし、
地の色と字で見分ける。スマホ版の図案を直したら、こちらも同じように直す。

文字の形を正しく出すため、SVG を Google Chrome（画面なしで起動）で描く。
書体は Google Fonts の Noto Serif JP Black と Noto Serif（SIL Open Font License 1.1）。
描くときに Google Fonts から書体を取るので、ネットワークが要る。

書き出し先:
    assets/icon.png                     Flet がアプリのアイコンに使う（1024px）
    packaging/windows/Assets/*.png      MSIX（Microsoft Store）が使う
    docs/assets/icon.png                紹介サイト（lo.ldas.jp）の左上（128px）

使い方:
    uv run python scripts/build_icons.py
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent

MASTER = 1024
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
GOOGLE = (
    '<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+JP:wght@900'
    '&family=Noto+Serif:wght@600&display=block" rel="stylesheet">'
)
CHAR = "読"

INDIGO_LIGHT = "#2f5a8c"  # 藍。左上が明るい
INDIGO_DARK = "#1b3557"
INK = "#f3ebdc"  # 生成り
SHU = "#e2603f"  # 朱。読み取り枠


def svg() -> str:
    bg = (
        '<defs><radialGradient id="g" cx="35%" cy="25%" r="95%">'
        f'<stop offset="0" stop-color="{INDIGO_LIGHT}"/>'
        f'<stop offset="1" stop-color="{INDIGO_DARK}"/></radialGradient></defs>'
        '<rect width="1024" height="1024" fill="url(#g)"/>'
    )
    ghosts = (
        "<g font-family=\"'Noto Serif JP','Noto Serif',serif\" font-size=\"150\" "
        f'fill="{INK}" opacity="0.10">'
        '<text x="610" y="150">文</text><text x="880" y="140">A</text>'
        '<text x="30" y="590">字</text><text x="870" y="420">g</text>'
        '<text x="40" y="960">書</text><text x="880" y="960">R</text></g>'
    )
    corners = (
        f'<g fill="none" stroke="{SHU}" stroke-width="34" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M190 330 V230 Q190 185 235 185 H335"/>'
        '<path d="M689 185 H789 Q834 185 834 230 V330"/>'
        '<path d="M190 694 V794 Q190 839 235 839 H335"/>'
        '<path d="M689 839 H789 Q834 839 834 794 V694"/></g>'
    )
    text = (
        '<text x="512" y="530" text-anchor="middle" dominant-baseline="central" '
        'font-family="\'Noto Serif JP\',serif" font-weight="900" '
        f'font-size="430" fill="{INK}">{CHAR}</text>'
    )
    return (
        '<svg viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg">'
        f"{bg}{ghosts}{corners}{text}</svg>"
    )


def render_square(png: Path) -> None:
    """角を丸めていない正方形を Chrome で描く。"""
    html = (
        f'<!doctype html><html><head><meta charset="utf-8">{GOOGLE}<style>'
        "html,body{margin:0;width:1024px;height:1024px;overflow:hidden}"
        "svg{display:block;width:1024px;height:1024px}"
        f"</style></head><body>{svg()}</body></html>"
    )
    page = png.with_suffix(".html")
    page.write_text(html, encoding="utf-8")
    subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            "--window-size=1024,1024",
            "--virtual-time-budget=15000",
            f"--screenshot={png}",
            page.as_uri(),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def rounded(square: Image.Image) -> Image.Image:
    """Big Sur 風に角を丸める（前の版と同じ丸み）。縁を滑らかにするため 4 倍で切り抜く。"""
    big = MASTER * 4
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, big - 1, big - 1], radius=int(big * 0.22), fill=255
    )
    out = square.convert("RGBA")
    out.putalpha(mask.resize((MASTER, MASTER), Image.LANCZOS))
    return out


def render_master() -> Image.Image:
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "icon.png"
        render_square(png)
        square = Image.open(png).convert("RGB")
    if square.size != (MASTER, MASTER):
        raise SystemExit(f"Chrome の出力の大きさが違います: {square.size}")
    return rounded(square)


def emit() -> None:
    master = render_master()

    app_icon = ROOT / "assets" / "icon.png"
    app_icon.parent.mkdir(parents=True, exist_ok=True)
    master.save(app_icon, optimize=True)
    print(f"{app_icon.relative_to(ROOT)}  {MASTER}x{MASTER}")

    site = ROOT / "docs" / "assets" / "icon.png"
    master.resize((128, 128), Image.LANCZOS).save(site, optimize=True)
    print(f"{site.relative_to(ROOT)}  128x128")

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
        master.resize((size, size), Image.LANCZOS).save(path, optimize=True)
        print(f"{path.relative_to(ROOT)}  {size}x{size}")

    # ワイドタイルだけ正方形ではないので、中央に置く。
    wide = Image.new("RGBA", (310, 150), (0, 0, 0, 0))
    glyph = master.resize((132, 132), Image.LANCZOS)
    wide.paste(glyph, ((310 - 132) // 2, (150 - 132) // 2), glyph)
    path = msix / "Wide310x150Logo.png"
    wide.save(path, optimize=True)
    print(f"{path.relative_to(ROOT)}  310x150")


if __name__ == "__main__":
    emit()
