# 配る — 作業手順の下書き

**2026-09-22、両方のストアで公開が完了しました。**
macOS 版は `.dmg` を GitHub Release（`v0.1.0`）に、Windows 版は Microsoft Store
（Store ID `9N07ZD1ZPKBZ`、審査通過済み。バッジ「In Microsoft Store」を確認済み）
に出ています。ソースも公開済みです。

Windows 側の経緯:
2026-09-21 に手元の Windows 機で 1 本作り、起動して画面が出るところまで確かめた
（`build\windows\`、280MB）。翌 2026-09-22、`packaging/windows/AppxManifest.xml.in`
を作り、Partner Center でアプリ名を予約（Store ID `9N07ZD1ZPKBZ`、Identity は本物の
値に差し替え済み）。GitHub Actions のビルド workflow（`.github/workflows/
windows-build.yml`）で MSIX とスクリーンショット（日英）を CI 上で作れることを確認。
そのあと Partner Center の申請フォーム（Pricing/Properties/Age ratings/Packages/
Store listings）を埋めて提出し、**同日中に審査を通過して公開された。**
GitHub Pages（プライバシーポリシー等）とストア掲載文の下書きは commit / push 済み
（`https://nakamura196.github.io/local-ocr/`）。

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

### 2. macOS を配る — **済（2026-09-21）**

`.app` を作り、Developer ID で署名し、Apple の公証を通して `.dmg` にするところまで、
スクリプト 4 本で通しました。雛形は archival-packager。持ってきたうえで、
このアプリで違うところ（pyobjc、同梱する llama.cpp、Flet 0.86.2 の変化）を直しています。

- [x] **設定は build スクリプトの引数で渡す。** `pyproject.toml` に `[tool.flet]` は
      置きませんでした（archival-packager と同じ形。設定が 2 か所に分かれない）
      - `--product "Local OCR"` / `--bundle-id com.nakamura.localocr` / `--org com.nakamura`
      - **`--product` は `CFBundleDisplayName` しか書き換えない。**
        メニューバーに出るのは `CFBundleName` なので、
        `--info-plist "CFBundleName=Local OCR"` も渡している
      - **バンドルのファイル名は `local-ocr.app` のまま作られる。**
        Finder と dmg に出るのはファイル名なので、build.zsh が
        `Local OCR.app` に改名する
- [x] **`scripts/build.zsh`** — `--exclude` は `.venv` `binaries` `build` `tests`
      `scripts` `.git` `.github` に加えて `docs` `packaging` `.flet`
      `.pytest_cache` `.ruff_cache`
      - **`--cleanup-package-files '**/*.dSYM' '**/PyObjCTest'` を渡している。
        これが無いと macOS のビルドが必ず失敗する**（下の「踏んだ当たり」を参照）
      - `NOTICE` と `LICENSE` はアプリの中に入れた（実際に入れるのは sign.zsh）
      - **`flutter_assets/NOTICES.Z` を確認した。** 120KB で入っている
        （Flutter 側の表示。`.Z` は gzip 圧縮。Flet が自動で入れる）。
        build.zsh が毎回有無を出すので、版が変わって入らなくなれば気づける
- [x] **`scripts/entitlements.plist`** — archival-packager と**同じでよい**と確認した。
      入れているのは `com.apple.security.files.user-selected.read-write` の 1 つだけ
      - **ネットワークの項目は要らない。** `network.client` / `network.server` は
        **App Sandbox の中でだけ意味を持つ** entitlement で、非サンドボックスの
        アプリには効かない。hardened runtime はネットワークを制限しない
        （制限するのはコード注入・ライブラリの読み込み・他プロセスへの介入）。
        127.0.0.1 に llama-server を立てることも、Hugging Face からモデルを
        取ってくることも、これで通る
      - `disable-library-validation` も足していない。同じ Team ID で署名した
        実行ファイルの起動と dylib の読み込みは通る（実際に通った）
- [x] **`scripts/sign.zsh`** — 雛形の落とし穴はそのまま効く。加えて 2 つ足した
      - 同梱物は `Contents/Resources/bin/` に置く（19 件、25MB）
      - 署名対象は `file(1)` の Mach-O 判定で選ぶ。**実測 157 件**
      - 深い階層から署名 → framework をバンドルとして再署名 → 本体を entitlements 付きで再シール
      - バンドル外を指す symlink を署名の前に消す（今回は 0 件だった）
      - **足した: `otool -L` で `@rpath` の参照を全部突き合わせる。**
        開発機には前に取った llama.cpp が `~/PaddleOCR校正/llama-*/` に残っていて、
        そちらで動いてしまうと取り込みの欠けに気づけない
      - **足した: `LICENSE` / `NOTICE` がリポジトリに無ければ止める**
- [x] **`scripts/notarize.zsh`** — `op run --env-file=.env --` で API キーを渡す。
      `.env` は 1Password の `op://` 参照だけを書き、`.gitignore` 済み。
      雛形は `.env.example`（項目名は placeholder のまま。0.5 の判断に合わせた）
- [x] **`scripts/release.zsh`** — `create-dmg` で固め、dmg も署名・公証・staple。
      マウントして `spctl` と同梱 llama-server の起動まで確かめる。
      `--publish` を付けたときだけタグと GitHub Release を作る
- [x] **`tests/test_packaging.py` を足した。** 配布物そのものは CI で作れないので、
      「外した瞬間に壊れるがビルドしないと気づけない」約束をスクリプトの文面として見張る
      （dSYM を落としているか、ライセンス全文を数えているか、署名を実行ビットで
      絞っていないか、公証を確かめる前に dmg を作っていないか、など 22 本）
- [x] **`.dmg` を開いて実際に起動するところまで確かめた（2026-09-21）。**
      **1 回目は起動に失敗した**（上の当たり 4）。**署名と公証が通っても、
      中身が動くかは分からない。必ず開いて起動させる**
- [ ] **別のマシンで開いて確かめる。** 署名・公証が通っても、Gatekeeper が
      symlink で弾くことがある。ビルドした機械では気づけない
- [ ] **GitHub Release に出す**（`./scripts/release.zsh --publish`）。上の確認のあと

**踏んだ当たり（5 つ）**

1. **`.venv` が古くて `uv run flet` が動かなかった。**
   リポジトリを `paddleocr-local` から改名する前に作った `.venv` が残っており、
   `.venv/bin/` の中の起動用スクリプトに当時の絶対パスが焼き込まれていた。
   `rm -rf .venv && uv sync --frozen` で作り直した。**改名したら `.venv` も作り直す。**
   `.venv/bin/python` は symlink なので素の Python は動いてしまい、気づきにくい

2. **Xcode 26 の `strip` が `.dSYM` を処理できず、ビルドが必ず落ちた。**

       strip: fatal error: string table not at the end of the file
              (can't be processed) in file: .../PyObjCTest/category_gp14...so.dSYM
              (for architecture x86_64)

   依存の `pyobjc-core` は、自分の試験用モジュール（`PyObjCTest`、280 個）を wheel に
   同梱しており、それぞれに `.dSYM`（デバッグ情報）が付いている。その x86_64 の側で
   strip が fatal error になり、Xcode は飛ばさないのでビルド全体が失敗する。
   **archival-packager では起きない**（あちらは pyobjc を使わない）。
   対処は `--cleanup-package-files '**/*.dSYM' '**/PyObjCTest'`。
   どちらも実行には要らない（前者は人がクラッシュを読むための情報、後者は pyobjc 自身の試験）
   - 最初は pub-cache の `.dSYM` を消して回ったが、**これは効かない。**
     Flet はビルドごとに `build/site-packages` から作り直すので、消しても戻ってくる。
     原因は共有のキャッシュではなくこちらの依存だった

3. **`(( n++ ))` は値が 0 のとき終了状態 1 を返す。** `set -e` のスクリプトで、
   何も出力せずに即死する。`n=$((n + 1))` に直した。
   **archival-packager の `sign.zsh` にも同じ書き方が残っている**（`(( removed++ ))`）。
   あちらはバンドル外を指す symlink が見つかったときに同じ形で落ちる

4. **`src/` レイアウトのパッケージが、配布物では import できなかった。**
   `.dmg` を開いて起動したところ、これで落ちた。

       ModuleNotFoundError: No module named 'local_ocr'

   **配布物には editable install が無い。** パッケージ後のソースは
   `.../Resources/app/src/local_ocr/` に置かれるが、`sys.path` に載るのは
   `.../Resources/app/` だけなので、`src/` の下は見えない。
   対処は `main.py` の冒頭で `src/` を `sys.path` に入れること。
   **archival-packager の `main.py` は最初からこれをやっている**
   （「パッケージ後は sys.path にソースが載らないため、ここで通す」というコメント付き）。
   持ってくるファイルをスクリプト 4 本だと思い込み、`main.py` を見比べなかったのが漏れの原因

   **なぜ最後まで気づけないのか。** 開発中は `uv sync` の editable install が
   `src/` を通すので、この 3 行が無くても動く。**署名も公証も通る**
   （中身が動くかは見ていない）。`.dmg` を開いた人が最初の発見者になる。

   **同じ形を見張る試験を足した**
   （`tests/test_packaging.py::test_main_puts_the_source_on_the_path_without_help`）。
   **試験の書き方にも当たりがあった**: 「`local_ocr` が import できるか」を見ると、
   手元の editable install の `.pth` が `src/` を `sys.path` に足すので**常に通ってしまう**。
   `python -S`（site-packages の処理を止める）で走らせ、
   **`main.py` だけで `src/` が `sys.path` に載るか**を見る形にしてある

5. **`--cleanup-packages` の理解が逆だった（0.5 の記載を訂正）。**
   Flet 0.86.2 は **既定で有効にする**（`flet_cli` の `build_base.py` で
   `cleanup.packages` の既定が `True`。止めるには pyproject の
   `[tool.flet.cleanup] packages = false` が要る）。
   **そして止めなくてよい。** 消される既定の一覧は serious_python の
   `junkFilesDesktop`（`**.c` `**.h` `**.pyi` `**.a` `__pycache__` など）だけで、
   `*.dist-info/LICENSE` は入っていない。**実測: 依存 28 個に対して
   ライセンス全文 43 件が配布物に残った。** build.zsh が毎回数えて 0 件なら止まる

**Flet 0.86.2 で変わっていたこと**

- **`app.zip` を作らない。** 0.28 系までは Python 側を app.zip に固めていたが、
  いまは `site-packages` がそのまま
  `Contents/Resources/serious_python_darwin_serious_python_darwin.bundle/Contents/Resources/`
  に並ぶ。**「zip の中は署名できない」という制約はここでは消えている**が、
  同梱する実行ファイルを `Contents/Resources/bin/` に置く形は変えていない
  （アプリ側の探し先が `core/bundled.py` に書いてあり、Windows と揃っている）

**実測値（2026-09-21、M4 Max）**

| | |
|---|---|
| `Local OCR.app` | 290MB |
| うち同梱 llama.cpp | 25MB（19 件） |
| 署名した Mach-O | 157 件 |
| 依存のライセンス全文 | 43 件（依存 28 個） |
| `flutter_assets/NOTICES.Z` | 120KB |
| ビルド時間 | 約 3 分（Python の梱包 50 秒 + Xcode 25 秒） |

### 3. Windows を配る

**まず Windows 機で手で作る（2026-09-21 に方針を変えた）。**
当初は「手元に Windows 機が無いので CI でしか作れない」としていたが、
**Windows 機が使えることが分かった**ので、先に手で 1 本作って動かす。
CI を先に書くと、スクリプトの当たりと workflow の当たりが混ざって切り分けにくい。
**そのとおりに `.ps1` が落ちた。** 直した 4 つはこの節の末尾に書いてある。

- [x] **`scripts/build.ps1` を書いた（2026-09-21）。** `build.zsh` の Windows 側。
      `fetch-binaries.ps1` → `flet build windows` → exe の隣の `bin\` に
      llama.cpp を置く → `LICENSE` / `NOTICE` を入れる → 点検
      - **`.venv` が入っていないか / `local_ocr` が入っているか / ライセンス全文が
        残っているか**を毎回見る。macOS 側で踏んだ当たりと同じ形を見張る
      - **バックティックの行継続を使っていない。** 引数は配列にまとめて渡す
      - **Windows 機で走らせて直した（2026-09-21）。** 踏んだ当たりは下の 4 つ
      - 署名はしない。ストアに出せば Microsoft が署名し直す。手元で試すぶんには
        SmartScreen の警告を「詳細情報」→「実行」で越える
- [x] **`scripts/fetch-binaries.ps1` は Windows 機で通した（2026-09-21）。**
      llama.cpp b10776 の win-vulkan-x64 を取得 → `binaries\windows\` に 32 件
      （実行ファイル 1 / DLL 30 / そのほか 1、97MB）→ `--version` で起動確認まで
- [x] **Windows 機で作って、起動して画面が出るところまで確かめた（2026-09-21）。**
      `build\windows\`（280MB）、`local-ocr.exe` が立ち上がり、画面は全部出た。
      点検も通った（`.venv` なし / `local_ocr` あり / ライセンス全文 47 件 /
      `bin\` に 32 件）
      - **NDL古典籍 OCR Lite で 1 枚読ませて、通った（2026-09-21）。** 設定から
        79MB を取得 → 縦書き 3 行の画像を読ませて 3 行 29 文字、0.7 秒（準備 5 秒）。
        行の切り出しも並び順も合っていた。設定画面の機種判定も効いている
        （Apple Vision が「この機械では使えません（macOS 用）」になる）
      - **同梱した llama-server はまだ動かしていない。** NDL の経路は
        onnxruntime で、llama-server を通るのは PaddleOCR-VL だけ。
        `bundled.py` は `sys.executable` の隣の `bin\` を見るので、
        **梱包した形でその解決が効くかは 1.7GB を取って 1 枚読ませるまで分からない**。
        macOS 側は「梱包は通るが中身が動かない」を実際に踏んでいる。**ここが残りの本丸**
      - 梱包（MSIX）はこれから。下の 3 つが残り
- [x] **GitHub Actions のビルド workflow を書いた（2026-09-22）。**
      `.github/workflows/windows-build.yml`。手動起動（`workflow_dispatch`）のみ。
      雛形は archival-packager の `ci.yml`。`build.ps1` が取得・ビルド・同梱・
      点検を一本でやってくれるので、あちらよりだいぶ短い
      - **Actions は SHA で固定した**（可変タグは乗っ取られた瞬間に流れ込む）。
        `cache`/`upload-artifact` の SHA は archival-packager で動作実績のある
        ものをそのまま流用
      - [x] **1 回目は落ちた（2026-09-22）。** `tests/test_packaging.py` の
            実行ビットの検査が Windows で落ちた。`os.stat().st_mode` は
            Windows の git checkout では POSIX の実行ビットを反映しない
            （常に固定値）。macOS 専用スクリプト（`build.zsh` 等）の話なので、
            Windows では `pytest.skip` にした
      - [x] **2 回目で通った（2026-09-22）。** `LocalOCR.msix`（約 107MB）が
            出来て、アーティファクトとしてアップロードされた。**local-ocr で
            初めての MSIX。** ダウンロードして手元では確認済み（署名は無い —
            Store が提出時に署名し直す）
      - [x] **画面写真を撮る手立てを追加（2026-09-22）。**
            `scripts/screenshot-windows.ps1`（雛形は archival-packager）を
            workflow に足した。**まだ「起動直後の何も読んでいない画面」しか
            撮れない。** README の macOS 版のような「画像を読ませて認識済み」
            の画面にするには、サンプル画像を読ませて認識完了まで待つ処理が
            要る（次の課題）
- [x] **`packaging/windows/AppxManifest.xml.in`（2026-09-22）。** `Assets/` は
      既に揃っていた（0. 下ごしらえで作成済み）。archival-packager を雛形に、
      対応言語を `ja-JP`/`en-US` の両方、`runFullTrust` は同梱の llama-server
      起動用として書いた
      - [x] **アプリ名の予約（2026-09-22）。** Partner Center で「Local OCR」を
            予約した（ダッシュボードでの手作業。API からはできない）。
            **Store ID: `9N07ZD1ZPKBZ`**。3 か月以内（〜2026-12-22）に提出しないと
            予約が失効する。`Identity` の `Name`/`Publisher` は本物の値に
            書き換え済み（`SatoruNakamura.LocalOCR` /
            `CN=B36F83DF-04BA-4243-A19A-C4E79E9C7FF0`）
      - `@EXE@`/`@VERSION@` を実際の値に置き換える仕組み（archival-packager の
        `build.ps1` 相当）はまだ書いていない
- [ ] **Microsoft ストアの規約を、申請前に読み直す。**
      llama-server を同梱にすれば大きな問題は無いはずだが、
      「アプリが外からコードを取ってきて動かすこと」の扱いは変わる。
      モデル (.gguf) の取得はデータなので別
- [ ] **CI での動作確認の手立てを決める**
      （archival-packager は `scripts/screenshot-windows.ps1` を CI で使っている）。
      手で作るあいだは要らないが、CI に移したら「署名は通るが起動しない」を
      見つける手立てがこれしか無くなる

**`.ps1` で踏んだ当たり（2026-09-21、Windows 11 + Windows PowerShell 5.1）**

1. **`.ps1` は UTF-8 の BOM を付けて保存する。** BOM が無いと
   `powershell.exe`（5.1）はファイルを ANSI（日本語環境では Shift-JIS）として
   読む。コメントの日本語が化けた先に引用符が現れて、**文法エラーで落ちる**
   （`Unexpected token 'LICENSE'` / `The string is missing the terminator`）。
   中身は正しいのに文法が壊れて見えるので気づきにくい。
   `pwsh`（7）は BOM 無しでも UTF-8 として読むため、7 でしか試さないと見つからない。
   **`.zsh` 側には無い制約。`.ps1` を書き足すときは BOM を確かめる**
2. **`pwsh` を前提にしない。** Windows に最初から入っているのは
   `powershell.exe`（5.1）だけ。`build.ps1` が `fetch-binaries.ps1` を
   `& pwsh -File` で呼んでいて、それでは動かなかった。
   `& (Join-Path $PSScriptRoot "fetch-binaries.ps1")` に変えて、
   いま動いている PowerShell でそのまま呼ぶ
3. **実行ファイルの出力を `Select-Object -First 1` で受けない。**
   パイプを途中で打ち切ると PowerShell が相手を強制終了させ、
   **`$LASTEXITCODE` が起動の成否と無関係な値になる**。
   `llama-server --version` は 0 で終わっているのに
   「同梱した llama-server が起動しません」で止まった。
   全部受け取ってから exit code を見て、そのあとで 1 行目を取る
4. **`Set-StrictMode -Version Latest` のもとで、空になりうる結果に `.Count` を
   直接書かない。** 5.1 では `$null.Count` が
   `The property 'Count' cannot be found on this object` で落ちて、
   意図した `throw`（ライセンス全文が 1 件も残っていない、など）に届かない。
   `@(...)` で包む

**ビルド機に要るもの（`.ps1` の外。2026-09-21 に手元の Windows 11 で踏んだ）**

- **Visual Studio Build Tools の C++ ワークロード。** `winget install
  Microsoft.VisualStudio.2022.BuildTools --override "--add
  Microsoft.VisualStudio.Workload.VCTools --includeRecommended --quiet --wait"`。
  Flutter SDK は `flet build` が自分で入れる
- **Windows の「開発者モード」をオンにする。** Flutter のプラグインビルドが
  symlink を使うため。オフだと `pub get` まで通ってから
  `Building with plugins requires symlink support. Please enable Developer Mode`
  で止まる。設定 → システム → 開発者向け、または
  `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock` の
  `AllowDevelopmentWithoutDevLicense`（DWORD）を 1 にする（管理者権限）。
  **CI に移すときはランナー側も確かめる**（GitHub の windows ランナーは
  既定でオンだが、前提として書いておく）

### 3.5. 公開するページ（GitHub Pages）

**要るのは Windows ストアに出すときだけです。** Microsoft の申請フォームに
「プライバシーポリシーの URL」の欄があり、**ページが実在しないと審査で止まります**
（archival-packager は 0.1.6 のとき、切れた URL で実際に差し戻された。
`archival-packager/docs/_config.yml` に記録がある）。
macOS の `.dmg` を GitHub Releases で配るだけなら要りません。

- [x] **GitHub にリポジトリを作る。** 済んでいた（このメモが古かっただけ）。
      `nakamura196/local-ocr` は既に public
- [x] **`docs/` を GitHub Pages として配信する（2026-09-22）。** `docs/_config.yml`
      を置き、`gh api -X POST repos/nakamura196/local-ocr/pages` で有効化。
      URL は `https://nakamura196.github.io/local-ocr/`
      - **リポジトリ名を変えるとリダイレクトされない。** 掲載情報と審査がこの URL を
        見るので、改名するなら URL の差し替えも同時に行う
      - **まだ push していない。** `docs/` の中身は Pages の設定を有効にしただけでは
        表示されない。下のファイルをコミットして main に push するまで、
        URL は 404 のまま
- [x] **`docs/privacy-policy.md`（2026-09-22）** — 書いた。実際のコードを確認して
      通信先を洗い出した: 認識モデルの取得（`raw.githubusercontent.com/ndl-lab`、
      `huggingface.co/PaddlePaddle`）、IIIF 入力時の取得、同一端末内の連携用
      ローカルブリッジ（既定オフ、`127.0.0.1` のみ、許可元を明示的に指定）。
      テレメトリ・クラッシュレポート・更新確認は無いことをコードで確認済み
- [x] **`docs/index.md`（2026-09-22）** — 書いた。審査通過後、Windows のダウンロード欄も
      Microsoft Store への実際のリンクに差し替え済み（別セッションで対応）
- [ ] **`docs/usage.md`**（マニュアル）— 必須ではない。掲載文から誘導先があると親切。
      まだ書いていない

**archival-packager の真似をしないところが 1 つあります。**
あちらは同じ文面を `docs/privacy-policy.md`（公開ページ）と
`store/privacy-policy.txt`（申請用）の 2 か所に持っていて、中身がほぼ同じです
（130 行と 128 行）。ずれる元なので、こちらは **`docs/` を正本にして、
`store/` 側は URL だけ持つ**（または `docs/` から生成する）形にします。

### 4. 掲載するもの

- [x] **`store/listing-ja.md` / `listing-en.md`（2026-09-22）。** 説明文を書いた。
      **貼り忘れが起きるのでファイルに置いて、申請はスクリプトから行う**
      （0.1.0 で開発者名が抜けた前例）。**初回申請は結局ダッシュボードに手で貼った**
      （`scripts/store_submit.py` は持ってきていない。次回の更新で要るかを判断する）
- [x] プライバシーポリシーは **3.5 の `docs/privacy-policy.md` が正本**。
      両ファイルには URL だけ書いた（archival-packager のように .txt を別に持たない）
- [x] **`store/screenshots/{ja,en}/`（2026-09-22）。** CI の Windows runner で
      撮った（`scripts/screenshot-windows.ps1`、1486×973、要件の 1366×768 以上）。
      settings.json を仕込んで言語を固定したので、runner の既定言語に依存しない。
      **まだ「起動直後の何も読んでいない画面」だけ。** README の macOS 版
      （画像を読ませて認識済み）と同じ形にするのは次の課題
- [ ] `scripts/store_submit.py` — 申請 API。まだ持ってきていない。次回の更新
      （アプリ内容の差し替え）で要るかどうかは、そのときに判断する
      - **`--check` を申請の直前に挟まない**（1 回目が通って 2 回目が 403 になる）
      - **ダッシュボードと API を混ぜない**（作りかけの申請が残っていると API が失敗する）

---

## 完了（2026-09-22）

~~1~~ → ~~0~~ → ~~0.5~~ → ~~公開に切り替える~~ → ~~2 のスクリプト~~ →
~~.dmg を出して使ってもらう~~（`v0.1.0`）→ ~~3（Windows を配る）~~ →
**両ストアで公開完了**。

**やったこと(Windows 側の一連)**: Partner Center でアプリ名予約
（Store ID `9N07ZD1ZPKBZ`）→ `AppxManifest.xml.in` の Identity を本物の値に
差し替え → GitHub Actions（`.github/workflows/windows-build.yml`）で MSIX と
スクリーンショット（日英）を CI 上で作成 → Partner Center の申請フォーム
（Pricing/Properties/Age ratings/Packages/Store listings）を埋めて提出 →
**同日中に審査通過、公開。**

**残っている小さな宿題（急がない）**:
- README の macOS 版のような「画像を読ませて認識済み」の画面に、Windows の
  スクリーンショットも近づける（今のは「起動直後の何も読んでいない画面」）
- `scripts/store_submit.py`（次回更新時の判断）
- `docs/usage.md`（マニュアル、必須ではない）
