# Web管理画面

このディレクトリは、スプレッドシートと Drive を正として使うアクセシビリティ管理画面です。Google スプレッドシートが唯一の管理台帳であり、この画面は既存の `Jobs`、`Review`、`Runs`、`Metrics` タブを読み書きし、実行時は `a11y_runner` と `process_page` を再利用します。

## 主な機能

- `site` と `status` で絞り込めるジョブ一覧。
- ジョブ作成と、共有ランナーを使った保護付き実行。
- `old`、`ai`、`gold` の HTML プレビュー。
- CMS 由来のノイズを取り除いた構造差分。
- 要確認の判断（`accept`、`edit`、`skip`）、承認、gold 反映、指標サマリ。

## セキュリティ方針

このサービスを直接公開しないでください。自治体の HTML を表示し、Drive とスプレッドシートへ書き込めるためです。

推奨する公開方法は次のとおりです。

1. Cloud Run へデプロイし、組織の方針に合わせてアクセス制限を設定します。
2. Cloud Run を Identity-Aware Proxy など組織の認証で保護し、対象の Google Workspace グループまたはドメインだけに許可します。
3. サービスアカウントには、対象スプレッドシートと Drive フォルダだけへの権限を付けます。

ローカルまたは限定公開向けの代替として HTTP Basic 認証を使えます。`BASIC_AUTH_USERNAME` と `BASIC_AUTH_PASSWORD` を両方設定してください。認証設定がない場合、API は `503` を返します。`AUTH_DISABLED_FOR_TESTS=true` はユニットテスト専用です。

## サービスアカウント設定

1. Google Cloud のサービスアカウントを作成します。
2. プラットフォーム上どうしても必要な場合を除き、広いプロジェクト権限は付けません。
3. 対象 Google スプレッドシートを、サービスアカウントのメールアドレスへ編集者として共有します。
4. 入力、AI 出力、gold 出力の Drive フォルダも同じサービスアカウントへ共有します。
5. Cloud Run では実行サービスアカウントの Application Default Credentials を使います。`GOOGLE_APPLICATION_CREDENTIALS` やサービスアカウント JSON 鍵ファイルは使いません。ローカル開発では `gcloud auth application-default login` を使います。

## 環境変数

ローカル開発では `web/.env.example` をコピーして使えます。本番で主に使う変数は次のとおりです。

- `GOOGLE_SHEET_ID` または `SHEET_ID`: 対象スプレッドシートの ID。
- `GOOGLE_APPLICATION_CREDENTIALS`: Cloud Run では設定しません。ローカルで JSON 鍵を使う例外時だけ、リポジトリ外のファイルパスを指定します。
- `BASIC_AUTH_USERNAME` / `BASIC_AUTH_PASSWORD`: Identity-Aware Proxy などを使わず Basic 認証にする場合だけ設定します。
- `PORT`: Cloud Run では自動設定されます。

Drive フォルダ ID は、ランナーと同じくスプレッドシートの `Config` 行から読みます。

- `drive_input_folder_id`
- `drive_output_ai_folder_id`
- `drive_output_gold_folder_id`

## ローカル開発

バックエンド:

```bash
pip install -r web/requirements.txt
export GOOGLE_SHEET_ID=...
export BASIC_AUTH_USERNAME=admin
export BASIC_AUTH_PASSWORD=change-me
uvicorn web.backend.app:app --reload --port 8080
```

フロントエンド:

```bash
cd web/frontend
npm install
npm run dev
```

Vite 開発時は、必要に応じて `/api` をバックエンドへプロキシするか、ビルド済み Docker コンテナを使ってください。

## Docker と Cloud Run

ローカルビルド例:

```bash
docker build -f web/Dockerfile -t claude-a11y-admin .
docker run --rm -p 8080:8080 \
  -e GOOGLE_SHEET_ID=... \
  -e BASIC_AUTH_USERNAME=admin \
  -e BASIC_AUTH_PASSWORD=change-me \
  claude-a11y-admin
```

Cloud Run デプロイ例（詳細は [`docs/deploy-cloud-run.md`](../docs/deploy-cloud-run.md) を参照）:

```bash
gcloud run deploy claude-a11y-admin \
  --source . \
  --region asia-northeast1 \
  --service-account claude-a11y-admin@PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars GOOGLE_SHEET_ID=YOUR_SHEET_ID \
  --set-secrets BASIC_AUTH_PASSWORD=claude-a11y-basic-auth-password:latest \
  --no-allow-unauthenticated
```

その後、組織で使う HTTPS ロードバランサまたは Cloud Run の経路に Identity-Aware Proxy などを設定し、対象グループまたはドメインだけにアクセスを許可してください。
