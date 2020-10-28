# Atcoder reminder

It notifies you of Atcoder events and displays your team's competition results in a table and chart.

## Setup

- Require
  - `curl`
  - `at`
  - `cron`
  - `python3`
  - `chromium browser`
  - `chromedriver`
  - `zlib`
  - `libjpeg`
- Install python library
  - ex: `pip3 install -r requirements.txt`
- Regist `check.py` in cron
  - ex：`00 1-23/3 * * * cd [project_root_path]/atcoder && python3 check.py >> log/check.log 2>&1`
- Make `config.ini` file with reference to `config-sample.ini`

## Others

- Linting & Type check
  - `./check.sh`
- Test
  - `./test.sh`
