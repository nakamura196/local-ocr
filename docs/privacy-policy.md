---
title: "プライバシーポリシー / Privacy Policy"
---

**Local OCR**

最終更新: 2026年9月22日 / Last updated: 22 September 2026

---

## English

### Summary

**This application does not collect any personal information, and does not
transmit anything to the developer.**

Recognition happens entirely on your computer. No image and no recognised
text is sent anywhere by the application itself. The developer has no means
of knowing what images a user processes.

### Information handled

**Images the user selects.** The application reads the image files, clipboard
contents, or folder the user chooses, in order to recognise the characters in
them. **Originals are read only and are never modified.** Recognised text is
exported only to the location the user chooses (plain text or TEI/XML).

### Network access

The application contacts the network in these cases only:

- **Recognition model downloads.** Each engine's model is fetched the first
  time it is used, then cached on disk. NDLOCR Lite and NDL Kotenseki OCR
  Lite are fetched from `raw.githubusercontent.com/ndl-lab`; PaddleOCR-VL is
  fetched from `huggingface.co/PaddlePaddle`. No user file or user input is
  sent with these requests — only the model files are downloaded.
- **IIIF input.** If the user opens a IIIF manifest URL instead of a local
  file, the manifest and the page images are fetched from the server that
  publishes them (a third party the user has chosen by supplying the URL).
  They are then read locally like any other image.
- **Local bridge (off by default).** The settings screen has an option to let
  another tool on the *same computer* (such as a browser-based proofreading
  page) send images to be recognised. When off, nothing is reachable. When
  turned on, a server listens on `127.0.0.1` only — unreachable from other
  computers — and accepts requests only from the origins the user has
  explicitly allow-listed (default: `https://tei-editor.ldas.jp` and its former address
  `https://tei-iiif-editor.vercel.app`).

The application performs no other network activity. There is no telemetry, no
crash reporting, and no update check.

### Storage locations

- Recognition models and (during development only) the bundled `llama.cpp`
  binaries: under `%LOCALAPPDATA%\Local OCR` on Windows,
  `~/Library/Application Support/Local OCR` on macOS
- Exported text: only the location the user chooses
- Settings: the same folder as the models, as `settings.json`

The models take up to about 2 GB. If the drive holding those folders is
short of space, set the environment variable `LOCAL_OCR_DATA_DIR` to a
folder on another drive and restart the application; everything above
moves there. The current location is shown on the application's Settings
screen. Files already downloaded are not moved for you — copy them across,
or let the application fetch them again.

### Uninstallation

Removing the application removes the application itself. The models folder
above (which can be around 2 GB once every engine has been used) is not
removed automatically and can be deleted manually if no longer needed.
Exported text files are the user's own material and are not removed.

### Disclosure to third parties

None. The developer receives no user data, so there is nothing to disclose.

### Bundled third-party software

`llama.cpp`, which runs the PaddleOCR-VL model, is bundled. Its licence and
how to obtain its source are stated in the `NOTICE` file included with the
distribution. It does not access the network itself; the application starts
it locally to run the model already on disk.

### Contact

Satoru Nakamura, The University of Tokyo — nakamura@hi.u-tokyo.ac.jp

---

## 日本語

### 結論

**このアプリは、利用者の個人情報を収集しません。開発者に何も送信しません。**

文字の認識はすべて利用者の端末の中で完結します。アプリ自身が画像や認識結果を
どこかへ送ることはありません。開発者は、利用者がどのような画像を処理したかを
知る手段を持ちません。

### 扱う情報

**利用者が選んだ画像。** アプリは、利用者が指定した画像ファイル・クリップボードの
内容・フォルダを読み取り、そこに写っている文字を認識します。**原本は読み取るだけで、
変更しません。** 認識した文字は、利用者が指定した場所にのみ書き出します
（プレーンテキストまたは TEI/XML）。

### 通信

アプリが外部と通信するのは、次の場合だけです。

- **認識モデルの取得。** 各エンジンのモデルは、初めて使うときに取得され、以後は
  端末に保存されます。NDLOCR Lite と NDL古典籍OCR Lite は
  `raw.githubusercontent.com/ndl-lab` から、PaddleOCR-VL は
  `huggingface.co/PaddlePaddle` から取得します。この通信で送信されるのは
  モデルファイルを求める要求のみで、利用者のファイルや入力内容は送信されません。
- **IIIF の入力。** 手元のファイルの代わりに IIIF マニフェストの URL を開いた場合、
  そのマニフェストとページ画像を、公開元のサーバー（利用者が URL を渡すことで
  選んだ第三者）から取得します。取得後は、ほかの画像と同じように端末内で
  読み取るだけです。
- **同一端末上のほかの道具との連携(既定は無効)。** 設定画面に、
  **同じ端末で動く**ほかの道具(ブラウザ上の校正画面など)から画像を送って
  認識させられる機能があります。無効のときは誰からも接続できません。
  有効にすると、`127.0.0.1`(同じ端末からのみ到達可能。ほかの端末からは
  繋がりません)で待ち受け、利用者があらかじめ許可した接続元
  (既定は `https://tei-editor.ldas.jp` と、以前の URL
  `https://tei-iiif-editor.vercel.app`)からの要求だけを受け付けます。

これ以外に、アプリが自ら通信を行うことはありません。利用状況の送信(テレメトリ)、
クラッシュレポートの送信、更新確認のいずれも行いません。

### 保存先

- 認識モデルと(開発時のみ)同梱の `llama.cpp`: Windows は
  `%LOCALAPPDATA%\Local OCR`、macOS は `~/Library/Application Support/Local OCR` 配下
- 書き出したテキスト: 利用者が指定した場所のみ
- 設定: モデルと同じフォルダの `settings.json`

モデルは最大 2GB ほどになります。上のフォルダがあるドライブの空きが足りない
場合は、環境変数 `LOCAL_OCR_DATA_DIR` に別の場所を設定してアプリを起動し直して
ください。上記がすべてそちらに移ります。いまの場所はアプリの「設定」画面に
表示されています。**取得済みのファイルは自動では移りません。** 手で写すか、
アプリに取り直させてください。

### アンインストール

アプリを削除すると、アプリ本体が削除されます。上記のモデルフォルダ
(すべてのエンジンを使うと 2GB 近くになります)は自動では削除されないため、
不要であれば手動で削除してください。書き出したテキストは利用者自身の資料であるため
削除されません。

### 第三者への提供

ありません。開発者は利用者のデータを取得しないため、提供する対象がありません。

### 同梱している第三者のソフトウェア

PaddleOCR-VL のモデルを動かす `llama.cpp` を同梱しています。ライセンスと入手方法は
配布物に含まれる `NOTICE` に記載しています。`llama.cpp` 自身が通信することはなく、
アプリが端末内で起動して、すでに端末にあるモデルを動かすだけです。

### お問い合わせ

中村 覚(東京大学) nakamura@hi.u-tokyo.ac.jp
