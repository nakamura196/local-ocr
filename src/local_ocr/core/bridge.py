"""ほかの道具から、この機械の OCR を使えるようにする窓口。

ブラウザの中で動く頁(校正の画面など)は、手元のコマンドを起動できない。
繋ぐ道は HTTP しかないので、**開けている間だけ llama-server を立てたままにし**、
127.0.0.1 の決まったポートで待つ。

決めごとは 4 つ。

- **既定は閉じている。** 開けた時点で、その機械で開いているどの頁からでも
  画像を投げられる状態になる。利用者が設定画面で開けたときだけ開く
- **繋いでよい相手は、利用者が足した一覧だけ。** `*`(どの頁からでも)は作らない。
  閉じている間と、一覧が空のときは、誰も名乗れない相手を渡して全部断る。
  **`--cors-origins` を省いてはいけない。** 省くと llama-server の既定の `*` になり、
  閉じているつもりのまま全開になる
- **外には出さない。** 待つのは 127.0.0.1 だけなので、同じ機械の中からしか繋がらない
- **繋いでよい相手を変えたら、立て直す。** llama-server は起動のときの一覧しか見ない。
  ここで立て直しておかないと、画面の一覧と実際に通る相手がずれる

いま出せるのは PaddleOCR-VL だけ(常駐のサーバを持つのがこれだけのため)。
`engines/base.py` の `recognize` をそのまま外に出す汎用の窓口は、
読む道具が出揃ってから作る(docs/design.md)。
"""

from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING

from . import prefs

if TYPE_CHECKING:  # 実行時には取り込まない(runtime.py がこちらを取り込むため)
    from .runtime import Runtime

# 起動スクリプト版と同じ既定。校正の画面からしか呼べないようにしている。
DEFAULT_ORIGINS = ("https://tei-iiif-editor.vercel.app",)

# 誰も名乗れない相手。`.invalid` は RFC 2606 で予約されていて、どの頁の出どころにも
# ならない。「全部断る」を、空文字や `*` ではなくこれで表す。
DENY_ALL = "https://none.invalid"


# --- 開いているかどうか ---------------------------------------------------
def enabled() -> bool:
    return bool(prefs.get("share", False))


def set_enabled(on: bool) -> None:
    prefs.save(share=bool(on))


# --- 繋いでよい相手 -------------------------------------------------------
def allowed_origins() -> list[str]:
    saved = prefs.get("origins")
    if isinstance(saved, list):
        # 空の一覧は「まだ誰も許可していない」。既定で埋め戻さない。
        return [str(v).strip() for v in saved if str(v).strip()]
    # 起動スクリプト版と、この窓口より前の版は 1 つだけ持っていた。
    legacy = str(prefs.get("origin") or "").strip()
    return [legacy] if legacy else list(DEFAULT_ORIGINS)


def set_allowed_origins(values: list[str]) -> None:
    prefs.save(origins=list(dict.fromkeys(values)))


def normalize_origin(text: str) -> str:
    """入れられた文字を、ブラウザが名乗る形("https://example.com")に揃える。

    受け付けるのは「どの頁か」ではなく「どの出どころか」。道(パス)まで書かれても
    落とす。ブラウザが送ってくる Origin に道は入らないので、残すと一生一致しない。

    合わないものは `ValueError` を投げる。中身は画面側が文面を引くための短い名前
    (`empty` / `wildcard` / `scheme` / `path`)。**ここに画面の文言を書かない。**
    """
    value = text.strip()
    if not value:
        raise ValueError("empty")
    if "*" in value:
        raise ValueError("wildcard")
    if "//" not in value:
        # 「example.com」「localhost:3000」だけ書かれたとき。
        value = "https://" + value
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("scheme")
    if parsed.path.strip("/") or parsed.query or parsed.fragment:
        raise ValueError("path")
    return f"{parsed.scheme}://{parsed.netloc}"


def cors_value() -> str:
    """llama-server の `--cors-origins` にそのまま渡す値。

    閉じている間も、立っているサーバはある(画面から読むときに使う)。そのときは
    **どの頁からも通さない**値にしておく。窓口の開け閉めが、ここだけで効く。
    """
    origins = allowed_origins() if enabled() else []
    return ",".join(origins) if origins else DENY_ALL


class Bridge:
    """窓口の開け閉め。サーバの起動・停止そのものは `Runtime` が持つ。

    **新しく `Runtime` を作らない。** 読む道具が持っているものをそのまま渡す。
    別に作ると同じポートへ二重に立てようとして、重みを二度読むことになる。
    """

    def __init__(self, runtime: Runtime) -> None:
        self._rt = runtime

    @property
    def enabled(self) -> bool:
        return enabled()

    @property
    def endpoint(self) -> str:
        return self._rt.endpoint

    @property
    def port(self) -> int:
        return self._rt.port

    @property
    def origins(self) -> list[str]:
        return allowed_origins()

    @property
    def open(self) -> bool:
        """いま本当に繋がるか。開けたつもりで落ちていることがあるので、毎回見る。"""
        return enabled() and self._rt.ready

    def port_busy(self) -> bool:
        """閉じたあとも同じポートで何かが待っているか(もう 1 つ開いたこのアプリなど)。"""
        return self._rt.health() != "down"

    # --- 開け閉め ---------------------------------------------------------
    def turn_on(self) -> None:
        """開ける。重みの読み込みが終わるまで戻らないので、**糸(スレッド)から呼ぶ。**

        失敗しても設定は倒さない。「開けるつもりだが開けていない」を画面に出して、
        何をすればよいかを見せるため(黙って閉じると、なぜ繋がらないか分からない)。
        """
        set_enabled(True)
        # 閉じた状態で立っていたら、繋いでよい相手を入れ替えるために立て直す。
        self._rt.stop()
        self._rt.start()
        if not self._rt.wait_ready():
            raise RuntimeError("OCR を起動できませんでした")

    def turn_off(self) -> None:
        set_enabled(False)
        self._rt.stop()

    # --- 繋いでよい相手 ---------------------------------------------------
    def add_origin(self, origin: str) -> None:
        if origin in self.origins:
            return
        set_allowed_origins([*self.origins, origin])

    def remove_origin(self, origin: str) -> None:
        set_allowed_origins([v for v in self.origins if v != origin])
