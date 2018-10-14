import pandas as pd
import datetime as dt
import re
import os
import sys
from IPython import embed
import configparser
import pickle
import logging
import util
import slack

def fetchContestList():
	raw_contest_list = util.scrapeTable(url='https://beta.atcoder.jp/contests?lang=ja')[1]  # 予定されているコンテストが存在しない場合過去のコンテストテーブルを参照してしまう
	date_list = raw_contest_list['開始時刻'].map(lambda x: dt.datetime.strptime(x.split(',')[1][:-5], '%Y-%m-%d %H:%M:%S'))
	time_list = raw_contest_list['時間'].map(lambda x: dt.timedelta() if x == '∞' else dt.timedelta(hours=int(x[0:2]),minutes=int(x[3:5])))
	get = lambda i: lambda x: x.split(',')[i]
	return pd.DataFrame({
		'id'			: raw_contest_list['コンテスト名'].map(get(0)),
		'date'			: date_list,
		'title'			: raw_contest_list['コンテスト名'].map(get(1)),
		'link'			: raw_contest_list['コンテスト名'].map(get(0)),
		'time'			: time_list,
		'finish_date'	: [d+t for d,t in zip(date_list, time_list)],
		'is_rating'		: raw_contest_list['Rated対象'].map(lambda x: x != '×'),
		'rating_limit'	: raw_contest_list['Rated対象'].map(lambda x: -1 if x == '×' else 99999 if x == 'All' else int(x[2:])),
	})

def updateContestList(fetched_contest_list):
	fn = 'data/contest_list.pickle'
	if os.path.exists(fn):
		contest_list = pickle.load(open(fn, 'rb'))
		new_contest_list = fetched_contest_list[ ~fetched_contest_list['id'].isin(contest_list['id']) ]
		contest_list.append(new_contest_list).to_pickle(fn)
	else:
		fetched_contest_list.to_pickle(fn)
		new_contest_list = fetched_contest_list
	return new_contest_list

def setContestReminder(new_contest_list):
	for i,contests in new_contest_list.groupby('date').__iter__():
		# remind notify contest
		contests_link_str_list = ['<https://beta.atcoder.jp'+c['link']+'|'+c['title']+('' if c['is_rating'] else '（レート変動なし）')+'>' for i,c in contests.iterrows()]
		Slack.setReminder(
			config['slack']['channel_name'],
			contests.iloc[0]['date'] - dt.timedelta(hours=12),
			'今日の' + contests.iloc[0]['date'].strftime('%H:%M')+'から '+'・'.join(contests_link_str_list)+' が行われます'
		)
		Slack.setReminder(
			config['slack']['channel_name'],
			contests.iloc[0]['date'] - dt.timedelta(minutes=15),
			'開始15分前です'
		)
	for i,contests in new_contest_list.groupby('finish_date').__iter__():
		# remind generate contest result
		contest_id_list = [c['id'] for i,c in contests.iterrows()]
		util.setReminder(
			contests.iloc[0]['finish_date'] + dt.timedelta(seconds=30),
			'cd '+os.getcwd()+' && python3 generate.py '+' '.join(contest_id_list)+' >> log/generate.log 2>&1'
		)

def selectTodaysContestList(contest_list):
	return contest_list[contest_list['date'] - dt.datetime.now() < dt.timedelta(days=1)]

if __name__ == '__main__':
	logging.basicConfig()
	logger = logging.getLogger(__name__)
	logger.setLevel(logging.INFO)

	config = configparser.ConfigParser()
	config.read('config.ini')

	Slack = slack.Slack(
		token=config['slack']['token'],
		legacy_token=config['slack']['legacy_token'],
		name=config['slack']['name'],
		icon=config['slack']['icon'],
	)

	logger.info('fetch contest list')
	fetched_contest_list = fetchContestList()

	# コンテスト情報が変更されるかもしれないので、開始まで一日を切ったコンテストのみ登録する
	logger.info('select todays contest list')
	todays_contest_list = selectTodaysContestList(fetched_contest_list)

	logger.info('update contest list')
	new_contest_list = updateContestList(todays_contest_list)

	if len(new_contest_list) == 0:
		logger.info("contest")
		logger.info("There is no new contest.")
	else:
		logger.info('set contest reminder')
		setContestReminder(new_contest_list)
