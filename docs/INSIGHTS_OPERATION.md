# Threadsインサイト運用

## 取得方針

インサイトは定期取得しません。ユーザーがチャットで明示的に依頼したときだけ、ChatGPTが `requests/collect_insights.yml` を更新し、その変更を検知した `Collect Insights On Demand` が1回だけ実行します。

アカウント審査中など、Threads APIへのアクセスを止めたい期間はRepository variable `THREADS_INSIGHTS_ENABLED` を未設定・削除・`false` のいずれかにします。要求ファイルが更新されても、この変数が文字列 `true` でなければAPIへアクセスしません。

## チャット要求ファイル

```yaml
enabled: true
request_id: '20260715-210000'
requested_at: '2026-07-15T21:00:00+09:00'
limit: 30
active_days: 30
request_delay_seconds: 1.0
force: false
```

### パラメータ

- `enabled`: 実行するときだけ `true`
- `request_id`: 要求ごとに異なる1〜64文字のID
- `requested_at`: 監査用のJST日時
- `limit`: `posts/posted_log.yml` の末尾から確認する件数。最大30件
- `active_days`: 投稿後何日以内を対象にするか。最大90日
- `request_delay_seconds`: 投稿ごとの取得間隔。最低1秒
- `force`: 同日取得済みの投稿も再取得するか。通常は `false`

## 二重実行防止

`requests/collect_insights_state.yml` に、最後に正常処理した `request_id` を保存します。

```yaml
last_processed_request_id: '20260715-210000'
processed_at: '2026-07-15T21:01:05+09:00'
collected_count: 18
parameters:
  limit: 30
  active_days: 30
  request_delay_seconds: 1.0
  force: false
```

Actionsの再実行や同じ要求の再送があっても、同一 `request_id` は処理しません。workflowは毎回 `main` の最新状態をcheckoutするため、過去のrunを再実行した場合も最新の処理済みIDを参照します。

## API安全制限

- 読み取り専用のインサイトGETだけを使用
- 1回の対象は最大30件
- 対象期間は最大90日
- リクエスト間隔は最低1秒
- GETの一時エラーだけ最大3回再試行
- 同じJST日付で取得済みの投稿は通常スキップ
- `force: true` は検証目的で明示された場合だけ使用
- 投稿作成・公開・削除APIは呼ばない

## 保存ファイル

### `posts/insights/YYYY-MM.yml`

月ごとの時系列履歴です。投稿ごとの数値推移を確認するときに使います。

各レコードには以下を保存します。

- 投稿ID
- 取得日時
- 予約ID・予約日時・投稿日時
- カテゴリ・シリーズID
- ルート投稿／返信の区別
- views / likes / replies / reposts / quotes
- engagement_rate_pct
- reply_rate_pct
- spread_rate_pct
- APIエラー

### `posts/insights_log.yml`

月別方式へ移行する前の旧履歴です。同日重複判定と最新一覧生成では引き続き参照しますが、新しい結果は追記しません。

### `posts/insights_latest.yml`

各投稿の最新の正常取得結果だけをまとめた一覧です。ChatGPTで直近投稿を比較分析するときは、まずこちらを読みます。

## チャットでの利用例

```text
直近30件、投稿後30日以内のThreadsインサイトを取得してください。
取得後、返信率を重視して直近投稿を分析し、
良かった要素と弱かった要素を整理してください。
```

依頼を受けたChatGPTは、一意の `request_id` を付けて要求ファイルを更新します。Actions完了後に `posts/insights_latest.yml` と投稿予定・履歴を読み、結果を回答します。

## 指標

- 反応率 = （いいね + 返信 + リポスト + 引用）÷ 表示数
- 返信率 = 返信数 ÷ 表示数
- 拡散率 = （リポスト + 引用）÷ 表示数

投稿数が少ない間は平均値だけで結論を出さず、本文・キャラクター・問いかけ形式・投稿時刻も合わせて個別に確認します。
