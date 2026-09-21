#!/usr/bin/env zsh
# 配布用の .app / .exe を作る。
#
# 使い方:
#   ./scripts/build.zsh            # ホスト OS 向け（macOS）
#   ./scripts/build.zsh windows    # Windows（Windows 上でのみ。クロスビルド不可）
#
# 前提:
#   - 同梱する llama.cpp を binaries/<os>/ に置いてあること
#     （./scripts/fetch-binaries.zsh。無いと sign.zsh で止まる）
#   - Flutter SDK（flet build が無ければ自分で入れる。--yes で対話を飛ばす）
#
# このあと: sign.zsh → notarize.zsh → release.zsh

set -euo pipefail

cd "${0:A:h}/.."

TARGET="${1:-macos}"
PRODUCT="Local OCR"
BUNDLE_ID="com.nakamura.localocr"

# --exclude が無いと .venv（数百 MB）や binaries が丸ごと app.zip に入る。
# binaries は app.zip ではなくバンドル内 Resources/bin へ置く（sign.zsh）。
# app.zip の中身は署名できないので、そこに実行ファイルを入れると公証で必ず弾かれる。
EXCLUDES=(
  .venv
  binaries
  build
  tests
  scripts
  docs        # 設計書と画面写真。実行には要らない
  packaging   # Windows ストア用のアイコン
  .flet       # flet run が作る手元の作業場
  .git
  .github
  .pytest_cache
  .ruff_cache
)

# 配布物から落とすもの（依存が持ち込む、実行に要らないファイル）。
#
# **`**/*.dSYM` は、入れておかないと macOS のビルドが必ず失敗する。**
#
#   strip: fatal error: string table not at the end of the file
#          (can't be processed) in file: .../PyObjCTest/category_gp14...so.dSYM
#          (for architecture x86_64)
#   ** BUILD FAILED **
#
# 何が起きているか: 依存の `pyobjc-core` は、自分の試験用モジュール
# （`PyObjCTest`、280 個）を wheel に同梱しており、それぞれに `.dSYM`
# （デバッグ情報）が付いている。Xcode 26 の strip は、この `.dSYM` の x86_64 の
# 側を処理できずに fatal error で止まる。Xcode は「落ちたら飛ばす」ことをしないので、
# ビルド全体が失敗する。
#
# なぜ archival-packager では起きないか: あちらは pyobjc を使わない。
# こちらは Apple Vision を呼ぶために入れているので、この一式が必ず付いてくる。
#
# 消してよい理由: `.dSYM` は「落ちたときに行番号を人が読む」ためだけのもの。
# `PyObjCTest` は pyobjc 自身の試験で、アプリからは呼ばない。
CLEANUP_PACKAGE_FILES=(
  '**/*.dSYM'
  '**/PyObjCTest'
)

print "[1/3] flet build ${TARGET}"
# --yes: Flutter SDK 導入の対話確認を飛ばす（無いと CI で EOFError）
# --no-rich-output: Windows のコンソールが進捗のスピナー文字を encode できない
#
# **ライセンス全文について（0.86.2 で実測した結論）。**
# Flet 0.86.2 は `--cleanup-packages` を **既定で有効にする**
# （flet_cli の build_base.py で `cleanup.packages` の既定が True）。
# 止めるには pyproject の `[tool.flet.cleanup] packages = false` が要る。
# **止めなくてよい。** 消される既定の一覧は serious_python の `junkFilesDesktop`
# （`**.c` `**.h` `**.pyi` `**.a` `__pycache__` など）だけで、
# `*.dist-info/LICENSE` は対象に入っていない。実測でも 28 個の依存のうち
# 24 個のライセンス全文が残った。下の [2/3] で毎回数えて見張る。
uv run flet build "${TARGET}" . \
  --yes \
  --no-rich-output \
  --exclude "${EXCLUDES[@]}" \
  --cleanup-package-files "${CLEANUP_PACKAGE_FILES[@]}" \
  --product "${PRODUCT}" \
  --bundle-id "${BUNDLE_ID}" \
  --org com.nakamura \
  --info-plist "CFBundleName=${PRODUCT}"
#
# --info-plist で CFBundleName を入れているのは、--product が
# CFBundleDisplayName しか書き換えないため。メニューバーに出る名前は
# CFBundleName の側なので、両方そろえないと「local-ocr」と表示される。

if [[ "${TARGET}" != "macos" ]]; then
  print "[2/3] 成果物"
  print "  build/${TARGET}/ ($(du -sh "build/${TARGET}" | cut -f1))"
  exit 0
fi

APP=$(find build/macos -maxdepth 1 -name "*.app" | head -1)
[[ -d "${APP}" ]] || { print -u2 "  .app が見つかりません"; exit 1 }

# バンドルの名前を製品名に揃える。Flet 0.86.2 は、--product を渡しても
# バンドルのファイル名をプロジェクト名（local-ocr）のままにする。
# **Finder と dmg に出るのはファイル名**なので、ここで直さないと利用者には
# 「local-ocr」と見える。中の CFBundleExecutable は触らない（起動に使われる）。
if [[ "${APP:t}" != "${PRODUCT}.app" ]]; then
  rm -rf "build/macos/${PRODUCT}.app"
  mv "${APP}" "build/macos/${PRODUCT}.app"
  APP="build/macos/${PRODUCT}.app"
  print "  バンドル名を ${PRODUCT}.app に変更"
fi

# --------------------------------------------------------------------------
print "[2/3] 出来たものを点検"

# .venv が入っていないか。除外を書き忘れると静かに数百 MB 増えるだけで、
# 動きは変わらないので気づけない。
#
# **Flet 0.86.2 は app.zip を作らない。** 0.28 系までは Python 側を app.zip に
# 固めてバンドルに入れていたが、いまは site-packages がそのまま
# serious_python_darwin...bundle の中に並ぶ。だから中身を見るのに unzip は要らない。
# （実行ファイルを Python 側に置くと公証で弾かれる、という話は変わらない。
#   バンドルに素で並ぶぶんは署名できるが、アプリの探し先が変わるだけで利点がない）
if find "${APP}" -type d -name ".venv" -print -quit | grep -q .; then
  print -u2 "  バンドルに .venv が入っています。--exclude を確認してください"
  exit 1
fi
print "  .venv: 入っていない"

# 依存が同梱しているライセンス全文が残っているか。
# **数えるのは深さを限らずに。** 多くの wheel は *.dist-info/licenses/LICENSE の
# ように 1 階層下に置く（maxdepth 2 で数えると 43 件が 5 件に見える）。
SITE=$(find "${APP}/Contents" -type d -name "site-packages" 2>/dev/null | head -1)
if [[ -n "${SITE}" ]]; then
  LICENSES=$(find "${SITE}" -type f \
    \( -iname "LICENSE*" -o -iname "LICENCE*" -o -iname "COPYING*" -o -iname "NOTICE*" \) \
    | wc -l | tr -d ' ')
  DISTINFO=$(find "${SITE}" -maxdepth 1 -name "*.dist-info" | wc -l | tr -d ' ')
  print "  同梱された依存のライセンス全文: ${LICENSES} 件（依存 ${DISTINFO} 個）"
  (( LICENSES > 0 )) || { print -u2 "  1 件も残っていません。cleanup の対象が広がっていませんか"; exit 1 }
fi

# 落としたはずのものが残っていないか。
for junk in PyObjCTest '*.dSYM'; do
  found=$(find "${APP}" -name "${junk}" | wc -l | tr -d ' ')
  (( found == 0 )) || print -u2 "  警告: ${junk} が ${found} 件残っています"
done

# Flutter 側（BSD-3-Clause ほか）の表示。Flet が自動で入れるが、版が変わって
# 入らなくなったらこちらの NOTICE に写す必要があるので、有無を毎回出す。
NOTICES=$(find "${APP}/Contents" -name "NOTICES*" 2>/dev/null | head -1)
if [[ -n "${NOTICES}" ]]; then
  print "  flutter_assets/${NOTICES:t}: $(du -h "${NOTICES}" | cut -f1)"
else
  print -u2 "  警告: Flutter 側の NOTICES が見つかりません。NOTICE への写しが要るかもしれません"
fi

print "[3/3] 成果物"
print "  ${APP} ($(du -sh "${APP}" | cut -f1))"
print
print "  次: ./scripts/sign.zsh で Developer ID 署名"
