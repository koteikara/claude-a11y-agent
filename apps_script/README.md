# Apps Script 操作メニュー

このディレクトリには、第2段階のスプレッドシート操作用 Apps Script ソースがあります。Apps Script はジョブの状態フラグ変更、シート整備、通知だけを担当します。HTML の処理は Python ランナーが担当します。

## ファイル

- `appsscript.json`: 最小限の権限と `Asia/Tokyo` タイムゾーンを持つマニフェストです。
- `Code.gs`: カスタムメニューと選択行への操作です。
- `Setup.gs`: 入力規則、条件付き書式、トリガ設置です。
- `Notify.gs`: 状態変化時のメール通知と Google Chat 通知です。
- `../.clasp.json.example`: リポジトリ直下から clasp を使う場合の設定テンプレートです。`apps_script/.clasp.json.example` も、このディレクトリから clasp を実行する人向けに用意しています。

## clasp で反映する

1. clasp をインストールし、認証します。

   ```bash
   npm install -g @google/clasp
   clasp login
   ```

2. 第1段階の管理スプレッドシートを開き、紐付いた Apps Script プロジェクトを作成または開いて、プロジェクト設定からスクリプト ID をコピーします。
3. リポジトリ直下で `.clasp.json` を作り、`scriptId` を設定します。

   ```bash
   cp .clasp.json.example .clasp.json
   ```

4. ソースを反映します。

   ```bash
   clasp push
   ```

## スクリプトプロパティ

Apps Script のプロジェクト設定にあるスクリプトプロパティへ設定します。秘密情報をコミットしないでください。

| キー | 用途 | 必須 |
|---|---|---|
| `RUNNER_ENDPOINT` | `runSelectedNow` 用の任意の直接実行 HTTP エンドポイント | 任意 |
| `RUNNER_TOKEN` | 直接実行エンドポイント用の Bearer token | エンドポイントが認証を要求する場合 |
| `CHAT_WEBHOOK` | Google Chat Incoming Webhook URL | 任意 |
| `NOTIFY_DEFAULT_EMAIL` | `Jobs.reviewer` が空のときの通知先 | 推奨 |

## 初回設定

1. スプレッドシートを再読み込みし、`A11y` メニューが表示されることを確認します。
2. `A11y > シート整備` を実行し、プルダウンと条件付き書式を適用します。
3. `A11y > 通知トリガを設置` を実行し、5分間隔の `notifyOnStatusChange` トリガを設置します。
4. 通常のフラグ方式では `選択行を実行（キュー投入）` を使います。`今すぐ実行（直接）` は `RUNNER_ENDPOINT` が設定済みの場合だけ使います。
