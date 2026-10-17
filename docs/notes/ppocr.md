# PP-OCR（PaddleOCR）を読む道具に足す実験ノート

日付の見出しの下に書き足す。前の記述は書き換えない（誤りは新しい日付で「訂正」と書く）。

## 2026-10-15

- **試したこと**: PaddleOCR の PP-OCR（行の検出 + 1 行の読み取り）を、ONNX Runtime だけで動かす。
  元はブラウザ版の TypeScript 実装（IIIF Kasane）で、公式 PaddleOCR 3.x の手順を写してある。
  Python 側は numpy と onnxruntime だけで書き直した（`src/local_ocr/ppocr/`）
- **OpenCV を使わなかった理由**: 配布物が重くなるため。輪郭抽出の代わりに「行ごとの続いた区間 + 素集合」で
  つながった画素を求め（2000px の頁で約 15ms）、切り出しの 3 次補間も numpy で書いた
- **公式の ONNX が出ていた**: `PaddlePaddle/PP-OCRv6_small_{det,rec}_onnx`（Apache-2.0）。
  変換も再配布も要らないので、取得先を動かない番号（コミット）で指すだけにした。
  設定は `inference.yml` から読む（しきい値・入力の高さ・文字の一覧。PyYAML は入れず、必要な形だけ読む）
- **測り方**: 次の 2 頁を読み、行数・時間・出力を見た（正解との突き合わせはしていない）
  - 英語の活字: Internet Archive `darwinmodernscie00darw` の 41 頁目（`https://archive.org/download/darwinmodernscie00darw/page/n40_w1234.jpg`、1437×2185）
  - 縦書きの漢籍（目次）: https://candra.dhii.jp/iiifimgs/yurenja_kkz/016/016_01/016_01_006.tif/full/2000,/0/default.jpg
- **実測（M 系 Mac、CPU）**: 英語頁は v5・v6 とも 47 行。検出 約 0.23 秒 + 読み取り 約 1.0 秒。
  v6 は v5 が読み違えた `verifed`・`18l3`・`eficacy`・`ftted` を正しく読んだ。
  一方で v6 は引用符の前後の空白を落とす所があった（`"Essay on Dew"is`）。
  縦書きの頁は v5 が 27 行、v6 が 25 行で、v6 は 0.6 秒。v5 は 勤助品、v6 は 勸助品 と、旧字の違いが出た
- **却下した案**:
  - v5 を v6 と並べて出す: 同じ言語を読むモデルが 2 つ並ぶと利用者が選べない。v6 は読み違いが少なく、ラテン文字の言語も読める
  - v5 を ONNX に変えて自前の repo に置き直す: 公式が ONNX を出しているので不要。変換の道は、公式に無いモデル用に
    `scripts/ppocr/convert.py` として残した（v5 mobile の rec で動作確認、同じ大きさの ONNX ができた）
  - OpenCV を足す: 上のとおり
- **途中で分かった、自明でないこと**:
  - v6 の検出の `inference.yml` では `DetResizeForTest` が null。入力の大きさの決め方は yml からは分からないので、
    v5 のブラウザ版と同じ規則（短い辺を 64 まで上げ、長い辺は 4000 まで）を使った
  - 文字の一覧は 18,708 字、ONNX の出力は 18,710 クラス（空白 1 つ + 一覧 + 末尾の半角スペース）
  - OpenCV の縮小（INTER_LINEAR）は、環境ごとに別の実装を使うため、numpy の同じ式でもビットまでは一致しない
    （ランダム画像 60 枚中 6 枚で最大 2 段階ずれ）。読みの結果は変わらなかった
  - 公式の並べ替え（SortQuadBoxes）は横書きだけで、縦書きの頁だと列が左から右に出る。
    縦長の箱が過半の頁だけ、右から左・同じ列は上から下に並べる規則を足した（英語頁の出力は変わらない）
  - 公式は検出を原寸で行う。ここでは長辺を 2048px に縮めてから検出し、切り出しは原寸から行う
- **限界（確かめていないこと）**: 人手の翻刻との文字誤り率は測っていない。Windows では動かしていない。
  横書きの頁も縦書きの頁も、1 頁ずつしか見ていない。縦書きの頁の上端の物差し（目盛り）は読んでしまう（そのまま残した）
- 主張の候補: 公式の ONNX と numpy だけで、OpenCV なしに PP-OCRv6 を手元の CPU で 1 頁 1 秒前後で動かせる（上の実測）
- 関連: PaddleOCR（PaddlePaddle Authors, Apache-2.0）https://github.com/PaddlePaddle/PaddleOCR

## 2026-10-17 small を medium に置き換えた

- **試したこと**: PP-OCRv6 の medium（公式の ONNX、`PaddlePaddle/PP-OCRv6_medium_{det,rec}_onnx`）を、
  0.1.11 の small と同じ漢籍の版本 28 頁で読み、PaddleOCR-VL の読みと突き合わせた。
  medium を足すか置き換えるかを決めるため
- **測り方**: 各頁の本文を difflib で VL の読みと並べ、3 字以下の置き換えを数えた（VL を正解とは見なさない。違いの数）
- **結果**:
  - VL と違う字: small 167 → medium 148（約 1 割減）
  - small の明らかな誤りのうち 59 字が medium で直った（首→晉、華→卒、薩埵→庄氣 など）
  - medium だけが VL と違う 40 字は、大半が字体の差（別/别、寶/寳、荊/荆、麼/麽）。
    はっきりした誤りは「末後句」の末→未、「白法」の白→自 など
  - 「拖泥帶水」の 1 か所は、medium が水、VL が永と読んだ。medium が正しいと見ているが、版面では未確認
  - 1 頁の時間: small 3.1 秒 / medium 6.3 秒（手元の Mac、ONNX Runtime の CPU）。大きさ: 31MB / 139MB
  - 公式の表（W-Avg / 古典籍 Anc.）: small 81.3 / 71.1、medium 83.2 / 72.4。今回の差の向きと合う
- **決めたこと**: small を medium に置き換えた（id も `ppocrv6-medium` に変えた）。
  同じ言語を読むモデルを 2 つ並べない方針どおり。small の利点は速さだけで、
  その差（3 秒と 6 秒）は VL（1 頁 20 秒〜1 分）と比べれば小さい。大きさも VL の 1.8GB よりずっと小さい
- **却下した案**: small と medium を並べる。どちらを選べばよいか利用者が迷う。
  id を `ppocrv6-small` のまま中身だけ替える。名前と中身が食い違う
- **途中で分かったこと**: 取得したファイルは repo 名と rev ごとの場所に置くので、置き換えると
  medium は「未取得」に見え、取得し直しになる。small のファイル（31MB）は消えずに残る。
  保存してあった道具の選択が `ppocrv6-small` でも、起動時に既定の道具に戻るので壊れない
- **限界**: 人手の翻刻とはくらべていない。漢籍の版本以外（活字・欧文）では medium と small をくらべていない。
  Windows では速さを測っていない
