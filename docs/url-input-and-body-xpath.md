# URL 入力と body_xpath 仕様

このメモは、`Jobs.input_file` に実在 URL を指定する運用と、URL から取得した HTML に対する `body_xpath` 抽出の現在の実装仕様です。

## 対応済みの入力方式

runner は `Jobs.input_file` を次のように解釈します。

- `http://` または `https://` で始まる値: URL 入力として扱い、HTTP GET で HTML を取得します。
- URL 以外の値: Google Drive 入力フォルダ内のファイル名またはパスとして読みます。
- 空欄: 従来どおり `site/page_id.html` を Google Drive 入力フォルダから読みます。

URL 入力でも既存の Drive 入力方式は維持します。`input_file` が URL の場合、取得して `body_xpath` 抽出した HTML を `site/page_id.html` として Drive 入力フォルダへ保存し、その実行の old HTML として処理します。

## URL 取得仕様

URL 入力では、runner が timeout と User-Agent を指定して HTML を取得します。HTTP エラー、タイムアウト、通信エラー、文字コードデコードエラー、XPath エラーはジョブ単位の例外として扱い、`Jobs.status=error` と `Jobs.error` に内容を残します。

## `body_xpath` 抽出仕様

URL から取得した HTML は、本文領域だけを処理できるように `body_xpath` で抽出できます。`body_xpath` が指定されている場合は、XPath に一致した先頭の HTML 要素を `outerHTML` として `process_page()` に渡します。

`body_xpath` が未指定の場合は、HTML 内の `body` 要素全体を `outerHTML` として使います。`body` 要素がない場合は、パース結果のルート要素を使います。

## `body_xpath` の優先順

`body_xpath` は次の優先順で決定します。

1. `Jobs` 行の `body_xpath`
2. `Sites` タブの `body_xpath`
3. `Config` タブの `body_xpath`
4. 未指定なら `body` 要素全体

ジョブ単位で本文領域が異なる場合は `Jobs.body_xpath`、サイト全体で同じ場合は `Sites.body_xpath`、全体既定値は `Config.body_xpath` に置きます。

## Jobs タブ例

| site | page_id | input_file | body_xpath | status |
|---|---|---|---|---|
| saga-city | test-url-001 | `https://www.example.jp/path/to/page.html` | `//*[@id="contents-in"]` | queued |

この例では、runner が `input_file` の URL から HTML を取得し、`//*[@id="contents-in"]` に一致する要素だけを old HTML として処理します。

## `check_gold` の対象範囲

`check_gold` は現在、Google Drive 入力フォルダの old HTML と Google Drive gold 出力フォルダの gold HTML を、`tests/cases/html_pairs.jsonl` の定義に基づいて比較する検証機能です。URL 入力ジョブの `input_file` から old HTML を再取得する処理は行いません。URL 入力で生成した結果を `check_gold` で検証したい場合は、対応する old HTML を Drive 入力フォルダに配置してください。

## 互換性方針

既存の Drive 入力方式は残します。URL 入力対応後も、`input_file` が URL ではない場合は従来どおり Google Drive 入力フォルダ内のファイル名またはパスとして読みます。
