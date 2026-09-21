"""保存。テキストと TEI/XML。ファイルに書くのはここだけ。

**書きかけのファイルを残さない。** 隣に書いてから差し替える。途中で落ちたときに
中途半端な XML が残ると、開いた側には「壊れた保存結果」にしか見えない。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path, PurePosixPath

from PIL import Image

from . import prefs

TEXT_SUFFIX = ".txt"
TEI_SUFFIX = ".xml"


def write_text(dest: Path, text: str) -> None:
    body = text if text.endswith("\n") else text + "\n"
    _write(dest, body)


def write_tei(dest: Path, xml: str) -> None:
    _write(dest, xml)


def _write(dest: Path, body: str) -> None:
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(dest)


def image_beside(dest: Path, image: Image.Image, source: Path | None = None) -> Path:
    """TEI の隣に版面を置く。`<graphic>` の指す先が無い TEI を作らないため。

    元のファイルがあるならそのまま写す。**詰め直さない**(JPEG を PNG に開き直すと、
    元が 0.8MB でも 4.5MB になる)。貼り付けた画像のように元が無いときだけ書き出す。
    """
    if source is not None and source.is_file():
        out = dest.with_suffix(source.suffix.lower() or ".png")
        if out != source:
            shutil.copyfile(source, out)
        return out
    out = dest.with_suffix(".png")
    image.convert("RGB").save(out, format="PNG")
    return out


# 版面まで何段さかのぼってよいか。これを超えるなら、隣に置いた方が持ち運べる。
MAX_UP = 2


def graphic_url(dest: Path, source: Path) -> str | None:
    """`<graphic url="…">`。TEI の置き場所から見た相対の道にする。

    絶対の道を書くと、そのパソコンでしか開けない TEI になる。**遠すぎるときは
    None**(`../../../../..` と書いても、人に渡した先では開けない)。そのときは
    版面を隣に置く。決めるのは呼ぶ側。
    """
    try:
        rel = os.path.relpath(source, dest.parent)
    except ValueError:
        # Windows で TEI と画像が別のドライブにあると、そもそも相対にできない。
        return None
    parts = Path(rel).parts
    if sum(1 for part in parts if part == "..") > MAX_UP:
        return None
    return PurePosixPath(*parts).as_posix()


# --- 保存先を覚える -------------------------------------------------------
#
# 毎回ダイアログで選んでもらうが、開く場所は前回の続きにする。
# 1 ページごとに同じフォルダを探し直させない。


def last_dir() -> str | None:
    saved = str(prefs.get("save_dir") or "")
    return saved if saved and Path(saved).is_dir() else None


def remember_dir(dest: Path) -> None:
    prefs.save(save_dir=str(dest.parent))
