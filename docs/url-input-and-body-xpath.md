# URL 入力と body_xpath 対応方針

このメモは、実運用で `Jobs.input_file` に実在 URL を指定する運用へ移行するための方針です。現時点では URL 入力対応は未実装であり、今後の PR 対象です。

## 現状

- runner は `Jobs.input_file` を Google Drive 入力フォルダ内のファイル名またはパスとして扱います。
- `Jobs.input_file` が空欄の場合は `site/page_id.html` を入力パスとして扱います。
- `input_file` が `http://` または `https://` で始まっても、URL から HTML を取得する処理はありません。
- `Sites` タブには `body_xpath` 列があります。
- `Jobs` タブには `body_xpath` 列がありません。
- Web API の `JobCreate` にも `body_xpath` はありません。
- runner は現在、サイトごとの `Sites.body_xpath` を `process_page()` に渡します。

## 実運用の入力方針

実運用では、`Jobs.input_file` に Drive 内ファイル名ではなく、実在するページ URL を指定する想定です。

```text
https://www.example.jp/path/to/page.html
```

URL から取得した HTML はページ全体をそのまま処理せず、`body_xpath` で指定した本文部分だけを抽出して処理します。本文領域は、抽出対象要素の `outerHTML` として扱う方針です。

## `body_xpath` の優先順

URL 入力対応後は、`body_xpath` を次の優先順で決定する予定です。

1. `Jobs` 行の `body_xpath`
2. `Sites` タブの `body_xpath`
3. `Config` タブの `body_xpath`
4. 未指定なら `body` 要素全体

ジョブ単位で本文領域が異なる場合は `Jobs.body_xpath`、サイト全体で同じ場合は `Sites.body_xpath`、全体既定値は `Config.body_xpath` に置く想定です。

## 未実装事項

次の項目はまだ未実装です。今後の PR で対応します。

- `input_file` が `http://` または `https://` の場合に URL として扱う。
- `requests` 等で HTML を取得する。
- HTML 取得時に timeout を設定する。
- HTML 取得時の User-Agent を明示する。
- HTTP エラー、タイムアウト、XPath 不一致を `Jobs.error` に残す。
- `body_xpath` で本文領域を `outerHTML` として抽出する。
- `Jobs` スキーマに `body_xpath` 列を追加する。
- Web API の `JobCreate` に `body_xpath` を追加する。
- 既存の Google Drive 入力方式を維持する。

## 互換性方針

既存の Drive 入力方式は残します。URL 入力対応後も、`input_file` が URL ではない場合は従来どおり Google Drive 入力フォルダ内のファイル名またはパスとして読みます。
