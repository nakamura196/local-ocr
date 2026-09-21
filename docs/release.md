# 配る — 作業手順の下書き

**2026-09-21 時点で、どちらのストアにも出していません。**
済んだのは「1. llama-server の同梱」「0. 下ごしらえ」と、
「0.5. ソースを公開に切り替える前に」（**公開への切り替えまで含めて全部**）です。
**ソースは 2026-09-21 に公開しました。**
`packaging/windows/` にはアイコンの 5 枚だけが入っています
（`AppxManifest.xml.in` などはまだ）。

雛形は **archival-packager**（https://github.com/nakamura196/archival-packager ）。
**同じ Flet 0.86.2 の構成で、Apple の公証と
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
- 公証用の App Store Connect API キー（`.p8`）。**手元にも CI にも平文で置かず、
  1Password から `op run` で `APP_STORE_API_KEY` / `APP_STORE_API_ISSUER` として
  渡す。** どの項目かは手元の控えを見る（ここには書かない）
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

### 0.5. ソースを公開に切り替える前に

**2026-09-21、`nakamura196/local-ocr` を非公開で作りました。** 中身を見てから
公開に切り替える、という順番です。ここはその切り替えの関所。

**いまの散らかり具合（2026-09-21 に測った）**

Python 6,834 行、試験 114 本、`TODO` / `FIXME` の書き置きなし、`print` の消し忘れなし、
手元の絶対パスの直書きなし。ruff は同日 CI に入れて 0 件。
**公開を止めるほど散らかってはいません。**
**下の「必ず」は 2026-09-21 に 6 項目すべて済ませました。権利の面で公開を
止めるものはありません。** あとは「切り替えるときの操作」だけです。

**必ず（権利と表示。ここだけは出す前に済ませる）**

- [x] **PaddleOCR-VL のモデルの条件を `NOTICE` に書いた（2026-09-21）。**
      **Apache-2.0。追加の条件は無い。** 配っている当人の記載で確かめた。
      - GGUF を配っているのは **PaddlePaddle 自身**（repo の持ち主が元のモデルと同じ）。
        「変換した第三者が別の条件を付けている」形にはなっていない。取得に同意も申請も
        要らない（Hugging Face の API が `gated: false` を返す）
      - **落とし穴: GGUF の repo には `LICENSE` ファイルが無い。** モデルカードの
        バッジが `./LICENSE` を指しているが、その先は Entry not found。
        条件の拠りどころはモデルカード冒頭の `license: apache-2.0` の記載。
        全文は元のモデル（`PaddleOCR-VL-1.6`）の側にあり、素の Apache-2.0
        （末尾が "Copyright (c) 2025 PaddlePaddle Authors"）
      - 1.5 と 1.5-GGUF も同じ Apache-2.0。1.6 はその派生
- [x] **配布物に入る Python の依存の表示を確かめた（2026-09-21）。結論: 問題なし。**
      **コピーレフトは certifi（MPL-2.0）1 つだけで、GPL / LGPL は 1 つも無い。**
      **archival-packager が踏んだ chardet（LGPL-2.1+）と text-unidecode
      （Artistic/GPL）は、どちらも入っていない。**
      - 28 個の一覧と各ライセンスは `NOTICE` の C 節。取り直すのは
        `uv tree --no-dev --frozen`
      - **入るものは `pyproject.toml` の `[project] dependencies` だけで決まる。**
        `flet build` はその行をそのまま pip に渡す（flet-cli の
        `commands/build_base.py` の `package_python_app` で確認）。
        `[dependency-groups] dev`（pytest / flet-cli とその下の chardet）は入らない。
        **`flet[desktop]` を `flet[all]` にした瞬間に崩れる**ので、ここは動かさない
      - **6 つ（flet / flet-desktop / flatbuffers / pyobjc-core /
        pyobjc-framework-CoreML / pyobjc-framework-Vision）は、ライセンス全文を
        wheel のどこにも持っていない。** `METADATA` に名前が書いてあるだけ。
        この分の文面はこちらで持つ必要がある（`NOTICE` の C 節に書いた）
      - 版は `uv.lock` ではなくビルド時に pip が解決する。**大きく上げたときは
        測り直す**
- [x] **NDL の 2 つの表示を最終確認した（2026-09-21）。** 上流 2 repo とも
      CC BY 4.0（repo 直下の `LICENCE`、GitHub API の SPDX も `CC-BY-4.0`）。
      表示・改変の明示・ライセンスへのリンクは `NOTICE` にそろっている
- [x] **`tests/data/` の出どころを `NOTICE` に書いた（2026-09-21）。**
      上流 `ndl-lab/ndlocr-lite` の試し画像 `resource/digidepo_3048008_0025.jpg`
      （表のあるページ）を、上流由来の版面検出にかけて出た座標。CC BY 4.0 の派生物。
      **画像そのものは入れていない**（座標だけ）
- [x] **このファイル自身を読み直した（2026-09-21）。** 直したのは 3 か所。
      - 1Password の項目名は**消した**。公開して得がない（項目名だけでは中身は
        取れないが、書く理由も無い）
      - `~/git/kim/archival-packager` は、公開されている
        https://github.com/nakamura196/archival-packager に差し替えた。
        読む人にとってはこちらのほうが使える
      - `~/git/CLAUDE.md` への参照は、そこに書いてある中身そのものに置き換えた
      - **署名鍵の名前（`Developer ID Application: Satoru Nakamura (Q6S8JS6GWV)`）は
        そのまま残す。** Team ID は秘密ではない。署名された `.dmg` に対して
        誰でも `codesign -dv` で読める
      - `~/PaddleOCR校正` は残す。東洋文庫へ配った版が実際に使っている場所で、
        `core/paths.py` にも書いてある
- [x] `docs/design.md` の `toyo_urenja_tei/work/paddle/`（手元の道）を直した
      （2026-09-21）。CER の数字は残し、**どう測ったか**（人手の翻刻 352 行を正解に
      2 通りの渡し方で突き合わせた）に書き換えた。正解のデータは別の作業のもので
      このリポジトリには入っていない、と明記してある

**やった方がよい（読みやすさ。公開を止めはしない）**

- [ ] **`ui/work.py` が 1,133 行。** `WorkView` 1 クラスにメソッド 48。
      1 つ 1 つは短く名前も付いているので読めるが、書き出し・実行・描画の 3 つに
      割ると見通しがよくなる。**急がない。触るなら試験を足してから**
- [ ] 型の検査（mypy / pyright）は入れていない。註釈は全体に付いているので、
      入れるなら CI に 1 行足すだけ。既存の当たりがどれだけ出るかは未確認
- [ ] コメントと `docs/` は日本語、README とコミットは英語、という今の形でよいか決める
      （tei-scanner・archival-packager と同じ形ではある）

**切り替えるときの操作 — 済（2026-09-21）**

- [x] **visibility を public にした。** https://github.com/nakamura196/local-ocr
      - 切り替える前に `gitleaks detect` を履歴全体（24 コミット）にかけて 0 件。
        手元の絶対パス・メールアドレスの直書きも無し
- [x] **Secret scanning と Push protection を ON。** 公開にすれば無料で使える
      - `gh api -X PATCH repos/nakamura196/local-ocr
        -f 'security_and_analysis[secret_scanning][status]=enabled'
        -f 'security_and_analysis[secret_scanning_push_protection][status]=enabled'`
      - **まだ入れていない**もの（どちらも公開 repo では無料）:
        `secret_scanning_non_provider_patterns`（提供元の分からない形のものも拾う）と
        `secret_scanning_validity_checks`（見つけた鍵がまだ生きているか確かめる）
- [x] **画面の写真を README に入れた。** 日英 1 枚ずつ（`docs/images/screenshot-{ja,en}.png`）。
      『竹取物語』のページを NDL古典籍OCR Lite で読んだところ。出どころは `NOTICE` の A 節に追記
      - 撮り方: アプリを起動して画像を 1 枚読ませた状態にし、
        `screencapture -l <窓 id> -o` で窓だけを撮る。窓の id は Quartz の
        `CGWindowListCopyWindowInfo` を、アプリの Flet プロセスの PID で絞って得る。
        そのあと長辺 1600px に縮めて `pngquant` で約 360KB
      - **見つかった小さな当たり: 英語のとき、エンジンの選択肢の文字が切れる**
        （「NDL Koten OCR Lite (kuzushij」で途切れる）。`app.py` の
        `engine_dropdown` の `width=240` が日本語の長さに合わせてある。急がない

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
      - **`--cleanup-packages` を付けないこと。** 付けると依存に同梱されている
        ライセンス全文が消える（既定では付かない。0.5 で確かめた）
      - **`NOTICE` と `LICENSE` をアプリの中に入れる。** 依存のうち 6 つは
        自分ではライセンス全文を持っておらず、その分の文面は `NOTICE` にしかない
      - **`flutter_assets/NOTICES` の現物をここで確認する。** Flutter 側
        （BSD-3-Clause ほか）の表示が入っているはず。まだ見ていない
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
      - **Actions は SHA で固定する**（可変タグは乗っ取られた瞬間に流れ込む）
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

~~1~~（済）→ ~~0~~（済）→ ~~0.5 の「必ず」~~（済）→ ~~公開に切り替える~~（済）→ 2 →
（.dmg を出して使ってもらう）→ 3 → 3.5 → 4。

**次は 2.（macOS を配る）です。** 公開への切り替えは 2026-09-21 に済みました。

3.5（公開ページ）は Windows ストアに出すときだけ要ります。
