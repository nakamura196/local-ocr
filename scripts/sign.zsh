#!/usr/bin/env zsh
# Flet が作った .app に llama.cpp を埋め込み、Developer ID + hardened runtime で署名する。
#
# 使い方: ./scripts/sign.zsh [.app へのパス]
#
# なぜ app.zip ではなくバンドルの中に置くのか
# -------------------------------------------
# Python 側（assets/ など）に実行ファイルを置くと、flet build がそれを app.zip に
# 格納する。起動はできるが、公証に出すと必ず弾かれる。Apple の審査は app.zip の
# 中まで降りて、次の 3 つを実行ファイルに要求する。
#
#   The binary is not signed with a valid Developer ID certificate.
#   The signature does not include a secure timestamp.
#   The executable does not have the hardened runtime enabled.
#
# zip の中のファイルは署名できないので、原理的に通せない。だから llama-server と
# その dylib は .app のバンドル内（Contents/Resources/bin/）に置き、
# 1 つずつ署名する。アプリ側の探し先は src/local_ocr/core/bundled.py。
#
# 署名の取りこぼしに注意
# ----------------------
# 「実行ファイル」だけを対象にすると dylib を取りこぼす。dylib は実行ビットを
# 持たないことがあり（Python.framework の libssl / libcrypto が実際にそう）、
# 取りこぼすと公証が Invalid で返る。判定は必ず file(1) の Mach-O 判定で行い、
# パーミッションで絞らないこと。

set -euo pipefail

cd "${0:A:h}/.."

# .app の名前は Flet の版や --product の扱いで変わるため、探して決める。
APP="${1:-$(find build/macos -maxdepth 1 -name "*.app" 2>/dev/null | head -1)}"
IDENTITY="Developer ID Application: Satoru Nakamura (Q6S8JS6GWV)"
ENTITLEMENTS="scripts/entitlements.plist"
BINARIES="binaries/macos"

[[ -d "$APP" ]] || { print -u2 "アプリが見つかりません: $APP（./scripts/build.zsh を先に）"; exit 1 }
[[ -f "$ENTITLEMENTS" ]] || { print -u2 "entitlements が見つかりません: $ENTITLEMENTS"; exit 1 }
[[ -x "$BINARIES/llama-server" ]] || {
  print -u2 "同梱するものがありません: $BINARIES/llama-server（./scripts/fetch-binaries.zsh を先に）"
  exit 1
}

# codesign のセキュアタイムスタンプ取得は、ネットワーク次第で確率的に失敗する。
retry() {
  local n=1
  until "$@"; do
    (( n++ ))
    (( n > 3 )) && return 1
    print -u2 "  retry ($n/3)"
    sleep 15
  done
}

print "[1/4] llama.cpp をバンドルへ配置"
DEST="$APP/Contents/Resources/bin"
rm -rf "$DEST"
mkdir -p "$DEST"
# binaries/macos/ の中身をそのまま入れる。個別に列挙すると、llama.cpp の版が
# 変わって増えた dylib を取りこぼす（fetch-binaries.zsh も同じ方針で取り込んでいる）。
#
# 内訳: llama-server 本体、それが @loader_path で引く libllama / libggml / libmtmd、
#       および llama.cpp の LICENSE（MIT）。
#
# dylib は **実体だけを install id が示す名前（soname）で置き、symlink は張らない。**
# バンドル内の symlink は Gatekeeper の
#   invalid destination for symbolic link in bundle
# を招きやすい。llama-server の rpath は @loader_path なので、同じ階層に
# soname で並んでいれば解決する。
cp -R "$BINARIES"/. "$DEST"/
find "$DEST" -type f -name '*.dylib' -exec chmod 755 {} +
chmod 755 "$DEST/llama-server"
print "  $DEST（$(ls "$DEST" | wc -l | tr -d ' ') 件、$(du -sh "$DEST" | cut -f1)）"

# @rpath の参照が全部そろっているか。開発機には前に取った llama.cpp が
# ~/PaddleOCR校正/llama-*/ に残っていることがあり、そちらで動いてしまうと
# 欠けに気づけない。ここはバンドルの中だけを見る。
print "  --- @rpath の参照を突き合わせ ---"
typeset -i missing=0
for macho in "$DEST"/llama-server "$DEST"/*.dylib; do
  while IFS= read -r ref; do
    [[ -e "$DEST/${ref#@rpath/}" ]] || { print -u2 "    欠け: ${macho:t} -> $ref"; missing=$((missing + 1)) }
  done < <(otool -L "$macho" | awk '/@rpath\//{print $1}')
done
(( missing == 0 )) || { print -u2 "  参照が $missing 件欠けています。fetch-binaries.zsh を見直してください"; exit 1 }
print "    欠けなし"

# ライセンス表示を配布物に入れる。**6 つの依存（flet / flet-desktop /
# flatbuffers / pyobjc-core / pyobjc-framework-CoreML / pyobjc-framework-Vision）は
# ライセンス全文を wheel のどこにも持っておらず、その文面は NOTICE にしかない。**
# 同梱した llama.cpp（MIT）と、NDL の 2 つ（CC BY 4.0。表示が要る）も同じ。
# バンドルに入れずに配ると条件を満たさない。
for doc in LICENSE NOTICE; do
  [[ -f "$doc" ]] || { print -u2 "$doc がありません。配布物に必要です"; exit 1 }
  cp "$doc" "$APP/Contents/Resources/$doc"
done
print "  $APP/Contents/Resources/{LICENSE,NOTICE}"

# バンドルの外を指す symlink があると、公証は通っても Gatekeeper が
#   rejected (invalid destination for symbolic link in bundle)
# で弾く。serious_python_darwin.framework の中に、ビルドした機械の pub-cache を
# 指す絶対パスの symlink が残る。実行時には要らない残骸なので消す。
# **署名の前に消すこと**（後で消すと封が破れる）。
print "[1.5/4] バンドル外を指す symlink を除去"
typeset -i removed=0
while IFS= read -r link; do
  [[ -n "$link" ]] || continue
  print "  削除: ${link#$APP/} -> $(readlink "$link")"
  rm -f "$link"
  removed=$((removed + 1))
done < <(find "$APP" -type l -exec sh -c 'case "$(readlink "$1")" in /*) echo "$1";; esac' _ {} \; 2>/dev/null)
if (( removed == 0 )); then print "  なし"; fi

print "[2/4] バンドル内の Mach-O を全て署名"
# パーミッションで絞らない（dylib は実行ビットを持たないことがある）。
#
# 署名は必ず深い階層から行う。framework 本体を先に署名すると、後からその内部の
# dylib を署名した時点で封が破れ、"a sealed resource is missing or invalid" になる。
# find の出力順は不定なので、パス区切りの数で深い順に並べ替える。
typeset -a machos
while IFS= read -r f; do
  [[ -n "$f" ]] && machos+=("$f")
done < <(find "$APP" -type f -exec sh -c 'file -b "$1" | grep -q "Mach-O" && echo "$1"' _ {} \; 2>/dev/null \
         | awk -F/ '{print NF"\t"$0}' | sort -rn | cut -f2-)

print "  対象 ${#machos[@]} 件（深い順）"
for f in "${machos[@]}"; do
  # アプリ本体の実行ファイルは最後に entitlements 付きで署名するので飛ばす。
  [[ "$f" == "$APP/Contents/MacOS/"* ]] && continue
  retry codesign --force --options runtime --timestamp -s "$IDENTITY" "$f" 2>/dev/null
done

# framework は「バンドル」として署名し直す必要がある。内部ファイルを個別に
# 署名したあとでここを通すことで、封を正しく結び直す。これも深い順。
print "  framework バンドルを再署名"
while IFS= read -r fw; do
  [[ -n "$fw" ]] || continue
  retry codesign --force --options runtime --timestamp -s "$IDENTITY" "$fw" 2>/dev/null
done < <(find "$APP" -type d -name "*.framework" 2>/dev/null \
         | awk -F/ '{print NF"\t"$0}' | sort -rn | cut -f2-)
print "  完了"

print "[3/4] アプリ本体を再シール（entitlements 付き）"
retry codesign --force --options runtime --timestamp \
  --entitlements "$ENTITLEMENTS" -s "$IDENTITY" "$APP"

print "[4/4] 検証"
codesign --verify --strict "$APP" && print "  codesign --verify --strict: OK"
print "  --- 同梱 llama-server の署名 ---"
codesign -dv --verbose=2 "$DEST/llama-server" 2>&1 \
  | grep -E "Authority=Developer ID|TeamIdentifier|flags|Timestamp" | sed 's/^/    /'
print "  --- アプリ本体 ---"
codesign -dv --verbose=2 "$APP" 2>&1 \
  | grep -E "Authority=Developer ID|TeamIdentifier|flags|Timestamp" | sed 's/^/    /'
print "  --- 未署名 Mach-O が残っていないか ---"
typeset -i unsigned=0
for f in "${machos[@]}"; do
  codesign -v "$f" >/dev/null 2>&1 || { print "    UNSIGNED: $f"; unsigned=1 }
done
if (( unsigned == 0 )); then print "    なし"; fi
print
print "  次: op run --env-file=.env -- ./scripts/notarize.zsh"
