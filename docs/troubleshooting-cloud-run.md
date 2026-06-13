# Cloud Run トラブルシュート

Cloud Run Service / Cloud Run Jobs 構築時に発生しやすい問題と確認方法です。Secret 値、API キー、パスワード、サービスアカウント JSON はログやドキュメントに貼り付けないでください。

## `gcloud` が認識されない

原因:

- Google Cloud CLI が未インストール。
- Google Cloud CLI のパスが Windows の `PATH` に入っていない。
- インストール後に PowerShell を開き直していない。

確認:

```powershell
gcloud --version
```

対処:

- Google Cloud CLI をインストールする。
- インストール後に PowerShell を開き直す。
- それでも認識されない場合は、Google Cloud CLI の `bin` ディレクトリが `PATH` に含まれているか確認する。

## `gcloud artifacts repositories describe` が `NOT_FOUND` になる

原因:

- Artifact Registry リポジトリがまだ作成されていません。
- `PROJECT_ID`、`REGION`、`REPOSITORY` のいずれかが誤っています。

対処:

```powershell
gcloud artifacts repositories create $REPOSITORY `
  --repository-format docker `
  --location $REGION `
  --description "Claude A11y Cloud Run images"
```

## `gcloud builds submit -f` が `unrecognized arguments` になる

原因:

- `gcloud builds submit` では Dockerfile 指定用の `-f web/Dockerfile` を直接渡せません。

対処:

- `cloudbuild.local.yaml` を作成し、`gcloud builds submit --config cloudbuild.local.yaml .` を使います。
- 具体例は [`deploy-cloud-run.md`](deploy-cloud-run.md#artifact-registry--cloud-build) を参照してください。

## Cloud Build ログが PowerShell に出ない

原因:

- PowerShell 側にストリーミングログが表示されない場合があります。

確認:

```powershell
gcloud builds describe BUILD_ID --format="value(status)"
```

`BUILD_ID` は `gcloud builds submit` の出力や Google Cloud Console の Cloud Build 履歴で確認します。

## Cloud Run のブラウザアクセスが `Forbidden` になる

原因:

- Cloud Run Service が `--no-allow-unauthenticated` で保護されています。
- ブラウザでログインしている Google アカウントに `roles/run.invoker` がありません。
- `roles/run.invoker` を付与したユーザーと、ブラウザのログインアカウントが異なります。

対処:

```powershell
$WEB_VIEWER="user:viewer@example.com"
gcloud run services add-iam-policy-binding $WEB_SERVICE `
  --region $REGION `
  --member $WEB_VIEWER `
  --role roles/run.invoker
```

## `/docs` が `401 Authentication required` になる

意味:

- Cloud Run IAM 認証は通っています。
- FastAPI アプリに到達しています。
- アプリ側の Basic 認証で止まっています。

これは、Cloud Run IAM 認証とアプリ到達の確認としては正常です。Basic 認証ユーザー名とパスワードを入力して Web 管理画面に進めるか確認してください。

PowerShell での確認例:

```powershell
$SERVICE_URL = gcloud run services describe claude-a11y-admin --region asia-northeast1 --format "value(status.url)"

curl.exe -i `
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" `
  "$SERVICE_URL/docs"
```

## `/healthz` の確認で混乱する

現行実装では `/healthz` はアプリ側 Basic 認証の対象外で、成功時に次を返します。

```json
{"status":"ok"}
```

ただし、Cloud Run Service 自体を `--no-allow-unauthenticated` にしているため、未公開 Service では ID トークンなしのアクセスは Cloud Run IAM 側で拒否されます。Cloud Run 上では ID トークン付きで確認してください。

```powershell
$SERVICE_URL = gcloud run services describe claude-a11y-admin --region asia-northeast1 --format "value(status.url)"

curl.exe -i `
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" `
  "$SERVICE_URL/healthz"
```

`/docs` で `401 Authentication required` を確認するほうが、Cloud Run IAM 認証を通過して FastAPI の Basic 認証まで到達したことを判断しやすい場合があります。

## Cloud Run Jobs 実行結果が `n_total: 0` になる

意味:

- runner は正常に起動しています。
- `Jobs` タブに `status=queued` の処理対象行がありません。

対処:

- `Jobs` タブに対象行があるか確認する。
- `status` が `queued` になっているか確認する。
- `site` が runner の `--site` 指定と一致しているか確認する。
