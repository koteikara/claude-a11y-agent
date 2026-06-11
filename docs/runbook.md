# Claude-A11y Agent 実行手順

このドキュメントは、参考リポジトリ `koteikara/gemini-a11y-agent` の README にある「対象・前提」「主な機能」「検証済み例」の整理方法を参考にしつつ、このリポジトリで提供している **Claude-A11y Agent 回帰テスト／検証ツール** を実行するための手順をまとめたものです。

## 1. このツールで確認できること

このリポジトリは、HTML アクセシビリティ移行時の修正ルールが退行していないかを検証するための pytest ベースのテストキットです。

主に次の観点を確認できます。

- `mechanical_rules.py` に実装された機械的な文字列・DOM 修正ルール
- `specs/a11y_hybrid_detect_fix.jsonl` に定義された LLM プロンプト契約
- `tests/fixtures/html/{site}/{stage}/{page_id}.html` に配置した old / ai / gold HTML ペア
- 実 LLM（Gemini または Claude）を呼び出すオンライン回帰テスト
- `skills/a11y-pressure-test` による繰り返し実行型の readiness 検査

## 2. 前提条件

- Python 3.10 以上を推奨
- `pip` が利用できること
- 通常のオフラインテストだけなら LLM API キーは不要
- 実 LLM 回帰を実行する場合のみ、利用するプロバイダの API キーが必要
  - Gemini: `GEMINI_API_KEY`
  - Claude: `ANTHROPIC_API_KEY`

## 3. リポジトリを取得する

```bash
git clone <このリポジトリのURL>
cd claude-a11y-agent
```

すでにリポジトリが手元にある場合は、作業ディレクトリをリポジトリ直下へ移動します。

```bash
cd /path/to/claude-a11y-agent
```

## 4. Python の仮想環境を作成する

依存関係をプロジェクト単位で分離するため、仮想環境の利用を推奨します。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Windows PowerShell の場合は、仮想環境の有効化コマンドが異なります。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

## 5. 最小依存関係をインストールする

通常の機械ルール検証とオフラインプロンプト検証には、開発用依存関係だけを入れます。

```bash
pip install -r requirements-dev.txt
```

この状態では、`@llm` マーカー付きのオンラインテストは自動的にスキップされます。

## 6. まず通常テストを実行する

```bash
pytest -q
```

このコマンドで、次の検証が実行されます。

- 機械ルールの単体テスト
- DOM 操作ルールの構造アサーション
- プロンプト雛形のプレースホルダ充填確認
- LLM 出力契約 JSON のパース確認

LLM API キーが未設定でも実行できます。

## 7. HTML ペアの回帰テストを実行する

old / ai / gold の HTML fixture を使った検証は、通常 CI では重くなりやすいため、環境変数で明示的に有効化します。

```bash
RUN_HTML_PAIRS=1 pytest -m html_pairs
```

ai と gold のドリフトだけを確認したい場合は、次を実行します。

```bash
RUN_HTML_PAIRS=1 pytest -m drift
```

pipeline 本体まで接続できる環境では、E2E テストも実行できます。

```bash
RUN_HTML_PAIRS=1 RUN_E2E=1 pytest -m e2e
```

## 8. Gemini で実 LLM 回帰を実行する

Gemini を使う場合は、追加依存関係をインストールし、`LLM_PROVIDER=gemini` と `GEMINI_API_KEY` を設定します。

```bash
pip install -r requirements-llm-gemini.txt
export LLM_PROVIDER=gemini
export RUN_LLM_TESTS=1
export GEMINI_API_KEY="<your-gemini-api-key>"
pytest -m llm
```

必要に応じてモデル名を上書きできます。

```bash
export GEMINI_MODEL="gemini-1.5-pro"
pytest -m llm
```

## 9. Claude で実 LLM 回帰を実行する

Claude を使う場合は、追加依存関係をインストールし、`LLM_PROVIDER=claude` と `ANTHROPIC_API_KEY` を設定します。

```bash
pip install -r requirements-llm-claude.txt
export LLM_PROVIDER=claude
export RUN_LLM_TESTS=1
export ANTHROPIC_API_KEY="<your-anthropic-api-key>"
pytest -m llm
```

必要に応じてモデル名を上書きできます。

```bash
export CLAUDE_MODEL="claude-sonnet-4-20250514"
pytest -m llm
```

## 10. 実現度をまとめて確認する

複数回の通常テストと HTML ペア回帰をまとめて実行し、実現度を High / Medium / Low で確認する場合は、Codex skill の pressure test ハーネスを使います。

```bash
python skills/a11y-pressure-test/scripts/pressure_test.py --repeat 2
```

このハーネスは、既定で次を実行します。

1. `pytest -q`
2. `RUN_HTML_PAIRS=1 pytest -m html_pairs`
3. 通過率にもとづく readiness 判定

## 11. 典型的な実行順序

初回セットアップから通常検証までの最短手順は次のとおりです。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pytest -q
```

HTML fixture まで含めて確認する場合は、続けて次を実行します。

```bash
RUN_HTML_PAIRS=1 pytest -m html_pairs
```

実 LLM まで確認する場合は、Gemini または Claude のどちらか一方を選び、該当する追加依存関係と API キーを設定してから `pytest -m llm` を実行します。

## 12. テスト結果の見方

- `passed`: 対象のルールまたは契約を満たしています。
- `skipped`: 実行条件が満たされていません。例: `RUN_LLM_TESTS=1` または `RUN_HTML_PAIRS=1` が未設定。
- `xfail`: 既知の限界として明示されているケースです。
- `failed`: 期待結果との差分があります。該当テスト名と fixture / JSONL ケースを確認してください。

失敗時は、次の順で確認すると原因を切り分けやすくなります。

1. 失敗したテストファイルとケース ID を確認する。
2. `tests/cases/*.jsonl` の入力・期待値を確認する。
3. HTML ペアの場合は `tests/fixtures/html/{site}/old` と `gold` を比較する。
4. 実 LLM 回帰の場合は、API キー、モデル名、プロンプト契約 JSON の必須キーを確認する。

## 13. よく使うコマンド一覧

| 目的 | コマンド |
|---|---|
| 通常テスト | `pytest -q` |
| HTML ペア回帰 | `RUN_HTML_PAIRS=1 pytest -m html_pairs` |
| ai / gold ドリフト確認 | `RUN_HTML_PAIRS=1 pytest -m drift` |
| E2E 検証 | `RUN_HTML_PAIRS=1 RUN_E2E=1 pytest -m e2e` |
| Gemini 実 LLM 回帰 | `LLM_PROVIDER=gemini RUN_LLM_TESTS=1 GEMINI_API_KEY=... pytest -m llm` |
| Claude 実 LLM 回帰 | `LLM_PROVIDER=claude RUN_LLM_TESTS=1 ANTHROPIC_API_KEY=... pytest -m llm` |
| readiness 検査 | `python skills/a11y-pressure-test/scripts/pressure_test.py --repeat 2` |


## 14. スプレッドシート・Drive ランナーで運用する

非エンジニア向けの運用では、Google Sheets をジョブ管理画面、Google Drive を入出力置き場として使います。Python ランナー `a11y_runner/` が `Jobs` の `queued` 行を読み取り、Drive から HTML を取得して `process_page()` を実行し、結果を Sheet と Drive に書き戻します。

### 14.1 ランナー依存関係と認証

```bash
pip install -r requirements-runner.txt
export GOOGLE_APPLICATION_CREDENTIALS=/secure/path/to/service-account.json
```

サービスアカウントの JSON 鍵はリポジトリに置かず、対象 Sheet と Drive フォルダをサービスアカウントのメールアドレスに共有してください。設定例は `.env.example` を参照します。

### 14.2 シートを初期化する

```bash
python -m a11y_runner init-sheet --sheet <SHEET_ID>
```

`Config`, `Sites`, `Jobs`, `Runs`, `Review`, `Metrics` の各タブとヘッダを作成します。再実行しても既存行は壊しません。

### 14.3 処理待ちジョブを確認・実行する

```bash
python -m a11y_runner run --sheet <SHEET_ID> --dry-run
python -m a11y_runner run --sheet <SHEET_ID> --site saga-city --limit 10
```

`--dry-run` は対象一覧の表示だけを行います。実行時は `queued` → `running` → `done` / `needs_review` / `error` の順に `Jobs.status` を更新し、要確認事項は `Review` タブへ追記します。

### 14.4 gold チェックを記録する

```bash
python -m a11y_runner check --sheet <SHEET_ID> --site saga-city
```

Drive の gold HTML に既存 `html_pairs` チェックを適用し、合否を `Metrics` と `Review` に記録します。
