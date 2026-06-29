# セットアップ手順

## 1. GitHub Secrets を登録

Repository → Settings → Secrets and variables → Actions → Repository secrets に以下を登録します。

- `BIKANSAN_ACCESS_TOKEN`
- `BIKANSAN_USER_ID`
- `OPENAI_API_KEY`
- `CATBOX_USERHASH`（任意。Catbox匿名アップロードなら空でも可）
- `ALLOW_THREADS_DELETE`（削除テスト時だけ `true`）

## 2. Threads API 接続確認

Actions → `Test Threads API` → Run workflow。

最初は `post_text` を空欄にして `/me` の確認だけ行います。

想定アカウントの `id` / `username` が出たらOKです。

## 3. テキスト投稿テスト

Actions → `Test Threads API` → Run workflow。

`post_text` に以下のような短文を入れます。

```text
微炭酸アンチテーゼ 自動投稿テストです。あとで削除します。
```

投稿IDが返ればOKです。

## 4. 削除テスト

Secrets の `ALLOW_THREADS_DELETE` を一時的に `true` にします。

Actions → `Delete Threads Post` → Run workflow。

- `post_id`: 削除したい投稿ID
- `confirm`: `true`

削除後は、`ALLOW_THREADS_DELETE` を `false` または削除してください。

## 5. 画像生成・Catboxアップロード

`posts/ideas.yml` に投稿ネタを入れます。

Actions → `Prepare Weekly Posts` → Run workflow。

成功すると以下が更新されます。

- `assets/webp/*.webp`
- `posts/schedule.yml`

## 6. 画像付き投稿

Actions → `Post Daily` → Run workflow。

手動テストでは、`date` と `time_slot` を `schedule.yml` の値に合わせます。

## 7. インサイト収集

Actions → `Collect Insights` → Run workflow。

`posts/insights_log.yml` に結果が追記されます。
