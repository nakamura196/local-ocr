#!/usr/bin/env zsh
# 公証済み .app を .dmg に固め、dmg 自体も署名・公証・staple する。
#
# 使い方:
#   op run --env-file=.env -- ./scripts/release.zsh              # dmg を作るだけ
#   op run --env-file=.env -- ./scripts/release.zsh --publish    # タグ付け + GitHub Release
#
#   ./scripts/release.zsh --publish     # 公証済みの dmg がもう在るなら op は要らない
#
# 前提:
#   - ./scripts/build.zsh → sign.zsh → notarize.zsh まで完了していること
#     （このスクリプトは .app が署名・公証・staple 済みであることを検証してから始める）
#   - dmg を作るときだけ create-dmg（brew install create-dmg）と
#     APP_STORE_API_KEY / APP_STORE_API_ISSUER（1Password 参照を op run で注入）が要る。
#     **既に公証済みの dmg が在れば、作り直さないので資格情報も要らない**
#
# なぜ .app を配らず .dmg にするか
# --------------------------------
# .app をそのまま zip で配ると、展開時に実行ビットや署名が壊れることがある。
# Gatekeeper の隔離属性まわりの挙動も .dmg のほうが素直で、「ドラッグして
# Applications へ」という導線も利用者に馴染みがある。
#
# なぜ dmg も公証するか
# ---------------------
# 中の .app を staple してあっても、dmg 自体に ticket が無いと初回マウント時に
# ネットワーク越しの検証が要る。オフラインの端末や、検疫の厳しい組織内
# ネットワークではそこで止まる。dmg にも staple しておく。
#
# --publish を付けない限り外に何も出さない。既定は dmg を作るところまで。

set -euo pipefail

cd "${0:A:h}/.."

PUBLISH=""
[[ "${1:-}" == "--publish" ]] && PUBLISH=1

APP=$(find build/macos -maxdepth 1 -name "*.app" 2>/dev/null | head -1)
IDENTITY="Developer ID Application: Satoru Nakamura (Q6S8JS6GWV)"
VOLNAME="Local OCR"

[[ -d "$APP" ]] || { print -u2 "アプリが見つかりません。./scripts/build.zsh を先に実行してください"; exit 1 }

VERSION=$(grep -m1 -E '^version *= *"' pyproject.toml | sed -E 's/.*"([^"]+)".*/\1/')
[[ -n "$VERSION" ]] || { print -u2 "pyproject.toml から version を読めません"; exit 1 }
TAG="v${VERSION}"
DMG="build/local-ocr-${VERSION}.dmg"

print "リリース ${TAG}"

# 公証済みの dmg がもう在るなら、作り直さない。
#
# **作り直すと、同じ中身をもう一度 Apple に送ることになる。** そのために
# 1Password の認証がまた要り、公開がそこで止まる（2026-09-21 に 2 回止まった）。
# dmg の署名と公証チケットの両方が有効なら、そのまま配って差し支えない。
# 作り直したいときは先に消す（`rm build/local-ocr-*.dmg`）。
REUSE=""
if [[ -f "$DMG" ]] \
  && codesign --verify --strict "$DMG" 2>/dev/null \
  && xcrun stapler validate "$DMG" >/dev/null 2>&1; then
  REUSE=1
  print "  既にある公証済みの dmg を使う: $DMG ($(du -h "$DMG" | cut -f1))"
fi

# 公証に出すときだけ資格情報が要る。
if [[ -z "$REUSE" ]]; then
  command -v create-dmg >/dev/null || { print -u2 "create-dmg がありません（brew install create-dmg）"; exit 1 }
  : "${APP_STORE_API_KEY:?APP_STORE_API_KEY が未設定です。op run --env-file=.env -- 経由で実行してください}"
  : "${APP_STORE_API_ISSUER:?APP_STORE_API_ISSUER が未設定です}"
  KEY_PATH="$HOME/.private_keys/AuthKey_${APP_STORE_API_KEY}.p8"
  [[ -f "$KEY_PATH" ]] || { print -u2 "API キーが見つかりません: $KEY_PATH"; exit 1 }
fi

# --------------------------------------------------------------------------
print "[1/5] .app の状態を確認"

# ここを飛ばすと、未公証の .app を dmg に固めて配ってしまう。dmg 側の公証は
# 通るので、配ったあと利用者側で初めて弾かれる。
codesign --verify --strict "$APP" \
  || { print -u2 "  署名が不正です。./scripts/sign.zsh を先に"; exit 1 }
xcrun stapler validate "$APP" >/dev/null 2>&1 \
  || { print -u2 "  公証チケットがありません。./scripts/notarize.zsh を先に"; exit 1 }

# ライセンス表示の同梱漏れ。同梱した llama.cpp（MIT）、NDL の 2 つ（CC BY 4.0、
# 表示が要る）、それに全文を自分で持たない 6 つの依存の分が NOTICE にある。
for doc in LICENSE NOTICE; do
  [[ -f "$APP/Contents/Resources/$doc" ]] \
    || { print -u2 "  $doc がバンドルに入っていません。./scripts/sign.zsh を先に"; exit 1 }
done
print "  署名・公証・ライセンス表示 OK"

if [[ -n "$PUBLISH" ]]; then
  [[ -z "$(git status --porcelain --untracked-files=no)" ]] \
    || { print -u2 "  未コミットの変更があります"; exit 1 }
  git rev-parse "$TAG" >/dev/null 2>&1 \
    && { print -u2 "  タグ $TAG は既にあります。pyproject.toml の version を上げてください"; exit 1 }
fi

# --------------------------------------------------------------------------
if [[ -n "$REUSE" ]]; then
  print "[2-4/5] dmg の作成・署名・公証は済んでいるので飛ばす"
else
print "[2/5] .dmg を作成"
rm -f "$DMG"
CREATE_DMG_ARGS=(
  --volname "$VOLNAME"
  --window-pos 200 120
  --window-size 600 400
  --icon-size 120
  --icon "${APP:t}" 150 200
  --hide-extension "${APP:t}"
  --app-drop-link 450 200
  --no-internet-enable
)
ICNS="$APP/Contents/Resources/AppIcon.icns"
[[ -f "$ICNS" ]] && CREATE_DMG_ARGS+=(--volicon "$ICNS")

create-dmg "${CREATE_DMG_ARGS[@]}" "$DMG" "$APP" >/dev/null
print "  $DMG ($(du -h "$DMG" | cut -f1))"

# --------------------------------------------------------------------------
print "[3/5] .dmg に署名"
# create-dmg の出力は未署名。署名しておけば「配布中に差し替えられていない」ことまで
# 検証できる。
codesign --force --timestamp -s "$IDENTITY" "$DMG"
codesign --verify --strict "$DMG"
print "  OK"

# --------------------------------------------------------------------------
print "[4/5] .dmg を公証（完了まで待機）"
xcrun notarytool submit "$DMG" \
  --key "$KEY_PATH" --key-id "$APP_STORE_API_KEY" --issuer "$APP_STORE_API_ISSUER" --wait

xcrun stapler staple "$DMG"
xcrun stapler validate "$DMG"
fi

# --------------------------------------------------------------------------
print "[5/5] 配布前の最終確認"
# ダウンロード直後の利用者と同じ経路で確かめる。マウントした .app を評価しないと、
# dmg だけ通って中身が弾かれる構成に気づけない。
MOUNT=$(mktemp -d)
hdiutil attach "$DMG" -nobrowse -quiet -mountpoint "$MOUNT"
trap 'hdiutil detach "$MOUNT" -quiet 2>/dev/null || true; rmdir "$MOUNT" 2>/dev/null || true' EXIT

MOUNTED_APP=$(find "$MOUNT" -maxdepth 1 -name "*.app" | head -1)
[[ -d "$MOUNTED_APP" ]] || { print -u2 "  dmg の中に .app がありません"; exit 1 }
spctl -a -vv "$MOUNTED_APP" 2>&1 | sed 's/^/  /'

# 同梱した llama-server が、マウントしたバンドルの中から実際に起動するか。
# dylib は @loader_path で隣を引くので、取り込みに欠けがあればここで落ちる。
MOUNTED_BIN="$MOUNTED_APP/Contents/Resources/bin"
"$MOUNTED_BIN/llama-server" --version 2>&1 | grep -m1 version | sed 's/^/  同梱 llama.cpp: /'

# ライセンス表示が dmg の中まで届いているか。
for doc in LICENSE NOTICE; do
  [[ -f "$MOUNTED_APP/Contents/Resources/$doc" ]] \
    || { print -u2 "  $doc が dmg の中の .app にありません"; exit 1 }
done
print "  LICENSE / NOTICE: OK"

hdiutil detach "$MOUNT" -quiet
trap - EXIT
rmdir "$MOUNT" 2>/dev/null || true

if [[ -z "$PUBLISH" ]]; then
  print
  print "完了: $DMG"
  print "公開する場合は --publish を付けて再実行してください（タグ $TAG を打ちます）。"
  print "**別のマシンで開いて確かめてから公開すること。** 署名・公証が通っても、"
  print "Gatekeeper が symlink で弾くことがあり、ビルドした機械では気づけない。"
  exit 0
fi

# --------------------------------------------------------------------------
print
print "タグ $TAG を打って GitHub Release を作成"
git tag -a "$TAG" -m "Local OCR $TAG"
git push origin "$TAG"
gh release create "$TAG" "$DMG" --title "$TAG" --generate-notes --verify-tag
print "  $(gh release view "$TAG" --json url -q .url)"
