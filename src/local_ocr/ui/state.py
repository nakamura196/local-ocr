"""画面をまたいで持ち回る値。Flet には依存させない。

エンジンの実体はここで 1 回だけ作る。画面を移るたびに作り直すと、
常駐しているサーバを取りこぼして二重に起動してしまう。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from ..core import prefs, reading, source, tei
from ..core.bridge import Bridge
from ..core.gateway import Gateway
from ..core.ocr import IMAGE_SUFFIXES
from ..engines import Engine, Line, Result, all_engines, runs_here
from .i18n import current, engine_label, t

__all__ = ["IMAGE_SUFFIXES", "AppState", "Doc", "Job", "Run"]


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
    # 取り寄せ先(IIIF)。手元のファイルではないページはこちらを持つ。
    url: str = ""
    runs: dict[str, Run] = field(default_factory=dict)
    primary: str = ""
    # 版面の寸法。**版面を手放したあとも残す。** TEI は行の枠を版面の座標で
    # 書くので、画像そのものが無くても寸法だけは要る。
    width: int = 0
    height: int = 0

    def __post_init__(self) -> None:
        if self.image is not None:
            self.width, self.height = self.image.size

    @classmethod
    def of(cls, item: source.Item) -> Job:
        return cls(source=item.label, path=item.path, url=item.url)

    # --- 版面 -------------------------------------------------------------
    def load(self) -> Image.Image:
        """版面を手元に用意する。**糸(スレッド)の中から呼ぶ**(取り寄せがある)。"""
        if self.image is None:
            self.attach(source.open_image(source.Item(self.source, self.path, self.url)))
        return self.image  # type: ignore[return-value]

    def attach(self, image: Image.Image) -> None:
        self.image = image
        self.width, self.height = image.size

    def release(self) -> None:
        """版面を手放す。何百ページもの束を開いたとき、全部を抱えたままにしない。

        **もう一度開ける当て(ファイルか URL)があるときだけ**手放す。
        貼り付けた画像は、手放すと二度と戻らない。
        """
        if self.path is not None or self.url:
            self.image = None

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
class Doc:
    """読ませるページの束。**1 枚だけのときも、長さ 1 の束として扱う。**

    こうしておくと、画面の作りが「1 枚か、たくさんか」で割れない。
    ページを行き来する帯だけを、2 ページ以上のときに出す。
    """

    title: str
    jobs: list[Job]
    index: int = 0
    # どこから開いたか。フォルダの名前か、マニフェストの URL。TEI の出どころに書く。
    # **絶対の道は入れない**(利用者の名前がファイルに残る)。
    origin: str = ""

    @property
    def current(self) -> Job | None:
        if not self.jobs:
            return None
        return self.jobs[min(max(self.index, 0), len(self.jobs) - 1)]

    @property
    def many(self) -> bool:
        return len(self.jobs) > 1

    @property
    def total(self) -> int:
        return len(self.jobs)

    def go(self, index: int) -> None:
        self.index = min(max(index, 0), max(0, len(self.jobs) - 1))

    def read(self) -> list[Job]:
        """読み終えているページだけ。保存の対象はこれ(空のページを書き出さない)。"""
        return [job for job in self.jobs if job.result is not None]

    def keep_only(self, index: int) -> None:
        """いま見ているページ以外の版面を手放す。

        200 ページのフォルダを開いて全部を抱えると、それだけで何 GB にもなる。
        読んだ文字と枠は残るので、戻ったときは版面を開き直すだけで済む。
        """
        for i, job in enumerate(self.jobs):
            if i != index:
                job.release()

    @classmethod
    def of(cls, items: list[source.Item], title: str, origin: str = "") -> Doc:
        return cls(title=title, jobs=[Job.of(item) for item in items], origin=origin)


@dataclass
class AppState:
    engines: list[Engine] = field(default_factory=all_engines)
    doc: Doc | None = None
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

    # --- いま読んでいるもの -----------------------------------------------
    @property
    def job(self) -> Job | None:
        """いま画面に出ているページ。画面側はこれまでどおり 1 枚だけを見る。"""
        return self.doc.current if self.doc else None

    def open(self, doc: Doc) -> None:
        self.doc = doc

    def open_job(self, job: Job) -> None:
        """1 枚を開く(選ぶ・貼り付け・前回の続き)。長さ 1 の束にする。"""
        self.doc = Doc(title=job.source, jobs=[job])

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

    # --- 読み方(道具ごと) ---------------------------------------------------
    #
    # **読むたびに選ばせない。** 設定画面で道具ごとに決め、1 つで読む・くらべる・
    # 束をまとめて読む、のどれでも同じものを使う。窓口(`core/gateway.py`)は見ない
    # (呼び手が決める)。

    def mode_of(self, engine: Engine) -> str:
        saved = prefs.get("modes")
        wanted = saved.get(engine.id) if isinstance(saved, dict) else None
        try:
            return reading.mode_for(engine, wanted)
        except ValueError:
            # 版が変わって無くなった読み方。既定に戻す。
            return reading.mode_for(engine, None)

    def set_mode(self, engine_id: str, mode: str) -> None:
        saved = prefs.get("modes")
        modes = dict(saved) if isinstance(saved, dict) else {}
        modes[engine_id] = mode
        prefs.save(modes=modes)

    def _default_engine_id(self) -> str:
        """既定は取得の要らないもの。何も準備せずに 1 回目が成功するように。"""
        ready = [e for e in self.usable if not e.assets]
        return (ready or self.usable)[0].id

    # --- ほかの道具に開く窓口 -------------------------------------------
    @property
    def bridge(self) -> Bridge | None:
        """設定の「ほかの道具から使えるようにする」が使う窓口。

        **読む道具とサーバは、画面と同じものをそのまま渡す。** ここで新しく作ると、
        同じポートに二重に立てようとして重みを二度読む。窓口から使えるのは、
        この OS で動く道具すべて(`core/gateway.py`)。
        """
        if self._bridge is None:
            runtime = next(
                (rt for e in self.engines if (rt := getattr(e, "runtime", None)) is not None),
                None,
            )
            gateway = Gateway(
                engines=lambda: self.usable,
                upstream=lambda: runtime.endpoint if runtime is not None else None,
            )
            self._bridge = Bridge(runtime, gateway)
        return self._bridge

    def shutdown(self) -> None:
        for e in self.engines:
            try:
                e.shutdown()
            except Exception:  # noqa: BLE001, S110 - 終了処理なので握りつぶす
                pass

    # --- 書き出し ---------------------------------------------------------
    def tei(self, pages: list[tuple[Job, str]], title: str = "", origin: str = "") -> str:
        """いま版面に出ている結果を TEI/XML にする。1 ページでも N ページでも同じ口。

        渡すのは (ページ, 版面の道) の並び。**道を決めるのは書き出す側**
        (`ui/work.py`)で、保存先が決まってからでないと相対の道が作れない。
        """
        if not pages:
            raise ValueError("書き出せるページがありません")
        first = pages[0][0]
        engine = next((e for e in self.engines if e.id == first.primary), None)
        return tei.build(
            [
                tei.Page(
                    lines=job.lines,
                    width=job.width,
                    height=job.height,
                    image_url=url,
                )
                for job, url in pages
            ],
            tei.Meta(
                title=title or (first.path.stem if first.path else first.source),
                engine=engine_label(engine) if engine is not None else "",
                # 絶対の道は書かない(利用者の名前がファイルに残る)。
                # 束で開いたときは、どこから開いたか(フォルダ名・マニフェストの URL)。
                source=origin or first.source,
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
                "url": job.url or None,
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
            # 取り寄せたページ(IIIF)。版面は手元に残っているので、
            # 開き直すのは作業画面に任せる(ここで取り寄せに行かない)。
            url=str(saved.get("url") or ""),
        )
        job.record(Run(engine_id=engine_id, result=Result(text=str(saved["text"]), lines=lines)))
        job.primary = engine_id
        return job
