"""端末から使う口。画面を開かずに、画面と同じ道具で同じ結果を出す。

**flet を取り込まない。** 画面の無いところ(サーバ・CI・他のスクリプトの中)でも
動くようにする。読む道具も TEI の組み立ても画面側と同じものを使うので、
出てくるものは画面で保存したものと一致する。

    local-ocr 画像.jpg
    local-ocr フォルダ --format tei --out out.xml
    local-ocr --list-engines
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from PIL import Image

from .core import export, fetch, tei
from .core.ocr import IMAGE_SUFFIXES
from .engines import Engine, Line, all_engines, runs_here
from .ui.i18n import current, engine_label, t


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    if args.list_engines:
        _list_engines()
        return 0

    paths = _expand(args.paths)
    if not paths:
        return _fail(t("cli.no_images"))

    try:
        engine = _engine(args.engine)
    except LookupError as exc:
        return _fail(str(exc))

    if engine.assets and not engine.available() and not args.fetch:
        size = fetch.human(fetch.total_bytes(engine.assets))
        return _fail(t("cli.not_fetched", engine=engine_label(engine), size=size))

    out = Path(args.out) if args.out else None
    try:
        pages, texts = _read(engine, paths, out, quiet=args.quiet)
    finally:
        engine.shutdown()
    if not pages:
        return 1

    if args.format == "tei":
        body = tei.build(pages, _meta(args, paths, engine))
    else:
        body = "\n\n".join(texts).rstrip("\n") + "\n"

    if out is None:
        sys.stdout.write(body)
    else:
        (export.write_tei if args.format == "tei" else export.write_text)(out, body)
        _say(t("cli.wrote", name=out.name, pages=len(pages)), args.quiet)
    return 0


# --- 読む -----------------------------------------------------------------


def _read(
    engine: Engine, paths: list[Path], out: Path | None, quiet: bool
) -> tuple[list[tei.Page], list[str]]:
    """1 枚ずつ読む。1 枚こけても残りは読む(戻り値には入れない)。"""

    def on_progress(label: str, ratio: float | None) -> None:
        pct = f" {ratio * 100:.0f}%" if ratio is not None else ""
        _say(f"\r{label}{pct}", quiet, end="")

    engine.prepare(on_progress)
    _say("", quiet)

    pages: list[tei.Page] = []
    texts: list[str] = []
    for path in paths:
        try:
            with Image.open(path) as img:
                started = time.monotonic()
                result = engine.recognize(img)
                width, height = img.size
        except Exception as exc:  # noqa: BLE001 - 1 枚こけても残りは読む
            _fail(t("cli.failed", name=path.name, error=exc))
            continue
        lines = result.lines or [Line(text=s) for s in result.text.splitlines() if s.strip()]
        pages.append(
            tei.Page(
                lines=lines,
                width=width,
                height=height,
                image_url=_graphic_url(out, path),
            )
        )
        texts.append(result.text)
        _say(
            t(
                "cli.read",
                name=path.name,
                count=len(lines),
                chars=len(result.text),
                seconds=f"{time.monotonic() - started:.1f}",
            ),
            quiet,
        )
    return pages, texts


def _graphic_url(out: Path | None, image: Path) -> str:
    """`<graphic url="…">`。書き出し先から見た相対の道にする。

    端末から使うときは、画像を勝手に写さない(画面側は隣に置くが、こちらは
    渡された場所を触らない方が驚きが無い)。相対にできないときだけ絶対の道になる。
    """
    dest = out or Path.cwd() / "_"
    return export.graphic_url(dest, image) or image.resolve().as_posix()


# --- 引数 -----------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="local-ocr", description=t("cli.description"))
    p.add_argument("paths", nargs="*", metavar="PATH", help=t("cli.help.paths"))
    p.add_argument("--engine", metavar="ID", default="", help=t("cli.help.engine"))
    p.add_argument("--format", choices=("text", "tei"), default="text", help=t("cli.help.format"))
    p.add_argument("--out", metavar="PATH", default="", help=t("cli.help.out"))
    p.add_argument("--title", metavar="TEXT", default="", help=t("cli.help.title"))
    p.add_argument("--fetch", action="store_true", help=t("cli.help.fetch"))
    p.add_argument("--quiet", "-q", action="store_true", help=t("cli.help.quiet"))
    p.add_argument("--list-engines", action="store_true", help=t("cli.help.list"))
    return p


def _expand(paths: list[str]) -> list[Path]:
    """フォルダは、その中の画像に開く(中のフォルダまでは潜らない)。"""
    out: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if path.is_dir():
            out += sorted(
                child
                for child in path.iterdir()
                if child.is_file() and child.suffix.lower().lstrip(".") in IMAGE_SUFFIXES
            )
        elif path.is_file():
            out.append(path)
        else:
            _fail(t("cli.failed", name=raw, error=t("cli.not_found")))
    return out


def _engine(engine_id: str) -> Engine:
    here = [e for e in all_engines() if runs_here(e)]
    if not engine_id:
        # 画面側と同じ既定。取得の要らないものを先に。
        ready = [e for e in here if not e.assets]
        return (ready or here)[0]
    for e in all_engines():
        if e.id == engine_id:
            if not runs_here(e):
                raise LookupError(t("cli.unsupported", engine=engine_label(e)))
            return e
    raise LookupError(t("cli.unknown_engine", engine=engine_id))


def _meta(args, paths: list[Path], engine: Engine) -> tei.Meta:
    if args.title:
        title = args.title
    elif len(paths) == 1:
        title = paths[0].stem
    else:
        title = paths[0].parent.name or paths[0].stem
    source = paths[0].name if len(paths) == 1 else t("cli.source.many", count=len(paths))
    return tei.Meta(title=title, engine=engine_label(engine), source=source, language=current())


def _list_engines() -> None:
    for e in all_engines():
        if not runs_here(e):
            state = t("settings.state.unsupported", names=", ".join(sorted(e.platforms)))
        elif not e.assets:
            state = t("settings.state.none_needed")
        else:
            size = fetch.human(fetch.total_bytes(e.assets))
            key = "settings.state.fetched" if e.available() else "settings.state.not_fetched"
            state = t(key, size=size)
        print(f"{e.id:<16} {engine_label(e):<28} {state}")


# --- 知らせ ---------------------------------------------------------------
#
# 読んだ中身は標準出力、それ以外は標準エラーに出す。混ぜると、
# パイプで次の道具に渡したときに中身が汚れる。


def _say(message: str, quiet: bool, end: str = "\n") -> None:
    if not quiet:
        print(message, file=sys.stderr, end=end, flush=True)


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
