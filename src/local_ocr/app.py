"""画面。

やることは 3 つだけに絞っている: エンジンを選ぶ / 画像を渡す / 読んだ文字をコピーする。
エンジンごとの違い(取得の要否・常駐の有無)は engines/ 側が吸収する。
"""

from __future__ import annotations

import threading
import traceback

import flet as ft
from PIL import Image

from .core import ocr as ocr_call
from .engines import available_engines

TITLE = "Local OCR"
SUBTITLE = "画像の文字を、このパソコンの中で読みます。画像は外に出ません。"


def main(page: ft.Page) -> None:
    page.title = TITLE
    page.window.width = 720
    page.window.height = 720
    page.padding = 20
    page.theme_mode = ft.ThemeMode.SYSTEM

    print("[main] start", flush=True)
    engines = {e.id: e for e in available_engines()}
    print("[main] engines", list(engines), flush=True)
    current = next(iter(engines.values()))
    # 読み取り中に画面を触らせないための札。
    busy = {"on": False}

    engine_note = ft.Text(current.note, size=12, color=ft.Colors.ON_SURFACE_VARIANT)
    status = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
    bar = ft.ProgressBar(visible=False)
    result = ft.TextField(
        multiline=True, min_lines=12, max_lines=12, expand=True,
        hint_text="ここに読んだ文字が出ます", text_size=13,
    )

    def note(msg: str, error: bool = False) -> None:
        status.value = msg
        status.color = ft.Colors.ERROR if error else ft.Colors.ON_SURFACE_VARIANT
        page.update()

    def on_progress(label: str, ratio: float | None) -> None:
        bar.visible = True
        bar.value = ratio
        pct = f"  {ratio * 100:.0f}%" if ratio is not None else ""
        note(f"{label}{pct}")

    # --- 読み取り ---------------------------------------------------------
    def run_ocr(img: Image.Image) -> None:
        if busy["on"]:
            return
        busy["on"] = True
        threading.Thread(target=_worker, args=(img,), daemon=True).start()

    def _worker(img: Image.Image) -> None:
        try:
            if not current.available():
                note("はじめての利用です。必要なものを取得します")
            current.prepare(on_progress)
            bar.visible = False
            note("読んでいます…")
            r = current.recognize(img)
            result.value = r.text
            note(f"読み終わりました（{len(r.text)} 文字）" if r.text else "文字が見つかりませんでした")
        except Exception as e:
            bar.visible = False
            note(f"うまくいきませんでした: {e}", error=True)
            traceback.print_exc()
        finally:
            busy["on"] = False
            page.update()

    # --- 入口 -------------------------------------------------------------
    # Flet 0.86 の FilePicker はサービスで、pick_files() が選ばれたものを返す
    # (以前の on_result コールバックは無い)。
    picker = ft.FilePicker()
    page.services.append(picker)

    async def pick(_=None) -> None:
        files = await picker.pick_files(
            dialog_title="読みたい画像を選びます",
            allowed_extensions=["png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp"],
        )
        if not files:
            return
        try:
            run_ocr(ocr_call.load(files[0].path))
        except Exception as ex:
            note(f"画像を開けませんでした: {ex}", error=True)

    def paste(_=None) -> None:
        img = ocr_call.from_clipboard()
        if img is None:
            note("クリップボードに画像がありません", error=True)
            return
        run_ocr(img)

    async def copy(_=None) -> None:
        if not result.value:
            return
        await page.clipboard.set(result.value)
        note("コピーしました")

    def on_engine(e) -> None:
        # Flet 0.86 の Dropdown は on_select。選ばれた値は control.value に入る。
        nonlocal current
        current = engines[dd.value]
        engine_note.value = current.note
        note("")
        page.update()

    dd = ft.Dropdown(
        value=current.id,
        options=[ft.DropdownOption(key=e.id, text=e.label) for e in engines.values()],
        on_select=on_engine,
        expand=True,
        dense=True,
    )

    def on_window_event(e) -> None:
        # 窓を閉じたら、常駐しているエンジンも止める。
        if e.data == "close":
            for eng in engines.values():
                try:
                    eng.shutdown()
                except Exception:
                    pass
            page.window.destroy()

    page.window.prevent_close = True
    page.window.on_event = on_window_event

    page.add(
        ft.Column(
            [
                ft.Text(TITLE, size=22, weight=ft.FontWeight.BOLD),
                ft.Text(SUBTITLE, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Divider(height=16),
                ft.Row([ft.Text("読む道具", size=13, width=70), dd]),
                engine_note,
                ft.Container(height=4),
                ft.Row([
                    ft.FilledButton("画像を選ぶ", on_click=pick),
                    ft.OutlinedButton("貼り付け", on_click=paste),
                    ft.Container(expand=True),
                    ft.OutlinedButton("コピー", on_click=copy),
                ]),
                bar,
                status,
                result,
            ],
            spacing=8,
            expand=True,
        )
    )
    note("画像を選ぶか、コピーした画像を貼り付けてください")
    print("[main] built", flush=True)


def run() -> None:
    ft.run(main)
