"""Yigdzin-1(チベット語 OCR)の中身。

- OCR 本体: [`BDRC/tibetan-ocr`](https://huggingface.co/BDRC/tibetan-ocr)
  (Apache-2.0)。llama.cpp で動かせるよう GGUF に変換したものを
  `nakamura196/yigdzin1-gguf` で配っている(経緯は NOTICE)
- 行検出: [`BDRC/PhotiLines_v2`](https://huggingface.co/BDRC/PhotiLines_v2)
  (CC BY 4.0)。`line_detection.py` は BDRC純正デスクトップアプリ
  (`buda-base/tibetan-ocr-app`)の同名モジュールを下敷きにした移植で、
  版面の分類・歪み補正など、このアプリで使わない部分は持ってきていない
  (`line_detection.py` の docstring に詳しい)
- 読み順: 自前では持たず、`ndl/order.py` の XY カットをそのまま使う
  (座標だけを見る汎用のロジックで、NDL 固有ではない)
"""
