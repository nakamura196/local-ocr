"""Mac App Store の掲載情報を App Store Connect に入れる（審査への提出はしない）。

使い方:
  op run --env-file=.env -- uv run -q --no-project --with pyjwt --with cryptography \
    python -I scripts/mas_listing.py [--build <ビルド番号>]

入れるもの（文面は store/mac/listing.json）:
  - 版の番号（.app の CFBundleShortVersionString）と、使うビルド
  - 日本語・英語の名前・副題・説明・キーワード・URL・プライバシーポリシー
  - カテゴリ・著作権表示・他者のコンテンツの権利の申告・年齢区分の質問への答え・審査担当への連絡先とメモ
  - 画面写真（store/mac/screenshots/<ja|en>/*.png。scripts/screenshot-mac.zsh で撮る）。
    既にある画面写真は消して入れ直す
入れないもの（画面で行う）: App のプライバシー（データの収集）。価格と配信地域は 2026-11-01 に API で設定済み。

何度流しても同じ結果になる（既にあるものは書き換える）。
"""
import argparse
import hashlib
import json
import os
import plistlib
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import jwt

APP_ID = "6829376468"
ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "store/mac/listing.json").read_text())


def token() -> str:
    kid = os.environ["APP_STORE_API_KEY"].strip()
    iss = os.environ["APP_STORE_API_ISSUER"].strip()
    key = Path(f"~/.private_keys/AuthKey_{kid}.p8").expanduser().read_text()
    now = int(time.time())
    return jwt.encode(
        {"iss": iss, "iat": now, "exp": now + 900, "aud": "appstoreconnect-v1"},
        key, algorithm="ES256", headers={"kid": kid},
    )


TOKEN = token()


def api(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        "https://api.appstoreconnect.apple.com" + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path} → {e.code}\n{e.read().decode()}")
    return json.loads(raw) if raw else {}


def upsert_localizations(kind: str, parent_rel: str, parent_type: str, parent_id: str,
                         existing: list[dict], fields: list[str]) -> None:
    by_locale = {x["attributes"]["locale"]: x["id"] for x in existing}
    for locale, src in DATA["locales"].items():
        attrs = {k: src[k] for k in fields if k in src}
        if locale in by_locale:
            api("PATCH", f"/v1/{kind}/{by_locale[locale]}",
                {"data": {"type": kind, "id": by_locale[locale], "attributes": attrs}})
            print(f"  {kind} {locale}: 更新")
        else:
            api("POST", f"/v1/{kind}", {"data": {
                "type": kind, "attributes": {"locale": locale, **attrs},
                "relationships": {parent_rel: {"data": {"type": parent_type, "id": parent_id}}}}})
            print(f"  {kind} {locale}: 作成")


SHOT_DIR = {"ja": "ja", "en-US": "en"}


def upload_screenshots(loc_id: str, locale: str) -> None:
    files = sorted((ROOT / "store/mac/screenshots" / SHOT_DIR[locale]).glob("*.png"))
    if not files:
        print(f"  画面写真 {locale}: ファイルが無いので飛ばす")
        return
    sets = api("GET", f"/v1/appStoreVersionLocalizations/{loc_id}/appScreenshotSets")["data"]
    desk = next((x for x in sets if x["attributes"]["screenshotDisplayType"] == "APP_DESKTOP"), None)
    if desk:
        for old in api("GET", f"/v1/appScreenshotSets/{desk['id']}/appScreenshots")["data"]:
            api("DELETE", f"/v1/appScreenshots/{old['id']}")
    else:
        desk = api("POST", "/v1/appScreenshotSets", {"data": {
            "type": "appScreenshotSets", "attributes": {"screenshotDisplayType": "APP_DESKTOP"},
            "relationships": {"appStoreVersionLocalization": {
                "data": {"type": "appStoreVersionLocalizations", "id": loc_id}}}}})["data"]
    for f in files:
        body = f.read_bytes()
        shot = api("POST", "/v1/appScreenshots", {"data": {
            "type": "appScreenshots", "attributes": {"fileName": f.name, "fileSize": len(body)},
            "relationships": {"appScreenshotSet": {"data": {"type": "appScreenshotSets", "id": desk["id"]}}}}})["data"]
        for op in shot["attributes"]["uploadOperations"]:
            part = body[op["offset"]:op["offset"] + op["length"]]
            req = urllib.request.Request(op["url"], data=part, method=op["method"],
                                         headers={h["name"]: h["value"] for h in op["requestHeaders"]})
            urllib.request.urlopen(req).read()
        api("PATCH", f"/v1/appScreenshots/{shot['id']}", {"data": {
            "type": "appScreenshots", "id": shot["id"],
            "attributes": {"uploaded": True, "sourceFileChecksum": hashlib.md5(body).hexdigest()}}})
    print(f"  画面写真 {locale}: {len(files)} 枚")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", help="使うビルド番号（省略時は最新の VALID）")
    args = ap.parse_args()

    plist = plistlib.loads((ROOT / "build/mas/Local OCR.app/Contents/Info.plist").read_bytes())
    version = plist["CFBundleShortVersionString"]

    builds = api("GET", f"/v1/builds?filter[app]={APP_ID}&filter[processingState]=VALID"
                        f"&filter[preReleaseVersion.version]={version}&sort=-uploadedDate&limit=20")["data"]
    if args.build:
        builds = [b for b in builds if b["attributes"]["version"] == args.build]
    if not builds:
        sys.exit(f"版 {version} の VALID なビルドが見つかりません")
    build = builds[0]
    print(f"版 {version} / ビルド {build['attributes']['version']}")

    versions = api("GET", f"/v1/apps/{APP_ID}/appStoreVersions?filter[platform]=MAC_OS"
                          "&filter[appStoreState]=PREPARE_FOR_SUBMISSION,DEVELOPER_REJECTED,REJECTED"
                          "&include=appStoreVersionLocalizations")
    if not versions["data"]:
        sys.exit("編集できる版（提出の準備中）がありません")
    ver = versions["data"][0]
    api("PATCH", f"/v1/appStoreVersions/{ver['id']}", {"data": {
        "type": "appStoreVersions", "id": ver["id"],
        "attributes": {"versionString": version, "copyright": DATA["copyright"]},
        "relationships": {"build": {"data": {"type": "builds", "id": build["id"]}}}}})
    print("  版の番号・著作権・ビルド: 設定")

    locs = [x for x in versions.get("included", []) if x["type"] == "appStoreVersionLocalizations"]
    upsert_localizations("appStoreVersionLocalizations", "appStoreVersion", "appStoreVersions",
                         ver["id"], locs,
                         ["description", "keywords", "promotionalText", "supportUrl", "marketingUrl"])

    locs = api("GET", f"/v1/appStoreVersions/{ver['id']}/appStoreVersionLocalizations")["data"]
    for loc in locs:
        if loc["attributes"]["locale"] in SHOT_DIR:
            upload_screenshots(loc["id"], loc["attributes"]["locale"])

    infos = api("GET", f"/v1/apps/{APP_ID}/appInfos?include=appInfoLocalizations")
    info = next(x for x in infos["data"] if x["attributes"]["state"] != "READY_FOR_DISTRIBUTION")
    api("PATCH", f"/v1/appInfos/{info['id']}", {"data": {
        "type": "appInfos", "id": info["id"], "relationships": {
            "primaryCategory": {"data": {"type": "appCategories", "id": DATA["primaryCategory"]}},
            "secondaryCategory": {"data": {"type": "appCategories", "id": DATA["secondaryCategory"]}}}}})
    print("  カテゴリ: 設定")
    ilocs = [x for x in infos.get("included", []) if x["type"] == "appInfoLocalizations"]
    upsert_localizations("appInfoLocalizations", "appInfo", "appInfos", info["id"], ilocs,
                         ["name", "subtitle", "privacyPolicyUrl"])

    age = api("GET", f"/v1/appInfos/{info['id']}/ageRatingDeclaration")["data"]
    attrs = {k: "NONE" for k in DATA["ageRating"]["enums_none"]}
    attrs |= {k: False for k in DATA["ageRating"]["booleans_false"]}
    api("PATCH", f"/v1/ageRatingDeclarations/{age['id']}",
        {"data": {"type": "ageRatingDeclarations", "id": age["id"], "attributes": attrs}})
    print("  年齢区分: 設定")

    # 未設定だと「Add for Review」が「Content Rights Information」不足で止まる (2026-11-01)
    api("PATCH", f"/v1/apps/{APP_ID}", {"data": {"type": "apps", "id": APP_ID, "attributes": {
        "contentRightsDeclaration": DATA["contentRightsDeclaration"]}}})
    print("  他者のコンテンツの権利: 設定")

    review = api("GET", f"/v1/appStoreVersions/{ver['id']}/appStoreReviewDetail")["data"]
    if review:
        api("PATCH", f"/v1/appStoreReviewDetails/{review['id']}", {"data": {
            "type": "appStoreReviewDetails", "id": review["id"], "attributes": DATA["review"]}})
    else:
        api("POST", "/v1/appStoreReviewDetails", {"data": {
            "type": "appStoreReviewDetails", "attributes": DATA["review"],
            "relationships": {"appStoreVersion": {"data": {"type": "appStoreVersions", "id": ver["id"]}}}}})
    print("  審査担当への連絡先とメモ: 設定")
    print("済み。残りは画面で: App のプライバシー。提出もしていない")


if __name__ == "__main__":
    main()
