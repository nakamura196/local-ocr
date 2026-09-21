"""切り出した 1 行を文字にする部分。どちらの道具も PARSeq を使う。

近代資料は**長さの違う 3 つのモデルを使い分ける**。レイアウト検出が「この行は
およそ何文字か」を一緒に返すので、短い行は短いモデルに回す。短いモデルの方が速く、
入りきらなかったときだけ長いモデルで読み直す。古典籍は 1 つのモデルだけを使う。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime
from PIL import Image

CHARSET_DIR = Path(__file__).parent / "charset"


def load_charset(name: str) -> str:
    """文字の一覧。並びがそのままモデルの出力の番号になる(0 は行の終わり)。

    上流の `src/config/NDLmoji.yaml` の `charset_train` をそのまま写したもの。
    **先頭が半角スペースなので、両端を削らない。**
    """
    text = (CHARSET_DIR / f"{name}.txt").read_text(encoding="utf-8")
    return text.removesuffix("\n")


class Parseq:
    def __init__(self, model_path: Path, charset: str, *, resample: int) -> None:
        self.charset = charset
        self.resample = resample
        opts = onnxruntime.SessionOptions()
        opts.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        # 1 行ずつを別のスレッドで同時に読ませるので、1 回の推論では広げない。
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        self.session = onnxruntime.InferenceSession(
            str(model_path), opts, providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]
        _, _, self.input_height, self.input_width = self.session.get_inputs()[0].shape

    def read(self, crop: Image.Image) -> str:
        if crop.width == 0 or crop.height == 0:
            return ""
        # 縦書きの行は左へ 90 度倒して、横長の 1 行として読ませる。
        if crop.height > crop.width:
            crop = crop.transpose(Image.Transpose.ROTATE_90)
        # **ここも上流と結果が変わる。** 近代資料の上流は OpenCV の INTER_LINEAR で
        # 縮めていて、縮めるときに間引きが起きる(前処理をぼかさない)。Pillow は
        # 縮尺に合わせて平均を取るので、細い画がつぶれにくい。実測: 上流の試し画像
        # 6 枚のうち、字が変わった 4 枚はすべてこちらが正しかった
        # (「硯にむかいて」「円筒形」「庁舎」「ものぐるほしけれ」)。
        # 古典籍の上流は Pillow を使っており、そちらは 4 枚とも 1 字も違わない。
        resized = crop.resize((self.input_width, self.input_height), self.resample)
        # BGR に入れ替えて -1..1 に収める。
        arr = np.asarray(resized.convert("RGB"))[:, :, ::-1].astype(np.float32)
        tensor = (arr / 127.5 - 1.0).transpose(2, 0, 1)[np.newaxis]

        logits = self.session.run(self.output_names, {self.input_name: tensor})[0]
        indices = np.argmax(logits[0], axis=1)
        stop = np.where(indices == 0)[0]
        end = stop[0] if stop.size > 0 else len(indices)
        return "".join(self.charset[i - 1] for i in indices[:end])


@dataclass
class _Pending:
    """読ませたい 1 行。`order` は版面の中での並び順で、最後に元に戻すために持つ。"""

    crop: Image.Image
    order: int
    char_hint: float


def _read_all(recognizer: Parseq, pending: Sequence[_Pending]) -> list[str]:
    if not pending:
        return []
    with ThreadPoolExecutor(thread_name_prefix="ndl-ocr") as pool:
        return list(pool.map(recognizer.read, [p.crop for p in pending]))


def read_single(recognizer: Parseq, crops: Iterable[Image.Image]) -> list[str]:
    """古典籍用。1 つのモデルで全部読む。"""
    pending = [_Pending(crop, i, 0.0) for i, crop in enumerate(crops)]
    return _read_all(recognizer, pending)


def read_cascade(
    short: Parseq,
    medium: Parseq,
    long: Parseq,
    crops: Sequence[Image.Image],
    hints: Sequence[float],
) -> list[str]:
    """近代資料用。文字数の見当でモデルを選び、入りきらなければ長い方へ送る。

    しきい値(25 / 45 / 98)は、それぞれのモデルが返せる最大の文字数
    (30 / 50 / 100)の手前。そこまで埋まった行は途中で切れている疑いがある。
    """
    done: dict[int, str] = {}
    to_short: list[_Pending] = []
    to_medium: list[_Pending] = []
    to_long: list[_Pending] = []
    for i, (crop, hint) in enumerate(zip(crops, hints, strict=True)):
        item = _Pending(crop, i, hint)
        (to_short if hint == 3 else to_medium if hint == 2 else to_long).append(item)

    for item, text in zip(to_short, _read_all(short, to_short), strict=True):
        if len(text) >= 25:
            to_medium.append(item)
        else:
            done[item.order] = text

    for item, text in zip(to_medium, _read_all(medium, to_medium), strict=True):
        if len(text) >= 45:
            to_long.append(item)
        else:
            done[item.order] = text

    # 長いモデルでも埋まりきった横書きの行は、左右に割ってもう一度読む。
    halves: list[_Pending] = []
    for item, text in zip(to_long, _read_all(long, to_long), strict=True):
        w, h = item.crop.size
        if len(text) >= 98 and h < w:
            halves.append(_Pending(item.crop.crop((0, 0, w // 2, h)), item.order, 100.0))
            halves.append(_Pending(item.crop.crop((w // 2, 0, w, h)), item.order, 100.0))
        else:
            done[item.order] = text

    half_texts = _read_all(long, halves)
    for i in range(0, len(halves) - 1, 2):
        done[halves[i].order] = half_texts[i] + half_texts[i + 1]

    return [done.get(i, "") for i in range(len(crops))]


__all__ = ["Parseq", "load_charset", "read_cascade", "read_single"]
