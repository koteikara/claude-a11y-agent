# Cloud Run 残作業チェックリスト

このチェックリストは、Cloud Run Service / Cloud Run Jobs の現在の構築・運用状況に合わせた確認用メモです。Web 管理画面は **Cloud Run Service**、runner は **Cloud Run Jobs**、秘密情報は **Secret Manager** で運用します。

> 重要: Cloud Run では `GOOGLE_APPLICATION_CREDENTIALS` を設定しません。サービスアカウント JSON 鍵も作成・保存・コミットしません。Web 管理画面は必ず `--no-allow-unauthenticated` を維持し、`--allow-unauthenticated` は使いません。

> 今回の運用では Cloud Scheduler による定期実行は作成しません。必要なときだけ Cloud Run Jobs を手動実行します。

## 0. 現在完了していること

- [x] Google Cloud プロジェクト作成済み
- [x] 必要 API 有効化済み
- [x] Cloud Run 用サービスアカウント作成済み
- [x] Secret Manager に以下を登録済み
  - `claude-a11y-basic-auth-password`
  - `claude-a11y-gemini-api-key`
- [x] Secret へのアクセス権付与済み
- [x] Artifact Registry にイメージ push 済み
- [x] Cloud Run Service `claude-a11y-admin` デプロイ済み
- [x] Cloud Run Jobs `claude-a11y-runner` 作成済み
- [x] Cloud Run Jobs の手動実行成功済み
- [x] `/docs` が `401 Authentication required` になることを確認済み
- [x] 定期実行は作成しない方針

## 1. PowerShell の作業準備

Windows PowerShell では、まずリポジトリへ移動します。

```powershell
cd C:\Users\nakagawa.to\claude-a11y-agent
```

PowerShell 変数例:

```powershell
$PROJECT_ID="your-project-id"
$REGION="asia-northeast1"
$REPOSITORY="claude-a11y"
$IMAGE_TAG=Get-Date -Format "yyyyMMdd-HHmmss"
$IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/claude-a11y:$IMAGE_TAG"

$SHEET_ID="your-google-sheet-id"
$WEB_SERVICE="claude-a11y-admin"
$RUNNER_JOB="claude-a11y-runner"
$WEB_SA="claude-a11y-admin@$PROJECT_ID.iam.gserviceaccount.com"
$RUNNER_SA="claude-a11y-runner@$PROJECT_ID.iam.gserviceaccount.com"

$SECRET_BASIC_AUTH_PASSWORD="claude-a11y-basic-auth-password"
$SECRET_GEMINI_API_KEY="claude-a11y-gemini-api-key"

gcloud config set project $PROJECT_ID
```

bash 変数例:

```bash
export PROJECT_ID="your-project-id"
export REGION="asia-northeast1"
export REPOSITORY="claude-a11y"
export IMAGE_TAG="$(date +%Y%m%d-%H%M%S)"
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/claude-a11y:${IMAGE_TAG}"

export SHEET_ID="your-google-sheet-id"
export WEB_SERVICE="claude-a11y-admin"
export RUNNER_JOB="claude-a11y-runner"
export WEB_SA="claude-a11y-admin@${PROJECT_ID}.iam.gserviceaccount.com"
export RUNNER_SA="claude-a11y-runner@${PROJECT_ID}.iam.gserviceaccount.com"

export SECRET_BASIC_AUTH_PASSWORD="claude-a11y-basic-auth-password"
export SECRET_GEMINI_API_KEY="claude-a11y-gemini-api-key"

gcloud config set project "${PROJECT_ID}"
```

PowerShell の継続行はバッククォート `` ` `` です。行末のバッククォートの後ろに空白を入れないでください。bash の `\` と混同しないでください。

## 2. Google Cloud Console で確認すること

### 2-1. Sheets / Drive の共有

- [ ] 対象スプレッドシートが `WEB_SA` と `RUNNER_SA` に共有されている。
- [ ] Drive 入力フォルダが `RUNNER_SA` から読める。
- [ ] Drive AI 出力フォルダが `RUNNER_SA` から書ける。
- [ ] Drive gold 出力フォルダが `WEB_SA` / `RUNNER_SA` から必要に応じて読める・書ける。

### 2-2. Sheets の `Config` タブ

Drive フォルダ ID は環境変数ではなく、Sheets の `Config` タブから読みます。

| key | value |
|---|---|
| `drive_input_folder_id` | 入力 HTML フォルダ ID |
| `drive_output_ai_folder_id` | AI 下書き HTML 出力フォルダ ID |
| `drive_output_gold_folder_id` | 承認済み gold HTML 出力フォルダ ID |
| `llm_provider` | 例: `gemini` |
| `default_site` | 例: `saga-city` |
| `run_mode` | 例: `batch` |

## 3. Artifact Registry / Cloud Build

Artifact Registry リポジトリがない場合は作成します。

```powershell
gcloud artifacts repositories describe $REPOSITORY --location $REGION

gcloud artifacts repositories create $REPOSITORY `
  --repository-format docker `
  --location $REGION `
  --description "Claude A11y Cloud Run images"
```

`describe` が成功する場合、`create` は不要です。`NOT_FOUND` の場合だけ作成してください。

Cloud Build は `-f web/Dockerfile` を直接渡さず、`cloudbuild.local.yaml` を使います。

```powershell
@"
steps:
- name: 'gcr.io/cloud-builders/docker'
  args: ['build', '-f', 'web/Dockerfile', '-t', '${IMAGE}', '.']
images:
- '${IMAGE}'
"@ | Set-Content cloudbuild.local.yaml -Encoding UTF8

gcloud builds submit --config cloudbuild.local.yaml .
```

PowerShell にログが出ない場合は build ID で状態を確認します。

```powershell
gcloud builds describe BUILD_ID --format="value(status)"
```

## 4. Cloud Run Service 確認

Web 管理画面は `--no-allow-unauthenticated` を維持します。

```powershell
gcloud run deploy $WEB_SERVICE `
  --image $IMAGE `
  --region $REGION `
  --service-account $WEB_SA `
  --set-env-vars "GOOGLE_SHEET_ID=$SHEET_ID,BASIC_AUTH_USERNAME=admin,LLM_PROVIDER=gemini" `
  --set-secrets "BASIC_AUTH_PASSWORD=$SECRET_BASIC_AUTH_PASSWORD`:latest,GEMINI_API_KEY=$SECRET_GEMINI_API_KEY`:latest" `
  --no-allow-unauthenticated
```

ブラウザで開くユーザーには `roles/run.invoker` を付与します。

```powershell
$WEB_VIEWER="user:viewer@example.com"
gcloud run services add-iam-policy-binding $WEB_SERVICE `
  --region $REGION `
  --member $WEB_VIEWER `
  --role roles/run.invoker
```

PowerShell で FastAPI 到達を確認します。

```powershell
$SERVICE_URL = gcloud run services describe claude-a11y-admin --region asia-northeast1 --format "value(status.url)"

curl.exe -i `
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" `
  "$SERVICE_URL/docs"
```

`401 Authentication required` が返れば、Cloud Run IAM 認証は通っており、アプリ側 Basic 認証まで到達しています。

`/healthz` は現行実装では `{"status":"ok"}` を返します。ただし Cloud Run IAM 認証は引き続き必要です。

```powershell
curl.exe -i `
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" `
  "$SERVICE_URL/healthz"
```

## 5. Cloud Run Jobs 確認

PowerShell では `--args` を必ずクォートします。

```powershell
gcloud run jobs update $RUNNER_JOB `
  --image $IMAGE `
  --region $REGION `
  --service-account $RUNNER_SA `
  --command "python" `
  --args="-m,a11y_runner,run,--sheet,$SHEET_ID,--site,saga-city,--limit,1" `
  --set-env-vars "LLM_PROVIDER=gemini" `
  --set-secrets "GEMINI_API_KEY=$SECRET_GEMINI_API_KEY`:latest" `
  --tasks 1 `
  --parallelism 1 `
  --task-timeout 3600
```

同名 Job がない場合は `update` を `create` に置き換えます。

手動実行:

```powershell
gcloud run jobs execute $RUNNER_JOB `
  --region $REGION `
  --wait
```

`Jobs` タブにヘッダーしかない場合や `status=queued` の対象行がない場合、runner は `n_total: 0` で正常終了します。これは環境構築失敗ではなく、処理対象行がないだけです。

## 6. Jobs タブ運用の注意

`input_file` は Google Drive 入力フォルダ内のファイル名またはパスに加えて、`http://` / `https://` の実在 URL も指定できます。URL 入力では runner が HTML を取得し、`body_xpath` による本文抽出を行います。

`body_xpath` 優先順は次のとおりです。

1. Jobs 行の `body_xpath`
2. Sites タブの `body_xpath`
3. Config タブの `body_xpath`
4. 未指定なら `body` 要素全体

Jobs タブ例:

| site | page_id | input_file | body_xpath | status |
|---|---|---|---|---|
| saga-city | test-url-001 | `https://www.example.jp/path/to/page.html` | `//*[@id="contents-in"]` | queued |

`check_gold` は Google Drive 入力フォルダの old HTML と gold HTML の比較が対象で、URL から old HTML を再取得しません。詳細は [`url-input-and-body-xpath.md`](url-input-and-body-xpath.md) を参照してください。

## 7. 定期実行

今回の運用では Cloud Scheduler は作成しません。ドキュメント上も定期実行は「必要な場合のみ」の任意扱いです。メインの確認は Cloud Run Jobs の手動実行で行います。

## 8. 最終チェック

- [ ] Web 管理画面は Cloud Run Service として動いている。
- [ ] runner は Cloud Run Jobs として動いている。
- [ ] Secret Manager から Secret を注入している。
- [ ] Cloud Run Service / Jobs に `GOOGLE_APPLICATION_CREDENTIALS` を設定していない。
- [ ] サービスアカウント JSON 鍵を作成・保存・コミットしていない。
- [ ] Web 管理画面は `--no-allow-unauthenticated` のまま。
- [ ] 閲覧者に必要な `roles/run.invoker` を付与している。
- [ ] `/docs` の `401 Authentication required` で FastAPI 到達を確認した。
- [ ] `/healthz` の戻り値が `{"status":"ok"}` であることを理解している。
- [ ] Cloud Run Jobs を手動実行できる。
- [ ] `n_total: 0` は処理対象行なしの場合の正常終了だと理解している。
- [ ] Cloud Scheduler は今回作成しない。
