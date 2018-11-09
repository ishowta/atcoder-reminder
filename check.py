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

contest_list_file_path = 'data/contest_list.pickle'

def readContestList():
	if os.path.exists(contest_list_file_path):
		with open(contest_list_file_path, 'rb') as fh:
			return pickle.load(fh)
	else:
		return pd.DataFrame([])

def fetchContestList():
	all_contest_list = util.scrapeTable(url='https://beta.atcoder.jp/contests?lang=ja')
	if len(all_contest_list) != 3:
		# 予定されているコンテストが一つも無い場合
		return pd.DataFrame([])
	raw_contest_list = all_contest_list[1]
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

def isNew(contest, previous_contest_list):
	return contest['id'] not in previous_contest_list['id']

def hasHeldToday(contest):
	return ( contest['date'] - dt.datetime.now() ) < dt.timedelta(days=1)

def setContestReminder(new_contest_list):

	# Remind notify contest
	for i,contests in new_contest_list.groupby('date').__iter__():
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

	# Remind generate contest result
	for i,contests in new_contest_list.groupby('finish_date').__iter__():
		contest_id_list = [c['id'] for i,c in contests.iterrows()]
		util.setReminder(
			contests.iloc[0]['finish_date'] + dt.timedelta(seconds=30),
			'cd '+os.getcwd()+' && python3 generate.py '+' '.join(contest_id_list)+' >> log/generate.log 2>&1'
		)

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

	logger.info('Read previous contest list')
	previous_contest_list = readContestList()

	logger.info('Fetch contest list')
	fetched_contest_list = fetchContestList()

	logger.info('Select new contest list')
	# コンテスト情報がいきなり変更されるかもしれないので、開始まで一日を切ったコンテストのみ登録する
	new_contest_list = fetched_contest_list[ fetched_contest_list.apply(lambda contest: hasHeldToday(contest) and isNew(contest, previous_contest_list), axis=1) ]

	logger.info('Store contest list')
	previous_contest_list.append(new_contest_list).to_pickle(contest_list_file_path)

	embed()

	if new_contest_list.empty:
		logger.info("There is no new contest.")
		exit()

	logger.info('Set contest reminder')
	setContestReminder(new_contest_list)
