# Atcoder reminder

## Setup

- require `curl, at, cron, python3, chromium-browser`(v69(v69が無い場合は`util.py`の`ChromeDriverManager('2.41')`を適宜修正する))
- `pip3 install -r requirements.txt`
- cronにcheck.pyの定期的な実行をするように設定する
  - 例：`00 1-23/3 * * * cd [path]/atcoder && python3 check.py >> log/check.log 2>&1`
- config-sample.iniを元にconfig.iniを作成

## Others

- コンテスト結果はjsで書いてhtmlをChromeから開いてしまっているので、とても環境に依存している…（macOSだとレイアウトが崩れる）
- チャートグラフの描画はAtcoderのサイトのjsをそのまま使ってしまっている…
- Type check
  - `mypy .`
