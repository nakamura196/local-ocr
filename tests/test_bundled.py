"""同梱した llama.cpp の扱い。

**CI にも開発機にも binaries/ が在るとは限らない**（`scripts/fetch-binaries.zsh` を
走らせた機械にしか無い）。なのでここで見るのは、置き場所の決め方と、同梱に
切り替えたことで守らなければならなくなった約束の方。

守らせたい約束は 2 つ。
  1. llama.cpp を初回取得の一覧に戻さない（戻すとストアの審査とぶつかる）
  2. 版を 2 か所に書かない（取得スクリプトは assets.py の LLAMA_BUILD を読む）
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from local_ocr.core import assets, bundled

REPO = Path(__file__).resolve().parents[1]


# --- 初回に取得するもの -------------------------------------------------------

def test_llama_is_not_downloaded_any_more():
    """実行ファイルを取ってきて動かす形に戻っていないこと。

    ストアの審査は「審査が見たものと、実際に動くものが同じ」であることを見る。
    llama.cpp を required() に戻すと、そこが崩れる。
    """
    for asset in assets.required():
        assert asset.dest.suffix == ".gguf", f"実行ファイルらしきものが混ざっています: {asset.key}"
        assert "llama.cpp" not in asset.url


def test_only_the_two_models_are_fetched():
    assert [a.key for a in assets.required()] == ["model", "mmproj"]


# --- 置き場所 -----------------------------------------------------------------

def test_dev_layout_is_one_of_the_candidates():
    """開発時（uv run / pytest）は、リポジトリ直下の binaries/<os>/ を見る。"""
    candidates = bundled._candidate_dirs()
    assert REPO / "binaries" / "macos" in candidates or REPO / "binaries" / "windows" in candidates


def test_packaged_layout_sits_outside_the_python_zip():
    """同梱先は sys.executable の隣。

    Python 側（app.zip に入る場所）に置くと、起動はできても公証で必ず弾かれる。
    """
    packaged = bundled._candidate_dirs()[0]
    assert packaged.name == "bin"
    assert Path(sys.executable).resolve().parent not in (packaged, packaged.parent.parent)


def test_missing_bundle_is_none_not_a_guess():
    """見つからないときに、それらしい道を作って返さないこと。

    Path を返してしまうと、呼ぶ側が is_file() を忘れた瞬間に
    「存在しない実行ファイルを起動しようとする」形の落ち方になる。
    """
    if bundled.bin_dir() is None:
        assert assets.server_path() is None
    else:
        assert assets.server_path() == bundled.bin_dir() / bundled.find("llama-server").name


# --- 版の固定 -----------------------------------------------------------------

@pytest.mark.parametrize("script", ["fetch-binaries.zsh", "fetch-binaries.ps1"])
def test_fetch_scripts_do_not_hardcode_the_build(script):
    """版は assets.py の LLAMA_BUILD だけに書く。

    2 か所に書くと、片方だけ上げたときに「取ってきたものと、アプリが探すもの」が
    ずれる。ずれても開発機では前に取ったものが残っていて動いてしまう。
    """
    text = (REPO / "scripts" / script).read_text(encoding="utf-8")
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert assets.LLAMA_BUILD not in body, f"{script} に版が直接書いてあります"
    assert "LLAMA_BUILD" in body


def test_the_line_the_scripts_read_still_looks_the_same():
    """取得スクリプトは `LLAMA_BUILD = "..."` という行そのものを読んでいる。"""
    source = (REPO / "src" / "local_ocr" / "core" / "assets.py").read_text(encoding="utf-8")
    found = re.findall(r'^LLAMA_BUILD = "(.*)"$', source, re.MULTILINE)
    assert found == [assets.LLAMA_BUILD]
