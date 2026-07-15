# 微炭酸アンチテーゼ Threads Autopilot

微炭酸アンチテーゼ（ねたみ・そねみ）のThreads投稿を、GitHub ActionsとThreads APIで自動化する専用リポジトリです。

## 現在の投稿方式

`Post Scheduler` は朝・夜の予約枠ごとに3回だけ予定を確認し、期限を過ぎた候補から親投稿を1件だけ処理します。

```yaml
scheduled_at: '2026-07-06T07:00:00+09:00'
delay_min_minutes: 2
delay_max_minutes: 14
delay_minutes: 9
publish_after: '2026-07-06T07:09:00+09:00'
status: ready
```

`delay_minutes` と `publish_after` は最初の通常実行時に一度だけ決まり、以後は再抽選されません。手動のdry runはAPI投稿もYAML更新も行いません。

### 遅延投稿の安全保留

自動実行時、`publish_after` から120分以上経過した未着手の `ready` 投稿は、過去分をまとめて送信しないよう `held` に変更します。

```yaml
status: held
hold_reason: automatic_lateness_exceeded_120_minutes
held_at: '2026-07-15T08:00:00+09:00'
```

`held` は自動投稿されません。内容と日時を確認したうえで、安定IDを指定した手動実行から再開できます。すでに親投稿や返信が成功している `posting` は、重複防止のため保留せず続きから再開します。

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

親投稿または返信の成功直後に `thread_progress` を保存し、次のAPI呼び出しより先にGitへcheckpointします。途中失敗後に対象IDを指定して手動実行すると、成功済みIDを再送せず未完了返信から再開します。

ThreadsへのPOSTは自動再試行しません。投稿成功後に応答だけ失われた場合、同じPOSTを再送すると重複するおそれがあるためです。インサイトなどの読み取りGETだけ、一時エラー時に最大3回再試行します。

### 投稿画像

このリポジトリは公開リポジトリのため、画像は `raw.githubusercontent.com` の公開URLをそのまま使用します。通常投稿時に第三者サービスへ自動再アップロードしません。

### 順序保護

同じ `series_id`、`series`、`sequence_group`、または曲投稿グループで、後続投稿がすでに `posted` の場合は古い未投稿を自動送信しません。必要な投稿だけ次で解除できます。

```yaml
allow_out_of_order: true
```

切替時点ですでに期限超過していた未投稿には `migration_hold: true` が自動設定されます。自動送信されず、安定IDを指定した手動実行でのみ対象にできます。

## インサイト取得

`Collect Insights` は毎週月曜21:07 JSTに実行します。

- 対象は直近30件、かつ投稿後30日以内
- 1リクエストごとに標準1秒待機
- 旧ログと月別ログを横断して同日重複を防止
- 手動で `force: true` を指定した場合だけ同日再取得

## ディレクトリ構成

```text
.github/workflows/       GitHub Actions
assets/webp/             投稿画像
posts/schedules/         週単位の投稿予定
posts/posted_log.yml     投稿ログ
posts/insights/          月別インサイト履歴
src/                     Python実装
tests/                   安全機構・スケジューラーテスト
```

## 主なワークフロー

| Workflow | 実行方法 | 用途 |
|---|---|---|
| `Post Scheduler` | 予約枠ごとに3回 / 手動 | 全予定確認、1件投稿、ツリー再開、遅延投稿の保留 |
| `Collect Insights` | 毎週月曜21:07 JST / 手動 | 直近投稿の指標取得 |
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
- `error` と `held` は自動投稿しない
- 定期実行1回につき親投稿は1件だけ
- workflowは `concurrency` で直列化
- API成功後は投稿IDを保存・checkpointしてから次のAPIへ進む
- ThreadsへのPOSTは自動再試行しない
- GETの再試行は指数バックオフ付きで最大3回
- 120分を超えた未着手投稿は自動保留する
- インサイト取得は週1回、リクエスト間隔を空ける
- アクセストークンやAPI keyをログ、YAML、READMEへ記録しない
