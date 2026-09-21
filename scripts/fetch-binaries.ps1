# 同梱する llama.cpp を取得して binaries\windows\ に置く（Windows 用）。
#
# 使い方: pwsh -File scripts/fetch-binaries.ps1
#
# 版は src/local_ocr/core/assets.py の LLAMA_BUILD から読む。**ここに書かない。**
# macOS 側は scripts/fetch-binaries.zsh。同じ版を使う。
#
# 取るのは Vulkan 版。CPU 版だと画像を見る部分が 1 行 93 秒かかる（実測）。
# そのぶん ggml-vulkan.dll だけで 55MB ある。
#
# 同梱する理由と、モデル (.gguf) を同梱しない理由は fetch-binaries.zsh の冒頭に
# 書いてある。

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Set-Location (Join-Path $PSScriptRoot "..")

$assets = "src/local_ocr/core/assets.py"
$m = Select-String -Path $assets -Pattern '^LLAMA_BUILD = "(.*)"$' | Select-Object -First 1
if (-not $m) { throw "$assets から LLAMA_BUILD を読めませんでした" }
$LlamaBuild = $m.Matches[0].Groups[1].Value

$Name = "llama-$LlamaBuild-bin-win-vulkan-x64.zip"
$Url  = "https://github.com/ggml-org/llama.cpp/releases/download/$LlamaBuild/$Name"

$Dest = "binaries\windows"
if (Test-Path $Dest) { Remove-Item -Recurse -Force $Dest }
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
$Work = Join-Path ([System.IO.Path]::GetTempPath()) ("fetch-" + [guid]::NewGuid())
New-Item -ItemType Directory -Force -Path $Work | Out-Null

try {
    Write-Host "[1/3] llama.cpp $LlamaBuild (win-vulkan-x64)"
    $zip = Join-Path $Work "llama.zip"
    Invoke-WebRequest -UseBasicParsing -OutFile $zip $Url
    Expand-Archive -Path $zip -DestinationPath (Join-Path $Work "llama") -Force

    # 配布物によって、中身が 1 階層のフォルダに入っている版と、そのまま並んでいる
    # 版がある。llama-server.exe を探し直して、どちらでも動くようにする。
    $server = Get-ChildItem -Recurse -Path (Join-Path $Work "llama") -Filter "llama-server.exe" |
              Select-Object -First 1
    if (-not $server) { throw "展開しましたが llama-server.exe が見つかりません" }
    $src = $server.Directory.FullName

    # ------------------------------------------------------------ 取り込み
    #
    # **実行ファイルは llama-server.exe だけ。それ以外は全部そのまま入れる。**
    # 個別に列挙すると取りこぼす。とくに ggml-cpu-*.dll は 14 種あり、どれが
    # 使われるかは動かす機械の CPU が決める（ggml が起動時に選ぶ）。1 つでも
    # 欠けると、その CPU の機械でだけ落ちる。手元に Windows 機が無いので、
    # そういう抜け方をされると気づけない。
    # LICENSE-LLVM-OpenMP は libomp.dll の再配布に要るので、これも入る。
    Write-Host "[2/3] 実行ファイルと DLL を取り出す"
    $dlls = 0
    $others = 0
    foreach ($f in Get-ChildItem -File -Path $src) {
        if ($f.Name -eq "llama-server.exe") {
            Copy-Item $f.FullName -Destination (Join-Path $Dest $f.Name) -Force
        } elseif ($f.Extension -eq ".exe") {
            # ほかの実行ファイル（llama-cli / llama-bench / ggml-rpc-server ほか）は入れない。
        } elseif ($f.Extension -eq ".dll") {
            Copy-Item $f.FullName -Destination (Join-Path $Dest $f.Name) -Force
            $dlls++
        } else {
            Copy-Item $f.FullName -Destination (Join-Path $Dest $f.Name) -Force
            $others++
        }
    }
    if (-not (Test-Path (Join-Path $Dest "llama-server.exe"))) {
        throw "llama-server.exe を取り出せませんでした"
    }
    if ($dlls -eq 0) { throw "DLL を 1 つも取り出せませんでした" }

    Write-Host "[3/3] 実際に起動するか確かめる"
    # DLL が足りなければここで落ちる。
    # **$ErrorActionPreference = "Stop" のまま 2>&1 を付けてはいけない。**
    # llama-server は版番号を stderr に書く。Stop のままだと PowerShell が
    # それを NativeCommandError に変えて投げ、正常な起動を失敗として扱う。
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $version = (& (Join-Path $Dest "llama-server.exe") --version 2>&1 | Select-Object -First 1)
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($code -ne 0) { throw "同梱した llama-server が起動しません: $version" }
    Write-Host "  $version"

    $size = (Get-ChildItem -Recurse -File -Path $Dest | Measure-Object -Property Length -Sum).Sum
    Write-Host ""
    Write-Host ("取得しました: {0}  ({1:N0} MB)" -f $Dest, ($size / 1MB))
    Write-Host "  実行ファイル 1 / DLL $dlls / そのほか $others"
    Write-Host ""
    Write-Host "モデル (.gguf) は同梱しません。アプリが初回に取得します。"
}
finally {
    Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue
}
