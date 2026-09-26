"""ほかの道具から、この機械の OCR を使えるようにする窓口の、開け閉めと決めごと。

ブラウザの中で動く頁(校正の画面など)は、手元のコマンドを起動できない。
繋ぐ道は HTTP しかないので、**開けている間だけ窓口(`core/gateway.py`)を立て**、
127.0.0.1 の決まったポート(既定 8080)で待つ。PaddleOCR-VL の llama-server は
その後ろ(8082)に隠れ、窓口だけが話す。

決めごとは 4 つ。

- **既定は閉じている。** 開けた時点で、その機械で開いているどの頁からでも
  画像を投げられる状態になる。利用者が設定画面で開けたときだけ開く
- **繋いでよい相手は、利用者が足した一覧だけ。** `*`(どの頁からでも)は作らない。
  閉じている間と、一覧が空のときは、どの頁も通さない
- **外には出さない。** 待つのは 127.0.0.1 だけなので、同じ機械の中からしか繋がらない
- **llama-server 自身は誰も通さない**(`--cors-origins` に誰も名乗れない相手を渡す)。
  頁は必ず窓口を通る。窓口は一覧を毎回読むので、相手を変えても立て直さなくてよい
"""

from __future__ import annotations

import socket
import urllib.parse
from typing import TYPE_CHECKING

from . import prefs

if TYPE_CHECKING:  # 実行時には取り込まない(runtime.py がこちらを取り込むため)
    from .gateway import Gateway
    from .runtime import Runtime

# 校正の画面(TEI/IIIF エディタ)からしか呼べないようにしている。
# エディタは 2026-09 に vercel.app から ldas.jp へ移った。旧 URL は転送に切り替わる
# までのあいだ使われるので、並べて持つ。
EDITOR_ORIGIN = "https://tei-editor.ldas.jp"
OLD_EDITOR_ORIGIN = "https://tei-iiif-editor.vercel.app"
DEFAULT_ORIGINS = (EDITOR_ORIGIN, OLD_EDITOR_ORIGIN)

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
        origins = [str(v).strip() for v in saved if str(v).strip()]
    else:
        # 起動スクリプト版と、この窓口より前の版は 1 つだけ持っていた。
        legacy = str(prefs.get("origin") or "").strip()
        if not legacy:
            return list(DEFAULT_ORIGINS)
        origins = [legacy]
    return _follow_editor_move(origins)


def _follow_editor_move(origins: list[str]) -> list[str]:
    """エディタの引っ越しに、保存済みの一覧を 1 度だけ追いつかせる。

    前の版は旧 URL を一覧に書き込んで保存している。そのままだと新しい URL の
    エディタから繋げない(403)。旧 URL を持っている人にだけ新しい URL を足す。
    **足すのは 1 度だけ。** そのあと利用者が外したら、外したままにする。
    """
    if prefs.get("editor_moved_to_ldas"):
        return origins
    if OLD_EDITOR_ORIGIN in origins and EDITOR_ORIGIN not in origins:
        origins = [EDITOR_ORIGIN, *origins]
        prefs.save(origins=origins, editor_moved_to_ldas=True)
    elif OLD_EDITOR_ORIGIN in origins or EDITOR_ORIGIN in origins:
        prefs.save(editor_moved_to_ldas=True)
    return origins


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


def allows(origin: str) -> bool:
    """この頁(出どころ)からの呼び出しを通してよいか。閉じている間は誰も通さない。"""
    return enabled() and origin != DENY_ALL and origin in allowed_origins()


# --- 窓口の場所 -----------------------------------------------------------
PORT_PREF_KEY = "port"  # 前の版で llama-server を立てていたのと同じ設定・同じ既定
DEFAULT_PORT = 8080


def port() -> int:
    return int(prefs.get(PORT_PREF_KEY, DEFAULT_PORT))


class Bridge:
    """窓口の開け閉め。窓口(HTTP)は `Gateway`、PaddleOCR-VL のサーバは `Runtime` が持つ。

    **新しく `Runtime` を作らない。** 読む道具が持っているものをそのまま渡す。
    別に作ると同じポートへ二重に立てようとして、重みを二度読むことになる。
    """

    def __init__(self, runtime: Runtime | None, gateway: Gateway | None = None) -> None:
        self._rt = runtime
        self._gw = gateway

    @property
    def enabled(self) -> bool:
        return enabled()

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def port(self) -> int:
        return port()

    @property
    def origins(self) -> list[str]:
        return allowed_origins()

    @property
    def open(self) -> bool:
        """いま本当に繋がるか。開けたつもりで落ちていることがあるので、毎回見る。"""
        if not enabled():
            return False
        if self._gw is not None:
            return self._gw.running
        return self._rt is not None and self._rt.ready

    def port_busy(self) -> bool:
        """閉じたあとも同じポートで何かが待っているか(もう 1 つ開いたこのアプリなど)。"""
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                return True
        except OSError:
            return False

    # --- 開け閉め ---------------------------------------------------------
    def turn_on(self) -> None:
        """開ける。PaddleOCR-VL の読み込みが終わるまで戻らないので、**糸(スレッド)から呼ぶ。**

        失敗しても設定は倒さない。「開けるつもりだが開けていない」を画面に出して、
        何をすればよいかを見せるため(黙って閉じると、なぜ繋がらないか分からない)。
        """
        set_enabled(True)
        if self._gw is not None and not self._gw.running:
            try:
                self._gw.start(self.port)
            except OSError as exc:
                raise RuntimeError("OCR の窓口を開けませんでした") from exc
        # PaddleOCR-VL が取得済みなら、先に立てておく(最初の 1 回を待たせない)。
        # 取得していなければ立てない。ほかの道具(NDL など)は窓口から使える。
        if self._rt is not None and getattr(self._rt, "fetched", True):
            self._rt.start()
            if not self._rt.wait_ready():
                raise RuntimeError("OCR を起動できませんでした")

    def turn_off(self) -> None:
        set_enabled(False)
        if self._gw is not None:
            self._gw.stop()
        if self._rt is not None:
            self._rt.stop()

    # --- 繋いでよい相手 ---------------------------------------------------
    def add_origin(self, origin: str) -> None:
        if origin in self.origins:
            return
        set_allowed_origins([*self.origins, origin])

    def remove_origin(self, origin: str) -> None:
        set_allowed_origins([v for v in self.origins if v != origin])
