#!/usr/bin/env zsh
# Mac App Store 用の provisioning profile を App Store Connect から取り、
# build/mas/embedded.provisionprofile に置く（sign-mas.zsh が使う）。
#
# 使い方: op run --env-file=.env -- ./scripts/mas-profile.zsh
#
# profile の名前は「Local OCR Mac App Store」（2026-10-31 に API で作成、1 年で切れる）。
# 切れたら同じ名前で作り直す（作り方は docs/notes/mas-sandbox.md）。
set -euo pipefail
cd "${0:A:h}/.."
NAME="Local OCR Mac App Store"
OUT="build/mas/embedded.provisionprofile"
mkdir -p "${OUT:h}"
uv run -q --no-project --with pyjwt --with cryptography python -I scripts/asc.py GET \
  "/v1/profiles?filter[name]=${NAME// /%20}&filter[profileState]=ACTIVE" \
  | python3 -c "
import json,sys,base64
d=json.load(sys.stdin)['data']
if not d: sys.exit('有効な profile がありません: $NAME')
a=d[0]['attributes']
open('$OUT','wb').write(base64.b64decode(a['profileContent']))
print('  ', a['name'], a['profileType'], '期限', a['expirationDate'][:10])
"
print "  $OUT"
