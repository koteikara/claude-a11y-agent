# Cloud Run デプロイ調査メモ

この文書は、Web 管理画面を **Cloud Run Service**、CLI runner を **Cloud Run Jobs** で安全に動かすための現状調査と不足点の一覧です。API キーやパスワードは Secret Manager で管理し、サービスアカウント JSON 鍵は原則使わない前提です。

## 1. 現状の構成

### Dockerfile

現在のコンテナ定義は `web/Dockerfile` です。

- `node:22-slim` で `web/frontend` をビルドします。
- `python:3.12-slim` に `web/requirements.txt` と `requirements-runner.txt` の依存関係をインストールします。
- `a11y_runner`、`a11y_testkit`、`mechanical_rules.py`、`web/backend`、ビルド済み frontend を `/app` にコピーします。
- `PORT=8080` を既定値にし、`8080` を expose します。
- 既定の起動コマンドは次の Web 管理画面用コマンドです。

```bash
uvicorn web.backend.app:app --host 0.0.0.0 --port ${PORT:-8080}
```

このイメージには runner の Python モジュールも含まれるため、Cloud Run Jobs ではコンテナの command / args を上書きして `python -m a11y_runner ...` を実行できます。

### Web 管理画面の起動コマンド

Cloud Run Service では Dockerfile の既定 CMD をそのまま利用します。

```bash
uvicorn web.backend.app:app --host 0.0.0.0 --port ${PORT:-8080}
```

Cloud Run は `PORT` を自動注入するため、通常 `PORT` を手動設定する必要はありません。

### CLI runner の起動コマンド

CLI の entrypoint は `python -m a11y_runner` です。主なサブコマンドは次のとおりです。

```bash
python -m a11y_runner init-sheet --sheet <SHEET_ID>
python -m a11y_runner run --sheet <SHEET_ID> --site <SITE> --limit <N>
python -m a11y_runner check --sheet <SHEET_ID> --site <SITE>
python -m a11y_runner promote --sheet <SHEET_ID>
```

Cloud Run Jobs では、用途ごとに Job を分けるか、同じ Job の実行時 args を上書きします。

例:

```bash
gcloud run jobs create claude-a11y-runner \
  --image REGION-docker.pkg.dev/PROJECT_ID/REPOSITORY/claude-a11y:TAG \
  --region asia-northeast1 \
  --service-account claude-a11y-runner@PROJECT_ID.iam.gserviceaccount.com \
  --command python \
  --args -m,a11y_runner,run,--sheet,SHEET_ID,--limit,10 \
  --set-secrets GEMINI_API_KEY=claude-a11y-gemini-api-key:latest
```

## 2. 必要環境変数

### Web 管理画面（Cloud Run Service）

| 変数 | 必須 | Secret Manager 推奨 | 用途 |
|---|---:|---:|---|
| `GOOGLE_SHEET_ID` | 必須 | いいえ | 管理台帳の Google Sheets ID。`SHEET_ID` でも代替可能ですが、本番は `GOOGLE_SHEET_ID` に統一します。 |
| `SHEET_ID` | 任意 | いいえ | `GOOGLE_SHEET_ID` 未設定時の代替名。 |
| `BASIC_AUTH_USERNAME` | 条件付き | どちらでも可 | IAP / Cloud Run IAM 以外に Basic 認証を使う場合のみ設定します。 |
| `BASIC_AUTH_PASSWORD` | 条件付き | はい | Basic 認証を使う場合のみ設定します。 |
| `GOOGLE_APPLICATION_CREDENTIALS` | 原則不要 | いいえ | ローカルや例外的な鍵ファイル利用時のみ。Cloud Run では未設定にして ADC を使います。 |
| `AUTH_DISABLED_FOR_TESTS` | 本番禁止 | いいえ | テスト専用。Cloud Run では設定してはいけません。 |
| `PORT` | 自動 | いいえ | Cloud Run が自動設定します。 |

Drive フォルダ ID は環境変数ではなく、Sheets の `Config` タブから読みます。

| Config key | 用途 |
|---|---|
| `drive_input_folder_id` | 入力 HTML の Drive フォルダ ID |
| `drive_output_ai_folder_id` | AI 下書き HTML の出力先 Drive フォルダ ID |
| `drive_output_gold_folder_id` | 承認済み gold HTML の出力先 Drive フォルダ ID |
| `llm_provider` | ジョブ行に provider がない場合の LLM provider 既定値 |
| `run_mode` | `batch` / `interactive` などの実行モード |
| `default_site` | 既定 site |

### CLI runner（Cloud Run Jobs）

| 変数 | 必須 | Secret Manager 推奨 | 用途 |
|---|---:|---:|---|
| `GEMINI_API_KEY` | Gemini 利用時 | はい | Gemini API キー。 |
| `ANTHROPIC_API_KEY` | Claude 利用時 | はい | Anthropic API キー。 |
| `LLM_PROVIDER` | 任意 | いいえ | `gemini` / `claude`。CLI 実行中は job / Config の provider が優先されます。 |
| `GEMINI_MODEL` | 任意 | いいえ | Gemini モデル名。 |
| `CLAUDE_MODEL` | 任意 | いいえ | Claude モデル名。 |
| `GOOGLE_APPLICATION_CREDENTIALS` | 原則不要 | いいえ | Cloud Run Jobs では未設定にして ADC を使います。 |

`--sheet <SHEET_ID>` は CLI 引数として渡す必要があります。Cloud Run Jobs の args に直接書くか、運用ラッパーを追加する場合は環境変数から引数化してください。

## 3. Cloud Run Service 向け不足点・注意点

### 現状で満たしている点

- Dockerfile は Cloud Run の `PORT` に合わせて uvicorn を起動できます。
- Web API と SPA shell は、Basic 認証が未設定かつテスト無効化もされていない場合、`503` を返して公開事故を防ぐ実装です。
- `--no-allow-unauthenticated` で Cloud Run Service を作成する運用に適しています。
- Google Drive は `google.auth.default()` を使っており、Cloud Run サービスアカウントの ADC で動作します。
- Google Sheets も ADC に対応しました。`GOOGLE_APPLICATION_CREDENTIALS` 未設定時は Cloud Run サービスアカウントの ADC を使います。

### 不足・運用で必ず補う点

1. **未認証公開は禁止**
   - `gcloud run deploy` では必ず `--no-allow-unauthenticated` を指定します。
   - IAP を使う場合は、外部 HTTPS ロードバランサ + Serverless NEG + IAP で保護し、許可する Google Workspace グループを限定します。
   - IAP をまだ構成しない場合でも、Cloud Run IAM で利用者に `roles/run.invoker` を付け、直接 URL を限定公開にします。

2. **アプリ内認証の位置付けを決める**
   - IAP / Cloud Run IAM を主認証にする場合、アプリ側 Basic 認証は二重認証になります。
   - 現状コードは Basic 認証情報が未設定だと Web UI / API が `503` になります。IAP のみで利用するには、IAP ヘッダー検証などのアプリ側認証方式を追加するか、組織の前段認証を信頼してアプリ側 Basic を設定する運用にしてください。
   - `AUTH_DISABLED_FOR_TESTS=true` を本番で使ってはいけません。

3. **Secret Manager 連携**
   - Basic 認証を使う場合、`BASIC_AUTH_PASSWORD` は Secret Manager から注入します。
   - API キーを Web 管理画面から直接使う設計にする場合のみ、該当キーを Service にも Secret 注入します。現状の Web 実行は主に runner を呼ぶため、LLM キーが必要になる可能性があります。

4. **サービスアカウント JSON 鍵を使わない**
   - Cloud Run では `GOOGLE_APPLICATION_CREDENTIALS` を設定せず、実行サービスアカウントの ADC を使います。
   - Sheet / Drive は対象ファイル・フォルダを実行サービスアカウントのメールアドレスに共有します。

5. **ヘルスチェック専用エンドポイントは未実装**
   - Cloud Run はコンテナ起動とポート listen で起動確認できますが、必要であれば認証不要の `/healthz` を追加する余地があります。
   - 追加する場合もデータや設定値を返さない実装にしてください。

## 4. Cloud Run Jobs 向け不足点・注意点

### 現状で満たしている点

- 同じコンテナイメージに CLI runner と依存関係が含まれています。
- command / args を上書きすれば Cloud Run Jobs で `init-sheet`、`run`、`check`、`promote` を実行できます。
- Google Drive / Sheets は ADC 対応のため、Jobs の実行サービスアカウントでアクセスできます。

### 不足・運用で必ず補う点

1. **Job 定義ごとの args 設計**
   - `run`、`check`、`promote` を別 Job にするか、実行時 args 上書きにするか決める必要があります。
   - `--sheet` は必須引数です。環境変数だけでは起動できません。

2. **タイムアウト・リトライ・並列度**
   - Sheets 行を更新するバッチのため、無制限の並列実行は避けます。
   - まずは `--tasks 1 --parallelism 1`、小さめの `--limit` で運用開始するのが安全です。
   - タイムアウトは対象ページ数と LLM 呼び出し時間に合わせて設定します。

3. **LLM キーの Secret 注入**
   - Gemini / Claude の API キーは Secret Manager から環境変数として注入します。
   - 利用しない provider のキーは注入しないでください。

4. **スケジューリング**
   - 定期実行する場合は Cloud Scheduler から Cloud Run Jobs Execute API を呼びます。
   - Scheduler 用サービスアカウントには対象 Job の実行権限のみを付与します。

5. **冪等性と排他**
   - runner は `queued` 行を取得し、ジョブごとに `running` / `done` / `needs_review` / `error` を更新します。
   - 複数 Job を同時実行すると同じ `queued` 行を拾う可能性があるため、運用上は単一実行を基本にしてください。

## 5. Secret Manager 名・環境変数名・IAM 権限一覧

### Secret 一覧

| Secret 名（例） | 注入先 | 環境変数名 | 必須条件 |
|---|---|---|---|
| `claude-a11y-basic-auth-password` | Service | `BASIC_AUTH_PASSWORD` | Basic 認証を使う場合 |
| `claude-a11y-basic-auth-username` | Service | `BASIC_AUTH_USERNAME` | ユーザー名も secret 化する場合 |
| `claude-a11y-gemini-api-key` | Service / Jobs | `GEMINI_API_KEY` | Gemini を使う場合 |
| `claude-a11y-anthropic-api-key` | Service / Jobs | `ANTHROPIC_API_KEY` | Claude を使う場合 |

サービスアカウント JSON 鍵を Secret Manager に保存する運用は原則採用しません。例外的に外部環境で必要な場合のみ、Cloud Run ではなくローカル・CI の個別手順として扱ってください。

### 実行サービスアカウント

| サービスアカウント | 用途 | 必要権限 |
|---|---|---|
| `claude-a11y-admin@PROJECT_ID.iam.gserviceaccount.com` | Cloud Run Service 実行 | 対象 Secret への `roles/secretmanager.secretAccessor`、ログ出力の標準権限。対象 Google Sheet と Drive フォルダにファイル共有で Editor 相当の権限。 |
| `claude-a11y-runner@PROJECT_ID.iam.gserviceaccount.com` | Cloud Run Jobs 実行 | 対象 Secret への `roles/secretmanager.secretAccessor`、ログ出力の標準権限。対象 Google Sheet と Drive フォルダにファイル共有で Editor 相当の権限。 |
| `claude-a11y-scheduler@PROJECT_ID.iam.gserviceaccount.com` | Cloud Scheduler から Jobs を起動 | 対象 Job 実行のための Cloud Run Job 実行権限。Secret や Sheet / Drive への直接アクセスは不要。 |

Google Sheets / Drive は、IAM ロールだけでは対象ファイルにアクセスできません。対象スプレッドシート、入力フォルダ、AI 出力フォルダ、gold 出力フォルダを、実行サービスアカウントのメールアドレスに共有してください。

### 有効化する API

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  sheets.googleapis.com \
  drive.googleapis.com
```

Cloud Scheduler を使う場合は追加で有効化します。

```bash
gcloud services enable cloudscheduler.googleapis.com
```

## 6. デプロイ例

### イメージビルド

```bash
gcloud artifacts repositories create claude-a11y \
  --repository-format docker \
  --location asia-northeast1

gcloud builds submit \
  --tag asia-northeast1-docker.pkg.dev/PROJECT_ID/claude-a11y/claude-a11y:TAG \
  -f web/Dockerfile \
  .
```

### Web 管理画面（Cloud Run Service）

Basic 認証を併用する例です。IAP / Cloud Run IAM で必ず前段を保護し、`--no-allow-unauthenticated` を外さないでください。

```bash
gcloud run deploy claude-a11y-admin \
  --image asia-northeast1-docker.pkg.dev/PROJECT_ID/claude-a11y/claude-a11y:TAG \
  --region asia-northeast1 \
  --service-account claude-a11y-admin@PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars GOOGLE_SHEET_ID=SHEET_ID,BASIC_AUTH_USERNAME=admin \
  --set-secrets BASIC_AUTH_PASSWORD=claude-a11y-basic-auth-password:latest \
  --no-allow-unauthenticated
```

### CLI runner（Cloud Run Jobs）

```bash
gcloud run jobs create claude-a11y-runner \
  --image asia-northeast1-docker.pkg.dev/PROJECT_ID/claude-a11y/claude-a11y:TAG \
  --region asia-northeast1 \
  --service-account claude-a11y-runner@PROJECT_ID.iam.gserviceaccount.com \
  --command python \
  --args -m,a11y_runner,run,--sheet,SHEET_ID,--limit,10 \
  --set-secrets GEMINI_API_KEY=claude-a11y-gemini-api-key:latest \
  --tasks 1 \
  --parallelism 1 \
  --task-timeout 3600
```

実行例:

```bash
gcloud run jobs execute claude-a11y-runner \
  --region asia-northeast1 \
  --wait
```

## 7. 最小限の実コード変更

Cloud Run のサービスアカウント JSON 鍵を使わない方針に合わせ、Google Sheets adapter を ADC 対応にしました。

- `GOOGLE_APPLICATION_CREDENTIALS` がある場合: 従来どおり gspread の service account JSON を使います（ローカル・例外用途）。
- `GOOGLE_APPLICATION_CREDENTIALS` がない場合: `google.auth.default(scopes=["https://www.googleapis.com/auth/spreadsheets"])` と `gspread.authorize()` で Cloud Run 実行サービスアカウントの ADC を使います。

追加で検討すべき実コード変更は次のとおりです。

1. IAP を主認証にする場合、IAP JWT / ヘッダー検証を追加し、Basic 認証必須の現在挙動と整理する。
2. Cloud Run の起動確認用に、秘匿情報を返さない `/healthz` を追加する。
3. Jobs 用に `A11Y_SHEET_ID` などから CLI 引数を組み立てる薄い entrypoint を追加する。ただし現状でも `--args` 指定で運用可能。
