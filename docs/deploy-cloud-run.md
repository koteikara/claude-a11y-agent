# Cloud Run デプロイ手順

この手順は、Web 管理画面を **Cloud Run Service**、runner を **Cloud Run Jobs** として運用するための管理者向けメモです。Secret Manager を使い、Cloud Run の実行サービスアカウントで Google Sheets / Drive にアクセスします。Cloud Run では `GOOGLE_APPLICATION_CREDENTIALS` を設定せず、サービスアカウント JSON 鍵ファイルを使わないでください。

## 方針

- Web 管理画面: Cloud Run Service として起動します。
- runner: Cloud Run Jobs として起動し、必要に応じて Cloud Scheduler から実行します。
- 認証: Cloud Run Service は `--no-allow-unauthenticated` を必須にし、組織の Cloud Run IAM / IAP で保護します。Basic 認証はローカルまたは二重防御用です。
- 秘密情報: API キーや Basic 認証パスワードは Secret Manager から環境変数へ注入します。
- Google Sheets / Drive: 対象スプレッドシートと Drive フォルダを、Cloud Run 実行サービスアカウントのメールアドレスに共有します。
- ローカル開発: `gcloud auth application-default login` による ADC、または `.env.example` をコピーした untracked `.env` を使います。

## コンテナと起動コマンド

`web/Dockerfile` は Web 管理画面と runner の共通イメージです。

- frontend は `web/frontend` をビルドして `web/frontend/dist` に配置します。
- backend には `web/backend`、`a11y_runner`、`a11y_testkit`、runner 依存関係を含めます。
- Cloud Run Service の Web 起動コマンドは Dockerfile の既定 CMD です。

```bash
uvicorn web.backend.app:app --host 0.0.0.0 --port ${PORT:-8080}
```

Cloud Run は `PORT` を自動注入するため、本番で `PORT` を明示設定する必要は通常ありません。起動確認用に、秘密情報や Sheets / Drive 内容を返さない `GET /healthz` を提供しています。

runner は同じイメージの command / args を Cloud Run Jobs 側で上書きします。

```bash
python -m a11y_runner run --sheet SHEET_ID --site saga-city --limit 10
```

`--sheet` を省略した場合、runner は `A11Y_SHEET_ID`、`GOOGLE_SHEET_ID`、`SHEET_ID` の順に環境変数から読みます。

## 必要な環境変数

### Web 管理画面（Cloud Run Service）

| 変数 | 必須 | Secret Manager 推奨 | 用途 |
|---|---:|---:|---|
| `GOOGLE_SHEET_ID` | 必須 | いいえ | 管理台帳の Google Sheets ID。`SHEET_ID` も互換 fallback として利用できます。 |
| `SHEET_ID` | 任意 | いいえ | `GOOGLE_SHEET_ID` 未設定時の fallback。 |
| `BASIC_AUTH_USERNAME` | 条件付き | 任意 | Basic 認証を併用する場合だけ設定します。 |
| `BASIC_AUTH_PASSWORD` | 条件付き | はい | Basic 認証を併用する場合だけ設定します。 |
| `GEMINI_API_KEY` | Gemini を Web から実行する場合 | はい | Web 画面からジョブ実行する場合の Gemini API キー。 |
| `ANTHROPIC_API_KEY` | Claude を Web から実行する場合 | はい | Web 画面からジョブ実行する場合の Anthropic API キー。 |
| `LLM_PROVIDER` | 任意 | いいえ | 既定 provider。Sheets `Config` / job 行が優先されます。 |
| `GEMINI_MODEL` | 任意 | いいえ | Gemini モデル名。 |
| `CLAUDE_MODEL` | 任意 | いいえ | Claude モデル名。 |
| `GOOGLE_APPLICATION_CREDENTIALS` | Cloud Run では設定禁止 | いいえ | ローカルで JSON 鍵を使う例外時だけ設定します。 |
| `AUTH_DISABLED_FOR_TESTS` | 本番禁止 | いいえ | ユニットテスト専用。Cloud Run では設定しません。 |
| `PORT` | 自動 | いいえ | Cloud Run が自動設定します。 |

### runner（Cloud Run Jobs）

| 変数 | 必須 | Secret Manager 推奨 | 用途 |
|---|---:|---:|---|
| `A11Y_SHEET_ID` | `--sheet` を省略する場合 | いいえ | runner が参照する Google Sheets ID。 |
| `GOOGLE_SHEET_ID` / `SHEET_ID` | 任意 | いいえ | `A11Y_SHEET_ID` 未設定時の fallback。 |
| `GEMINI_API_KEY` | Gemini 利用時 | はい | Gemini API キー。 |
| `ANTHROPIC_API_KEY` | Claude 利用時 | はい | Anthropic API キー。 |
| `LLM_PROVIDER` | 任意 | いいえ | 既定 provider。Sheets `Config` / job 行が優先されます。 |
| `GEMINI_MODEL` | 任意 | いいえ | Gemini モデル名。 |
| `CLAUDE_MODEL` | 任意 | いいえ | Claude モデル名。 |
| `GOOGLE_APPLICATION_CREDENTIALS` | Cloud Run では設定禁止 | いいえ | ローカルで JSON 鍵を使う例外時だけ設定します。 |

Drive フォルダ ID は環境変数ではなく、Sheets の `Config` タブから読みます。

| Config key | 用途 |
|---|---|
| `drive_input_folder_id` | 入力 HTML の Drive フォルダ ID |
| `drive_output_ai_folder_id` | AI 下書き HTML の出力先 Drive フォルダ ID |
| `drive_output_gold_folder_id` | 承認済み gold HTML の出力先 Drive フォルダ ID |
| `llm_provider` | job 行に provider がない場合の既定 provider |
| `run_mode` | `batch` / `interactive` などの実行モード |
| `default_site` | 既定 site |

## Google Cloud 初期設定

以下は `PROJECT_ID`、`REGION`、`TAG`、`SHEET_ID` を置き換えて実行してください。

```bash
export PROJECT_ID="your-project-id"
export REGION="asia-northeast1"
export REPOSITORY="claude-a11y"
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/claude-a11y:TAG"
export SHEET_ID="your-google-sheet-id"
gcloud config set project "${PROJECT_ID}"
```

必要 API を有効化します。

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

Artifact Registry を作成します。既にある場合は不要です。

```bash
gcloud artifacts repositories create "${REPOSITORY}" \
  --repository-format docker \
  --location "${REGION}" \
  --description "Claude A11y Cloud Run images"
```

実行サービスアカウントを作成します。

```bash
gcloud iam service-accounts create claude-a11y-admin \
  --display-name "Claude A11y Web admin runtime"

gcloud iam service-accounts create claude-a11y-runner \
  --display-name "Claude A11y runner job runtime"
```

対象 Google スプレッドシート、入力 Drive フォルダ、AI 出力 Drive フォルダ、gold 出力 Drive フォルダを、次のメールアドレスに共有してください。IAM ロールだけでは Sheets / Drive ファイルにはアクセスできません。

- `claude-a11y-admin@PROJECT_ID.iam.gserviceaccount.com`
- `claude-a11y-runner@PROJECT_ID.iam.gserviceaccount.com`

## Secret Manager

本物の値はコマンド履歴に残らない方法で登録してください。以下は標準入力から登録する例です。

```bash
printf '%s' 'replace-with-basic-auth-password' | \
  gcloud secrets create claude-a11y-basic-auth-password --data-file=-

printf '%s' 'replace-with-gemini-api-key' | \
  gcloud secrets create claude-a11y-gemini-api-key --data-file=-
```

Claude を使う場合だけ Anthropic API キーも登録します。

```bash
printf '%s' 'replace-with-anthropic-api-key' | \
  gcloud secrets create claude-a11y-anthropic-api-key --data-file=-
```

Secret を読む実行サービスアカウントへ最小限の権限を付与します。

```bash
gcloud secrets add-iam-policy-binding claude-a11y-basic-auth-password \
  --member "serviceAccount:claude-a11y-admin@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role roles/secretmanager.secretAccessor

gcloud secrets add-iam-policy-binding claude-a11y-gemini-api-key \
  --member "serviceAccount:claude-a11y-admin@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role roles/secretmanager.secretAccessor

gcloud secrets add-iam-policy-binding claude-a11y-gemini-api-key \
  --member "serviceAccount:claude-a11y-runner@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role roles/secretmanager.secretAccessor
```

サービスアカウント JSON 鍵を Secret Manager に保存する手順は採用しません。

## イメージビルド

```bash
gcloud builds submit \
  --tag "${IMAGE}" \
  -f web/Dockerfile \
  .
```

## Web 管理画面を Cloud Run Service へデプロイ

`--no-allow-unauthenticated` を外さないでください。以下は Basic 認証を二重防御として併用する例です。

```bash
gcloud run deploy claude-a11y-admin \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "claude-a11y-admin@${PROJECT_ID}.iam.gserviceaccount.com" \
  --set-env-vars "GOOGLE_SHEET_ID=${SHEET_ID},BASIC_AUTH_USERNAME=admin,LLM_PROVIDER=gemini" \
  --set-secrets "BASIC_AUTH_PASSWORD=claude-a11y-basic-auth-password:latest,GEMINI_API_KEY=claude-a11y-gemini-api-key:latest" \
  --no-allow-unauthenticated
```

デプロイ後、組織の方針に合わせて Cloud Run IAM または HTTPS ロードバランサ + Serverless NEG + IAP で閲覧者を制限してください。認証なし公開をデフォルトにしないでください。

起動確認例:

```bash
SERVICE_URL="$(gcloud run services describe claude-a11y-admin --region "${REGION}" --format 'value(status.url)')"
curl -fsS -H "Authorization: Bearer $(gcloud auth print-identity-token)" "${SERVICE_URL}/healthz"
```

## runner を Cloud Run Jobs へ作成

### queued ジョブ処理

```bash
gcloud run jobs create claude-a11y-runner \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "claude-a11y-runner@${PROJECT_ID}.iam.gserviceaccount.com" \
  --command python \
  --args -m,a11y_runner,run,--sheet,"${SHEET_ID}",--site,saga-city,--limit,10 \
  --set-env-vars "LLM_PROVIDER=gemini" \
  --set-secrets "GEMINI_API_KEY=claude-a11y-gemini-api-key:latest" \
  --tasks 1 \
  --parallelism 1 \
  --task-timeout 3600
```

`A11Y_SHEET_ID` を環境変数にして `--sheet` を省略する例です。

```bash
gcloud run jobs create claude-a11y-runner-env-sheet \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "claude-a11y-runner@${PROJECT_ID}.iam.gserviceaccount.com" \
  --command python \
  --args -m,a11y_runner,run,--site,saga-city,--limit,10 \
  --set-env-vars "A11Y_SHEET_ID=${SHEET_ID},LLM_PROVIDER=gemini" \
  --set-secrets "GEMINI_API_KEY=claude-a11y-gemini-api-key:latest" \
  --tasks 1 \
  --parallelism 1 \
  --task-timeout 3600
```

実行例:

```bash
gcloud run jobs execute claude-a11y-runner \
  --region "${REGION}" \
  --wait
```

### schema 初期化、gold チェック、promote

必要に応じて一時 Job を作るか、既存 Job の `--args` を更新します。

```bash
gcloud run jobs create claude-a11y-init-sheet \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "claude-a11y-runner@${PROJECT_ID}.iam.gserviceaccount.com" \
  --command python \
  --args -m,a11y_runner,init-sheet,--sheet,"${SHEET_ID}" \
  --tasks 1 \
  --parallelism 1 \
  --task-timeout 600
```

```bash
gcloud run jobs create claude-a11y-check-gold \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "claude-a11y-runner@${PROJECT_ID}.iam.gserviceaccount.com" \
  --command python \
  --args -m,a11y_runner,check,--sheet,"${SHEET_ID}",--site,saga-city \
  --tasks 1 \
  --parallelism 1 \
  --task-timeout 1800
```

```bash
gcloud run jobs create claude-a11y-promote \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "claude-a11y-runner@${PROJECT_ID}.iam.gserviceaccount.com" \
  --command python \
  --args -m,a11y_runner,promote,--sheet,"${SHEET_ID}" \
  --tasks 1 \
  --parallelism 1 \
  --task-timeout 1800
```

## Cloud Scheduler で Jobs を定期実行する場合

Scheduler 用サービスアカウントを作成し、対象 Job の実行権限だけを付与します。

```bash
gcloud iam service-accounts create claude-a11y-scheduler \
  --display-name "Claude A11y scheduler invoker"

gcloud run jobs add-iam-policy-binding claude-a11y-runner \
  --region "${REGION}" \
  --member "serviceAccount:claude-a11y-scheduler@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role roles/run.invoker
```

スケジュール例:

```bash
gcloud scheduler jobs create http claude-a11y-runner-nightly \
  --location "${REGION}" \
  --schedule "0 2 * * *" \
  --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/claude-a11y-runner:run" \
  --http-method POST \
  --oauth-service-account-email "claude-a11y-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"
```

## ローカル起動と確認

ADC を使う場合:

```bash
gcloud auth application-default login
cp .env.example .env
python -m a11y_runner run --dry-run --site saga-city --limit 3
```

Web 管理画面のローカル起動:

```bash
pip install -r web/requirements.txt
export GOOGLE_SHEET_ID="your-google-sheet-id"
export BASIC_AUTH_USERNAME="admin"
export BASIC_AUTH_PASSWORD="change-me"
uvicorn web.backend.app:app --host 0.0.0.0 --port 8080
```

別ターミナルで起動確認します。

```bash
curl -fsS http://localhost:8080/healthz
```

Docker 起動確認:

```bash
docker build -f web/Dockerfile -t claude-a11y-admin .
docker run --rm -p 8080:8080 \
  -e GOOGLE_SHEET_ID="your-google-sheet-id" \
  -e BASIC_AUTH_USERNAME="admin" \
  -e BASIC_AUTH_PASSWORD="change-me" \
  claude-a11y-admin
```

別ターミナル:

```bash
curl -fsS http://localhost:8080/healthz
```

## 運用上の注意

- Cloud Run Service では `--no-allow-unauthenticated` を必ず指定します。
- `AUTH_DISABLED_FOR_TESTS` は本番に設定しません。
- Cloud Run では `GOOGLE_APPLICATION_CREDENTIALS` を設定しません。
- runner は Sheets 行を更新するため、まずは `--tasks 1 --parallelism 1` と小さめの `--limit` で開始してください。
- 複数 runner を同時実行すると同じ `queued` 行を処理する可能性があるため、単一実行を基本にしてください。
- Secret Manager には API キーやパスワードだけを置き、サービスアカウント JSON 鍵は置かないでください。
