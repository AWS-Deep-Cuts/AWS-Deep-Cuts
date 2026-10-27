# Deep Cuts Radar（PoC）

AWS SDK for Python（botocore）の Git 履歴には、AWS の全サービスの API モデル（`botocore/data/<service>/<api-version>/service-2.json`）の追加・変更・削除が 2012 年から記録されています。
これを読むと、**新サービスの登場（新譜）**、**API 変更が止まったサービス（沈黙）**、**SDK から消えたサービス（廃盤）** を、発表記事より客観的なデータとして追えます。

`sdk_radar.py` はその PoC です。Deep Cuts の題材探し・ライフサイクル監視・「サービスの寿命」分析コンテンツの土台として使うことを想定しています。

## 実行方法

```bash
# 中身（blob）を取らない部分クローンなので、数秒〜数十秒・十数 MB で済みます
git clone --filter=blob:none --no-checkout https://github.com/boto/botocore.git
python3 sdk_radar.py ./botocore --since 2025-07-01 > radar.md
```

`snapshot-2026-10-27.md` は 2026-10-27 時点（botocore HEAD: 2026-10-26）の実行結果です。

## 読み方の注意

- SDK への追加日・削除日は、サービスの発表日・提供終了日と一致しません（プレビュー前に追加されることも、提供終了から遅れて削除されることもあります）。
- 「沈黙」は「死」とは限りません。EventBridge Scheduler（`scheduler`）のように API が完成していて変更が不要なサービスもあります。沈黙はあくまで「ライフサイクルを確認すべきシグナル」です。
- 活動量は、40 サービス超を一括変更したコミット（エンドポイント定義の一斉再生成など）を除外して数えています。
