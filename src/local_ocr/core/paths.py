"""どこに何を置くかを、OS ごとに 1 か所で決める。

配置先を各所に散らすと、片方の OS でしか通らない書き方が紛れ込む。
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

APP_DIR_NAME = "Local OCR"

# 2026-09-21 まで使っていた名前。アプリ名が Local OCR に決まる前の名残り。
# 中身は 1.8GB あるので、取り直させずに移す（data_dir() を参照）。
FORMER_DIR_NAME = "PaddleOCR Local"

# 2026-09 に東洋文庫へ配った起動スクリプト版の置き場所。すでに 1.8GB を
# 取得済みの方に再取得させないため、あればそちらを使う。
LEGACY_DIR_NAME = "PaddleOCR校正"

# 置き場所を明示的に指定したいときの逃げ道。
#
# **画面には出していない。** 設定を増やすと、その分だけ説明するものが増える。
# 大半の方は触らなくてよい。要るのは 1 つの場面で、そこでは本物に困る:
# **Windows で C: が小さく D: が大きい機械**。モデルは最大 1.8GB あるので、
# 空きが無い機械では入らない。そういう方に「この 1 行を実行してください」と
# 案内して救うための口。
#
# **画面の設定にしなかった理由。** 設定ファイル（settings.json）は、その
# 置き場所の中にある。「どこに置くか」を、その場所の中には書けない。
# 画面から変えられるようにするには、既定の場所に道しるべのファイルを別に置く
# 二段構えが要る。実際に困る方が出てから作る。
DATA_DIR_ENV = "LOCAL_OCR_DATA_DIR"


def is_windows() -> bool:
    return platform.system() == "Windows"


def _os_dir(name: str) -> Path:
    """OS の作法に従った、その名前の置き場所。"""
    if is_windows():
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / name
    return Path.home() / "Library" / "Application Support" / name


def data_dir() -> Path:
    """モデルと llama.cpp を置く場所。

    ホーム直下ではなく OS の作法に従う。ホーム直下はバックアップ対象に
    入りやすく、2GB 近い再取得可能なファイルを同期させてしまう。

    環境変数 LOCAL_OCR_DATA_DIR があれば、そこを使う（DATA_DIR_ENV の注を参照）。
    """
    # **いちばん強い。** 空きが無い機械の逃げ道なので、ほかの候補がどう在ろうと
    # 指定された場所を使う。空文字は「指定していない」として扱う（シェルで
    # うっかり空のまま export したときに、変な場所を掘らせない）。
    override = os.environ.get(DATA_DIR_ENV, "").strip()
    if override:
        return Path(override).expanduser()

    legacy = Path.home() / LEGACY_DIR_NAME
    if legacy.is_dir():
        return legacy

    current = _os_dir(APP_DIR_NAME)
    if current.is_dir():
        return current

    # 前の名前のフォルダがあれば、そのまま名前を変える。中身はモデルと
    # settings.json で、取り直すと 1.8GB になる。移せなかったとき（権限など）は
    # 前の名前のまま使う。空振りしても害はない。
    former = _os_dir(FORMER_DIR_NAME)
    if former.is_dir():
        try:
            former.rename(current)
        except OSError:
            return former
    return current


def settings_file() -> Path:
    return data_dir() / "settings.json"
