"""配る手順の、外してはいけない約束。

**ここで見るのは .app そのものではなくスクリプトの中身。** 配布物を作るには
Flutter SDK と署名鍵と公証の資格情報が要り、CI や他人の機械では作れない。
それでも「外した瞬間に配布物が壊れるが、手元では最後まで気づけない」約束が
いくつかあるので、文面として見張っておく。

守らせたい約束（どれも docs/release.md に理由が書いてある）:

  1. `--cleanup-packages` を付けない — 依存が同梱しているライセンス全文が消える
  2. `--exclude` に `.venv` と `binaries` を入れる — 前者は数百 MB の無駄、
     後者は app.zip に入ると公証で必ず弾かれる
  3. `LICENSE` と `NOTICE` をバンドルの中に入れる — 6 つの依存はライセンス全文を
     wheel のどこにも持っておらず、その文面は NOTICE にしかない
  4. 署名対象を実行ビットで絞らない — dylib は実行ビットを持たないことがあり、
     取りこぼすと公証が Invalid で返る
  5. dmg を作る前に公証を確かめる — 未公証の .app を dmg に固めると、dmg 側の
     公証は通るので、配ったあと利用者側で初めて弾かれる
"""

from __future__ import annotations

import json
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"


def _body(name: str) -> str:
    """コメント行を落とした中身。約束を「コメントに書いただけ」で通さないため。"""
    text = (SCRIPTS / name).read_text(encoding="utf-8")
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


@pytest.mark.parametrize("script", ["build.zsh", "sign.zsh", "notarize.zsh", "release.zsh"])
def test_scripts_exist_and_are_executable(script):
    path = SCRIPTS / script
    assert path.is_file(), f"{script} がありません"
    if sys.platform == "win32":
        # 実行ビットは POSIX の概念。Windows の git checkout では
        # os.stat().st_mode が常に固定値を返し、実際のビットを反映しない
        # （2026-09-22、Windows の CI で初めて踏んだ）。
        pytest.skip("実行ビットは Windows では確かめられない")
    assert path.stat().st_mode & 0o111, f"{script} に実行ビットがありません"


# --- 1. ライセンス全文を消さない ---------------------------------------------

def test_build_counts_the_licence_texts_it_ships():
    """依存が同梱しているライセンス全文が、配布物に残っていることを毎回数える。

    Flet 0.86.2 は `--cleanup-packages` を **既定で有効にする**。消される既定の
    一覧（serious_python の `junkFilesDesktop`）に `*.dist-info/LICENSE` は入って
    いないので、これで困らない。ただし Flet や serious_python の版が上がれば
    一覧は変わりうる。**消えても起動するので、配ったあとまで気づけない。**
    だから build.zsh が毎回数えて、0 件なら止まる。
    """
    body = _body("build.zsh")
    assert "LICENSE*" in body, "ライセンス全文を数えていません"
    assert "LICENSES > 0" in body, "0 件でも止まらない書き方になっています"


def test_build_drops_the_debug_symbols_that_break_xcode():
    """`**/*.dSYM` を落とさないと、macOS のビルドが Xcode の段階で必ず失敗する。

    依存の pyobjc-core が試験用モジュール（PyObjCTest）とその .dSYM を同梱しており、
    Xcode 26 の strip はその x86_64 の側を処理できずに fatal error で止まる。
    """
    body = _body("build.zsh")
    assert "--cleanup-package-files" in body
    assert "*.dSYM" in body, "dSYM を落としていません。macOS のビルドが失敗します"


def test_build_declares_japanese_so_system_dialogs_follow():
    """日本語を申告しないと、ファイルを選ぶ窓 (OS が出すもの) が英語で出る。

    OS はアプリが申告した言語の中からしか選ばない。Flet の Info.plist は en だけ。
    2026-09-22、デモ動画の収録で、日本語の Mac で「開く」の窓が英語だったのを見て発覚。
    """
    body = _body("build.zsh")
    assert "CFBundleLocalizations" in body
    assert "string ja" in body


@pytest.mark.parametrize("script", ["build.zsh", "build.ps1"])
def test_build_keeps_package_sources_for_opencv(script):
    """依存を .pyc に置き換えると、cv2 が config.py を見つけられずに起動で落ちる。"""
    assert "--no-compile-packages" in _body(script)


# --- 2. 配布物に入れるもの / 入れないもの ------------------------------------

@pytest.mark.parametrize("excluded", [".venv", "binaries", "build", "tests", "scripts"])
def test_build_excludes_what_must_not_ship(excluded):
    body = _body("build.zsh")
    assert excluded in body, f"--exclude に {excluded} がありません"


def test_bundled_binaries_do_not_go_into_the_python_zip():
    """llama.cpp は app.zip ではなくバンドル内 Resources/bin へ。

    app.zip の中のファイルは署名できないので、そこに実行ファイルを置くと
    原理的に公証を通せない（src/local_ocr/core/bundled.py に同じことが書いてある）。
    """
    assert "Contents/Resources/bin" in _body("sign.zsh")


# --- 3. ライセンス表示を配布物に入れる ---------------------------------------

@pytest.mark.parametrize("script", ["sign.zsh", "notarize.zsh", "release.zsh"])
def test_licence_files_are_handled_at_every_step(script):
    """入れる（sign）→ 入っているか確かめる（notarize / release）。"""
    body = _body(script)
    assert "LICENSE" in body and "NOTICE" in body, f"{script} が表示の同梱を見ていません"


def test_the_notice_the_scripts_copy_actually_exists():
    for doc in ("LICENSE", "NOTICE"):
        assert (REPO / doc).is_file(), f"{doc} がリポジトリ直下にありません"


# --- 4. 署名の取りこぼし ------------------------------------------------------

def test_signing_selects_mach_o_by_file_type_not_by_permission():
    """判定は file(1) の Mach-O 判定で行う。

    実行ビットで絞ると dylib を取りこぼす。取りこぼしても手元では動くが、
    公証が Invalid で返る。
    """
    body = _body("sign.zsh")
    assert "Mach-O" in body
    assert "-perm" not in body, "パーミッションで署名対象を絞っています"


def test_signing_removes_absolute_symlinks_before_signing():
    """バンドル外を指す symlink は、署名の前に消す。

    後で消すと封が破れる。残すと公証は通っても Gatekeeper が
    invalid destination for symbolic link in bundle で弾く。
    """
    body = _body("sign.zsh")
    assert "readlink" in body
    remove = body.index("rm -f \"$link\"")
    sign = body.index("codesign --force")
    assert remove < sign, "symlink の除去が署名より後にあります"


# --- 5. 未公証のものを配らない ------------------------------------------------

def test_release_checks_the_notarisation_ticket_first():
    body = _body("release.zsh")
    validate = body.index("stapler validate")
    create = body.index("create-dmg \"${CREATE_DMG_ARGS[@]}\"")
    assert validate < create, "公証の確認が dmg 作成より後にあります"


def test_release_does_not_publish_unless_asked():
    """既定では外に何も出さない。タグと Release は --publish のときだけ。"""
    body = _body("release.zsh")
    assert "--publish" in body
    tag = body.index("git tag -a")
    guard = body.index('if [[ -z "$PUBLISH" ]]; then')
    assert guard < tag, "--publish の判定より前にタグを打っています"


# --- entitlements -------------------------------------------------------------

def test_entitlements_are_the_minimum_for_developer_id():
    """非サンドボックス。足すのはファイル選択ダイアログの 1 つだけ。

    ネットワークの項目は要らない（App Sandbox の中でしか意味を持たない）。
    library validation の緩和も、実際に落ちるまで足さない（最小権限）。
    """
    data = plistlib.loads((SCRIPTS / "entitlements.plist").read_bytes())
    assert data == {"com.apple.security.files.user-selected.read-write": True}


# --- 資格情報を平文で持たない -------------------------------------------------

def test_secrets_are_injected_from_1password_not_stored():
    """.env.example は op:// 参照の雛形だけ。実値も項目名も置かない。"""
    example = REPO / ".env.example"
    assert example.is_file()
    text = example.read_text(encoding="utf-8")
    assert "op://" in text
    assert "<item-name>" in text, "1Password の項目名が書かれていませんか"
    assert not (REPO / ".env").is_file() or ".env" in (REPO / ".gitignore").read_text(
        encoding="utf-8"
    ), ".env が .gitignore に入っていません"


# --- 配布物で起動できること ---------------------------------------------------

def test_main_puts_the_source_on_the_path_without_help():
    """`main.py` だけで `local_ocr` が import できること。

    **これは見た目の問題ではない。** 開発中は editable install が src/ を通すので、
    この処理が無くても動いてしまう。配布物には editable install が無く、
    パッケージ後のソースは `.../Resources/app/src/local_ocr/` に置かれるだけで、
    sys.path に載るのは `.../Resources/app/` だけ。だから

        ModuleNotFoundError: No module named 'local_ocr'

    で起動できない。**署名も公証も通り、.dmg が出来てから初めて分かる**
    （2026-09-21 に実際に踏んだ）。

    ここで import が通るかを見てはいけない。**手元の `.venv` には editable
    install が入っており、その `.pth` が src/ を sys.path に足してしまう。**
    だから main.py が何もしなくても import は通り、sys.path にも src/ が載る
    （それで一度この試験を取り逃がした）。`-S` を付けて site-packages の
    処理そのものを止め、**main.py だけで src/ が載るか**を見る。
    配布物には editable install が無いので、そこが唯一の入口になる。
    """
    text = (REPO / "main.py").read_text(encoding="utf-8")
    marker = "from local_ocr"
    assert marker in text, "main.py が local_ocr を import していません"
    prelude = text[: text.index(marker)]

    # `python -c` には __file__ が無いので、main.py の場所を与えてから実行する
    # （main.py はその場所を起点に src/ を探す）。
    code = f"__file__ = {str(REPO / 'main.py')!r}\n{prelude}\nimport json, sys\nprint(json.dumps(sys.path))"

    result = subprocess.run(
        [sys.executable, "-S", "-c", code],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, f"main.py の冒頭が実行できません:\n{result.stderr}"
    paths = {str(Path(entry).resolve()) for entry in json.loads(result.stdout) if entry}
    assert str(REPO / "src") in paths, (
        "main.py が src/ を sys.path に載せていません。"
        "配布物では ModuleNotFoundError: No module named 'local_ocr' で起動できません。"
        f"\n載っていたのは: {sorted(paths)}"
    )
