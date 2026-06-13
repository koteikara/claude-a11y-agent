# Claude-A11y Agent

Claude-A11y Agent は、自治体サイトなどのページ移行時に、HTML をアクセシビリティ観点で整え、AI が作成した下書き（ai）を人が確認して最終版（gold）へ承認するためのツールです。Google スプレッドシートを管理台帳、Google Drive を入出力置き場として使い、Web 管理画面と runner が同じ台帳を読み書きします。

## 現在の推奨構成

現在の推奨運用は次の構成です。

- **Web 管理画面**: Cloud Run Service `claude-a11y-admin`
- **runner**: Cloud Run Jobs `claude-a11y-runner`
- **秘密情報**: Secret Manager
  - Basic 認証パスワード
  - Gemini / Anthropic などの API キー
- **認証**: Cloud Run Service は `--no-allow-unauthenticated` を維持し、閲覧者には必要に応じて `roles/run.invoker` を付与します。
- **Google 認証**: Cloud Run では実行サービスアカウントの ADC を使います。`GOOGLE_APPLICATION_CREDENTIALS` は設定しません。
- **サービスアカウント鍵**: JSON 鍵は作成・保存・コミットしません。
- **定期実行**: 必須ではありません。今回の運用では Cloud Scheduler は作成せず、必要なときに Cloud Run Jobs を手動実行します。

Cloud Run Service / Cloud Run Jobs の構築手順は [`docs/cloud-run-setup-checklist.md`](docs/cloud-run-setup-checklist.md) を参照してください。詳細な背景、PowerShell / bash のコマンド例、Cloud Build、Cloud Run Jobs 更新例は [`docs/deploy-cloud-run.md`](docs/deploy-cloud-run.md) にまとめています。

## 使い方の概要

| 使い方 | 主な利用者 | 主な場所 |
|---|---|---|
| スプレッドシートで管理 | 一覧で大量のページを登録・確認する担当者 | Google Sheets の `Jobs` タブ |
| Web 管理画面 | old / ai / gold の比較、要確認、承認を行う担当者 | Cloud Run Service の Web UI |
| runner 実行 | 処理待ち行を一括処理する管理者 | Cloud Run Jobs |

`Jobs` タブに `status=queued` の対象行がない場合、runner は `n_total: 0` で正常終了します。これは環境構築の失敗ではなく、処理対象がない状態です。

## `input_file` と URL 入力の現状

runner は `Jobs.input_file` に Google Drive 入力フォルダ内のファイル名またはパス、または `http://` / `https://` の実在 URL を指定できます。空欄の場合は従来どおり `site/page_id.html` を Drive 入力から読みます。

URL 入力の場合、runner は URL から HTML を取得し、`body_xpath` が指定されていれば一致した先頭要素の `outerHTML` だけを処理対象にします。`body_xpath` は `Jobs.body_xpath`、`Sites.body_xpath`、`Config.body_xpath` の順に解決し、未指定なら `body` 要素全体を処理します。詳細仕様は [`docs/url-input-and-body-xpath.md`](docs/url-input-and-body-xpath.md) を参照してください。

`check_gold` は現在も Google Drive 入力と gold 出力の比較を前提にしており、URL から old HTML を再取得する用途には対応していません。

## ドキュメント

- Cloud Run 構築チェックリスト: [`docs/cloud-run-setup-checklist.md`](docs/cloud-run-setup-checklist.md)
- Cloud Run 詳細手順: [`docs/deploy-cloud-run.md`](docs/deploy-cloud-run.md)
- URL 入力と `body_xpath` 仕様: [`docs/url-input-and-body-xpath.md`](docs/url-input-and-body-xpath.md)
- Cloud Run トラブルシュート: [`docs/troubleshooting-cloud-run.md`](docs/troubleshooting-cloud-run.md)
- 開発者向け詳細: [`docs/開発者向け.md`](docs/開発者向け.md)
- 用語集: [`docs/用語集.md`](docs/用語集.md)

## セキュリティ上の注意

- Secret 値、API キー、Basic 認証パスワード、サービスアカウント JSON はリポジトリに書かないでください。
- 本番の Cloud Run Service を `--allow-unauthenticated` にしないでください。
- Cloud Run Service / Jobs に `GOOGLE_APPLICATION_CREDENTIALS` を設定しないでください。
- サービスアカウント JSON 鍵を本番運用の前提にしないでください。
