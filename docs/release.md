# 配る — 作業手順の下書き

**2026-09-21 時点で、どちらのストアにも出していません。**
済んだのは「1. llama-server の同梱」だけです（`scripts/fetch-binaries.zsh` /
`.ps1`）。`packaging/windows/` はまだ空です。

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

- [x] **アイコンを作った（2026-09-21）。** `scripts/build_icons.py` が Pillow だけで
      描いて書き出す。元絵の画像ファイルは持たない（いつ走らせても同じものが出る）
      - 絵柄は藍色の地に縦書きの頁、四隅に朱色の読み取り枠。
        archival-packager（青緑＋箱）と色も形も重ならないようにしてある
      - 出るもの: `assets/icon.png`（1024px、Flet 用）と
        `packaging/windows/Assets/` の 5 枚（`Square44x44Logo` /
        `Square150x150Logo` / `Square310x310Logo` / `Wide310x150Logo` / `StoreLogo`）
      - 32px まで読める（16px では枠が消えて白い頁だけになる）。
        直したら `uv run python scripts/build_icons.py` で全部作り直す
- [x] **`LICENSE` を置いた（2026-09-21）。** MIT。tei-scanner と archival-packager に揃えた
- [x] **`NOTICE` に llama.cpp の同梱を書き足した。** 1. の中で済ませた
- [x] **データの置き場所の名前をアプリ名に揃えた（2026-09-21）。**
      `core/paths.py` の `APP_DIR_NAME` が `"Local OCR"` になった。
      前の名前（`"PaddleOCR Local"`）のフォルダがあれば、`data_dir()` が中身ごと
      名前を変える。1.8GB を取り直させないため。移せなかったときは前の名前のまま使う。
      東洋文庫へ配った起動スクリプト版（`~/PaddleOCR校正`）の扱いは今までどおり優先。
      `tests/test_paths.py` が見張る

### 1. llama-server の同梱 — **済（2026-09-21）**

- [x] **ビルド時に取ってくるスクリプトを書く。** `scripts/fetch-binaries.zsh`（macOS）と
      `scripts/fetch-binaries.ps1`（Windows / CI から呼ぶ）
      - 版は**書かない**。両方とも `src/local_ocr/core/assets.py` の `LLAMA_BUILD` を
        読む（zsh は `sed`、ps1 は `Select-String`）。2 か所に書くと、片方だけ上げた
        ときにずれる。ずれても開発機では前に取ったものが残っていて動いてしまう。
        `tests/test_bundled.py` が、スクリプトに版が直書きされていないか見張る
      - 置き場所は `binaries/macos/` `binaries/windows/`。`.gitignore` 済み
      - どちらも最後に `llama-server --version` を実際に走らせて確かめる
- [x] **`core/assets.py` を直す。** 取得するのは `.gguf` 2 つだけになった
- [x] **同梱先を見に行くようにする。** `core/bundled.py` を足した。
      `core/runtime.py` はそこが返した道を起動する
      - macOS: `<アプリ>/Contents/Resources/bin/`、Windows: exe と同じ並びの `bin/`
      - 開発中は `binaries/<os>/` を見る。無いときは
        「`./scripts/fetch-binaries.zsh` を実行してください」と出す
        （1.8GB 落とし終わってから気づかないよう、**取得より先に**見る）
- [x] **macOS の Metal シェーダ。** **b10776 には外に出ていない**
      （`libggml-metal.dylib` の中）。ただし版によって外に出る形があるので、
      取り込みの規則を「**実行ファイルは llama-server だけ。それ以外はそのまま入れる**」
      にしてある。個別に列挙していない
- [x] 同梱した状態で通しで確認（2026-09-21、M4 Max）。
      `binaries/macos/llama-server` が起動し、取得済みのモデルで
      NDL の試し画像を 1.4 秒で読んだ。起動 1.0 秒
- [x] **`NOTICE` に llama.cpp を書き足した。** 同梱は再配布なので MIT 全文を入れた。
      Windows 版だけ `libomp.dll` が入るので LLVM OpenMP の分も書いた

**取り込みで気をつけたところ（macOS）**

- dylib は実体だけを **install id が示す名前（soname）** で置き、symlink は張らない。
  バンドル内の symlink は Gatekeeper の
  「invalid destination for symbolic link in bundle」を招きやすい。
  `llama-server` の rpath は `@loader_path` なので、同じ階層に soname で並べば解決する
- 除外の型を `llama-*` だけにすると、**傘の `llama` 1 本が漏れる**（実際に漏れた）。
  `llama|llama-*|ggml-*` にしてある
- 取り込んだあと `otool -L` で `@rpath` の参照を全部突き合わせ、欠けがないか見ている。
  開発機には `~/PaddleOCR校正/llama-*/` に前に取ったものが残っていることがあり、
  そちらで動いてしまうと欠けに気づけない

**残っている小さな宿題**

- `.ps1` は**まだ 1 度も走らせていない**（手元に Windows も pwsh も無い）。
  初めて走るのは 3. の CI。落ちるならそこ
- 前の版で `~/PaddleOCR校正/llama-b10776/`（27MB）を取得済みの人は、それが
  そのまま残る。害は無いが消えもしない。消す処理を入れるかは未決

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

### 3.5. 公開するページ（GitHub Pages）

**要るのは Windows ストアに出すときだけです。** Microsoft の申請フォームに
「プライバシーポリシーの URL」の欄があり、**ページが実在しないと審査で止まります**
（archival-packager は 0.1.6 のとき、切れた URL で実際に差し戻された。
`archival-packager/docs/_config.yml` に記録がある）。
macOS の `.dmg` を GitHub Releases で配るだけなら要りません。

- [ ] **GitHub にリポジトリを作る。** いま remote がありません。ここが先
- [ ] **`docs/` を GitHub Pages として配信する。** 置くのは `docs/_config.yml` 1 枚
      （テーマは `jekyll-theme-minimal`）。URL は
      `https://nakamura196.github.io/<repo 名>/privacy-policy.html` の形になる
      - **リポジトリ名を変えるとリダイレクトされない。** 掲載情報と審査がこの URL を
        見るので、改名するなら URL の差し替えも同時に行う
- [ ] **`docs/privacy-policy.md`** — これだけは必須。書くこと:
      「画像は手元だけで処理し、外に送らない」。ただし**モデルの初回取得で
      Hugging Face と GitHub に繋ぐ**ので、そこは正直に書く
- [ ] **`docs/index.md`** — 何をする道具か、どこで手に入るか（ストアと Releases の表）
- [ ] **`docs/usage.md`**（マニュアル）— 必須ではない。掲載文から誘導先があると親切

**archival-packager の真似をしないところが 1 つあります。**
あちらは同じ文面を `docs/privacy-policy.md`（公開ページ）と
`store/privacy-policy.txt`（申請用）の 2 か所に持っていて、中身がほぼ同じです
（130 行と 128 行）。ずれる元なので、こちらは **`docs/` を正本にして、
`store/` 側は URL だけ持つ**（または `docs/` から生成する）形にします。

### 4. 掲載するもの

- [ ] `store/listing-ja.md` / `listing-en.md` — 説明文。**貼り忘れが起きるので
      ファイルに置いて、申請はスクリプトから行う**（0.1.0 で開発者名が抜けた前例）
- [ ] プライバシーポリシーは **3.5 の `docs/privacy-policy.md` が正本**。
      ここには URL だけ書く（archival-packager のように .txt を別に持たない）
- [ ] `store/screenshots/{ja,en}/` — 日英それぞれ
- [ ] `scripts/store_submit.py` — 申請 API。持ってくる
      - **`--check` を申請の直前に挟まない**（1 回目が通って 2 回目が 403 になる）
      - **ダッシュボードと API を混ぜない**（作りかけの申請が残っていると API が失敗する）

---

## 順番の目安

~~1~~（済）→ 0 → 2 →（.dmg を出して使ってもらう）→ 3 → 3.5 → 4。

**次は 0 です。** アイコンと `LICENSE` が無いと 2 の署名の手順が止まります。

3.5（公開ページ）は Windows ストアに出すときだけ要ります。ただし
**GitHub にリポジトリを作るのは 2 より前でも構いません**（`.dmg` を
Releases に置くのにも要るため）。
