# Cloud Run 残作業チェックリスト

このチェックリストは、Google Cloud プロジェクト作成、必要 API の有効化、Cloud Run 用サービスアカウント作成が終わった後に実施する残作業です。Web 管理画面は **Cloud Run Service**、runner は **Cloud Run Jobs**、秘密情報は **Secret Manager** で運用します。

> 重要: Cloud Run では `GOOGLE_APPLICATION_CREDENTIALS` を設定しません。サービスアカウント JSON 鍵も作成・保存・コミットしません。Web 管理画面のデプロイでは必ず `--no-allow-unauthenticated` を指定し、`--allow-unauthenticated` は使いません。

> 権限: Google Cloud の Owner 権限を前提にしません。実行者には、Artifact Registry への書き込み、Cloud Build の実行、Cloud Run Service/Jobs の管理、Secret Manager の Secret 作成・version 追加・IAM 付与、対象サービスアカウントの `iam.serviceAccounts.actAs` など、組織ポリシーに沿った必要最小限の権限を付与してください。

## 0. 置き換える値

以下だけを自分の環境に合わせて置き換えれば、以降のコマンドをそのまま使えます。

```bash
export PROJECT_ID="your-project-id"
export REGION="asia-northeast1"
export REPOSITORY="claude-a11y"
export IMAGE_TAG="$(date +%Y%m%d-%H%M%S)"
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/claude-a11y:${IMAGE_TAG}"

export SHEET_ID="your-google-sheet-id"
export DRIVE_INPUT_FOLDER_ID="your-drive-input-folder-id"
export DRIVE_OUTPUT_AI_FOLDER_ID="your-drive-output-ai-folder-id"
export DRIVE_OUTPUT_GOLD_FOLDER_ID="your-drive-output-gold-folder-id"

export WEB_SERVICE="claude-a11y-admin"
export RUNNER_JOB="claude-a11y-runner"
export WEB_SA="claude-a11y-admin@${PROJECT_ID}.iam.gserviceaccount.com"
export RUNNER_SA="claude-a11y-runner@${PROJECT_ID}.iam.gserviceaccount.com"
export SCHEDULER_SA="claude-a11y-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"

export SECRET_BASIC_AUTH_PASSWORD="claude-a11y-basic-auth-password"
export SECRET_GEMINI_API_KEY="claude-a11y-gemini-api-key"
export SECRET_ANTHROPIC_API_KEY="claude-a11y-anthropic-api-key"

gcloud config set project "${PROJECT_ID}"
```

## 1. Google Cloud Console で人間が実施する操作

### 1-1. スプレッドシートをサービスアカウントへ共有する

- [ ] 対象スプレッドシートをブラウザで開く。
- [ ] 右上の **共有** を押す。
- [ ] `WEB_SA` のメールアドレスを **編集者** として追加する。
- [ ] `RUNNER_SA` のメールアドレスを **編集者** として追加する。
- [ ] 通知メールが不要なら通知のチェックを外す。
- [ ] 共有を保存する。

確認する値:

```text
Web 管理画面: claude-a11y-admin@PROJECT_ID.iam.gserviceaccount.com
runner: claude-a11y-runner@PROJECT_ID.iam.gserviceaccount.com
```

### 1-2. Google Drive フォルダをサービスアカウントへ共有する

次の 3 つのフォルダを、それぞれ `WEB_SA` と `RUNNER_SA` に共有します。runner が読み書きし、Web 管理画面も表示・承認で参照するためです。

- [ ] 入力 HTML フォルダ: `DRIVE_INPUT_FOLDER_ID`
- [ ] AI 下書き HTML 出力フォルダ: `DRIVE_OUTPUT_AI_FOLDER_ID`
- [ ] 承認済み gold HTML 出力フォルダ: `DRIVE_OUTPUT_GOLD_FOLDER_ID`

各フォルダでの操作:

- [ ] Google Drive でフォルダを開く。
- [ ] フォルダ名のメニューまたは右クリックから **共有** を開く。
- [ ] `WEB_SA` を追加する。
- [ ] `RUNNER_SA` を追加する。
- [ ] 入力フォルダは読み取りだけでよければ **閲覧者**、出力フォルダは **編集者** にする。迷う場合は運用開始時のみ 3 フォルダとも **編集者** にし、後で最小権限に調整する。
- [ ] 共有を保存する。

### 1-3. Sheets の `Config` タブに Drive フォルダ ID を入力する

スプレッドシートの `Config` タブに次の key/value を入れます。Drive フォルダ ID は環境変数ではなく、Sheets の `Config` から読みます。

| key | value |
|---|---|
| `drive_input_folder_id` | `DRIVE_INPUT_FOLDER_ID` の値 |
| `drive_output_ai_folder_id` | `DRIVE_OUTPUT_AI_FOLDER_ID` の値 |
| `drive_output_gold_folder_id` | `DRIVE_OUTPUT_GOLD_FOLDER_ID` の値 |
| `llm_provider` | 例: `gemini` |
| `default_site` | 例: `saga-city` |
| `run_mode` | 例: `batch` |

## 2. gcloud で実行できる操作

### 2-1. Artifact Registry リポジトリを確認・作成する

既に作成済みなら `describe` が成功します。失敗した場合だけ `create` を実行します。

```bash
gcloud artifacts repositories describe "${REPOSITORY}" \
  --location "${REGION}" \
  || gcloud artifacts repositories create "${REPOSITORY}" \
    --repository-format docker \
    --location "${REGION}" \
    --description "Claude A11y Cloud Run images"
```

### 2-2. Secret Manager に値を登録する

本物の API キーやパスワードをコマンドに直接貼ると、シェル履歴に残る可能性があります。次のように、画面に表示されない入力から Secret を作成または更新します。

Basic 認証パスワード:

```bash
read -rsp "Basic auth password: " BASIC_AUTH_PASSWORD_VALUE; echo
printf '%s' "${BASIC_AUTH_PASSWORD_VALUE}" | \
  gcloud secrets create "${SECRET_BASIC_AUTH_PASSWORD}" --data-file=- \
  || printf '%s' "${BASIC_AUTH_PASSWORD_VALUE}" | \
    gcloud secrets versions add "${SECRET_BASIC_AUTH_PASSWORD}" --data-file=-
unset BASIC_AUTH_PASSWORD_VALUE
```

Gemini API キー:

```bash
read -rsp "Gemini API key: " GEMINI_API_KEY_VALUE; echo
printf '%s' "${GEMINI_API_KEY_VALUE}" | \
  gcloud secrets create "${SECRET_GEMINI_API_KEY}" --data-file=- \
  || printf '%s' "${GEMINI_API_KEY_VALUE}" | \
    gcloud secrets versions add "${SECRET_GEMINI_API_KEY}" --data-file=-
unset GEMINI_API_KEY_VALUE
```

Anthropic API キーを使う場合だけ実行:

```bash
read -rsp "Anthropic API key: " ANTHROPIC_API_KEY_VALUE; echo
printf '%s' "${ANTHROPIC_API_KEY_VALUE}" | \
  gcloud secrets create "${SECRET_ANTHROPIC_API_KEY}" --data-file=- \
  || printf '%s' "${ANTHROPIC_API_KEY_VALUE}" | \
    gcloud secrets versions add "${SECRET_ANTHROPIC_API_KEY}" --data-file=-
unset ANTHROPIC_API_KEY_VALUE
```

### 2-3. Secret へのアクセス権を付与する

Web 管理画面には Basic 認証パスワードと、Web から利用する LLM の API キーだけを読めるようにします。runner には runner が利用する LLM の API キーだけを読めるようにします。

```bash
gcloud secrets add-iam-policy-binding "${SECRET_BASIC_AUTH_PASSWORD}" \
  --member "serviceAccount:${WEB_SA}" \
  --role roles/secretmanager.secretAccessor

gcloud secrets add-iam-policy-binding "${SECRET_GEMINI_API_KEY}" \
  --member "serviceAccount:${WEB_SA}" \
  --role roles/secretmanager.secretAccessor

gcloud secrets add-iam-policy-binding "${SECRET_GEMINI_API_KEY}" \
  --member "serviceAccount:${RUNNER_SA}" \
  --role roles/secretmanager.secretAccessor
```

Anthropic を使う場合だけ実行:

```bash
gcloud secrets add-iam-policy-binding "${SECRET_ANTHROPIC_API_KEY}" \
  --member "serviceAccount:${WEB_SA}" \
  --role roles/secretmanager.secretAccessor

gcloud secrets add-iam-policy-binding "${SECRET_ANTHROPIC_API_KEY}" \
  --member "serviceAccount:${RUNNER_SA}" \
  --role roles/secretmanager.secretAccessor
```

### 2-4. Artifact Registry へイメージをビルド・push する

```bash
gcloud builds submit \
  --tag "${IMAGE}" \
  -f web/Dockerfile \
  .
```

### 2-5. Cloud Run Service として Web 管理画面をデプロイする

このコマンドは `--no-allow-unauthenticated` を必ず含みます。認証なし公開にする `--allow-unauthenticated` は使いません。

```bash
gcloud run deploy "${WEB_SERVICE}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "${WEB_SA}" \
  --set-env-vars "GOOGLE_SHEET_ID=${SHEET_ID},BASIC_AUTH_USERNAME=admin,LLM_PROVIDER=gemini" \
  --set-secrets "BASIC_AUTH_PASSWORD=${SECRET_BASIC_AUTH_PASSWORD}:latest,GEMINI_API_KEY=${SECRET_GEMINI_API_KEY}:latest" \
  --no-allow-unauthenticated
```

デプロイ後、閲覧を許可する人またはグループに Cloud Run の呼び出し権限を付与します。Google Cloud Console で Cloud Run サービスの **権限** から設定しても、次の gcloud コマンドで設定しても構いません。

```bash
export WEB_VIEWER="user:viewer@example.com"
gcloud run services add-iam-policy-binding "${WEB_SERVICE}" \
  --region "${REGION}" \
  --member "${WEB_VIEWER}" \
  --role roles/run.invoker
```

### 2-6. `/healthz` を確認する

未公開 Service のため、ID トークンを付けて確認します。

```bash
SERVICE_URL="$(gcloud run services describe "${WEB_SERVICE}" --region "${REGION}" --format 'value(status.url)')"
curl -fsS -H "Authorization: Bearer $(gcloud auth print-identity-token)" "${SERVICE_URL}/healthz"
```

`{"ok":true}` が返れば起動確認は成功です。

### 2-7. Cloud Run Jobs を作成する

`--sheet` に `SHEET_ID` を渡す例です。Job でも `GOOGLE_APPLICATION_CREDENTIALS` は設定しません。

```bash
gcloud run jobs create "${RUNNER_JOB}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "${RUNNER_SA}" \
  --command python \
  --args -m,a11y_runner,run,--sheet,"${SHEET_ID}",--site,saga-city,--limit,10 \
  --set-env-vars "LLM_PROVIDER=gemini" \
  --set-secrets "GEMINI_API_KEY=${SECRET_GEMINI_API_KEY}:latest" \
  --tasks 1 \
  --parallelism 1 \
  --task-timeout 3600
```

同名 Job が既にある場合は、`create` の代わりに `update` を使います。

```bash
gcloud run jobs update "${RUNNER_JOB}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "${RUNNER_SA}" \
  --command python \
  --args -m,a11y_runner,run,--sheet,"${SHEET_ID}",--site,saga-city,--limit,10 \
  --set-env-vars "LLM_PROVIDER=gemini" \
  --set-secrets "GEMINI_API_KEY=${SECRET_GEMINI_API_KEY}:latest" \
  --tasks 1 \
  --parallelism 1 \
  --task-timeout 3600
```


Jobs タブには、Drive 入力フォルダ内のファイル名だけでなく、実在 URL も `input_file` に指定できます。URL 入力の場合は `body_xpath` に一致する本文要素だけを抽出し、AI 出力と gold 出力は既存の Drive 出力フォルダへ保存されます。

| job_id | site | page_id | input_file | body_xpath | provider | priority | status | promote_requested | notes |
|---|---|---|---|---|---|---:|---|---|---|
| `test-url-001` | `saga-city` | `test-url-001` | `https://www.example.jp/sample/page.html` | `//*[@id="contents-in"]` | `gemini` | `1` | `queued` | `false` | `URL input test` |

`body_xpath` を Jobs 行で空にした場合は、Config タブの `body_xpath` を fallback として参照します。

### 2-8. Job を手動実行する

```bash
gcloud run jobs execute "${RUNNER_JOB}" \
  --region "${REGION}" \
  --wait
```

失敗した場合は Cloud Run Jobs の実行詳細と Cloud Logging を確認します。

### 2-9. Cloud Scheduler から Job を定期実行する

Scheduler 用サービスアカウントが未作成の場合だけ作成します。

```bash
gcloud iam service-accounts describe "${SCHEDULER_SA}" \
  || gcloud iam service-accounts create claude-a11y-scheduler \
    --display-name "Claude A11y scheduler invoker"
```

Scheduler 用サービスアカウントに対象 Job の実行権限を付与します。

```bash
gcloud run jobs add-iam-policy-binding "${RUNNER_JOB}" \
  --region "${REGION}" \
  --member "serviceAccount:${SCHEDULER_SA}" \
  --role roles/run.invoker
```

毎日 2:00 に実行する例です。必要に応じて `--schedule` と `--time-zone` を変更してください。

```bash
gcloud scheduler jobs create http "${RUNNER_JOB}-nightly" \
  --location "${REGION}" \
  --schedule "0 2 * * *" \
  --time-zone "Asia/Tokyo" \
  --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${RUNNER_JOB}:run" \
  --http-method POST \
  --oauth-service-account-email "${SCHEDULER_SA}" \
  --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform"
```

既に Scheduler Job がある場合は、`create` の代わりに `update` を使います。

```bash
gcloud scheduler jobs update http "${RUNNER_JOB}-nightly" \
  --location "${REGION}" \
  --schedule "0 2 * * *" \
  --time-zone "Asia/Tokyo" \
  --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${RUNNER_JOB}:run" \
  --http-method POST \
  --oauth-service-account-email "${SCHEDULER_SA}" \
  --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform"
```

手動で Scheduler 経由の起動も確認できます。

```bash
gcloud scheduler jobs run "${RUNNER_JOB}-nightly" --location "${REGION}"
```

## 3. 最終確認

- [ ] スプレッドシートを `WEB_SA` / `RUNNER_SA` に共有した。
- [ ] Drive 3 フォルダを `WEB_SA` / `RUNNER_SA` に共有した。
- [ ] Sheets の `Config` タブに Drive フォルダ ID を入力した。
- [ ] Secret Manager に値を登録した。値は Git や `.env.example` に書いていない。
- [ ] Secret への `roles/secretmanager.secretAccessor` は必要なサービスアカウントにだけ付与した。
- [ ] イメージを Artifact Registry へ push した。
- [ ] Cloud Run Service は `--no-allow-unauthenticated` でデプロイした。
- [ ] `/healthz` が ID トークン付きで成功した。
- [ ] Cloud Run Jobs を作成し、手動実行が成功した。
- [ ] 必要な場合だけ Cloud Scheduler を作成した。
- [ ] Cloud Run Service / Jobs に `GOOGLE_APPLICATION_CREDENTIALS` を設定していない。
- [ ] サービスアカウント JSON 鍵を作成・保存していない。
