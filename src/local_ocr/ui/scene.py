"""撮影用の場面。Store の掲載画像を、CI の Windows 機で撮るためだけにある。

環境変数 `LOCAL_OCR_SCENE` があるときだけ動く。ふだんの起動では何もしない。
手元に Windows 機が無いので、画面をクリックして操作する代わりに、
アプリ自身に「見本を開いて読み終えた状態」まで進めさせる
(`scripts/screenshot-windows.ps1` が使う)。

**画面は本物のまま。** 読んだ結果も、その場で実際に読ませたもの。
掲載画像のために作った画面や、作り物の結果は出さない。

- `LOCAL_OCR_SCENE`: `read`(1 つで読む)か `compare`(くらべる)
- `LOCAL_OCR_SCENE_SOURCE`: 画像のファイルか、IIIF マニフェストの URL
- `LOCAL_OCR_SCENE_ENGINES`: 使う道具の id をカンマ区切りで。先頭が「1 つで読む」の道具
- `LOCAL_OCR_SCENE_PAGE`: 束のとき、開くページ(1 から数える)
- `LOCAL_OCR_SCENE_DONE`: 読み終えたら `ok`、しくじったら `error: …` を書くファイル。
  撮る側は、これが出来るのを待ってから撮る
"""

from __future__ import annotations

import asyncio
import os
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

from ..core import source
from ..ui.state import Doc

if TYPE_CHECKING:
    from ..app import App

ENV = "LOCAL_OCR_SCENE"

# モデルの取得と、CI の CPU での読み取りを待つ上限。
TIMEOUT = 30 * 60


def wanted() -> bool:
    return bool(os.environ.get(ENV, "").strip())


async def play(app: App) -> None:
    done = Path(os.environ.get(f"{ENV}_DONE", "") or "scene-done.txt")
    try:
        await asyncio.wait_for(_play(app), TIMEOUT)
    except Exception as exc:  # noqa: BLE001 - 撮る側に伝えて止めさせる
        traceback.print_exc()
        done.write_text(f"error: {exc!r}", encoding="utf-8")
        return
    # 結果を画面に描き終えるまで、少し待つ。
    await asyncio.sleep(2)
    done.write_text("ok", encoding="utf-8")


async def _play(app: App) -> None:
    kind = os.environ[ENV].strip()
    raw = os.environ[f"{ENV}_SOURCE"].strip()
    ids = [s.strip() for s in os.environ[f"{ENV}_ENGINES"].split(",") if s.strip()]
    page_no = int(os.environ.get(f"{ENV}_PAGE", "") or 1)

    state = app.state
    engines = [e for e in state.usable if e.id in ids]
    missing = set(ids) - {e.id for e in engines}
    if missing:
        raise RuntimeError(f"この OS では使えない道具: {sorted(missing)}")

    # 取得は先に済ませる。画面に「取得しますか」を出さないため。
    for engine in engines:
        await asyncio.to_thread(engine.prepare, lambda *_: None)

    state.set_engine(ids[0])
    state.compare = kind == "compare"
    if state.compare:
        state.compare_ids = set(ids)

    bundle = await asyncio.to_thread(source.expand, raw)
    doc = Doc.of(bundle.items, title=bundle.title, origin=bundle.origin)
    doc.go(page_no - 1)
    state.open(doc)
    app.go("work")
    view = app.view
    if kind == "compare":
        view.start_compare()  # type: ignore[union-attr]
    elif kind == "read":
        view.start()  # type: ignore[union-attr]
    else:
        raise ValueError(f"知らない場面: {kind}")

    job = doc.current
    assert job is not None
    while not (state.busy is False and set(ids if state.compare else ids[:1]) <= set(job.runs)):
        await asyncio.sleep(1)
    failed = [r.error for r in job.runs.values() if r.error]
    if failed:
        raise RuntimeError(f"読み取りに失敗: {failed}")
