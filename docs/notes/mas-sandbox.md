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
