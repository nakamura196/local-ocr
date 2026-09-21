"""NDL の 2 つの読み取り (NDLOCR Lite / NDL古典籍OCR Lite) の中身。

上流の実装を写したもの。**思いつきで書き換えない。** 直すときは上流を見比べる。

- NDLOCR Lite: https://github.com/ndl-lab/ndlocr-lite (`d25e0d4`)
- NDL古典籍OCR Lite: https://github.com/ndl-lab/ndlkotenocr-lite (`ede4283`)
- どちらも CC BY 4.0。表示の文面は repo の `NOTICE` にある

上流との違いは 3 つだけで、読みの結果は変えない。

1. **配布物を軽くするため、依存を減らした。** OpenCV は使う場所が無く、lxml は
   文字列を組み立てるところでは呼ばれておらず、PyYAML は読み込む中身
   (種類の並びと文字の一覧) を `classes.py` と `charset/` に持たせて要らなくした。
   networkx は読み順の仕上げ 1 か所だけで、そこは `order.py` に書き直した
2. **ファイルに書き出す部分を持ってきていない。** この道具の出口は `core/export.py`
3. 途中の受け渡しに使う XML は上流と同じ形のまま。**ここを自前の形に置き換えない**
   (上流の読み順の処理が XML の木をそのまま並べ替えるので、合わせておく方が安い)
"""
