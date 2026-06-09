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

## HTMLペア回帰テスト（old / ai / gold）

移行元HTMLと人が確認した期待HTMLを、実体ファイルとJSONL索引で回帰資産化するための仕組みです。

### 3系統の役割

| stage | 意味 | テスト上の扱い |
|---|---|---|
| `old` | 移行元HTML（処理前の入力） | `baseline:"old"` を持つチェックだけが比較対象にします。 |
| `ai` | AIを通して生成した出力（任意のスナップショット） | `ai`↔`gold` のドリフト比較にだけ使います。差分は情報出力で、失敗にはしません。 |
| `gold` | 人が確認した期待出力（正・ゴールド） | 検証の主対象です。hardチェックは `gold` に対して失敗を検出します。 |

### ディレクトリ規約と追加手順

HTML fixture は次の規約で配置します。

```text
tests/fixtures/html/{site}/{stage}/{page_id}.html
```

- `stage` は `old` / `ai` / `gold` のいずれかです。
- `old` と `gold` は必須で、厳密に `{page_id}.html` を置きます。
- `ai` は任意です。生成日などの接尾辞を許容し、`{page_id}.html` または `{page_id}_0820.html` のように `_` 区切りで置けます。
- 空ディレクトリを保持するため、各 `old` / `ai` / `gold` に `.gitkeep` を置いています。

ペアを追加するときは、`old` と `gold` のHTMLを置き、`tests/cases/html_pairs.jsonl` に1行追加するだけです。`ai` は任意で、存在する場合だけドリフト比較が走ります。HTMLペア回帰は大きなfixture更新で通常CIを止めないよう、`RUN_HTML_PAIRS=1` を付けたときだけ実行します。

索引1行の主なキーは `id`, `site`, `page_id`, `has_ai`, `body_xpath`, `exercises`, `checks` です。`body_xpath` を省略した場合は文書全体を対象にします。

### check カタログ要約

| 分類 | check | 概要 |
|---|---|---|
| 機械判定（hard） | `no_tag` | `font`, `u`, `s`, `strike`, `i`, `center`, `graphic`, `html`, `body`, `head` などの禁止タグが無いこと。 |
| 機械判定（hard） | `no_anchor_text` | `<a>` テキストに「こちら」「ここ」「詳細」などの指示語を含まないこと。 |
| 機械判定（hard） | `anchor_href_present` | 全 `<a>` が非空の `href` を持つこと。 |
| 機械判定（hard） | `href_no_pattern` | `<a href>` が指定正規表現（例: `[?&]smf=`）に一致しないこと。 |
| 機械判定（hard） | `no_short_weekday` | `（月）` のような短縮曜日表記が無いこと。 |
| 機械判定（hard） | `alt_present` | 全 `<img>` が `alt` 属性を持つこと（空altは可）。 |
| 機械判定（hard） | `no_id` | 共通パーツ由来の `id` が無いこと。 |
| 機械判定（hard） | `no_layout_table` | `<th>` を持たず、`border="0"` または `class` に `nb` / `layout` を含む表が無いこと。 |
| 機械判定（hard） | `no_consecutive_br` | 連続 `<br>` が無いこと。 |
| 機械判定（hard） | `tag_count_not_decreased` | `baseline:"old"` と比較し、指定タグ数が減っていないこと。既定では `iframe` 用です。 |
| 助言判定（advisory） | `no_attr` | `align`, `bgcolor`, `cellpadding`, `cellspacing`, `valign`, `nowrap` などのレガシー表示属性を警告します。 |
| 助言判定（advisory） | `text_coverage` | `gold` の可視テキスト長 ÷ `old` の可視テキスト長が指定比率以上かを警告します。 |
| 実装あり・既定不採用 | `attr_whitelist` | 全属性が許可リスト内かを確認します。このCMSの `gold` は `class` 等を保持するため既定索引では使いません。 |
| 非機械 | alt内容の公式充足 | 「主題＋様子＋付加情報＋種類」の充足はLLMまたは人手レビューで担保します。 |
| 非機械 | 年号の文脈補完 | 文脈推測が必要な年号補完はLLMまたは人手レビューで担保します。 |

未知の `check.type` が索引に現れた場合は、将来拡張に備えて失敗ではなくスキップと警告にします。

### 比較前処理（CMS自動付与属性の除去）

`gold` は対象CMSがHTML出力した結果であり、`class` / `id` / `style` / `role` / `aria-*` / `data-*` などは人間の意図ではなくCMSが自動付与した副産物を含みます。そのため `ai`↔`gold` ドリフト比較と `@e2e` 比較では、比較時のメモリ上コピーから次の属性を剥がしてから正規化します。

- 除去する属性: `class`, `style`, `id`, `role`, `tabindex`, `target`, `width`, `height`, `aria-*`, `data-*`, `border`, `cellpadding`, `cellspacing`, `allow`, `allowfullscreen`, `frameborder`, `referrerpolicy`, `scrolling`
- 残す意味属性: `href`, `src`, `alt`, `scope`, `colspan`, `rowspan`, `summary`, `title`, `lang`

`gold` ファイル自体は加工せず、`strip_cms_attrs()` を適用したコピーだけを比較に使います。

### 実行方法

```bash
pytest -q                                      # 通常CI: 既存の機械＋オフラインプロンプト（HTMLペアは自動スキップ）
RUN_HTML_PAIRS=1 pytest -m html_pairs         # goldチェック＋ai↔goldドリフト。未配置ペアは自動スキップ
RUN_HTML_PAIRS=1 pytest -m drift              # ai↔goldドリフト確認（差分は情報出力）
RUN_HTML_PAIRS=1 RUN_E2E=1 pytest -m e2e      # pipeline本体が接続できる場合だけ実行
```

## Codex skill: a11y-pressure-test

このリポジトリ内のアクセシビリティ回帰修正について、決定的なオフライン検査を繰り返し実行して実現度を測る Codex skill を `skills/a11y-pressure-test/` に追加しています。

```bash
python skills/a11y-pressure-test/scripts/pressure_test.py --repeat 2
```

このハーネスは通常の `pytest -q` と、`RUN_HTML_PAIRS=1` を付けた HTML ペア回帰を実行し、通過率から High / Medium / Low の readiness を出力します。
