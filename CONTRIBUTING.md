# 作業する人へ

Local OCR に手を入れるときの、最小の手順です。
**作業はプルリクエストを出すところまで**です。新しい版として配ること（リリース）は、
中村が行います（手順は [`docs/release.md`](docs/release.md)）。コントリビューターはリリースしません。

新しい読む道具（エンジン）を足すときは、先に [`docs/adding-an-engine.md`](docs/adding-an-engine.md) を読んでください。
PP-OCR の仲間なら、データを 1 件足すだけで増やせます。

## 用意するもの（最初の 1 回だけ）

- GitHub でこのリポジトリに書き込める権限（中村が招待します）
- Python 3.12 と [uv](https://docs.astral.sh/uv/)（パッケージを入れて、コマンドを実行する道具）

```
git clone https://github.com/nakamura196/local-ocr.git
cd local-ocr
uv sync
```

## 手元でアプリを動かす

```
PYTHONPATH=src .venv/bin/python main.py
```

Windows では `.venv\Scripts\python.exe` を使います。
モデルは、使う画面で初めて選んだときに自動で取得されます。
PaddleOCR-VL や Yigdzin-1 を動かすときだけ、先に `./scripts/fetch-binaries.zsh` が要ります
（画像を読む部品 `llama-server` を取ってくるスクリプトです）。

画面を使わずに試すときは、次のようにします。

```
uv run local-ocr --list-engines
uv run local-ocr <画像のパス> --engine <エンジンの id> --fetch
```

## 出す前に通すもの

```
uv run pytest
uv run --with ruff==0.16.8 ruff check .
```

どちらも通すのが条件です。ruff（コードの書き方を点検する道具）の版は固定してあります。
GitHub 上の自動の点検（Actions）は、無料枠の都合で動かないことがあるので、手元で通しておきます。

## 1 つの作業の流れ

1. main を最新にして、ブランチを作る。名前は `feat/〜`（機能を足す）、`fix/〜`（直す）、
   `docs/〜`（文書だけ）のどれかで始める
   ```
   git switch main
   git pull
   git switch -c feat/<短い名前>
   ```
2. 直す。画面に関わるときは、アプリを動かして確かめる
3. 上の 2 つの点検を通す
4. コミットして、GitHub に送る。**ファイルは 1 つずつ指定します**（`git add .` と `git add -A` は使いません）
   ```
   git add <直したファイル>
   git commit -m "feat: <何をしたか>"
   git push -u origin feat/<短い名前>
   ```
   コミットの題は、`feat: 〜` `fix: 〜` `docs: 〜` `test: 〜` のどれかで始め、日本語で 1 行に書きます。
   例: `feat: PP-OCRv6 tiny を読む道具に足す`
5. プルリクエストを作る。本文に、何をどう変えたか（2〜3 行）、確かめた方法、
   画面に関わるときはスクリーンショットを書く

## してはいけないこと

- main へ直接 push する。マージする。リリースする（これは中村が行います）
- パスワード、鍵、トークンをファイルに書く、コミットする、チャットに貼る
- `.env*`・`*.pem`・`*.key` などのファイルをコミットする
- 更新履歴（`docs/changelog*.md`）の版の見出しを足す。配るときに中村が書きます
  （そのかわり、PR の説明に「利用者から見て何が変わるか」を 1 行書いてください）

迷ったら、作業を止めて、Issue かプルリクエストに書いて聞いてください。
