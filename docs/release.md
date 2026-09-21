# 配る — 作業手順の下書き

**2026-09-21 時点で、どちらのストアにも出していません。** 配るための道具も
まだ 1 つもありません（`scripts/` と `packaging/windows/` は空）。
後日ここから進めるための下書きです。

雛形は `~/git/kim/archival-packager`。**同じ Flet 0.86.2 の構成で、Apple の公証と
Microsoft ストアの審査を両方通した実績があります。** 書き写せば済むところが多いので、
下の TODO では「どのファイルを持ってくるか」を毎回書いています。

## 決めたこと（2026-09-21）

| | 決めたこと | 理由 |
|---|---|---|
| macOS | **Mac App Store には出さない。** Developer ID で署名 → 公証 → `.dmg` → GitHub Releases | 審査が無く、鍵も公証の手立ても手元にそろっている。App Store はサンドボックスの中で常駐サーバを立てることになり、確かめる手間が数週間ぶん増える |
| Windows | GitHub Actions でビルド → MSIX → **Microsoft ストア** | 手元に Windows 機が無い。ストアに出すと Microsoft が署名し直すので、Windows 用の証明書を買わずに済む |
| llama-server | **アプリに同梱する。** 初回に取りに行くのをやめる | いまは初回起動時に GitHub から実行ファイルを取ってきて動かしている。これはストアの審査（審査が見たものと、実際に動くものが別になる）と正面からぶつかる。archival-packager も同じ理由で、外部の実行ファイルはビルド時に取り込んで一緒に署名している |
| モデル (.gguf) | **今までどおり初回取得のまま** | 1.8GB あり、中身はデータであって実行ファイルではない。同梱する必要がない |

## 手元にあるもの（確認済み）

- 署名鍵 `Developer ID Application: Satoru Nakamura (Q6S8JS6GWV)`
- 公証用の App Store Connect API キー `~/.private_keys/AuthKey_<KEY_ID>.p8`
  （1Password の `app-store-connect-notarization`。`APP_STORE_API_KEY` /
  `APP_STORE_API_ISSUER` を `op run` で渡す）
- Microsoft Partner Center のアカウントと申請 API の設定
  （archival-packager の `store/API設定手順.md`）

---

## TODO

### 0. 下ごしらえ

- [ ] **アイコンを作る。** 配布物・Dock・ストア掲載のすべてで要る。
      元になる 1 枚（1024×1024 程度）を用意し、`build_icons.py` に各サイズを吐かせる
      - 持ってくる: `archival-packager/scripts/build_icons.py`
      - Windows 側は `packaging/windows/Assets/` に 5 枚
        （`Square44x44Logo` / `Square150x150Logo` / `Square310x310Logo` /
        `Wide310x150Logo` / `StoreLogo`）
- [ ] **`LICENSE` を置く。** いま `local-ocr` に LICENSE がない。
      署名の手順で `LICENSE` と `NOTICE` をアプリの中に入れるので、無いと止まる
- [ ] **`NOTICE` に llama.cpp の同梱を書き足す。** いまは「動かすのに使う」と
      書いてあるだけ。同梱すると再配布になるので、MIT の全文を入れる
- [ ] **データの置き場所の名前を見直すか決める**（`core/paths.py` の
      `APP_DIR_NAME = "PaddleOCR Local"`）。アプリ名は Local OCR になっている。
      変えると、既に 1.8GB を取得済みの人が取り直しになる。**変えるなら移行処理も要る**

### 1. llama-server の同梱（ここが一番大きい）

- [ ] **ビルド時に取ってくるスクリプトを書く。** 版を固定する
      - 持ってくる: `archival-packager/scripts/fetch-binaries.zsh`（macOS）と
        `fetch-binaries.ps1`（Windows / CI から呼ぶ）
      - 置き場所は `binaries/macos/` `binaries/windows/`。**リポジトリには入れない**
      - 版は `src/local_ocr/core/assets.py` の `LLAMA_BUILD` と揃える
- [ ] **`core/assets.py` を直す。** llama-server を「取得するもの」から外す
      - `.gguf` 2 つ（本体と mmproj）は取得したまま残す
- [ ] **同梱先を見に行くようにする。** `core/paths.py` に「同梱した実行ファイルの
      置き場所」を返す関数を足し、`core/runtime.py` がそこを起動する
      - macOS: `<アプリ>/Contents/Resources/bin/llama-server`
      - Windows: exe と同じ並び
      - **開発中（`uv run`）は同梱物が無いので、`binaries/<os>/` を見に行く道も残す**
- [ ] **macOS の Metal シェーダを忘れない。** llama.cpp の macOS ビルドは
      `ggml-metal.metal` / `*.metallib` を横に置く形のことがある。
      取ってきた中身をそのまま入れる（個別に列挙すると取りこぼす）
- [ ] 同梱した状態で通しで動かし、**モデル取得 → 読み取り**までを確認する

### 2. macOS を配る

- [ ] **`[tool.flet]` の設定を `pyproject.toml` に足す**（または build スクリプトの
      引数で渡す）。`--product "Local OCR"` / `--bundle-id com.nakamura.localocr` /
      `--org com.nakamura`
- [ ] **`scripts/build.zsh`** — 持ってくる。`--exclude` に `.venv` `binaries`
      `build` `tests` `scripts` `.git` `.github` を入れる
      （入れないと `.venv` が丸ごとアプリに入る）
- [ ] **`scripts/entitlements.plist`** — 持ってくる。
      **常駐サーバを 127.0.0.1 に立てるので、ネットワーク関係の項目が
      archival-packager と同じでよいか確かめる**
- [ ] **`scripts/sign.zsh`** — 持ってくる。中の落とし穴がそのまま効く
      - 同梱物は app.zip ではなく `Contents/Resources/bin/` に置く
        （zip の中は署名できず、公証で弾かれる）
      - 署名対象は `file(1)` の Mach-O 判定で選ぶ。**実行ビットで絞らない**
        （dylib は実行ビットを持たないことがあり、取りこぼすと公証が Invalid）
      - 深い階層から署名する。framework を先に署名すると封が破れる
      - **バンドルの外を指す symlink を、署名の前に消す**
        （`serious_python_darwin.framework` の中にビルド機の絶対パスが残る）
- [ ] **`scripts/notarize.zsh`** — 持ってくる。`op run` で API キーを渡す
- [ ] **`scripts/release.zsh`** — 持ってくる。`create-dmg` が要る
      （`brew install create-dmg`）。`--publish` でタグ付けと GitHub Release まで
- [ ] **別のマシンで開いて確かめる。** 署名・公証が通っても、Gatekeeper が
      symlink で弾くことがある。ビルドした機械では気づけない

### 3. Windows を配る

- [ ] **GitHub Actions のビルド workflow を書く**（いまは ci / audit /
      dependabot の 3 本だけ）。Windows ランナーで
      `fetch-binaries.ps1` → `flet build windows` → MSIX
      - **Actions は SHA で固定する**（`~/git/CLAUDE.md` の方針）
- [ ] **`packaging/windows/AppxManifest.xml.in`** と `Assets/` を持ってくる
- [ ] **Microsoft ストアの規約を、申請前に読み直す。**
      llama-server を同梱にすれば大きな問題は無いはずだが、
      「アプリが外からコードを取ってきて動かすこと」の扱いは変わる。
      モデル (.gguf) の取得はデータなので別
- [ ] Windows 機が無いので、**動作確認の手立てを決める**
      （archival-packager は `scripts/screenshot-windows.ps1` を CI で使っている）

### 4. 掲載するもの

- [ ] `store/listing-ja.md` / `listing-en.md` — 説明文。**貼り忘れが起きるので
      ファイルに置いて、申請はスクリプトから行う**（0.1.0 で開発者名が抜けた前例）
- [ ] `store/privacy-policy.txt` — 「画像は手元だけで処理し、外に送らない」ことを書く。
      ただし**モデルの初回取得で Hugging Face と GitHub に繋ぐ**ので、そこは正直に書く
- [ ] `store/screenshots/{ja,en}/` — 日英それぞれ
- [ ] `scripts/store_submit.py` — 申請 API。持ってくる
      - **`--check` を申請の直前に挟まない**（1 回目が通って 2 回目が 403 になる）
      - **ダッシュボードと API を混ぜない**（作りかけの申請が残っていると API が失敗する）

---

## 順番の目安

1 →（0 と並行）→ 2 →（.dmg を出して使ってもらう）→ 3 → 4。

**1 を先にやるのが大事です。** llama-server の扱いを決めずに 2 を進めると、
署名と公証をやり直すことになります。
