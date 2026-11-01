#!/usr/bin/env zsh
# Mac App Store 版を作る。build/macos の .app を build/mas に複製し、
# App Sandbox つきで Apple Distribution 署名して、.pkg にまとめる。
#
# 使い方: ./scripts/sign-mas.zsh [ビルド番号]
#
# 前提:
#   - ./scripts/build.zsh と ./scripts/sign.zsh を済ませてあること
#     （llama-server の配置・LICENSE/NOTICE・バンドル外 symlink の除去は sign.zsh が行う。
#      その後の Developer ID 署名は、ここで全部かけ直すので残っていてよい）
#   - build/mas/embedded.provisionprofile（./scripts/mas-profile.zsh で取る）
#   - キーチェーンに Apple Distribution と 3rd Party Mac Developer Installer の証明書
#
# ビルド番号（CFBundleVersion）はアップロードのたびに増やす必要がある。
# 省略すると日時（YYYYMMDDHHMM）を使う。
#
# Developer ID 版（sign.zsh）との違い:
#   - entitlements は entitlements-mas.plist（サンドボックス）。同梱の llama-server だけ
#     entitlements-mas-inherit.plist（親のサンドボックスを継ぐ）
#   - provisioning profile を Contents/embedded.provisionprofile に入れる
#   - 公証は要らない。.pkg を App Store Connect に上げる（upload-mas.zsh）
# 確かめた経緯は docs/notes/mas-sandbox.md。

set -euo pipefail

cd "${0:A:h}/.."

SRC="$(find build/macos -maxdepth 1 -name "*.app" 2>/dev/null | head -1)"
APP="build/mas/${SRC:t}"
PROFILE="build/mas/embedded.provisionprofile"
IDENTITY="Apple Distribution: Satoru Nakamura (Q6S8JS6GWV)"
INSTALLER="3rd Party Mac Developer Installer: Satoru Nakamura (Q6S8JS6GWV)"
ENT_APP="scripts/entitlements-mas.plist"
ENT_CHILD="scripts/entitlements-mas-inherit.plist"
BUILD_NO="${1:-$(date +%Y%m%d%H%M)}"

[[ -d "$SRC" ]] || { print -u2 "アプリが見つかりません（./scripts/build.zsh を先に）"; exit 1 }
[[ -x "$SRC/Contents/Resources/bin/llama-server" ]] || { print -u2 "llama-server が未配置です（./scripts/sign.zsh を先に）"; exit 1 }
[[ -f "$PROFILE" ]] || { print -u2 "profile がありません: $PROFILE（./scripts/mas-profile.zsh を先に）"; exit 1 }

print "[1/5] 複製と Info.plist"
rm -rf "$APP"
ditto "$SRC" "$APP"
PLIST="$APP/Contents/Info.plist"
VERSION=$(plutil -extract CFBundleShortVersionString raw "$PLIST")
# App Store では分類が必須。暗号は HTTPS だけなので、輸出規制の申告は「該当なし」。
plutil -replace LSApplicationCategoryType -string "public.app-category.productivity" "$PLIST"
plutil -replace ITSAppUsesNonExemptEncryption -bool NO "$PLIST"
plutil -replace CFBundleVersion -string "$BUILD_NO" "$PLIST"
cp "$PROFILE" "$APP/Contents/embedded.provisionprofile"
print "  $VERSION ($BUILD_NO)"

if [[ -n "$(find "$APP" -type l -exec sh -c 'case "$(readlink "$1")" in /*) echo "$1";; esac' _ {} \; 2>/dev/null)" ]]; then
  print -u2 "バンドルの外を指す symlink が残っています（./scripts/sign.zsh を先に）"; exit 1
fi

print "[2/5] バンドル内の Mach-O を署名（深い順）"
# 深い順に署名する理由と、file(1) で判定する理由は sign.zsh を参照。
typeset -a machos
while IFS= read -r f; do
  [[ -n "$f" ]] && machos+=("$f")
done < <(find "$APP" -type f -exec sh -c 'file -b "$1" | grep -q "Mach-O" && echo "$1"' _ {} \; 2>/dev/null \
         | awk -F/ '{print NF"\t"$0}' | sort -rn | cut -f2-)
print "  対象 ${#machos[@]} 件"
CHILD="$APP/Contents/Resources/bin/llama-server"
for f in "${machos[@]}"; do
  [[ "$f" == "$APP/Contents/MacOS/"* ]] && continue
  if [[ "$f" == "$CHILD" ]]; then
    codesign --force -s "$IDENTITY" --entitlements "$ENT_CHILD" "$f" 2>/dev/null
  else
    codesign --force -s "$IDENTITY" "$f" 2>/dev/null
  fi
done
while IFS= read -r fw; do
  [[ -n "$fw" ]] && codesign --force -s "$IDENTITY" "$fw" 2>/dev/null
done < <(find "$APP" -type d -name "*.framework" 2>/dev/null | awk -F/ '{print NF"\t"$0}' | sort -rn | cut -f2-)

print "[3/5] アプリ本体を署名（サンドボックス）"
codesign --force -s "$IDENTITY" --entitlements "$ENT_APP" "$APP"

print "[4/5] 検証"
codesign --verify --strict --deep "$APP" && print "  codesign --verify --strict --deep: OK"
codesign -d --entitlements - --xml "$APP" 2>/dev/null | plutil -p - | grep -E "sandbox|application-identifier" | sed 's/^/  /'
codesign -d --entitlements - --xml "$CHILD" 2>/dev/null | plutil -p - | sed 's/^/  llama-server: /' | grep -E "sandbox|inherit"

print "[5/5] .pkg にまとめる"
PKG="build/mas/LocalOCR-${VERSION}-${BUILD_NO}.pkg"
rm -f "$PKG"
productbuild --component "$APP" /Applications --sign "$INSTALLER" "$PKG" >/dev/null
pkgutil --check-signature "$PKG" | grep -E "Status|3rd Party" | sed 's/^/  /'
print "  $PKG ($(du -h "$PKG" | cut -f1))"
print
print "  次: op run --env-file=.env -- ./scripts/upload-mas.zsh $PKG"
