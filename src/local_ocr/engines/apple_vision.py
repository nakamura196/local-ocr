"""macOS 標準の文字認識 (Vision.framework)。

取得するものが何も無く、すぐ使える。現代の活字と手書きに強い一方、
くずし字や版本の漢籍は不得手なので、そこは NDL や PaddleOCR-VL に渡す。
"""

from __future__ import annotations

import io
import sys

from PIL import Image

from ..core.assets import Asset
from .base import Line, Progress, Result

# 既定で見る言語。Vision は指定した順に優先する。
LANGUAGES = ["ja-JP", "en-US", "zh-Hans", "zh-Hant"]


class AppleVisionEngine:
    id = "apple-vision"
    label = "Apple Vision（macOS 標準）"
    note = "取得するものはありません。現代の活字・手書きに向きます。"
    platforms = frozenset({"darwin"})
    assets: list[Asset] = []

    def available(self) -> bool:
        if sys.platform != "darwin":
            return False
        try:
            import Vision  # noqa: F401
        except ImportError:
            return False
        return True

    def prepare(self, on_progress: Progress) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def recognize(self, img: Image.Image) -> Result:
        import Quartz
        import Vision
        from Foundation import NSData

        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG")
        data = NSData.dataWithBytes_length_(buf.getvalue(), len(buf.getvalue()))
        src = Quartz.CGImageSourceCreateWithData(data, None)
        if src is None:
            raise RuntimeError("画像を読み込めませんでした")
        cg = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)

        req = Vision.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        req.setRecognitionLanguages_(LANGUAGES)
        req.setUsesLanguageCorrection_(True)
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg, None)
        ok, err = handler.performRequests_error_([req], None)
        if not ok:
            raise RuntimeError(f"読み取りに失敗しました: {err}")

        w, h = img.size
        lines: list[Line] = []
        for obs in req.results() or []:
            cand = obs.topCandidates_(1)
            if not cand:
                continue
            text = cand[0].string()
            # Vision は左下原点の 0..1 で返す。画素座標・左上原点に直す。
            bb = obs.boundingBox()
            x = int(bb.origin.x * w)
            y = int((1.0 - bb.origin.y - bb.size.height) * h)
            lines.append(Line(text=text, box=(x, y, int(bb.size.width * w), int(bb.size.height * h))))

        return Result(text="\n".join(line.text for line in lines), lines=lines)
