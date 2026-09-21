"""アプリの入口。

Flet はリポジトリ直下の main.py を起点に配布物を作る。中身は src/ 側に置き、
ここは呼ぶだけにしている。

**src/ を sys.path に載せる処理を消さないこと。**
開発中は editable install（`uv sync`）が src/ を通してくれるので、これが無くても
動いてしまう。だが配布物には editable install が無い。パッケージ後のソースは
`.../Resources/app/src/local_ocr/` に置かれるだけで、`.../Resources/app/` しか
sys.path に載らないため、

    ModuleNotFoundError: No module named 'local_ocr'

で起動できない。**署名も公証も通り、.dmg まで出来てから初めて分かる**
（2026-09-21 に実際に踏んだ。archival-packager も同じ対処をしている）。
`tests/test_packaging.py` が、この 3 行が効いていることを見張る。
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from local_ocr.app import run

run()
