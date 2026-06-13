#!/usr/bin/env bash
set -euo pipefail

# Cloud Run デプロイ用サンプルです。
# 1) このファイルをコピーして使ってください。
# 2) 本物の API キーやパスワードはこのファイルに書かず、実行時の非表示プロンプトで入力してください。
# 3) Cloud Run では GOOGLE_APPLICATION_CREDENTIALS を設定しません。
# 4) Web 管理画面は --no-allow-unauthenticated でデプロイします。

PROJECT_ID="${PROJECT_ID:-your-project-id}"
REGION="${REGION:-asia-northeast1}"
REPOSITORY="${REPOSITORY:-claude-a11y}"
IMAGE_TAG="${IMAGE_TAG:-$(date +%Y%m%d-%H%M%S)}"
IMAGE="${IMAGE:-${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/claude-a11y:${IMAGE_TAG}}"

SHEET_ID="${SHEET_ID:-your-google-sheet-id}"
WEB_SERVICE="${WEB_SERVICE:-claude-a11y-admin}"
RUNNER_JOB="${RUNNER_JOB:-claude-a11y-runner}"
WEB_SA="${WEB_SA:-claude-a11y-admin@${PROJECT_ID}.iam.gserviceaccount.com}"
RUNNER_SA="${RUNNER_SA:-claude-a11y-runner@${PROJECT_ID}.iam.gserviceaccount.com}"
SCHEDULER_SA="${SCHEDULER_SA:-claude-a11y-scheduler@${PROJECT_ID}.iam.gserviceaccount.com}"

SECRET_BASIC_AUTH_PASSWORD="${SECRET_BASIC_AUTH_PASSWORD:-claude-a11y-basic-auth-password}"
SECRET_GEMINI_API_KEY="${SECRET_GEMINI_API_KEY:-claude-a11y-gemini-api-key}"
SECRET_ANTHROPIC_API_KEY="${SECRET_ANTHROPIC_API_KEY:-claude-a11y-anthropic-api-key}"

SITE="${SITE:-saga-city}"
LIMIT="${LIMIT:-10}"
LLM_PROVIDER="${LLM_PROVIDER:-gemini}"
BASIC_AUTH_USERNAME="${BASIC_AUTH_USERNAME:-admin}"
CREATE_SCHEDULER="${CREATE_SCHEDULER:-0}"
SCHEDULER_CRON="${SCHEDULER_CRON:-0 2 * * *}"
SCHEDULER_TIME_ZONE="${SCHEDULER_TIME_ZONE:-Asia/Tokyo}"

require_replaced() {
  local name="$1"
  local value="$2"
  case "${value}" in
    your-*|"" )
      echo "ERROR: ${name} を実際の値に置き換えてください。" >&2
      exit 1
      ;;
  esac
}

upsert_secret_from_prompt() {
  local secret_name="$1"
  local prompt="$2"
  local value=""

  read -rsp "${prompt}: " value
  echo
  if [[ -z "${value}" ]]; then
    echo "ERROR: ${secret_name} の値が空です。" >&2
    exit 1
  fi

  if gcloud secrets describe "${secret_name}" >/dev/null 2>&1; then
    printf '%s' "${value}" | gcloud secrets versions add "${secret_name}" --data-file=-
  else
    printf '%s' "${value}" | gcloud secrets create "${secret_name}" --data-file=-
  fi
  unset value
}

if [[ "${1:-}" == "--help" ]]; then
  cat <<USAGE
Usage: PROJECT_ID=... SHEET_ID=... [REGION=asia-northeast1] $0

Optional environment variables:
  REPOSITORY, IMAGE_TAG, WEB_SERVICE, RUNNER_JOB, WEB_SA, RUNNER_SA
  SECRET_BASIC_AUTH_PASSWORD, SECRET_GEMINI_API_KEY, SECRET_ANTHROPIC_API_KEY
  SITE, LIMIT, LLM_PROVIDER, BASIC_AUTH_USERNAME
  CREATE_SCHEDULER=1 SCHEDULER_CRON="0 2 * * *" SCHEDULER_TIME_ZONE="Asia/Tokyo"
USAGE
  exit 0
fi

require_replaced PROJECT_ID "${PROJECT_ID}"
require_replaced SHEET_ID "${SHEET_ID}"

if [[ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]]; then
  echo "ERROR: Cloud Run デプロイ前提では GOOGLE_APPLICATION_CREDENTIALS を設定しないでください。" >&2
  exit 1
fi

gcloud config set project "${PROJECT_ID}"

gcloud artifacts repositories describe "${REPOSITORY}" --location "${REGION}" >/dev/null 2>&1 \
  || gcloud artifacts repositories create "${REPOSITORY}" \
    --repository-format docker \
    --location "${REGION}" \
    --description "Claude A11y Cloud Run images"

upsert_secret_from_prompt "${SECRET_BASIC_AUTH_PASSWORD}" "Basic auth password"

case "${LLM_PROVIDER}" in
  gemini)
    LLM_SECRET_NAME="${SECRET_GEMINI_API_KEY}"
    LLM_SECRET_ENV="GEMINI_API_KEY=${SECRET_GEMINI_API_KEY}:latest"
    upsert_secret_from_prompt "${SECRET_GEMINI_API_KEY}" "Gemini API key"
    ;;
  anthropic)
    LLM_SECRET_NAME="${SECRET_ANTHROPIC_API_KEY}"
    LLM_SECRET_ENV="ANTHROPIC_API_KEY=${SECRET_ANTHROPIC_API_KEY}:latest"
    upsert_secret_from_prompt "${SECRET_ANTHROPIC_API_KEY}" "Anthropic API key"
    ;;
  *)
    echo "ERROR: LLM_PROVIDER は gemini または anthropic を指定してください。" >&2
    exit 1
    ;;
esac

gcloud secrets add-iam-policy-binding "${SECRET_BASIC_AUTH_PASSWORD}" \
  --member "serviceAccount:${WEB_SA}" \
  --role roles/secretmanager.secretAccessor

gcloud secrets add-iam-policy-binding "${LLM_SECRET_NAME}" \
  --member "serviceAccount:${WEB_SA}" \
  --role roles/secretmanager.secretAccessor

gcloud secrets add-iam-policy-binding "${LLM_SECRET_NAME}" \
  --member "serviceAccount:${RUNNER_SA}" \
  --role roles/secretmanager.secretAccessor

cat > cloudbuild.local.yaml <<EOF_BUILD
steps:
- name: 'gcr.io/cloud-builders/docker'
  args: ['build', '-f', 'web/Dockerfile', '-t', '${IMAGE}', '.']
images:
- '${IMAGE}'
EOF_BUILD

gcloud builds submit --config cloudbuild.local.yaml .

gcloud run deploy "${WEB_SERVICE}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "${WEB_SA}" \
  --set-env-vars "GOOGLE_SHEET_ID=${SHEET_ID},BASIC_AUTH_USERNAME=${BASIC_AUTH_USERNAME},LLM_PROVIDER=${LLM_PROVIDER}" \
  --set-secrets "BASIC_AUTH_PASSWORD=${SECRET_BASIC_AUTH_PASSWORD}:latest,${LLM_SECRET_ENV}" \
  --no-allow-unauthenticated

if gcloud run jobs describe "${RUNNER_JOB}" --region "${REGION}" >/dev/null 2>&1; then
  JOB_VERB="update"
else
  JOB_VERB="create"
fi

gcloud run jobs "${JOB_VERB}" "${RUNNER_JOB}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "${RUNNER_SA}" \
  --command python \
  --args "-m,a11y_runner,run,--sheet,${SHEET_ID},--site,${SITE},--limit,${LIMIT}" \
  --set-env-vars "LLM_PROVIDER=${LLM_PROVIDER}" \
  --set-secrets "${LLM_SECRET_ENV}" \
  --tasks 1 \
  --parallelism 1 \
  --task-timeout 3600

SERVICE_URL="$(gcloud run services describe "${WEB_SERVICE}" --region "${REGION}" --format 'value(status.url)')"
echo "Health check: ${SERVICE_URL}/healthz"
curl -fsS -H "Authorization: Bearer $(gcloud auth print-identity-token)" "${SERVICE_URL}/healthz"
echo

if [[ "${CREATE_SCHEDULER}" == "1" ]]; then
  gcloud iam service-accounts describe "${SCHEDULER_SA}" >/dev/null 2>&1 \
    || gcloud iam service-accounts create claude-a11y-scheduler \
      --display-name "Claude A11y scheduler invoker"

  gcloud run jobs add-iam-policy-binding "${RUNNER_JOB}" \
    --region "${REGION}" \
    --member "serviceAccount:${SCHEDULER_SA}" \
    --role roles/run.invoker

  if gcloud scheduler jobs describe "${RUNNER_JOB}-nightly" --location "${REGION}" >/dev/null 2>&1; then
    SCHEDULER_VERB="update"
  else
    SCHEDULER_VERB="create"
  fi

  gcloud scheduler jobs "${SCHEDULER_VERB}" http "${RUNNER_JOB}-nightly" \
    --location "${REGION}" \
    --schedule "${SCHEDULER_CRON}" \
    --time-zone "${SCHEDULER_TIME_ZONE}" \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${RUNNER_JOB}:run" \
    --http-method POST \
    --oauth-service-account-email "${SCHEDULER_SA}" \
    --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform"
fi

echo "Done. 手動 Job 実行例: gcloud run jobs execute ${RUNNER_JOB} --region ${REGION} --wait"
