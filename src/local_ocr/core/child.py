"""子プロセス(llama-server)の起動と停止。**アプリより長生きさせない。**

窓を閉じたときは `AppState.shutdown` が `Runtime.stop` を呼ぶので止まる。
だが kill・強制終了・アプリが落ちたときは、Python の後片付けは一切走らない。
そのとき llama-server は親を失って残り、重み(1〜2GB)を握ったまま動き続ける
(2026-10-01 に立てたものが、10-03 にもまだ 800MB で残っていた)。次に起動した
アプリはそれを「同じポートで動いているもの」として借りるので、気づきにくい。

なので、親が**どう死んでも** OS が子を片付ける形で立てる。

- macOS / Linux: `/bin/sh` の見張りを挟む。見張りは標準入力を読んで待ち、
  読み終わったら(=書き手のアプリがいなくなったら)子に SIGTERM を送る。
  アプリが死ぬと OS が書き口を閉じるので、kill -9 でもクラッシュでも届く。
  macOS には Linux の「親が死んだら知らせる」(PR_SET_PDEATHSIG)が無いので、
  この形にしている
- Windows: ジョブオブジェクトに入れ、「最後のハンドルが閉じたら中を全部殺す」
  を付ける。アプリが死ぬとハンドルが閉じる

`tests/test_child.py` が、アプリ役を kill して子が止まることを見張る。
"""

from __future__ import annotations

import os
import signal
import subprocess

from .paths import is_windows

# $1 以降が本来のコマンド。fd 3 に標準入力(アプリとつながったパイプ)を
# 控えておくのは、非対話の sh が `&` で裏に回したものの標準入力を
# /dev/null に差し替えるため。そのまま `read` すると即座に読み終わってしまう。
#
# - 子が自分で終わったら、見張りを畳んで同じ終了コードで終わる
#   (アプリから見た `poll()` が、llama-server の生死と一致する)
# - 読み終わったら子に SIGTERM、10 秒待っても残っていれば SIGKILL
_WATCH = r"""
exec 3<&0
"$@" 3<&- </dev/null &
c=$!
{ read -r _ <&3; kill "$c" 2>/dev/null; sleep 10 >/dev/null; kill -9 "$c" 2>/dev/null; } 3<&3 &
w=$!
exec 3<&-
wait "$c"
s=$?
kill "$w" 2>/dev/null
exit "$s"
"""

# Windows のジョブ。プロセスが生きている間は閉じてはいけないので、ここで持ち続ける。
_jobs: list[int] = []


def spawn(cmd: list[str]) -> subprocess.Popen[str]:
    """`cmd` を立てる。標準出力と標準エラーは 1 本にまとめて `stdout` で読める。"""
    if is_windows():
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            # コンソールの黒い窓が一瞬出るのを抑える。
            creationflags=subprocess.CREATE_NO_WINDOW,  # type: ignore[attr-defined]
        )
        _bind_to_us(proc)
        return proc
    return subprocess.Popen(
        ["/bin/sh", "-c", _WATCH, "sh", *cmd],
        # 何も書かない。閉じる(またはアプリが死ぬ)ことが、止めろの合図。
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        # 見張り・子・待ちの sleep をひとまとめにして、最後の手段で一度に殺せるように。
        start_new_session=True,
    )


def halt(proc: subprocess.Popen[str], timeout: float = 10.0) -> None:
    """止めて、終わるまで待つ。既に終わっていてもよい。

    `stdout` は閉じない。ログを読んでいるスレッドが最後まで読み、そちらで閉じる。
    """
    if is_windows():
        if proc.poll() is None:
            proc.terminate()
    elif proc.stdin is not None and not proc.stdin.closed:
        # 見張りに合図する。見張りが子に SIGTERM を送り、子が終われば見張りも終わる。
        try:
            proc.stdin.close()
        except OSError:
            pass
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if is_windows():
            proc.kill()
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        proc.wait(timeout=5)


def _bind_to_us(proc: subprocess.Popen[str]) -> None:
    """Windows: アプリのハンドルが閉じたら `proc` も終わるようにする。

    うまくいかなくても起動は止めない(従来どおり、窓を閉じれば止まる)。
    """
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]

    class _IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class _BasicLimit(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _ExtendedLimit(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimit),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    job_object_extended_limit_information = 9
    job_object_limit_kill_on_job_close = 0x2000

    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
    ]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return
    info = _ExtendedLimit()
    info.BasicLimitInformation.LimitFlags = job_object_limit_kill_on_job_close
    ok = kernel32.SetInformationJobObject(
        job, job_object_extended_limit_information, ctypes.byref(info), ctypes.sizeof(info),
    ) and kernel32.AssignProcessToJobObject(job, int(proc._handle))  # type: ignore[attr-defined]
    if ok:
        _jobs.append(job)
    else:
        kernel32.CloseHandle(job)
