# 微炭酸アンチテーゼ Threads Autopilot

微炭酸アンチテーゼ（ねたみ・そねみ）のThreads投稿を、GitHub ActionsとThreads APIで自動化する専用リポジトリです。

## 現在の投稿方式

`Post Scheduler` が5分間隔で全スケジュールを確認し、期限を過ぎた候補から親投稿を1件だけ処理します。

```yaml
scheduled_at: '2026-07-06T07:00:00+09:00'
delay_min_minutes: 2
delay_max_minutes: 14
delay_minutes: 9
publish_after: '2026-07-06T07:09:00+09:00'
status: ready
```

`delay_minutes` と `publish_after` は最初の通常実行時に一度だけ決まり、以後は再抽選されません。手動のdry runはAPI投稿もYAML更新も行いません。

### 後方互換

`scheduled_at` がない投稿は、`date` と `time_slot` から次のJST時刻を生成します。

| time_slot | JST |
|---|---:|
| morning | 07:00 |
| noon | 12:00 |
| afternoon | 15:00 |
| evening | 17:00 |
| night | 20:00 |
| summary | 21:00 |

### ツリー投稿

親投稿と返信は同じActions内で直列処理します。返信間隔は投稿ごとに設定できます。

```yaml
thread_delay_min_seconds: 8
thread_delay_max_seconds: 25
```

親投稿または返信の成功直後に `thread_progress` を保存し、次のAPI呼び出しより先にGitへcheckpointします。途中失敗後に `status: ready` へ戻すと、成功済みIDを再送せず未完了返信から再開します。

### 順序保護

同じ `series_id`、`series`、`sequence_group`、または曲投稿グループで、後続投稿がすでに `posted` の場合は古い未投稿を自動送信しません。必要な投稿だけ次で解除できます。

```yaml
allow_out_of_order: true
```

切替時点ですでに期限超過していた未投稿には `migration_hold: true` が自動設定されます。自動送信されず、安定IDを指定した手動実行でのみ対象にできます。

## ディレクトリ構成

```text
.github/workflows/       GitHub Actions
assets/webp/             投稿画像
posts/schedules/         週単位の投稿予定
posts/posted_log.yml     投稿ログ
src/                     Python実装
tests/                   スケジューラーテスト
```

## 主なワークフロー

| Workflow | 実行方法 | 用途 |
|---|---|---|
| `Post Scheduler` | 5分間隔 / 手動 | 全予定確認、1件投稿、ツリー再開 |
| `Post Morning (Legacy Manual Only)` | 手動 | 廃止案内のみ |
| `Process Image Zip` | 手動 | 画像のWebP化と週YAML反映 |
| `Add Song URLs` | 手動 | 曲投稿へのツリー返信追加 |

## 必要なGitHub Secrets

Secretsはリポジトリへ書かず、GitHub ActionsのRepository secretsで管理します。

- `BIKANSAN_ACCESS_TOKEN`
- `BIKANSAN_USER_ID`
- 画像生成など別workflowで必要な既存Secret

## 安全要件

- `posted` は再送しない
- `error` は自動再試行しない
- 定期実行1回につき親投稿は1件だけ
- workflowは `concurrency` で直列化
- API成功後は投稿IDを保存・checkpointしてから次のAPIへ進む
- アクセストークンやAPI keyをログ、YAML、READMEへ記録しない
