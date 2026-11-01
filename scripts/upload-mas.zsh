#!/usr/bin/env zsh
# sign-mas.zsh が作った .pkg を App Store Connect に上げる。
# 上げたビルドは数分〜数十分の処理のあと TestFlight に出る。審査への提出は別（画面か API）。
#
# 使い方: op run --env-file=.env -- ./scripts/upload-mas.zsh build/mas/LocalOCR-<版>-<番号>.pkg
#
# 資格情報は公証と同じ API キー（notarize.zsh と同じ前提）。
set -euo pipefail
cd "${0:A:h}/.."

PKG="${1:?.pkg を指定してください}"
[[ -f "$PKG" ]] || { print -u2 "見つかりません: $PKG"; exit 1 }
: "${APP_STORE_API_KEY:?op run --env-file=.env -- 経由で実行してください}"
: "${APP_STORE_API_ISSUER:?APP_STORE_API_ISSUER が未設定です}"

print "[1/2] 検査（validate）"
xcrun altool --validate-app -f "$PKG" -t macos --apiKey "$APP_STORE_API_KEY" --apiIssuer "$APP_STORE_API_ISSUER"
print "[2/2] アップロード"
xcrun altool --upload-app -f "$PKG" -t macos --apiKey "$APP_STORE_API_KEY" --apiIssuer "$APP_STORE_API_ISSUER"
