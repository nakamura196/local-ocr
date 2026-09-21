#!/usr/bin/env zsh
# 署名済み .app を Apple の notary service に送り、ticket を staple する。
#
# 使い方:
#   op run --env-file=.env -- ./scripts/notarize.zsh [.app へのパス]
#
# 前提:
#   - ./scripts/sign.zsh が完了していること（Developer ID + hardened runtime）
#   - App Store Connect API キーが ~/.private_keys/AuthKey_<KEY_ID>.p8 にあること
#   - APP_STORE_API_KEY / APP_STORE_API_ISSUER が環境にあること
#     （.env は 1Password の op:// 参照なので、必ず op run 経由で渡す。
#      平文で手元に置かない）
#
# 公証は何を見るか
# ----------------
# バンドルの中の Mach-O すべてに、Developer ID の署名・セキュアタイムスタンプ・
# hardened runtime がそろっていることを見る。app.zip のような書庫の中まで降りるので、
# 実行ファイルを Python 側に置くと通せない（scripts/sign.zsh の冒頭に理由）。

set -euo pipefail

cd "${0:A:h}/.."

APP="${1:-$(find build/macos -maxdepth 1 -name "*.app" 2>/dev/null | head -1)}"
ZIP="build/local-ocr-notarize.zip"

[[ -d "$APP" ]] || { print -u2 "アプリが見つかりません: $APP"; exit 1 }
: "${APP_STORE_API_KEY:?APP_STORE_API_KEY が未設定です。op run --env-file=.env -- 経由で実行してください}"
: "${APP_STORE_API_ISSUER:?APP_STORE_API_ISSUER が未設定です}"

KEY_PATH="$HOME/.private_keys/AuthKey_${APP_STORE_API_KEY}.p8"
[[ -f "$KEY_PATH" ]] || { print -u2 "API キーが見つかりません: $KEY_PATH"; exit 1 }

print "[1/4] 署名状態を確認"
codesign --verify --strict "$APP" \
  || { print -u2 "署名が不正です。先に ./scripts/sign.zsh を実行してください"; exit 1 }
for doc in LICENSE NOTICE; do
  [[ -f "$APP/Contents/Resources/$doc" ]] \
    || { print -u2 "$doc がバンドルに入っていません。./scripts/sign.zsh を先に"; exit 1 }
done
print "  OK"

# notarytool は .app ディレクトリを直接受け取れないため zip に固める。
# ditto --keepParent でバンドル構造とリソースフォークを保つ（zip コマンドでは壊れる）。
print "[2/4] 送信用 zip を作成"
rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"
print "  $ZIP ($(du -h "$ZIP" | cut -f1))"

print "[3/4] notary service へ送信（完了まで待機）"
xcrun notarytool submit "$ZIP" \
  --key "$KEY_PATH" \
  --key-id "$APP_STORE_API_KEY" \
  --issuer "$APP_STORE_API_ISSUER" \
  --wait

print "[4/4] ticket を staple して Gatekeeper 評価"
xcrun stapler staple "$APP"
xcrun stapler validate "$APP"
print "  --- spctl ---"
spctl -a -vv "$APP" 2>&1 | sed 's/^/  /'
print
print "  次: op run --env-file=.env -- ./scripts/release.zsh"
