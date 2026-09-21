"""IIIF マニフェストを、読む版面の並びに開く。

**版面の URL を組み立てるところと、取り寄せるところだけを持つ。** 読むのは
これまでどおり `engines/`。ここは「どの画像を、どの大きさで貰うか」を決める。

決めごとは 4 つ。

- **v2 と v3 の両方を読む。** 公開されているマニフェストは今も 2 系が多い。
  形は違うが、欲しいものは「カンバスの並び」と「その版面の URL」だけなので、
  取り出し方を 2 通り書いて、後ろはひとつにする
- **画像サービスがあるときは、縮めて貰う。** 原寸は 1 枚 50MB になることがあり、
  そのまま貰っても読む前に縮めるだけ。長辺 `MAX_SIDE` に収まる幅を頼む
  (`{幅},` は Image API 2 でも 3 でも通る書き方。`!w,h` は通らない配信元がある)
- **一度取り寄せた版面は手元に残す。** ページを行き来するたびに貰い直さない。
  置き場所は `data_dir()/iiif`。設定画面から消せる
- **文面をここに書かない。** 失敗は `ManifestError` に鍵だけ載せて投げ、
  言葉は呼ぶ側 (`ui/i18n.py`) が付ける。core は画面の言語を知らない
"""

from __future__ import annotations

import hashlib
import json
import shutil
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from . import fetch
from .paths import data_dir

# 貰う版面の長辺の上限。これより大きい版面は、配信元に縮めて貰う。
# 1600 は `core/ocr.py` の上限と揃えてある(どのみちそこまでしか使わない)。
MAX_SIDE = 1600

_HEADERS = {"User-Agent": "Local-OCR", "Accept": "application/json, application/ld+json"}


class ManifestError(RuntimeError):
    """マニフェストとして開けなかった。

    `key` は `ui/i18n.py` の鍵。**ここで日本語を組み立てない。**
    """

    def __init__(self, key: str, **kw: object) -> None:
        self.key = key
        self.kw = kw
        super().__init__(key)


@dataclass
class Canvas:
    """1 カンバス = 1 ページ。`image_url` は実際に貰いに行く先。"""

    label: str
    image_url: str
    width: int = 0
    height: int = 0


@dataclass
class Manifest:
    label: str
    canvases: list[Canvas] = field(default_factory=list)


# --- 読む -----------------------------------------------------------------


def load(url: str, lang: str = "", timeout: float = 30.0) -> Manifest:
    """マニフェストの URL から、ページの並びを作る。糸(スレッド)の中から呼ぶ。"""
    return parse(_get_json(url, timeout), url=url, lang=lang)


def parse(doc: object, url: str = "", lang: str = "") -> Manifest:
    """読み込み済みの JSON からページの並びを作る。取り寄せはしない(試験もここを見る)。"""
    if not isinstance(doc, dict):
        raise ManifestError("iiif.error.parse")
    kind = str(doc.get("type") or doc.get("@type") or "")
    if "Collection" in kind:
        # コレクションは「マニフェストの一覧」。どれを読むかは利用者が決める。
        raise ManifestError("iiif.error.collection")
    canvases = _canvases_v3(doc, lang) if _is_v3(doc) else _canvases_v2(doc, lang)
    if not canvases:
        raise ManifestError("iiif.error.empty")
    return Manifest(label=_label(doc.get("label"), lang) or url, canvases=canvases)


def _is_v3(doc: dict) -> bool:
    context = doc.get("@context")
    texts = context if isinstance(context, list) else [context]
    if any(isinstance(c, str) and "presentation/3" in c for c in texts):
        return True
    return "sequences" not in doc and isinstance(doc.get("items"), list)


# --- v3 -------------------------------------------------------------------


def _canvases_v3(doc: dict, lang: str) -> list[Canvas]:
    out: list[Canvas] = []
    for i, canvas in enumerate(_dicts(doc.get("items"))):
        if str(canvas.get("type") or "Canvas") != "Canvas":
            continue
        body = _painting_body(canvas)
        if body is None:
            continue
        found = _canvas(body, canvas, i, lang)
        if found is not None:
            out.append(found)
    return out


def _painting_body(canvas: dict) -> dict | None:
    """カンバスに貼られている版面。注釈の入れ子を 1 つだけ辿る。

    body は 1 つとは限らない(`Choice` で原本と赤外線が並ぶことがある)。
    **先頭を採る。** 選ばせるのは、この道具の仕事ではない。
    """
    for page in _dicts(canvas.get("items")):
        for anno in _dicts(page.get("items")):
            if str(anno.get("motivation") or "painting") != "painting":
                continue
            body = anno.get("body")
            if isinstance(body, list):
                body = next(iter(_dicts(body)), None)
            if isinstance(body, dict) and str(body.get("type") or "") == "Choice":
                body = next(iter(_dicts(body.get("items"))), None)
            if isinstance(body, dict):
                return body
    return None


# --- v2 -------------------------------------------------------------------


def _canvases_v2(doc: dict, lang: str) -> list[Canvas]:
    sequences = _dicts(doc.get("sequences"))
    canvases = _dicts(sequences[0].get("canvases")) if sequences else _dicts(doc.get("canvases"))
    out: list[Canvas] = []
    for i, canvas in enumerate(canvases):
        images = _dicts(canvas.get("images"))
        resource = images[0].get("resource") if images else None
        if not isinstance(resource, dict):
            continue
        found = _canvas(resource, canvas, i, lang)
        if found is not None:
            out.append(found)
    return out


# --- 2 系に共通 -----------------------------------------------------------


def _canvas(body: dict, canvas: dict, index: int, lang: str) -> Canvas | None:
    width = _int(body.get("width")) or _int(canvas.get("width"))
    height = _int(body.get("height")) or _int(canvas.get("height"))
    url = image_url(body, width, height)
    if not url:
        return None
    label = _label(canvas.get("label"), lang) or str(index + 1)
    return Canvas(label=label, image_url=url, width=width, height=height)


def image_url(body: dict, width: int = 0, height: int = 0) -> str:
    """貰いに行く先。画像サービスがあれば、縮めた版面を頼む。

    サービスが無いマニフェストでは、貼られている画像をそのまま貰う(原寸)。
    大きさを指定する手立てが無いので、縮めるのは読む側に任せる。
    """
    service = _service_id(body)
    if not service:
        return str(body.get("id") or body.get("@id") or "")
    return f"{service.rstrip('/')}/full/{_size(width, height)}/0/default.jpg"


def _size(width: int, height: int) -> str:
    """`{幅},`。Image API 2 でも 3 でも通る、いちばん素直な頼み方。"""
    longest = max(width, height)
    if not longest:
        # 寸法を書いていないマニフェスト。横幅だけ決め打ちで頼む。
        return f"{MAX_SIDE},"
    if longest <= MAX_SIDE:
        return f"{width},"
    return f"{max(1, round(width * MAX_SIDE / longest))},"


def _service_id(body: dict) -> str:
    services = body.get("service") or body.get("services")
    for service in _dicts([services] if isinstance(services, dict) else services):
        found = service.get("@id") or service.get("id")
        if found:
            return str(found)
    return ""


def _label(value: object, lang: str = "") -> str:
    """題。v3 は言語ごとの束、v2 は文字か `{"@value": …}`。

    画面の言語があればそれを優先する。無ければ `none` (言語を決めていない値)、
    それも無ければ先頭。**空の題で押し通さない**(ページの見分けが付かなくなる)。
    """
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        if "@value" in value:
            return str(value["@value"]).strip()
        for key in ([lang] if lang else []) + ["none", "en", "ja"] + list(value):
            got = value.get(key)
            if isinstance(got, list) and got:
                return str(got[0]).strip()
            if isinstance(got, str) and got:
                return got.strip()
    if isinstance(value, list):
        for item in value:
            found = _label(item, lang)
            if found:
                return found
    return ""


def _dicts(value: object) -> list[dict]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, dict)):
        return []
    return [v for v in value if isinstance(v, dict)]


def _int(value: object) -> int:
    try:
        return max(0, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


# --- 取り寄せ -------------------------------------------------------------


def _get_json(url: str, timeout: float) -> object:
    request = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as res:
            raw = res.read()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ManifestError("iiif.error.fetch", error=_reason(exc)) from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ManifestError("iiif.error.parse") from exc


def image(url: str, timeout: float = 120.0) -> Image.Image:
    """版面を 1 枚。**取り寄せるのは初回だけ**で、次からは手元のものを開く。"""
    cached = cache_path(url)
    if not cached.is_file():
        try:
            fetch.to_file(url, cached, timeout=timeout)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ManifestError("iiif.error.image", error=_reason(exc)) from exc
    try:
        return Image.open(cached)
    except (OSError, ValueError) as exc:
        # 画像として開けないものが残っていると、次からもずっと開けない。
        cached.unlink(missing_ok=True)
        raise ManifestError("iiif.error.image", error=_reason(exc)) from exc


def _reason(exc: Exception) -> str:
    """利用者に見せる短い理由。urllib の入れ子を剥がす。"""
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        return str(exc.reason)
    return str(exc)


# --- 取り寄せた版面の置き場 -----------------------------------------------


def cache_dir() -> Path:
    return data_dir() / "iiif"


def cache_path(url: str) -> Path:
    """URL 1 つに 1 ファイル。中身の種類はまちまちなので拡張子は付けない

    (PIL は中身を見て判断する)。
    """
    return cache_dir() / (hashlib.sha256(url.encode("utf-8")).hexdigest()[:32] + ".img")


def cache_bytes() -> int:
    if not cache_dir().is_dir():
        return 0
    return sum(p.stat().st_size for p in cache_dir().glob("*") if p.is_file())


def clear_cache() -> None:
    shutil.rmtree(cache_dir(), ignore_errors=True)
