# 配布用の Windows 版を作る。scripts/build.zsh の Windows 側。
#
# 使い方: pwsh -File scripts/build.ps1
#
# **Windows 上でしか動かない。** Flet はクロスビルドできないので、macOS から
# Windows 版を作ることはできない。
#
# 前提（入っていなければ下で止まって、何が足りないか言う）:
#   - Python 3.12 と uv           https://docs.astral.sh/uv/
#   - Visual Studio Build Tools の「C++ によるデスクトップ開発」
#     （Flutter の Windows 版がこれを使う。Flutter SDK 自体は flet build が入れる）
#
# 出るもの: build\windows\ 一式（そのまま動く）。
# 署名はしない。Microsoft ストアに出すと Microsoft が署名し直すため
# （docs/release.md の「決めたこと」）。手元で試すぶんには、
# 初回に SmartScreen の警告が出るので「詳細情報」→「実行」で進む。

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Set-Location (Join-Path $PSScriptRoot "..")

$Product  = "Local OCR"
$BundleId = "com.nakamura.localocr"

# 前提の確認。無いまま flet build に入ると、数分待ってから分かりにくい形で落ちる。
foreach ($tool in @("uv")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "$tool が見つかりません。https://docs.astral.sh/uv/ を入れてください"
    }
}

# ------------------------------------------------------------------ 同梱物
# llama.cpp を先に取る。取り忘れたまま作ると、出来たものが動かない。
if (-not (Test-Path "binaries\windows\llama-server.exe")) {
    Write-Host "[0/4] llama.cpp を取得"
    & pwsh -File scripts/fetch-binaries.ps1
    if ($LASTEXITCODE -ne 0) { throw "scripts/fetch-binaries.ps1 が失敗しました" }
}

# ------------------------------------------------------------------ ビルド
#
# 除外と cleanup の中身は build.zsh と同じ理由。**両方を直すこと。**
# `**/*.dSYM` と `**/PyObjCTest` は macOS 側の当たり（pyobjc が持ち込む）への
# 対処で、Windows には pyobjc が入らないので効かないが、残しておいて害は無い。
$Excludes = @(
    ".venv", "binaries", "build", "tests", "scripts",
    "docs", "packaging", ".flet",
    ".git", ".github", ".pytest_cache", ".ruff_cache"
)
$CleanupPackageFiles = @("**/*.dSYM", "**/PyObjCTest")

Write-Host "[1/4] flet build windows"
# 引数は 1 本の配列にまとめてから渡す。**行継続のバックティックを使わない。**
# 途中に空白が紛れただけで、以降の行が別のコマンドとして実行される。
$BuildArgs = @("run", "flet", "build", "windows", ".", "--yes", "--no-rich-output")
$BuildArgs += "--exclude"
$BuildArgs += $Excludes
$BuildArgs += "--cleanup-package-files"
$BuildArgs += $CleanupPackageFiles
$BuildArgs += @("--product", $Product, "--bundle-id", $BundleId, "--org", "com.nakamura")
# macOS 側の --info-plist は渡さない。Windows には効かず、初回の実行で
# 「そんな引数は無い」と落ちる可能性のほうが高い（この .ps1 はまだ 1 度も
# 走らせていないので、余計なものは足さない）。

& uv @BuildArgs
if ($LASTEXITCODE -ne 0) { throw "flet build windows が失敗しました" }

$BuildDir = "build\windows"
if (-not (Test-Path $BuildDir)) { throw "$BuildDir が出来ていません" }

# ------------------------------------------------------------------ 同梱
#
# **llama.cpp は Python 側ではなく、exe の隣の bin\ に置く。**
# アプリの探し先は src/local_ocr/core/bundled.py（Windows は exe と同じ階層の bin）。
# Python 側に置くと、パッケージの中に入って探せない。
Write-Host "[2/4] llama.cpp を同梱"
$Exe = Get-ChildItem -Path $BuildDir -Filter "*.exe" -File | Select-Object -First 1
if (-not $Exe) { throw "$BuildDir に exe が見つかりません" }
$BinDir = Join-Path $Exe.Directory.FullName "bin"
if (Test-Path $BinDir) { Remove-Item -Recurse -Force $BinDir }
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
Copy-Item "binaries\windows\*" -Destination $BinDir -Recurse -Force
$n = (Get-ChildItem -File -Path $BinDir).Count
Write-Host "  $BinDir（$n 件）"

# ライセンス表示。6 つの依存はライセンス全文を wheel のどこにも持っておらず、
# その文面は NOTICE にしかない。同梱した llama.cpp（MIT）と
# LLVM OpenMP（libomp.dll）、NDL の 2 つ（CC BY 4.0）も同じ。
foreach ($doc in @("LICENSE", "NOTICE")) {
    if (-not (Test-Path $doc)) { throw "$doc がありません。配布物に必要です" }
    Copy-Item $doc -Destination (Join-Path $Exe.Directory.FullName $doc) -Force
}
Write-Host "  LICENSE / NOTICE を入れました"

# ------------------------------------------------------------------ 点検
Write-Host "[3/4] 出来たものを点検"

# .venv が紛れ込んでいないか（除外を書き忘れると静かに数百 MB 増える）。
if (Get-ChildItem -Recurse -Directory -Path $BuildDir -Filter ".venv" -ErrorAction SilentlyContinue) {
    throw "配布物に .venv が入っています。--exclude を確認してください"
}
Write-Host "  .venv: 入っていない"

# **src\local_ocr が入っていること。** 入っていても sys.path には載らないので、
# main.py の冒頭で src\ を通している（2026-09-21 に macOS 版で
# ModuleNotFoundError: No module named 'local_ocr' を踏んだ）。
$src = Get-ChildItem -Recurse -Directory -Path $BuildDir -Filter "local_ocr" -ErrorAction SilentlyContinue |
       Select-Object -First 1
if (-not $src) { throw "配布物に local_ocr が入っていません" }
Write-Host "  local_ocr: 入っている"

# 依存が同梱しているライセンス全文が残っているか。
$licences = (Get-ChildItem -Recurse -File -Path $BuildDir -Include "LICENSE*", "LICENCE*", "COPYING*", "NOTICE*" -ErrorAction SilentlyContinue).Count
Write-Host "  同梱された依存のライセンス全文: $licences 件"
if ($licences -eq 0) { throw "1 件も残っていません。cleanup の対象が広がっていませんか" }

Write-Host "[4/4] 出来ました"
$size = (Get-ChildItem -Recurse -File -Path $BuildDir | Measure-Object -Property Length -Sum).Sum
Write-Host ("  {0}  ({1:N0} MB)" -f $BuildDir, ($size / 1MB))
Write-Host ""
Write-Host "  試すには: .\$($Exe.FullName.Substring((Get-Location).Path.Length + 1))"
Write-Host "  **起動して画面が出るところまで必ず確かめること。**"
Write-Host "  署名と梱包が通っても、中身が動くかは分からない（macOS 版で実際に踏んだ）。"
