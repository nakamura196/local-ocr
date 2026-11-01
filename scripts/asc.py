"""App Store Connect API を読み書きする小さな道具（mas-profile.zsh などが使う）。

使い方:
  op run --env-file=.env -- uv run -q --no-project --with pyjwt --with cryptography \
    python -I scripts/asc.py GET /v1/apps
  ... asc.py POST /v1/bundleIds '<json>'    # 本文は '@ファイル' でも渡せる

資格情報は公証と同じ（APP_STORE_API_KEY / APP_STORE_API_ISSUER と
~/.private_keys/AuthKey_<KEY_ID>.p8）。結果の JSON をそのまま標準出力に出す。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

import jwt

kid = os.environ["APP_STORE_API_KEY"].strip()
iss = os.environ["APP_STORE_API_ISSUER"].strip()
key = open(os.path.expanduser(f"~/.private_keys/AuthKey_{kid}.p8")).read()
now = int(time.time())
token = jwt.encode(
    {"iss": iss, "iat": now, "exp": now + 900, "aud": "appstoreconnect-v1"},
    key,
    algorithm="ES256",
    headers={"kid": kid},
)

method, path = sys.argv[1], sys.argv[2]
body = sys.argv[3].encode() if len(sys.argv) > 3 else None
if body and body.startswith(b"@"):
    body = open(body[1:].decode(), "rb").read()

req = urllib.request.Request(
    "https://api.appstoreconnect.apple.com" + path,
    data=body,
    method=method,
    headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
)
try:
    print(urllib.request.urlopen(req).read().decode())
except urllib.error.HTTPError as e:
    print(json.dumps({"HTTP": e.code, "err": e.read().decode()[:800]}, ensure_ascii=False))
    sys.exit(1)
