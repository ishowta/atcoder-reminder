# Setup
- Require
    - curl, at, cron, python3, chromium-browser
- pythonのライブラリをインストール
    - `pip3 install -r requirements.txt`
- cronにcheck.pyの定期的な実行をするように設定する
    - 例：`00 1-23/3 * * * cd [path]/atcoder && python3 check.py >> log/check.log 2>&1`
- config-sample.iniを元にconfig.iniを作成
