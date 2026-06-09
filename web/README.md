# Web Admin MVP

Thin browser admin for the Phase 1 Sheets/Drive accessibility runner. The Google Sheet remains the single source of truth; this UI only reads and writes the existing `Jobs`, `Review`, `Runs`, and `Metrics` tabs and reuses `a11y_runner` / `process_page` for execution.

## Features

- Job list filtered by `site` and `status`.
- Job creation and guarded execution through the shared runner engine.
- Sanitized `old` / `ai` / `gold` HTML previews in sandboxed iframes.
- CMS-noise-stripped structural diff using the shared `strip_cms_attrs` normalization helpers.
- Review decisions (`accept`, `edit`, `skip`), approval, gold promotion, and metrics summaries.

## Security model

Do **not** publish this service directly. It renders municipality HTML and can write to Drive/Sheets.

Recommended deployment:

1. Deploy to Cloud Run with ingress restricted as appropriate for your organization.
2. Put Cloud Run behind Identity-Aware Proxy (IAP) and restrict access to your Google Workspace group/domain.
3. Use a service account that has access only to the target Sheet and Drive folders.

MVP fallback for local/private deployments is HTTP Basic Auth. Set both `BASIC_AUTH_USERNAME` and `BASIC_AUTH_PASSWORD`. The API returns `503` if neither IAP/OAuth nor Basic Auth is configured. `AUTH_DISABLED_FOR_TESTS=true` is only for unit tests.

## Service account setup

1. Create a Google Cloud service account.
2. Grant the service account no broad project role unless your platform requires it.
3. Share the target Google Sheet with the service account email as editor.
4. Share the input, ai output, and gold output Drive folders with the same service account.
5. Provide credentials through Application Default Credentials or a Secret Manager-mounted `GOOGLE_APPLICATION_CREDENTIALS` file.

## Environment

Copy `web/.env.example` for local development. Required production variables:

- `GOOGLE_SHEET_ID` (or `SHEET_ID`): target spreadsheet key.
- `GOOGLE_APPLICATION_CREDENTIALS`: optional when Cloud Run service-account ADC is available.
- `BASIC_AUTH_USERNAME` / `BASIC_AUTH_PASSWORD`: only when not using IAP/OAuth.
- `PORT`: set automatically by Cloud Run.

The actual Drive folder IDs are read from the Sheet `Config` rows used by Phase 1:

- `drive_input_folder_id`
- `drive_output_ai_folder_id`
- `drive_output_gold_folder_id`

## Local development

Backend:

```bash
pip install -r web/requirements.txt
export GOOGLE_SHEET_ID=...
export BASIC_AUTH_USERNAME=admin
export BASIC_AUTH_PASSWORD=change-me
uvicorn web.backend.app:app --reload --port 8080
```

Frontend:

```bash
cd web/frontend
npm install
npm run dev
```

For Vite development, proxy `/api` to the backend if needed or use the built Docker container.

## Docker / Cloud Run

Build locally:

```bash
docker build -f web/Dockerfile -t claude-a11y-admin .
docker run --rm -p 8080:8080 \
  -e GOOGLE_SHEET_ID=... \
  -e BASIC_AUTH_USERNAME=admin \
  -e BASIC_AUTH_PASSWORD=change-me \
  -v "$GOOGLE_APPLICATION_CREDENTIALS:/secrets/service-account.json:ro" \
  -e GOOGLE_APPLICATION_CREDENTIALS=/secrets/service-account.json \
  claude-a11y-admin
```

Example Cloud Run deploy:

```bash
gcloud run deploy claude-a11y-admin \
  --source . \
  --region asia-northeast1 \
  --service-account claude-a11y-admin@PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars GOOGLE_SHEET_ID=YOUR_SHEET_ID \
  --no-allow-unauthenticated
```

Then enable IAP for the HTTPS load balancer or Cloud Run path used by your organization, and grant access only to the intended group/domain.
