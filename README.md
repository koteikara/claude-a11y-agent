# a11y-regression — Claude-A11y Agent 回帰テスト雛形

`機械` 32関数と `機械+AI` 16プロンプトのデグレを検出するための pytest 雛形。
事例はすべて JSONL のデータ駆動で、24事例Excelは同形式に変換して差し込むだけ。

## 構成
```
mechanical_rules.py            機械32ルールの実装（被テスト対象）
specs/a11y_hybrid_detect_fix.jsonl   16プロンプト雛形＋出力契約（被テスト対象）
a11y_testkit/jsonparse.py      最外部{...}を取り出す堅牢JSONパーサ
a11y_testkit/llm.py            LLM_PROVIDER で gemini/claude 切替＋Mock
tests/cases/mechanical_cases.jsonl   機械の入力/期待出力ペア（シード27件）
tests/cases/prompt_cases.jsonl       プロンプトのゴールデン事例（19件・16ルール網羅）
tests/test_mechanical_text.py  文字列関数（equals/telfax/bool/xfail）
tests/test_mechanical_dom.py   lxml DOM操作（構造アサーション）
tests/test_prompts.py          プロンプト：オフライン充填+契約／オンライン@llm
```

## 実行
```bash
pip install -r requirements-dev.txt      # 最低限 pytest と lxml
pytest                                   # 機械＋オフラインプロンプト（@llmは自動スキップ）

# 実LLM回帰（Geminiの例）
export LLM_PROVIDER=gemini RUN_LLM_TESTS=1 GEMINI_API_KEY=...
pip install -r requirements-llm-gemini.txt
pytest -m llm

# 実LLM回帰（Claudeの例）
export LLM_PROVIDER=claude RUN_LLM_TESTS=1 ANTHROPIC_API_KEY=...
pip install -r requirements-llm-claude.txt
pytest -m llm
```

## 2系統のテスト
- **機械**: `func(input) == expected` を直接検証。`fix_telfax` は `(text, needs_review)` を確認。
  `単語 広辞苑`（複数単語の区切りスペース保持）は CJK隣接ルールの既知の限界として **xfail** で明示。
- **プロンプト**:
  - オフライン（常時）= 雛形が全プレースホルダを埋め切るか＋出力契約JSONが堅牢パーサで読め必須キーを持つか。
  - オンライン（`@llm`）= 実LLMを呼び、契約充足＋安定アサーション（例: `2/3`は日付でない、`☆`固有名詞は keep）。

## 24事例Excelの取り込み
`データ移行総合マニュアル…抽出.xlsx` 形式とは別の「24件の実処理事例＋期待出力」Excelを、
`tests/cases/mechanical_cases.jsonl` / `prompt_cases.jsonl` と同じスキーマに変換して追記する。
列の対応例: `修正前→input` / `修正後→expected` / `ルール→rule` / 対象関数→`func`。

## CI（.github/workflows/tests.yml）
- `mechanical` ジョブ: 毎 push・PR でオフライン一式。
- `llm` ジョブ: `workflow_dispatch`（手動）/ `schedule`（週次）でのみ。`secrets.GEMINI_API_KEY` を使用。
