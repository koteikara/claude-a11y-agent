# Cloud Run デプロイ手順

この手順は、Web 管理画面を **Cloud Run Service**、runner を **Cloud Run Jobs** として運用するための管理者向けメモです。Cloud Run Service / Cloud Run Jobs の環境構築は一通り完了しており、今後はこの構成を前提に運用します。

## 現在の推奨運用

- Web 管理画面は Cloud Run Service `claude-a11y-admin` として運用します。
- runner は Cloud Run Jobs `claude-a11y-runner` として運用します。
- API キーや Basic 認証パスワードは Secret Manager から注入します。
- Cloud Run では `GOOGLE_APPLICATION_CREDENTIALS` を設定しません。
- サービスアカウント JSON 鍵は作成・保存・コミットしません。
- Web 管理画面は `--no-allow-unauthenticated` を維持します。
- Cloud Scheduler による定期実行は必須ではありません。今回の運用では作成せず、必要なときに Cloud Run Jobs を手動実行します。

初心者向けの残作業確認は [`cloud-run-setup-checklist.md`](cloud-run-setup-checklist.md)、トラブルシュートは [`troubleshooting-cloud-run.md`](troubleshooting-cloud-run.md)、URL 入力と `body_xpath` の仕様は [`url-input-and-body-xpath.md`](url-input-and-body-xpath.md) を参照してください。

## 前提

完了済みのもの:

- Google Cloud プロジェクト作成
- 必要 API 有効化
- Cloud Run 用サービスアカウント作成
- Secret Manager への Secret 登録
  - `claude-a11y-basic-auth-password`
  - `claude-a11y-gemini-api-key`
- Secret へのアクセス権付与
- Artifact Registry へのイメージ push
- Cloud Run Service `claude-a11y-admin` デプロイ
- Cloud Run Jobs `claude-a11y-runner` 作成
- Cloud Run Jobs の手動実行成功
- `/docs` が `401 Authentication required` になるところまで確認済み

`/docs` の `401 Authentication required` は、Cloud Run IAM 認証を通過し、FastAPI アプリ側の Basic 認証まで到達していることを示します。

## PowerShell の作業ディレクトリと変数

Windows PowerShell では、まずリポジトリへ移動します。

```powershell
cd C:\Users\nakagawa.to\claude-a11y-agent
```

PowerShell の変数設定例です。Secret 値、API キー、パスワード、実在の Sheet ID はここに書かず、実行環境で差し替えてください。

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

bash の場合は次の形式です。

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

PowerShell の継続行はバッククォート `` ` `` です。バッククォートの後ろに空白を置くと意図どおり継続されないため、行末の最後の文字にしてください。bash の `\` 継続行と混同しないでください。

## Artifact Registry / Cloud Build

`gcloud builds submit --tag $IMAGE -f web/Dockerfile .` のように `-f` を直接渡す方法は使いません。Cloud Build 設定ファイルを作成してから submit します。

### PowerShell

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

PowerShell に Cloud Build ログが表示されない場合は、build ID を使って状態を確認します。

```powershell
gcloud builds describe BUILD_ID --format="value(status)"
```

### bash

```bash
cat > cloudbuild.local.yaml <<EOF_BUILD
steps:
- name: 'gcr.io/cloud-builders/docker'
  args: ['build', '-f', 'web/Dockerfile', '-t', '${IMAGE}', '.']
images:
- '${IMAGE}'
EOF_BUILD

gcloud builds submit --config cloudbuild.local.yaml .
```

## Cloud Run Service のデプロイ

Web 管理画面は未認証公開しません。必ず `--no-allow-unauthenticated` を指定します。

```powershell
gcloud run deploy $WEB_SERVICE `
  --image $IMAGE `
  --region $REGION `
  --service-account $WEB_SA `
  --set-env-vars "GOOGLE_SHEET_ID=$SHEET_ID,BASIC_AUTH_USERNAME=admin,LLM_PROVIDER=gemini" `
  --set-secrets "BASIC_AUTH_PASSWORD=$SECRET_BASIC_AUTH_PASSWORD`:latest,GEMINI_API_KEY=$SECRET_GEMINI_API_KEY`:latest" `
  --no-allow-unauthenticated
```

閲覧するユーザーまたはグループには `roles/run.invoker` を付与します。

```powershell
$WEB_VIEWER="user:viewer@example.com"
gcloud run services add-iam-policy-binding $WEB_SERVICE `
  --region $REGION `
  --member $WEB_VIEWER `
  --role roles/run.invoker
```

ブラウザで `Forbidden` になる場合は、`roles/run.invoker` を付与したアカウントと、ブラウザでログインしている Google アカウントが一致しているか確認してください。

## Web 到達確認

Cloud Run Service は IAM 認証で保護されているため、PowerShell では ID トークン付きで確認します。

```powershell
$SERVICE_URL = gcloud run services describe claude-a11y-admin --region asia-northeast1 --format "value(status.url)"

curl.exe -i `
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" `
  "$SERVICE_URL/docs"
```

`401 Authentication required` が返れば、Cloud Run IAM 認証は通っており、FastAPI アプリ側の Basic 認証まで到達しています。

現行実装の `/healthz` は Basic 認証の対象外で、成功時に次を返します。

```json
{"status":"ok"}
```

Cloud Run 上では `/healthz` も Cloud Run IAM の保護を受けるため、ID トークン付きで確認します。

```powershell
curl.exe -i `
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" `
  "$SERVICE_URL/healthz"
```

`/healthz` はアプリの生存確認、`/docs` の `401` は Cloud Run IAM 通過と Basic 認証到達の確認、と役割を分けて考えると混乱しにくくなります。

## Cloud Run Jobs の作成・更新

PowerShell では `--args` を必ず 1 つの文字列としてクォートしてください。`--args -m,...` のように書くと PowerShell 側でパースエラーになることがあります。

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

新規作成時は `update` を `create` に置き換えます。

手動実行:

```powershell
gcloud run jobs execute $RUNNER_JOB `
  --region $REGION `
  --wait
```

`Jobs` タブにヘッダーしかない、または `status=queued` の対象行がない場合、runner は `n_total: 0` で正常終了します。これは環境構築失敗ではありません。

## Jobs タブと URL 入力の現状

runner は `input_file` を Google Drive 入力フォルダ内のファイル名またはパス、または `http://` / `https://` の実在 URL として扱います。`input_file` が空欄なら `site/page_id.html` を Drive 入力から読みます。

URL 入力では、URL から取得した HTML を `body_xpath` で本文部分だけにトリミングして処理できます。詳細仕様は [`url-input-and-body-xpath.md`](url-input-and-body-xpath.md) に分離しています。

`body_xpath` の優先順は次のとおりです。

1. Jobs 行の `body_xpath`
2. Sites タブの `body_xpath`
3. Config タブの `body_xpath`
4. 未指定なら `body` 要素全体

Jobs タブ例:

| site | page_id | input_file | body_xpath | status |
|---|---|---|---|---|
| saga-city | test-url-001 | `https://www.example.jp/path/to/page.html` | `//*[@id="contents-in"]` | queued |

`check_gold` は Google Drive 入力フォルダの old HTML と gold HTML の比較が対象で、URL から old HTML を再取得しません。

## 定期実行は任意

今回の運用では Cloud Scheduler は作成しません。必要になった場合だけ、Scheduler 用サービスアカウントを作成し、対象 Cloud Run Job に `roles/run.invoker` を付与してからスケジュールを作成してください。メイン手順では手動実行を基本とします。

## 関連トラブルシュート

今回発生した問題の対処は [`troubleshooting-cloud-run.md`](troubleshooting-cloud-run.md) にまとめています。

- `gcloud` が認識されない。
- Artifact Registry の `describe` が `NOT_FOUND` になる。
- `gcloud builds submit -f` が `unrecognized arguments` になる。
- Cloud Build ログが PowerShell に出ない。
- Cloud Run ブラウザアクセスが `Forbidden` になる。
- `/docs` が `401 Authentication required` になる。
- Cloud Run Jobs 実行結果が `n_total: 0` になる。
