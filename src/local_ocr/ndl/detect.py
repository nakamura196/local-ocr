"""版面のどこに行があるかを見つける部分。

古典籍は RTMDet、近代資料は DEIMv2。どちらも ONNX で、前処理と後処理だけが違う。
**数字は上流のまま。** 平均と標準偏差、2% の上下のばし、しきい値は学習時に合わせてある。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime
from PIL import Image

from .classes import Taxonomy


@dataclass
class Detection:
    """見つけた枠 1 つ。`box` は元画像の画素座標で (x0, y0, x1, y1)。"""

    class_index: int
    confidence: float
    box: tuple[int, int, int, int]
    # DEIMv2 だけが返す「この行はおよそ何文字か」の目安。RTMDet は返さない。
    pred_char_count: float | None = None


def _session(model_path: Path, optimize: bool) -> onnxruntime.InferenceSession:
    opts = onnxruntime.SessionOptions()
    opts.graph_optimization_level = (
        onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        if optimize
        else onnxruntime.GraphOptimizationLevel.ORT_DISABLE_ALL
    )
    return onnxruntime.InferenceSession(
        str(model_path), opts, providers=["CPUExecutionProvider"]
    )


def _pad_to_square(img: Image.Image) -> tuple[np.ndarray, int]:
    """右と下に黒を足して正方形にする。元の左上はそのままなので座標がずれない。"""
    arr = np.asarray(img.convert("RGB"))
    h, w = arr.shape[:2]
    side = max(h, w)
    padded = np.zeros((side, side, 3), dtype=np.uint8)
    padded[:h, :w, :] = arr
    return padded, side


class RTMDet:
    """古典籍向け。返ってくるのは行の枠だけで、種類は常に「本文」。"""

    # 上流の既定値。
    CONF_THRESHOLD = 0.3

    def __init__(self, model_path: Path, taxonomy: Taxonomy) -> None:
        self.taxonomy = taxonomy
        self.session = _session(model_path, optimize=False)
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]
        # **名前ではなくモデルに聞く。** 配布物の名前は 1280x1280 だが中身は 1024x1024。
        _, _, self.input_height, self.input_width = self.session.get_inputs()[0].shape

    def detect(self, img: Image.Image) -> list[Detection]:
        padded, side = _pad_to_square(img)
        resized = np.asarray(Image.fromarray(padded).resize((self.input_width, self.input_height)))
        # BGR に入れ替えてから、学習時の平均と標準偏差で割る。
        resized = resized[:, :, ::-1]
        mean = np.array([103.53, 116.28, 123.675], dtype=np.float32)
        std = np.array([57.375, 57.12, 58.395], dtype=np.float32)
        tensor = ((resized - mean) / std).transpose(2, 0, 1)[np.newaxis].astype(np.float32)

        dets, _labels = self.session.run(self.output_names, {self.input_name: tensor})
        # 上流は np.squeeze を使うが、枠が 1 つだけのときに形が崩れる。
        dets = np.asarray(dets).reshape(-1, 5)

        scores = dets[:, 4]
        keep = scores > self.CONF_THRESHOLD
        boxes = dets[keep, :4] / self.input_width * side
        scores = scores[keep]

        # 行の上下を 2% だけのばす。ぎりぎりで切ると端の文字が欠ける。
        out: list[Detection] = []
        for (x0, y0, x1, y1), score in zip(boxes, scores, strict=True):
            delta = (y1 - y0) * 0.02
            out.append(
                Detection(
                    class_index=self.taxonomy.index("line_main"),
                    confidence=float(score),
                    box=(int(x0), int(y0 - delta), int(x1), int(y1 + delta)),
                )
            )
        return out


class DEIM:
    """近代資料向け。行のほか、本文ブロックや図版などの種類も返す。"""

    # 上流の既定値。
    CONF_THRESHOLD = 0.25

    def __init__(self, model_path: Path, taxonomy: Taxonomy) -> None:
        self.taxonomy = taxonomy
        self.session = _session(model_path, optimize=True)
        self.input_names = [i.name for i in self.session.get_inputs()]
        self.output_names = [o.name for o in self.session.get_outputs()]
        _, _, self.input_height, self.input_width = self.session.get_inputs()[0].shape

    def detect(self, img: Image.Image) -> list[Detection]:
        padded, side = _pad_to_square(img)
        resized = np.asarray(Image.fromarray(padded).resize((self.input_width, self.input_height)))
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        tensor = ((resized / 255.0 - mean) / std).transpose(2, 0, 1)[np.newaxis].astype(np.float32)

        sizes = np.array([[self.input_height, self.input_width]], dtype=np.int64)
        outputs = self.session.run(
            self.output_names, {self.input_names[0]: tensor, self.input_names[1]: sizes}
        )
        labels = np.asarray(outputs[0]).reshape(-1)
        boxes = np.asarray(outputs[1]).reshape(-1, 4)
        scores = np.asarray(outputs[2]).reshape(-1)
        # 文字数の見当を返さない版もある。そのときは一番長いモデルに回す。
        char_counts = (
            np.asarray(outputs[3]).reshape(-1)
            if len(outputs) == 4
            else np.full(scores.shape, 100.0)
        )

        keep = scores > self.CONF_THRESHOLD
        scale = side / self.input_width
        boxes = np.clip((boxes[keep] * scale).astype(np.int32), 0, side)

        out: list[Detection] = []
        for box, score, label, count in zip(
            boxes, scores[keep], labels[keep], char_counts[keep], strict=True
        ):
            out.append(
                Detection(
                    # DEIMv2 の番号は 1 から。ndl.yaml の並びは 0 から。
                    class_index=int(label) - 1,
                    confidence=float(score),
                    box=(int(box[0]), int(box[1]), int(box[2]), int(box[3])),
                    pred_char_count=float(count),
                )
            )
        return out
