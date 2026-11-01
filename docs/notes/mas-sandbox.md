# Mac App Store に出せるか（App Sandbox）の実験ノート

日付の見出しの下に書き足す。前の記述は書き換えない（誤りは新しい日付で「訂正」と書く）。

## 2026-10-30

- **試したこと**: App Sandbox を有効にした署名で、同梱の llama-server を起動して 1 枚読めるか。
  `docs/release.md` で「App Store はサンドボックスの中で常駐サーバを立てることになり、確かめる手間が増える」
  として見送っていた点を、最小の形で確かめた
- **作り方**: 0.1.12 の配布用ビルド（`scripts/build.zsh` の出力）を複製し、Python 側の入口（`app/main.pyc`）だけを
  試験用に差し替えた。入口は画面を出さずに `local_ocr.cli.main()` で 1 枚読み、結果をホーム（＝入れ物）に書いて終わる。
  署名は Apple Development。
  - アプリ本体: `app-sandbox` / `network.client` / `network.server` / `files.user-selected.read-write`
  - `Contents/Resources/bin/llama-server`: `app-sandbox` / `inherit` の 2 つだけ（子プロセスの決まり）
  - それ以外の Mach-O（251 件、dylib と framework）は entitlement なしで、深い順に署名
  - `codesign --verify --strict --deep` は通った
- **測り方**: `open -W -n` で起動（Finder と同じ経路。端末から実行ファイルを直に叩くと `HOME` が入れ物に切り替わらない）。
  1 回目で入れ物ができたあと、PaddleOCR-VL 1.6 の 2 ファイルを入れ物の
  `Library/Application Support/Local OCR/` に `cp -c`（APFS の複製）で置き、2 回目で読んだ。
  画像は音釈の 1 頁（`034-07_25.jpg`）をバンドルの `Resources/` に入れて使った
- **結果**:
  - `HOME` と `Path.home()` が `~/Library/Containers/com.nakamura.localocr/Data` になり、`data_dir()` もその下を指した
  - 入れ物の外（旧置き場の `~/PaddleOCR校正`）は `PermissionError: Operation not permitted`。サンドボックスは効いている
  - `https://huggingface.co/` への HEAD が 200（network.client が効いている）
  - llama-server が `inherit` で起動し、127.0.0.1 で待ち受け、`--engine paddle-vl` で 1 頁を読めた（終了コード 0）。
    「音釋／奢摩他／梵語也此云…」と正しく出た。起動から終了まで約 20 秒。終了後に llama-server は残らない
- **途中で分かった、自明でないこと**:
  - 署名の Mach-O のうち実行ファイルは本体と llama-server の 2 つだけ。Python は本体の中で動くので、
    子に `inherit` を付けるのは llama-server だけでよい
  - サンドボックス版では、旧置き場（`~/PaddleOCR校正`）と非サンドボックス版の `~/Library/Application Support/Local OCR` が
    見えない。Developer ID 版から乗り換えた人は、1.8GB を取り直すことになる
- **確かめていないこと（限界）**:
  - 画面からの操作（ファイルを選ぶ窓、選んだフォルダへの書き出し、IIIF の取得）
  - 1.8GB のモデルの取得を入れ物の中で最後まで通すこと（今回は HEAD だけ）
  - Apple Distribution 署名・App Store 用の provisioning profile・審査

## 2026-10-31

- **試したこと**: 入口を差し替えない、ふだんの 0.1.12 を同じ署名（Apple Development + 上の entitlement）にし、画面から操作した
- **結果**:
  - 読む道具の切り替え、「画像を選ぶ」のファイル選択の窓（サンドボックスではシステムが代わりに出す窓）は動いた
  - デスクトップの画像を選び、PaddleOCR-VL で読めた。85 行・503 文字、12.6 秒（準備 23 秒）
  - llama-server は `/bin/sh` の見張り役（`core/child.py` の、親が落ちたら子も止める仕掛け）を経由して起動している。
    `/bin/sh` は OS の実行ファイルなので、何もしなくても親のサンドボックスを引き継ぎ、問題なく動いた
- **途中で分かった、自明でないこと**:
  - 画面の自動操作（キー送出）は、利用者が同じ Mac を使っている間は危ない。窓を前に出すたびに利用者の入力を奪い、
    逆にこちらのキーが別の窓に届く。Flutter の画面は読み上げ機能が動いていないと部品の一覧を出さないので、
    位置は画面写真から割り出すしかない
  - 書き出しも、利用者が選んだ保存先に書けた（本人が画面で確認）
- **確かめていないこと**: モデルの取得を入れ物の中で最後まで通すこと、Apple Distribution 署名・provisioning profile・審査、
  Developer ID 版から乗り換える人の 1.8GB の取り直し（旧置き場はサンドボックスから見えない）をどう案内するか

## 2026-10-31（その 2）: モデルの取得を入れ物の中で通す

- **試したこと**: 10-30 と同じく入口だけを差し替えた 0.1.12（Apple Development + 同じ entitlement）で、
  入れ物にモデルが無い状態から `core.fetch.download_all(assets.required())` を呼び、続けて `cli.main()` で 1 頁読んだ。
  取得は画面の「取得」ボタンと同じ関数を通る（画面の進捗表示そのものは見ていない）
- **作り方**: 入れ物の `Library/Application Support/Local OCR/` にあった 2 ファイルの SHA-256 を控えてから外へ移し、
  `open -W -n` で起動した。署名の手順は 10-30 の記述どおり（Mach-O 251 件を深い順、llama-server だけ `app-sandbox` + `inherit`）
- **結果**:
  - 取得前の判定は 2 ファイルとも「未取得」。`https://huggingface.co/` から 2 ファイル（935,769,056 + 881,770,560 バイト）を
    30.7 秒で取得した（この回線で約 59MB/s）
  - SHA-256 は控えと一致（本体 `f3ae46ec…`、mmproj `204d757d…`）。`.part` は残らなかった
  - 取ったモデルでそのまま 1 頁読めた。85 行・503 文字、7.2 秒（起動込み 8.6 秒）、終了コード 0。終了後に llama-server は残らない
  - 証明書の検証（HTTPS）もサンドボックスの中で問題なく通った。追加の entitlement は要らない
- **確かめていないこと**: 画面からの取得（進捗バー・途中で止める操作）、遅い回線や途中切断からのやり直し、
  Apple Distribution 署名・provisioning profile・審査、Developer ID 版から乗り換える人への 1.8GB 取り直しの案内

## 2026-10-31（その 3）: Apple Distribution 署名と provisioning profile に要るもの（調べただけ、まだ何も作っていない）

- **測り方**: 手元のキーチェーン（`security find-identity`）、Xcode の profile 置き場、
  App Store Connect API の読み取り（`GET /v1/certificates`・`/v1/bundleIds`・`/v1/profiles`・`/v1/apps`）。
  API キーは公証に使っているもの（`.env` の op 参照）。一覧が引けたので、読み取りの権限はある
- **今あるもの**:
  - 証明書は Apple Development 2 本と Developer ID Application 1 本だけ（チーム `Q6S8JS6GWV`）。
    **Mac の App Store 用の証明書（Apple Distribution と Mac Installer Distribution）は手元にも Apple 側にも無い**。
    KotenOCR（iOS）は Xcode の自動署名で出しているので、配布用の証明書が手元に残っていない
  - Bundle ID `com.nakamura.localocr` は **未登録**。App Store Connect のアプリの記録も無い
  - profile は iOS 用だけ。Mac App Store 用（`MAC_APP_STORE`）は無い
- **要るもの（順番どおり）**:
  1. 証明書 2 本: アプリ本体を署名する Apple Distribution と、`.pkg` を署名する Mac Installer Distribution。
     Xcode の「設定 → アカウント → 証明書を管理」で作ると、秘密鍵がキーチェーンの中だけにできる
     （API でも作れるが、手元で CSR を作ると秘密鍵がファイルとしてディスクに出る）
  2. Bundle ID `com.nakamura.localocr` の登録（macOS）。サンドボックスとネットワークは entitlement だけで足り、
     Bundle ID 側で有効にする機能は無い
  3. Mac App Store 用の profile（その Bundle ID + Apple Distribution）。`Contents/embedded.provisionprofile` に入れる
  4. App Store Connect でアプリの記録を作る（名前・SKU・主言語）。**API ではアプリの記録は作れない**ので画面で
- **署名の手順で、試験版から変わる点**:
  - 本体の entitlement に `com.apple.application-identifier = Q6S8JS6GWV.com.nakamura.localocr` と
    `com.apple.developer.team-identifier = Q6S8JS6GWV` を足す（profile と一致しないとアップロードで弾かれる）
  - Info.plist に `LSApplicationCategoryType` が無い（0.1.12 で確認）。App Store には必須
  - `productbuild --component "Local OCR.app" /Applications --sign "3rd Party Mac Developer Installer: …"` で `.pkg` にし、
    `xcrun altool --upload-package` で上げる（Xcode 27.1 の altool にまだある）。公証は要らない
  - 審査前に TestFlight（Mac）で、ストア署名の版を手元で動かせる
- **費用**: Apple Developer Program は既に払っている（iOS のアプリを出している）。追加は無い
- **確かめていないこと**: 審査の指針 2.5.2（実行可能なコードを後から取ってこない）に、1.8GB のモデル取得が当たらないか
  （モデルはデータで、実行するのは同梱の llama-server なので当たらないと考えるが、審査の判断は未確認）。
  Python と Flutter を同梱したアプリがアップロード時の検査（ITMS の警告）を通るか

## 2026-10-31（その 4）: 配布用の署名を作り、App Store Connect に上げた

- **作ったもの（すべて CLI か画面の自動操作）**:
  - 証明書 2 本を App Store Connect API（`POST /v1/certificates`、種類 `DISTRIBUTION` と `MAC_INSTALLER_DISTRIBUTION`）で作成。
    期限 2027-11-01。CSR と秘密鍵は一時フォルダで作り、キーチェーンへ入れた直後に消した
  - Bundle ID `com.nakamura.localocr`（`MAC_OS`）と profile「Local OCR Mac App Store」（`MAC_APP_STORE`）も API で作成
  - アプリの記録（App ID 6829376468、SKU `localocr-mac`、主言語は日本語）は **API では作れない**
    （`POST /v1/apps` は 403「apps does not allow CREATE」）ので、Chrome で画面を操作して作った
  - 手順は `scripts/sign-mas.zsh`（複製・Info.plist・署名・.pkg）、`scripts/mas-profile.zsh`、`scripts/upload-mas.zsh`、
    `scripts/asc.py`（API の道具）にまとめた
- **結果**: 0.1.12（ビルド番号 202610312125）の .pkg 179MB が `altool --validate-app` を警告なしで通り、アップロードも成功
- **途中で分かった、自明でないこと**:
  - API で入れた秘密鍵は、`security import -T /usr/bin/codesign` を付けても、初回の codesign でキーチェーンの許可を求められる。
    「常に許可」を選ばないと、署名する Mach-O（251 件）ごとに聞かれる
  - 新規アプリの画面のプルダウンは、拡張機能の値の設定やキー操作では反映されないことがあった（Bundle ID）。
    ページの JavaScript で値を入れ、change を送ると反映された
  - インストーラ証明書で署名した .pkg は、`pkgutil --check-signature` で「issued by Apple (Development)」と出る。これで正常
