# Apps Script control-plane UX

This directory contains the container-bound Apps Script source for the Phase 2 Sheets UX.
Apps Script only changes job flags, installs UX helpers, and sends notifications; the Python runner remains responsible for HTML processing.

## Files

- `appsscript.json`: manifest with minimal scopes and `Asia/Tokyo` timezone.
- `Code.gs`: custom menu and selected-row actions.
- `Setup.gs`: data validation, conditional formatting, and trigger installation.
- `Notify.gs`: status transition email / Google Chat notifications.
- `../.clasp.json.example`: template for local clasp configuration from the repository root. (`apps_script/.clasp.json.example` is also provided for users who run clasp from this directory.)

## Push with clasp

1. Install and authenticate clasp.

   ```bash
   npm install -g @google/clasp
   clasp login
   ```

2. Open the Phase 1 control spreadsheet, create or open its bound Apps Script project, and copy the script ID from **Project Settings**.
3. Create `.clasp.json` in the repository root from the example and set `scriptId`.

   ```bash
   cp .clasp.json.example .clasp.json
   ```

4. Push the source.

   ```bash
   clasp push
   ```

## Script Properties

Set these in Apps Script **Project Settings > Script Properties**. Do not commit secrets.

| Key | Purpose | Required |
|---|---|---|
| `RUNNER_ENDPOINT` | Optional direct-run HTTP endpoint for `runSelectedNow` | No |
| `RUNNER_TOKEN` | Bearer token for the direct-run endpoint | Required when endpoint requires auth |
| `CHAT_WEBHOOK` | Google Chat Incoming Webhook URL | No |
| `NOTIFY_DEFAULT_EMAIL` | Fallback notification recipient when `Jobs.reviewer` is blank | Recommended |

## First-time setup

1. Reload the spreadsheet and confirm the `A11y` menu appears.
2. Run **A11y > シート整備** to apply dropdowns and conditional formatting.
3. Run **A11y > 通知トリガを設置** to install the 5-minute `notifyOnStatusChange` trigger.
4. Use **選択行を実行（キュー投入）** for the default flag-based flow. Use **今すぐ実行（直接）** only when `RUNNER_ENDPOINT` is configured.
