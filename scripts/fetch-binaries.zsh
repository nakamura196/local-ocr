#!/usr/bin/env zsh
# 同梱する llama.cpp を取得して binaries/macos/ に置く（macOS 用）。
#
# 使い方: ./scripts/fetch-binaries.zsh
#
# 版は src/local_ocr/core/assets.py の LLAMA_BUILD から読む。**ここに書かない。**
# 2 か所に書くと、片方だけ上げたときに「取ってきたものと、アプリが探すもの」が
# ずれる。ずれても開発機では前に取ったものが残っていて動いてしまう。
#
# なぜ同梱するのか
# ----------------
# 0.1.0 までは初回起動時に GitHub から llama-server を取ってきて動かしていた。
# これはストアの審査（審査が見たものと、実際に動くものが別になる）と正面から
# ぶつかる。ビルド時に取り込み、アプリと一緒に署名する。
#
# モデル (.gguf) は同梱しない。1.8GB あり、中身はデータであって実行ファイルでは
# ないので、初回取得のままでよい（src/local_ocr/core/assets.py）。
#
# Windows 側は scripts/fetch-binaries.ps1（CI から呼ぶ）。同じ版を使う。

set -euo pipefail

cd "${0:A:h}/.."

case "$(uname -s)" in
  Darwin) ;;
  *) print -u2 "このスクリプトは macOS 用です。Windows は scripts/fetch-binaries.ps1。"; exit 1 ;;
esac

ASSETS="src/local_ocr/core/assets.py"
LLAMA_BUILD=$(sed -n 's/^LLAMA_BUILD = "\(.*\)"$/\1/p' "${ASSETS}")
[[ -n "${LLAMA_BUILD}" ]] || { print -u2 "${ASSETS} から LLAMA_BUILD を読めませんでした"; exit 1 }

case "$(uname -m)" in
  arm64)  NAME="llama-${LLAMA_BUILD}-bin-macos-arm64.tar.gz" ;;
  x86_64) NAME="llama-${LLAMA_BUILD}-bin-macos-x64.tar.gz" ;;
  *) print -u2 "対応していない CPU です: $(uname -m)"; exit 1 ;;
esac

DEST="binaries/macos"
URL="https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_BUILD}/${NAME}"

rm -rf "${DEST}"
mkdir -p "${DEST}"
WORK=$(mktemp -d)
trap 'rm -rf "${WORK}"' EXIT

print "[1/4] llama.cpp ${LLAMA_BUILD} ($(uname -m))"
curl -fsSL -o "${WORK}/llama.tar.gz" "${URL}"
tar -xzf "${WORK}/llama.tar.gz" -C "${WORK}"

# 配布物によって、中身が 1 階層のフォルダに入っている版と、そのまま並んでいる
# 版がある。llama-server を探し直して、どちらでも動くようにする。
SRC=$(dirname "$(find "${WORK}" -type f -name llama-server -perm -u+x | head -1)")
[[ -d "${SRC}" ]] || { print -u2 "展開しましたが llama-server が見つかりません"; exit 1 }

# ---------------------------------------------------------------- 取り込み
#
# **実行ファイルは llama-server だけ。それ以外は全部そのまま入れる。**
# 個別に列挙すると取りこぼす（llama.cpp の macOS ビルドは、版によって
# Metal のシェーダ ggml-metal.metal / *.metallib を横に置く形のことがある。
# b10776 では libggml-metal.dylib の中に入っており、外に出ていない）。
# llama-cli や llama-bench まで入れると、署名・公証の対象が無駄に増える。
#
# dylib は実体だけを、install id が示す名前（soname）で置く。
#   例: 実体 libggml.0.22.0.dylib / id @rpath/libggml.0.dylib → libggml.0.dylib
# シンボリックリンクは張らない。バンドル内の symlink は Gatekeeper の
# 「invalid destination for symbolic link in bundle」を招きやすい。
# llama-server の rpath は @loader_path なので、同じ階層に soname で
# 並んでいれば解決できる（otool -l llama-server で確認できる）。

print "[2/4] 実行ファイルと dylib を取り出す"
typeset -i libs=0 others=0
for src in "${SRC}"/*; do
  [[ -f "${src}" && ! -L "${src}" ]] || continue
  name="${src:t}"
  case "${name}" in
    llama-server) cp -f "${src}" "${DEST}/${name}"; chmod 755 "${DEST}/${name}" ;;
    *.dylib)
      soname=$(otool -D "${src}" | tail -1)
      cp -f "${src}" "${DEST}/${soname:t}"
      chmod 755 "${DEST}/${soname:t}"
      libs=$(( libs + 1 ))
      ;;
    # ほかの実行ファイル（llama / llama-cli / llama-bench / ggml-rpc-server ほか）は
    # 入れない。**`llama-*` だけでは、傘の `llama` 1 本が漏れる。**
    llama|llama-*|ggml-*) ;;
    # LICENSE、Metal のシェーダ、そのほか。**中身を見ずにそのまま入れる。**
    *) cp -f "${src}" "${DEST}/${name}"; others=$(( others + 1 )) ;;
  esac
done
[[ -f "${DEST}/llama-server" ]] || { print -u2 "llama-server を取り出せませんでした"; exit 1 }
(( libs > 0 )) || { print -u2 "dylib を 1 つも取り出せませんでした"; exit 1 }

# ネットから取ったファイルに macOS が付ける印を外す。これが無いと起動できない。
xattr -dr com.apple.quarantine "${DEST}" 2>/dev/null || true

print "[3/4] 参照の取りこぼしを調べる"
# @rpath の参照が全部そろっているかを見る。1 つでも欠けると、起動した瞬間に
# dyld が落とす。開発機では ~/PaddleOCR校正/llama-*/ に前に取ったものが
# 残っていることがあり、そちらで動いてしまうと気づけない。
missing=0
for f in "${DEST}"/llama-server "${DEST}"/*.dylib; do
  for ref in ${(f)"$(otool -L "${f}" | sed -n 's|^	@rpath/\([^ ]*\).*|\1|p')"}; do
    [[ -f "${DEST}/${ref}" ]] || { print -u2 "  足りません: ${ref} (${f:t} が要求)"; missing=1 }
  done
done
(( missing == 0 )) || exit 1

print "[4/4] 実際に起動するか確かめる"
# 参照が解決できていなければここで落ちる（arch 違いもここで出る）。
if ! version=$("${DEST}/llama-server" --version 2>&1); then
  print -u2 "同梱した llama-server が起動しません: ${version}"
  exit 1
fi
print "  ${${(f)version}[1]}"

print
print "取得しました: ${DEST}  ($(du -sh "${DEST}" | cut -f1))"
print "  実行ファイル 1 / dylib ${libs} / そのほか ${others}"
print
print "モデル (.gguf) は同梱しません。アプリが初回に取得します。"
