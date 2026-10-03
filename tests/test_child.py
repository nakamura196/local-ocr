"""llama-server がアプリより長生きしないこと。

2026-10-01 と 10-03 に、アプリを止めたあとも llama-server が残った
(親が launchd になり、800MB を握ったまま 2 日動いていた)。窓を閉じたときは
後片付けが走るが、kill・強制終了・落ちたときは Python の後片付けは走らない。

ここでは本物の llama-server の代わりに、印を書き続けるだけの子を立てる。
「アプリ」役の Python を 1 つ立て、その中から `child.spawn` で子を起こし、
アプリ役を後片付けの機会なしに殺す。子の印が止まれば合格。
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import time
from pathlib import Path

from local_ocr.core import child

SRC = Path(__file__).resolve().parents[1] / "src"

# 子(llama-server の代わり)。0.1 秒ごとに印を書く。試験が失敗しても
# 残り続けないよう、30 秒で自分から終わる。
_WORKER = textwrap.dedent(
    """
    import sys, time
    for _ in range(300):
        with open(sys.argv[1], "a") as f:
            f.write(".")
        time.sleep(0.1)
    """
)

# アプリ役。子を立てたことを知らせたら、殺されるまで待つ。
_APP = textwrap.dedent(
    """
    import sys, time
    sys.path.insert(0, sys.argv[1])
    from local_ocr.core import child
    proc = child.spawn([sys.executable, "-c", sys.argv[2], sys.argv[3]])
    print("up", flush=True)
    time.sleep(60)
    """
)


def _grows(path: Path, within: float) -> bool:
    """印が `within` 秒のあいだに増えたか。"""
    before = path.stat().st_size if path.exists() else 0
    time.sleep(within)
    after = path.stat().st_size if path.exists() else 0
    return after > before


def _wait_until_quiet(path: Path, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _grows(path, 0.5):
            return True
    return False


def test_the_server_dies_with_the_app_even_when_the_app_is_killed(tmp_path):
    marks = tmp_path / "marks"
    app = subprocess.Popen(
        [sys.executable, "-c", _APP, str(SRC), _WORKER, str(marks)],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert app.stdout is not None
        assert app.stdout.readline().strip() == "up"
        assert _grows(marks, 1.0), "子が動き出していない"
        # 後片付けの機会を与えない止め方(POSIX は SIGKILL、Windows は TerminateProcess)。
        app.kill()
        app.wait(timeout=10)
        assert _wait_until_quiet(marks), "アプリを殺したあとも子が動き続けている"
    finally:
        if app.poll() is None:
            app.kill()
            app.wait(timeout=10)
        if app.stdout is not None:
            app.stdout.close()


def test_halt_stops_the_server(tmp_path):
    marks = tmp_path / "marks"
    proc = child.spawn([sys.executable, "-c", _WORKER, str(marks)])
    assert _grows(marks, 1.0), "子が動き出していない"
    child.halt(proc)
    assert proc.poll() is not None
    assert _wait_until_quiet(marks), "止めたあとも子が動き続けている"
    _drain(proc)


def test_the_server_log_still_reaches_us(tmp_path):
    """画面の下に出すログ(標準出力)が、見張りを挟んでも届くこと。"""
    proc = child.spawn([sys.executable, "-c", "print('hello from server')"])
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "hello from server"
    child.halt(proc)
    _drain(proc)


def test_the_app_sees_when_the_server_exits_on_its_own():
    """llama-server が自分で落ちたら、`running` が偽になること(見張りが残らない)。"""
    proc = child.spawn([sys.executable, "-c", "import sys; sys.exit(3)"])
    assert proc.wait(timeout=10) == 3
    child.halt(proc)
    _drain(proc)


def _drain(proc: subprocess.Popen[str]) -> None:
    """`Runtime._pump` の役。最後まで読んで閉じる(見張りが居残っていれば、ここで止まる)。"""
    assert proc.stdout is not None
    proc.stdout.read()
    proc.stdout.close()
