import pandas as pd
import datetime as dt
import os
from IPython import embed
import configparser
import pickle
import logging
import util
import slack
from typing import Callable

contest_list_file_path = 'data/contest_list.pickle'


def readContestList() -> pd.DataFrame:
    if os.path.exists(contest_list_file_path):
        with open(contest_list_file_path, 'rb') as fh:
            return pickle.load(fh)
    else:
        return pd.DataFrame(
            columns={'id', 'date', 'title', 'link', 'time', 'finish_date', 'is_rating', 'rating_limit'})


def fetchContestList() -> pd.DataFrame:
    # サイトには開催中のコンテスト・開催予定のコンテスト・終了したコンテストが掲載されている
    all_raw_contest_list = util.scrapeTable(
        url='https://beta.atcoder.jp/contests?lang=ja')
    if len(all_raw_contest_list) != 3:
        # 予定されているコンテストが一つも無い場合
        return pd.DataFrame(
            columns={'id', 'date', 'title', 'link', 'time', 'finish_date', 'is_rating', 'rating_limit'})
    raw_contest_list = all_raw_contest_list[1]
    """
    返ってくるテーブルの型と例（pandas側の仕様上セルに入っているのはstringなので、すべて`split(',')`して取り出す）
    raw_contest_list = [
      {
        開始時刻: [
          (url) 'http://www.timeanddate.com/worldclock/fixedtime.html?iso=20181123T2100&p1=248',
          ('%Y-%m-%d %H:%M:%S+0900') '2018-11-23 21:00:00+0900'
        ],
        コンテスト名: [
          (link) '/contests/ddcc2019-qual',
          (string) 'DISCO presents ディスカバリーチャンネル コードコンテスト2019 予選'
        ],
        時間: [
            (h:m) '01:30'
        ]
        Rated対象: [
            (`x` | `All` | `~ a`(a:int)) '~ 1199'
        ]
      }
    ]
  """
    date_list = raw_contest_list['開始時刻'].splitBy(1).map(
        lambda x: dt.datetime.strptime(x[:-5], '%Y-%m-%d %H:%M:%S')
    )
    time_list = raw_contest_list['時間'].splitBy(0).map(
        lambda x: dt.timedelta() if x == '∞' else dt.timedelta(hours=int(x.split(':')[0]), minutes=int(x.split(':')[1])))

    return pd.DataFrame({
        'id': raw_contest_list['コンテスト名'].splitBy(0),
        'date': date_list,
        'title': raw_contest_list['コンテスト名'].splitBy(1),
        'link': raw_contest_list['コンテスト名'].splitBy(0),
        'time': time_list,
        'finish_date': [d + t for d, t in zip(date_list, time_list)],
        'is_rating': raw_contest_list['Rated対象'].splitBy(0).map(lambda x: x != '×'),
        'rating_limit': raw_contest_list['Rated対象'].splitBy(0).map(lambda x: -1 if x == '×' else 99999 if x == 'All' else int(x[2:])),
    })


def isNew(contest: pd.DataFrame, previous_contest_list: pd.DataFrame) -> bool:
    return contest['id'] not in previous_contest_list['id'].values


def hasHeldToday(contest: pd.DataFrame) -> bool:
    return (contest['date'] - dt.datetime.now()) < dt.timedelta(days=1)


def setContestReminder(new_contest_list: pd.DataFrame) -> None:

    # 12時間前の通知と15分前通知の登録
    for i, contests in new_contest_list.groupby('date').__iter__():
        contests_link_str_list = [
            '<https://beta.atcoder.jp' + c['link'] + '|' + c['title'] + ('' if c['is_rating'] else '（レート変動なし）') + '>'
            for i, c in contests.iterrows()
        ]
        Slack.setReminder(
            contests.iloc[0]['date'] - dt.timedelta(hours=12),
            '今日の' + contests.iloc[0]['date'].strftime('%H:%M') + 'から ' + '・'.join(contests_link_str_list) + ' が行われます'
        )
        Slack.setReminder(
            contests.iloc[0]['date'] - dt.timedelta(minutes=15),
            '開始15分前です'
        )

    # コンテスト結果通知の登録
    for i, contests in new_contest_list.groupby('finish_date').__iter__():
        contest_id_list = [c['id'] for i, c in contests.iterrows()]
        util.setReminder(
            contests.iloc[0]['finish_date'] + dt.timedelta(seconds=30),
            'cd ' + os.getcwd() + ' && python3 generate.py ' + ' '.join(contest_id_list) + ' >> log/generate.log 2>&1')


if __name__ == '__main__':
    logging.basicConfig()
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    config = configparser.ConfigParser()
    config.read('config.ini')

    Slack = slack.Slack(
        channel=config['slack']['channel_name'],
        token=config['slack']['token']
    )

    logger.info('Read previous contest list')
    registered_contest_list = readContestList()

    logger.info('Fetch current contest list')
    fetched_contest_list = fetchContestList()

    logger.info('Select new contest list')
    # コンテスト情報がいきなり変更されるかもしれないので、開始まで一日を切ったコンテストのみ登録する
    new_contest_list = fetched_contest_list[fetched_contest_list.apply(
        lambda contest: hasHeldToday(contest) and isNew(contest, registered_contest_list), axis=1)]

    if new_contest_list.empty:
        logger.info("There is no new contest.")
        exit()

    logger.info('Save contest list')
    registered_contest_list.append(new_contest_list).to_pickle(contest_list_file_path)

    logger.info('Set contest reminder')
    setContestReminder(new_contest_list)
