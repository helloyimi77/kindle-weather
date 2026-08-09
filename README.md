# Kindle Weather

Kindleの古いブラウザで見やすい、東京の電子ペーパー気象板です。

## 表示内容
- 気圧
- 24時間の気圧変化
- 気温
- 湿度
- 更新時刻

## 使い方
1. このフォルダ一式をGitHubの新しいリポジトリへアップロード。
2. Settings → Pages → Build and deployment で `Deploy from a branch` を選択。
3. Branch は `main` / `(root)` を選択して保存。
4. Actions を有効にする。
5. Actions → `Update weather` → `Run workflow` を一度実行。
6. 公開URL `https://<ユーザー名>.github.io/<リポジトリ名>/` をKindleで開いてブックマーク。

GitHub Actionsは毎日06:00 JSTに更新します。

## データ
現在値はOpen-Meteoの東京座標データを利用しています。
古いKindle向けにJavaScriptを使わず、完成済みHTMLだけを配信します。
