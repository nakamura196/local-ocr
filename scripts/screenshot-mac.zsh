#!/usr/bin/env zsh
# Mac App Store の掲載画像を撮る。scripts/screenshot-windows.ps1 の Mac 版。
#
# 使い方: ./scripts/screenshot-mac.zsh ja|en [出力先] [撮る場面…]   （既定は store/mac/screenshots/<言語>、全場面）
#   例: ./scripts/screenshot-mac.zsh en store/mac/screenshots/en 02-compare
# 前提: build/macos/Local OCR.app があること（./scripts/build-macos.zsh などで作る）。ネットにつながること
#
# アプリ自身に「見本を開いて読み終えた状態」まで進めさせ（src/local_ocr/ui/scene.py）、
# その窓だけを screencapture で撮る。画面を操作しないので、撮っている間に Mac を触ってもよい。
# 窓は 1180x780 で 16:10 ではないので、Mac App Store の大きさ（2880x1800）の台紙の中央に置く。
#
# 設定とモデルは使い捨てのフォルダに置く（LOCAL_OCR_DATA_DIR）。ふだんの設定には触らない。
# 保存の品書き（Windows の 04-tei）は画面のクリックが要るので撮らない。
set -euo pipefail
cd "${0:A:h}/.."

LANG_UI="${1:?ja か en を指定してください}"
[[ "$LANG_UI" == ja || "$LANG_UI" == en ]] || { print -u2 "ja か en を指定してください"; exit 1 }
OUT="${2:-store/mac/screenshots/$LANG_UI}"
ONLY=("${@:3}")
want() { (( ${#ONLY} == 0 )) || (( ${ONLY[(Ie)$1]} )) }
APP_BIN="build/macos/Local OCR.app/Contents/MacOS/local-ocr"
[[ -x "$APP_BIN" ]] || { print -u2 "見つかりません: $APP_BIN"; exit 1 }

# 見本は Windows と同じ。酉蓮社所蔵『阿毘達磨大毘婆沙論』（東洋文庫の IIIF で公開中）。
MANIFEST="https://u-renja.toyobunko-lab.jp/api/iiif/2/117-10/manifest"
PAGE_URL="https://img.toyobunko-lab.jp/iiif/kaken/21H04345/u-renja/117_10/117_10_0002.tif/full/1600,/0/default.jpg"

WORK="$(mktemp -d)"
export LOCAL_OCR_DATA_DIR="$WORK/data"
mkdir -p "$LOCAL_OCR_DATA_DIR" "$OUT"
SAMPLE="$WORK/117-10_0002.jpg"   # ファイル名がそのまま画面の題になる
curl -fsSL -o "$SAMPLE" "$PAGE_URL"

set_prefs() {   # settings.json を丸ごと書く（core/prefs.py が読む）
  print -r -- "$1" > "$LOCAL_OCR_DATA_DIR/settings.json"
}

window_id() {   # PID の持ついちばん大きい窓の番号
  uv run -q --no-project --with pyobjc-framework-Quartz python -I -c '
import sys, Quartz
ws = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
ws = [w for w in ws if w["kCGWindowOwnerPID"] == int(sys.argv[1]) and w.get("kCGWindowLayer") == 0]
ws.sort(key=lambda w: w["kCGWindowBounds"]["Width"] * w["kCGWindowBounds"]["Height"])
print(ws[-1]["kCGWindowNumber"] if ws else "")' "$1"
}

shoot() {   # $1=出力名。残りは「名前=値」の環境変数。読み終えるのを待って窓を撮る
  local name="$1"; shift
  local done="$WORK/done.txt"; rm -f "$done"
  env "$@" LOCAL_OCR_SCENE_DONE="$done" "$APP_BIN" >"$WORK/$name.log" 2>&1 &
  local pid=$!
  local i=0
  if (( $# > 0 )); then
    while [[ ! -s "$done" ]] && (( i < 120 )); do sleep 5; i=$((i+1)); done
    [[ "$(cat "$done" 2>/dev/null)" == ok ]] || { kill $pid; print -u2 "$name: 読み終わりませんでした: $(cat "$done" 2>/dev/null)"; return 1 }
    sleep 3
  else
    sleep 15
  fi
  local wid=""; i=0
  while [[ -z "$wid" ]] && (( i < 30 )); do wid="$(window_id $pid)"; [[ -n "$wid" ]] || sleep 1; i=$((i+1)); done
  screencapture -x -o -l "$wid" "$WORK/$name-raw.png"
  kill $pid; sleep 2
  # 2880x1800 の台紙の中央に置く。窓が大きければ収まるように縮める
  uv run -q --no-project --with pillow python -I -c '
import sys
from PIL import Image
src = Image.open(sys.argv[1]).convert("RGBA")  # 窓の角は透明。RGB にすると黒くなる
W, H = 2880, 1800
s = min(1.0, (W - 160) / src.width, (H - 160) / src.height)
src = src.resize((round(src.width * s), round(src.height * s)), Image.LANCZOS)
bg = Image.new("RGB", (W, H), (236, 238, 241))
bg.paste(src, ((W - src.width) // 2, (H - src.height) // 2), src)
bg.save(sys.argv[2])' "$WORK/$name-raw.png" "$OUT/$name.png"
  print "撮った: $OUT/$name.png"
}

set_prefs "{\"lang\": \"$LANG_UI\", \"last\": null}"
want 01-read && shoot 01-read LOCAL_OCR_SCENE=read LOCAL_OCR_SCENE_SOURCE="$SAMPLE" LOCAL_OCR_SCENE_ENGINES=ndl-koten-lite
set_prefs "{\"lang\": \"$LANG_UI\", \"last\": null}"
want 02-compare && shoot 02-compare LOCAL_OCR_SCENE=compare LOCAL_OCR_SCENE_SOURCE="$SAMPLE" LOCAL_OCR_SCENE_ENGINES=ndl-koten-lite,ndl-lite
set_prefs "{\"lang\": \"$LANG_UI\", \"last\": null}"
want 03-iiif && shoot 03-iiif LOCAL_OCR_SCENE=read LOCAL_OCR_SCENE_SOURCE="$MANIFEST" LOCAL_OCR_SCENE_ENGINES=ndl-koten-lite LOCAL_OCR_SCENE_PAGE=2
set_prefs "{\"lang\": \"$LANG_UI\", \"last\": null, \"engine\": \"ndl-koten-lite\"}"
want 05-landing && shoot 05-landing

rm -rf "$WORK"
print "済み: $OUT"
