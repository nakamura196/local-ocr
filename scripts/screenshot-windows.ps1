# Store の掲載に使うスクリーンショットを、アプリを起動して撮る。
#
# 手元に Windows 機が無いので、CI の Windows マシンの上で撮る。
# 雛形は archival-packager の scripts/screenshot-windows.ps1（2026-09-08 に
# 実際に撮れることを確認済み）。
#
# **画面全体ではなくアプリの窓だけを切り出す。** 全体を撮ると、後ろの端末画面と
# 「Test Mode / Windows Server 2025」の透かしが写り込み、掲載には使えない。
#
# 使い方: pwsh -File scripts/screenshot-windows.ps1 -Lang ja|en [-OutDir dir]
# 前提: build\windows にビルド済みの .exe があること。ネットにつながること
# （見本の版面と、モデルの初回取得）。
#
# 撮るもの（1 言語あたり 5 枚）:
#   01-read     1 つで読み終えた版面（PaddleOCR-VL）
#   02-compare  くらべる画面。食い違いに色が付いている
#   03-iiif     IIIF マニフェストから開いた束（95 ページの 2 ページ目を読んだところ）
#   04-tei      保存の品書きを開いたところ（TEI/XML）
#   05-landing  起動直後
#
# 画面を操作する代わりに、アプリ自身に「見本を開いて読み終えた状態」まで
# 進めさせる（src/local_ocr/ui/scene.py。環境変数 LOCAL_OCR_SCENE のときだけ動く）。
# 読んだ結果は CI の上で実際に読ませたもの。作り物は出さない。
#
# -Lang は起動前に settings.json（ui/i18n.py が読む。無指定なら OS の
# 言語に従う）に書いておく。Store は宣言した言語（ja-JP/en-US）ごとに
# 1 枚以上のスクリーンショットを要求するので、両方を撮る必要がある
# （archival-packager が実際に "NoScreenshotsOfAnyType" で弾かれた）。

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("ja", "en")]
    [string]$Lang,
    [string]$OutDir = "screenshots\$Lang"
)

$ErrorActionPreference = "Stop"

# 見本。酉蓮社所蔵『阿毘達磨大毘婆沙論』（東洋文庫の IIIF で公開中）。
# docs/guide-*.md の手順と動画で使っているのと同じ資料。
$Manifest = "https://u-renja.toyobunko-lab.jp/api/iiif/2/117-10/manifest"
$PageUrl  = "https://img.toyobunko-lab.jp/iiif/kaken/21H04345/u-renja/117_10/117_10_0002.tif/full/1600,/0/default.jpg"

# core/paths.py の data_dir() と同じ場所（core/prefs.py が読み書きする）。
$settingsDir = Join-Path $env:LOCALAPPDATA "Local OCR"
New-Item -ItemType Directory -Force -Path $settingsDir | Out-Null
$settingsPath = Join-Path $settingsDir "settings.json"

function Set-Pref([string]$Key, $Value) {
    $settings = if (Test-Path $settingsPath) {
        Get-Content $settingsPath -Raw | ConvertFrom-Json -AsHashtable
    } else { @{} }
    $settings[$Key] = $Value
    ($settings | ConvertTo-Json -Depth 10) | Set-Content -Path $settingsPath -Encoding UTF8
}

Set-Pref "lang" $Lang
# 「前回の続き」を出さない（場面の撮影で、前の場面の結果が残る）。
Set-Pref "last" $null
Write-Host "言語を $Lang に固定: $settingsPath"

Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
  [StructLayout(LayoutKind.Sequential)]
  public struct RECT { public int Left, Top, Right, Bottom; }
  [DllImport("user32.dll")]
  public static extern bool MoveWindow(IntPtr h, int x, int y, int w, int t, bool repaint);
  [DllImport("user32.dll")]
  public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")]
  public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")]
  public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);
  [DllImport("dwmapi.dll")]
  public static extern int DwmGetWindowAttribute(IntPtr h, int attr, out RECT r, int size);
}
"@

# Store は 1366x768 以上を求める。画面も窓もそれ以上にする。
try {
    Set-DisplayResolution -Width 1920 -Height 1080 -Force -ErrorAction Stop
    Write-Host "画面を 1920x1080 にした"
} catch {
    Write-Host "解像度を変更できなかった: $($_.Exception.Message)"
}

$exe = @(Get-ChildItem -Path build\windows -Filter "*.exe" -File)[0].FullName
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# 見本の版面を手元に置く。ファイル名がそのまま画面の題になる。
$sampleDir = Join-Path $PWD "screenshot-sample"
New-Item -ItemType Directory -Force -Path $sampleDir | Out-Null
$sample = Join-Path $sampleDir "117-10_0002.jpg"
if (-not (Test-Path $sample)) { Invoke-WebRequest -UseBasicParsing -OutFile $sample $PageUrl }

function Start-App([hashtable]$Scene) {
    # 場面の指定は環境変数で渡す。子プロセス（アプリ）が受け継ぐ。
    foreach ($k in @("LOCAL_OCR_SCENE", "LOCAL_OCR_SCENE_SOURCE", "LOCAL_OCR_SCENE_ENGINES",
                     "LOCAL_OCR_SCENE_PAGE", "LOCAL_OCR_SCENE_DONE")) {
        Remove-Item "Env:$k" -ErrorAction SilentlyContinue
    }
    foreach ($k in $Scene.Keys) { Set-Item "Env:$k" $Scene[$k] }

    Write-Host "起動: $exe"
    # 出力を拾っておく。**窓が出ただけでは起動確認にならない。**
    # 画面の組み立てで例外が出ても、Flet は自前のエラー画面をその窓に描くので、
    # 窓は出るし、プロセスも生きたままになる。
    $script:outLog = Join-Path $PWD "launch-stdout.log"
    $script:errLog = Join-Path $PWD "launch-stderr.log"
    $proc = Start-Process -FilePath $exe -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog

    # Flet は初回起動で Python を展開するので時間がかかる。窓が出るまで待つ。
    # 待たずに撮ると真っ黒な画像になる。
    $handle = [IntPtr]::Zero
    for ($i = 1; $i -le 60; $i++) {
        Start-Sleep -Seconds 2
        $proc.Refresh()
        if ($proc.MainWindowHandle -ne [IntPtr]::Zero) {
            $handle = $proc.MainWindowHandle
            Write-Host "窓が出るまで $($i * 2) 秒"
            break
        }
    }
    if ($handle -eq [IntPtr]::Zero) {
        throw "アプリの窓が出ませんでした。パッケージは作れているが起動していない"
    }

    # 起動直後に落ちていないか。窓が出たあとすぐ死ぬ場合がある。
    Start-Sleep -Seconds 5
    $proc.Refresh()
    if ($proc.HasExited) {
        throw "起動直後にアプリが終了しました（終了コード $($proc.ExitCode)）"
    }
    Assert-NoError

    # 窓の取っ手（ハンドル）は数秒で取れるが、Flet はそのあとで
    # 自分の既定の大きさ（app.py の page.window.width/height = 1180x780）を当てる。
    # すぐ広げても上書きされるので、落ち着くまで待ってから広げる。
    Start-Sleep -Seconds 15

    # Store は 1366x768 以上を求める。既定の 1180x780 では幅が足りないので広げる。
    # 広げてから、実際に効いたか確かめる。
    for ($try = 1; $try -le 3; $try++) {
        [void][Win32]::MoveWindow($handle, 0, 0, 1500, 980, $true)
        [void][Win32]::SetForegroundWindow($handle)
        Start-Sleep -Seconds 5
        $probe = New-Object Win32+RECT
        [void][Win32]::DwmGetWindowAttribute($handle, 9, [ref]$probe, 16)
        if (($probe.Right - $probe.Left) -ge 1366) { break }
        Write-Host "広げ直す（$try 回目。今 $($probe.Right - $probe.Left) px）"
    }
    return @{ Proc = $proc; Handle = $handle }
}

# 窓の中身がエラー画面になっていないか。プロセスは生きているので、
# 出力を読むしか見分ける手がない。
function Assert-NoError {
    foreach ($log in @($outLog, $errLog)) {
        if (-not (Test-Path $log)) { continue }
        $text = Get-Content $log -Raw
        if ([string]::IsNullOrEmpty($text)) { continue }
        if ($text -match "The application encountered an error") {
            Write-Host $text
            throw "起動はしたが、画面の組み立てで例外が出ています（上の出力を参照）"
        }
    }
}

# 場面が読み終わるのを待つ。アプリが LOCAL_OCR_SCENE_DONE に ok か error を書く。
# PaddleOCR-VL は初回に 1.8GB を取りに行き、CI の CPU で読むので長めに待つ。
function Wait-Scene([string]$Done, [int]$Minutes = 30) {
    $limit = $Minutes * 6
    for ($i = 1; $i -le $limit; $i++) {
        Start-Sleep -Seconds 10
        if (Test-Path $Done) {
            $status = (Get-Content $Done -Raw).Trim()
            Write-Host "場面の結果: $status（$($i * 10) 秒）"
            if ($status -ne "ok") {
                foreach ($log in @($outLog, $errLog)) { if (Test-Path $log) { Get-Content $log -Raw | Write-Host } }
                throw "場面を作れませんでした: $status"
            }
            return
        }
    }
    throw "場面が $Minutes 分で終わりませんでした"
}

function Save-Window([IntPtr]$Handle, [string]$Out) {
    [void][Win32]::SetForegroundWindow($Handle)
    Start-Sleep -Seconds 1
    # DWMWA_EXTENDED_FRAME_BOUNDS(9) を使う。GetWindowRect だと影の分の余白が入る。
    $r = New-Object Win32+RECT
    [void][Win32]::DwmGetWindowAttribute($Handle, 9, [ref]$r, 16)
    $w = $r.Right - $r.Left
    $h = $r.Bottom - $r.Top
    Write-Host "窓の大きさ: ${w}x${h}"
    if ($w -lt 1366) { Write-Host "::warning::幅が 1366 未満。Store の要件を満たさない" }

    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.Left, $r.Top, 0, 0, (New-Object System.Drawing.Size $w, $h))
    $bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)

    # 単色に近ければ描画されていない。撮れたかどうかの判定に使う。
    $colors = @{}
    for ($x = 0; $x -lt $bmp.Width; $x += 37) {
        for ($y = 0; $y -lt $bmp.Height; $y += 37) { $colors[$bmp.GetPixel($x, $y).ToArgb()] = $true }
    }
    $g.Dispose()
    $bmp.Dispose()
    Write-Host "書き出し: $Out（色の種類: $($colors.Count)）"
    if ($colors.Count -le 2) { Write-Host "::warning::画面が描画されていない可能性が高い" }
    return $r
}

# 窓の右上からの位置をクリックする。Flet（Flutter）の品書きは、
# アプリの外から開く手段がこれしかない。
function Click-At([Win32+RECT]$R, [int]$FromRight, [int]$FromTop) {
    $x = $R.Right - $FromRight
    $y = $R.Top + $FromTop
    [void][Win32]::SetCursorPos($x, $y)
    Start-Sleep -Milliseconds 300
    [Win32]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)  # 左ボタンを押す
    Start-Sleep -Milliseconds 100
    [Win32]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)  # 離す
    # 押したあとは、カーソルを品書きにかからない所へ逃がす
    Start-Sleep -Milliseconds 300
    [void][Win32]::SetCursorPos($R.Left + 300, $R.Bottom - 20)
}

function Stop-App($App) {
    if (-not $App.Proc.HasExited) { Stop-Process -Id $App.Proc.Id -Force }
    # 同梱の llama-server も止まるのを待つ（次の起動で同じポートを使う）。
    Start-Sleep -Seconds 3
    Get-Process -Name "llama-server" -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2
}

function Run-Scene([hashtable]$Scene) {
    $done = Join-Path $PWD "scene-done.txt"
    Remove-Item $done -ErrorAction SilentlyContinue
    $Scene["LOCAL_OCR_SCENE_DONE"] = $done
    $app = Start-App $Scene
    try {
        Wait-Scene $done
        Assert-NoError
    } catch {
        Stop-App $app
        throw
    }
    return $app
}

# --- 01 と 04: 1 つで読む → 保存の品書き ----------------------------------
$app = Run-Scene @{
    LOCAL_OCR_SCENE = "read"; LOCAL_OCR_SCENE_SOURCE = $sample
    LOCAL_OCR_SCENE_ENGINES = "paddle-vl"
}
$r = Save-Window $app.Handle (Join-Path $OutDir "01-read.png")
# 「保存」は上の帯の右端（設定の歯車）の 1 つ左。窓の右端から約 120px、
# 上端から約 61px（タイトルバー込み）。窓の幅を 1500 に固定しているので位置は動かない。
Click-At $r 120 61
Start-Sleep -Seconds 2
[void](Save-Window $app.Handle (Join-Path $OutDir "04-tei.png"))
Stop-App $app

# --- 02: くらべる（食い違いに色が付く） ------------------------------------
$app = Run-Scene @{
    LOCAL_OCR_SCENE = "compare"; LOCAL_OCR_SCENE_SOURCE = $sample
    LOCAL_OCR_SCENE_ENGINES = "ndl-koten-lite,paddle-vl"
}
[void](Save-Window $app.Handle (Join-Path $OutDir "02-compare.png"))
Stop-App $app

# --- 03: IIIF マニフェストから開いた束 -------------------------------------
$app = Run-Scene @{
    LOCAL_OCR_SCENE = "read"; LOCAL_OCR_SCENE_SOURCE = $Manifest
    LOCAL_OCR_SCENE_ENGINES = "ndl-koten-lite"; LOCAL_OCR_SCENE_PAGE = "2"
}
[void](Save-Window $app.Handle (Join-Path $OutDir "03-iiif.png"))
Stop-App $app

# --- 05: 起動直後 -----------------------------------------------------------
# 場面の指定なしで起動する。前の場面で選んだ道具が残らないよう、既定に戻す。
Set-Pref "engine" "ndl-koten-lite"
Set-Pref "last" $null
$app = Start-App @{}
[void](Save-Window $app.Handle (Join-Path $OutDir "05-landing.png"))
Stop-App $app
