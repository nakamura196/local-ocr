"""画面をまたいで持ち回る値。Flet には依存させない。

エンジンの実体はここで 1 回だけ作る。画面を移るたびに作り直すと、
常駐しているサーバを取りこぼして二重に起動してしまう。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from ..core import prefs, tei
from ..core.bridge import Bridge
from ..core.ocr import IMAGE_SUFFIXES
from ..engines import Engine, Line, Result, all_engines, runs_here
from .i18n import current, engine_label, t

__all__ = ["IMAGE_SUFFIXES", "AppState", "Job", "Run"]


@dataclass
class Run:
    """1 つの読む道具で読んだ結果。くらべるときは、これが道具の数だけ並ぶ。"""

    engine_id: str
    result: Result | None = None
    # 読むのにかかった秒数。どの道具が速いかは、くらべるときの判断材料になる。
    seconds: float = 0.0
    # 下ごしらえ(取得・サーバの起動・重みの読み込み)にかかった秒数。
    # **読んだ秒数と混ぜない。** 混ぜると 1 回目と 2 回目で桁が変わり、
    # 道具どうしの速さがくらべられなくなる。
    prepare_seconds: float = 0.0
    error: str = ""

    @property
    def lines(self) -> list[Line]:
        """画面に並べる行。枠を返さないエンジンでは、改行で割って揃える。

        **元にするのは、利用者が見ている文字(`result.text`)。** 「まとめて」で
        直した分を、行の一覧にもコピーにも TEI にも同じように効かせる。
        行数が変わっていなければ、エンジンが返した枠をそのまま連れていく。
        """
        if self.result is None:
            return []
        texts = [s for s in self.result.text.splitlines() if s.strip()]
        boxed = self.result.lines
        if not boxed:
            return [Line(text=s) for s in texts]
        if len(texts) != len(boxed):
            # 行を足すか消すかされている。枠との対応が付かないので、
            # エンジンが返したままを出す(枠を捨てない)。
            return boxed
        return [Line(text=s, box=line.box) for s, line in zip(texts, boxed)]

    @property
    def text(self) -> str:
        return self.result.text if self.result else ""

    @property
    def timing(self) -> str:
        """「0.8 秒（準備 41 秒）」。下ごしらえが要らなかったときは括弧を出さない。"""
        if self.result is None:
            return ""
        if self.prepare_seconds >= 0.5:
            return t(
                "timing.with_prepare",
                seconds=f"{self.seconds:.1f}",
                prepare=f"{self.prepare_seconds:.0f}",
            )
        return t("timing.plain", seconds=f"{self.seconds:.1f}")


@dataclass
class Job:
    """読ませる 1 枚と、読む道具ごとの結果。

    結果を 1 つに決め打ちしないのは、複数の道具でくらべられるようにするため。
    版面に枠を重ねるのは、そのうち `primary` に選ばれた 1 つ。
    """

    source: str
    image: Image.Image | None = None
    path: Path | None = None
    runs: dict[str, Run] = field(default_factory=dict)
    primary: str = ""

    def record(self, run: Run, prefer: bool = False) -> None:
        """読み終えた結果をしまう。

        `prefer` は「これを版面に出す」。**1 つで読んだときは必ず立てる。**
        立てないと、道具を変えて読み直しても前の道具の結果が版面に出たままになり、
        「新しい道具が読めていない」ようにしか見えない。
        くらべるときは立てない(先に読み終えたものを出したまま、あとから
        勝手に入れ替わらないようにする)。
        """
        self.runs[run.engine_id] = run
        if run.result is None:
            return
        if prefer or not self.primary or self.primary not in self.runs:
            self.primary = run.engine_id

    @property
    def run(self) -> Run | None:
        return self.runs.get(self.primary)

    @property
    def result(self) -> Result | None:
        run = self.run
        return run.result if run else None

    @property
    def lines(self) -> list[Line]:
        run = self.run
        return run.lines if run else []

    @property
    def text(self) -> str:
        run = self.run
        return run.text if run else ""


@dataclass
class AppState:
    engines: list[Engine] = field(default_factory=all_engines)
    job: Job | None = None
    busy: bool = False
    # くらべる表示かどうかと、くらべる相手。作業画面を作り直しても残す。
    compare: bool = False
    compare_ids: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self._bridge: Bridge | None = None
        self._engine_id = str(prefs.get("engine") or "")
        if self._engine_id not in {e.id for e in self.usable}:
            self._engine_id = self._default_engine_id()
        if not self.compare_ids:
            # 既定は、いま取得が済んでいる道具すべて。
            self.compare_ids = {
                e.id for e in self.usable if not e.assets or e.available()
            }

    # --- エンジン ---------------------------------------------------------
    @property
    def usable(self) -> list[Engine]:
        """この OS で動くもの。設定画面だけが、動かないものも含めて見る。"""
        return [e for e in self.engines if runs_here(e)]

    @property
    def engine(self) -> Engine:
        return next(e for e in self.usable if e.id == self._engine_id)

    @property
    def engine_id(self) -> str:
        return self._engine_id

    def set_engine(self, engine_id: str) -> None:
        self._engine_id = engine_id
        prefs.save(engine=engine_id)

    def _default_engine_id(self) -> str:
        """既定は取得の要らないもの。何も準備せずに 1 回目が成功するように。"""
        ready = [e for e in self.usable if not e.assets]
        return (ready or self.usable)[0].id

    # --- ほかの道具に開く窓口 -------------------------------------------
    @property
    def bridge(self) -> Bridge | None:
        """設定の「ほかの道具から使えるようにする」が使う窓口。

        **読む道具が持っているサーバをそのまま渡す。** ここで新しく作ると、
        同じポートに二重に立てようとして重みを二度読む。常駐のサーバを持つ
        道具が 1 つも無ければ None(窓口の節ごと出さない)。
        """
        if self._bridge is None:
            runtime = next(
                (rt for e in self.engines if (rt := getattr(e, "runtime", None)) is not None),
                None,
            )
            if runtime is None:
                return None
            self._bridge = Bridge(runtime)
        return self._bridge

    def shutdown(self) -> None:
        for e in self.engines:
            try:
                e.shutdown()
            except Exception:  # noqa: BLE001 - 終了処理なので握りつぶす
                pass

    # --- 書き出し ---------------------------------------------------------
    def tei(self, job: Job, image_url: str) -> str:
        """いま版面に出ている結果を TEI/XML にする。

        `image_url` は、TEI を置く場所から見た版面の道。書き出す側(`ui/work.py`)が
        保存先を決めてから渡す。
        """
        if job.image is None:
            raise ValueError("版面がありません")
        engine = next((e for e in self.engines if e.id == job.primary), None)
        return tei.build(
            [
                tei.Page(
                    lines=job.lines,
                    width=job.image.width,
                    height=job.image.height,
                    image_url=image_url,
                )
            ],
            tei.Meta(
                title=job.path.stem if job.path else job.source,
                engine=engine_label(engine) if engine is not None else "",
                # 絶対の道は書かない(利用者の名前がファイルに残る)。
                source=job.source,
                language=current(),
            ),
        )

    # --- 前回の続き -------------------------------------------------------
    def remember(self, job: Job) -> None:
        """次に起動したとき、続きから戻れるようにしまう。しまうのは表示中の 1 つ。"""
        result = job.result
        if result is None:
            return
        prefs.save(
            last={
                "source": job.source,
                "path": str(job.path) if job.path else None,
                "engine": job.primary,
                "text": result.text,
                "lines": [[ln.text, *(ln.box or ())] for ln in result.lines],
            }
        )

    @staticmethod
    def forget() -> None:
        prefs.save(last=None)

    @staticmethod
    def last() -> Job | None:
        """しまってあった前回の結果。画像が消えていても、文字だけは出す。"""
        saved = prefs.get("last")
        if not isinstance(saved, dict) or not saved.get("text"):
            return None
        path = Path(saved["path"]) if saved.get("path") else None
        image = None
        if path is not None and path.is_file():
            try:
                image = Image.open(path)
            except (OSError, ValueError):
                image = None
        lines = [
            Line(text=row[0], box=tuple(row[1:5]) if len(row) >= 5 else None)
            for row in saved.get("lines", [])
            if row
        ]
        engine_id = str(saved.get("engine") or "")
        job = Job(
            source=str(saved.get("source") or t("source.last")),
            image=image,
            path=path if image is not None else None,
        )
        job.record(Run(engine_id=engine_id, result=Result(text=str(saved["text"]), lines=lines)))
        job.primary = engine_id
        return job
