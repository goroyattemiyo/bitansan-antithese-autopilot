# 微炭酸アンチテーゼ Threads Autopilot

微炭酸アンチテーゼ（ねたみ・そねみ）の Threads 毎日画像付き投稿を自動化するための専用リポジトリです。

## 目的

- 投稿ネタを `posts/ideas.yml` で管理
- OpenAI API で投稿文・画像プロンプト・WebP画像を生成
- WebP画像を GitHub に保存
- WebP画像を Catbox にアップロード
- Catbox の画像URLを使って Threads API へ画像付き投稿
- 投稿ログ、インサイト、削除操作を管理

## 保存方針

- PNG / JPG 原本は GitHub に保存しない
- GitHub に保存する画像は WebP のみ
- 投稿用の `image_url` は Catbox の WebP URL を使う
- 投稿予定は `posts/schedule.yml` で管理

## 必要な GitHub Secrets

Settings → Secrets and variables → Actions → Repository secrets に以下を登録してください。

| Secret | 用途 |
|---|---|
| `BIKANSAN_ACCESS_TOKEN` | Threads 長期アクセストークン |
| `BIKANSAN_USER_ID` | Threads user id |
| `OPENAI_API_KEY` | 投稿文・画像生成用 OpenAI API key |
| `CATBOX_USERHASH` | Catbox userhash。匿名アップロードなら未登録でも可 |
| `ALLOW_THREADS_DELETE` | 削除ワークフロー用。削除時だけ `true` にする |

## 最初の検証順

1. `Test Threads API` workflow でプロフィール確認
2. `Test Threads API` workflow で短いテキスト投稿
3. `Delete Threads Post` workflow でテスト投稿を削除
4. `Prepare Weekly Posts` workflow で `ideas.yml` から投稿予定・画像を生成
5. `Post Daily` workflow で画像付き投稿をテスト
6. `Collect Insights` workflow でインサイト取得

## ディレクトリ構成

```text
.github/workflows/       GitHub Actions
assets/webp/             GitHubに保存するWebP画像
posts/                   投稿ネタ・投稿予定・ログ
prompts/                 キャラ設定・生成プロンプト
src/                     Python実装
```

## 主なワークフロー

| Workflow | 実行方法 | 用途 |
|---|---|---|
| `test-threads.yml` | 手動 | Threads接続・テキスト投稿テスト |
| `prepare-weekly.yml` | 手動 | ideas.yml から投稿文・WebP画像・Catbox URLを生成 |
| `post-daily.yml` | cron / 手動 | 当日分をThreadsへ投稿 |
| `collect-insights.yml` | cron / 手動 | 投稿済みIDのインサイト収集 |
| `delete-post.yml` | 手動のみ | 指定投稿の削除 |

## 注意

- アクセストークンや API key は絶対にコミットしないでください。
- 削除ワークフローは `workflow_dispatch` の手動実行専用です。
- 画像生成・Catboxアップロードは API / 外部サービスに依存します。初回は少数件でテストしてください。
