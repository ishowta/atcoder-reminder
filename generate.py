import os
import sys
import time
import json
import pickle
import argparse
import configparser
from pprint import pprint, pformat
import datetime as dt
import pandas as pd
import jinja2
from PIL import Image
from IPython import embed
import util
import slack
import logging
from typing import Optional

def fetchContestStatistics(link):
    def browserOp(driver):
        open = driver.find_element_by_id('standings-panel-heading')
        input = driver.find_element_by_id('input-affiliation')
        driver.execute_script("document.getElementsByClassName('form-inline')[0].style.display = 'block';")
        input.send_keys(config['atcoder']['affiliation'])

    raw_contest_statistics = util.scrapeTable(
        url='https://beta.atcoder.jp'+link+'/standings?lang=en',
        op=browserOp
    )[0].iloc[:-2]

    get = lambda i: lambda x: x.split(',')[i]
    result = pd.DataFrame({
        'rank'          : raw_contest_statistics.Rank.map(get(0)),
        'global_rank'   : raw_contest_statistics.Rank.map(lambda x: get(1)(x)[1:-1]),
        'name'          : raw_contest_statistics.User.map(get(1)),
        'score'         : raw_contest_statistics.Score.map(get(0)),
    })

    del raw_contest_statistics['Rank']
    del raw_contest_statistics['User']
    del raw_contest_statistics['Score']
    isCorrect = lambda item: len(item.split(',')) >= 2
    points = raw_contest_statistics.applymap(isCorrect)

    result['isJoin'] = [any(item != '-' for i,item in row.iteritems()) for i, row in raw_contest_statistics.iterrows()]

    return {'result':result, 'points':points}

def fetchUserList():
    def op(obj):
        try:
            if 'user-' in obj.span.attrs['class'][0]:
                color = obj.span.attrs['class'][0].replace('user-','')
                return obj.get_text(',', strip=True)+','+color
        except AttributeError:
            pass
        return None

    raw_user_list = util.scrapeTable(
        url='https://beta.atcoder.jp/ranking?f.Affiliation=' +
            config['atcoder']['affiliation'],
        tableOp=op
    )[1]

    get = lambda i: lambda x: x.split(',')[i]
    user_list = pd.DataFrame({
        'name'          : raw_user_list['User'].map(get(0)),
        'color'         : raw_user_list['User'].map(get(2)),
        'rating'        : raw_user_list['Rating'],
        'count'         : raw_user_list['Match'],
    })
    user_list['rank'] = list(range(1, len(user_list) + 1))

    return user_list

def generateContestResult(contest_list, contest_statistics_list, user_list):
    result_html = Jinja2.get_template('result.tpl.html').render({
        'contest_list': contest_list,
        'contest_statistics_list': contest_statistics_list,
        'user_list': user_list,
    })

    result_image = util.operateBrowser(
        page=result_html,
        return_screenshot=True,
        width=940,
        height=270,
    )

    return result_image

def waitRatingUpdate(contest_list, contest_statistics_list, pre_user_list):
    for time_count in range(0,60):
        # コンテストに参加しているレート対象者全員のレートが更新されているかチェック
        def checkChangeRate(user) -> Optional[bool]:
            pre_user = pre_user_list[pre_user_list['name'] == user['name']]
            if pre_user.empty:
                return None
            count_diff = int(user['count']) - int(pre_user['count'])
            if count_diff != 0:
                return True
            return False
        def getPreRating(user_result) -> Optional[int]:
            pre_user = pre_user_list[pre_user_list['name'] == user_result['name']]
            return (int)(pre_user['rating']) if not pre_user.empty else None
        def selectRatedUser(contest, statistics):
            def isRatedUser(user_result):
                rating = getPreRating(user_result)
                if rating is None:
                    return user_result['isJoin']
                else:
                    return user_result['isJoin'] and (rating <= (int)(contest['rating_limit']))
            return statistics['result'][[isRatedUser(user_result) for i,user_result in statistics['result'].iterrows()]]

        user_list = fetchUserList()
        rated_user_name_list = set(user for (i,c), s in zip(contest_list.iterrows(), contest_statistics_list) for user in list(selectRatedUser(c, s)['name']))
        user_list['isRatedUser'] = user_list['name'].isin(rated_user_name_list)
        user_list['isNewUser'] = ~user_list['name'].isin(pre_user_list['name'])
        user_list['hasRateChanged'] = [(checkChangeRate(user) or True) if user['isRatedUser'] else False for i,user in user_list.iterrows()]
        user_list['hasRateChanged'] = [(checkChangeRate(user) if checkChangeRate(user) is not None else True) if user['isRatedUser'] else False for i,user in user_list.iterrows()]
        logger.info('rated user  : '+','.join(user_list[user_list['isRatedUser']]['name'].values))
        logger.info('change user : '+','.join(user_list[user_list['hasRateChanged']]['name'].values))
        logger.info('(new user)  : '+','.join(user_list[user_list['isNewUser']]['name'].values))
        if sum(user_list['hasRateChanged']) != sum(user_list['isRatedUser']):
            logger.info('Not all rates have been updated yet...')
        else:
            time.sleep(5)  # countの更新とrateの更新の間にラグがあるみたいなので少し待ってみる（５秒で足りない可能性あり）
            logger.info('Rate change!')
            return
        time.sleep(60)
    # timeout
    exit()

def generateContestChart(uesr_list, pre_user_list):
    user_list['rating_diff'] = [(user['rating'] - int(pre_user_list[pre_user_list['name'] == user['name']]['rating'])) if sum(pre_user_list['name'] == user['name']) == 1 else 0 for i,user in user_list.iterrows()]
    user_list['rank_diff'] = [(int(pre_user_list[pre_user_list['name'] == user['name']]['rank']) - user['rank']) if sum(pre_user_list['name'] == user['name']) == 1 else 0 for i,user in user_list.iterrows()]

    logger.info('get users chart')
    user_chart_list = [util.scrape('https://beta.atcoder.jp/users/'+user['name'], '//*[@id="main-container"]/div/div[3]/script[2]/text()')[0] for i, user in user_list.iterrows()]

    def generateChart(chart_range):
        def printChartOp(driver):
            driver.execute_script(
                "x_min=%d;x_max=%d;y_min=%d;y_max=%d" % chart_range)
            for ((i, u), chart) in zip(user_list.iterrows(), user_chart_list):
                driver.execute_script(chart)
                driver.execute_script(
                    'user_name="'+u['name']+'"; user_index='+str(i)+';')
                driver.execute_script('initChart2()')
            driver.execute_script('stage_graph.update()')

        # save web page with image
        return util.operateBrowser(
            url='file://'+os.getcwd()+'/chart/template.html',
            return_screenshot=True,
            op=printChartOp
        )
    im1 = generateChart((1502372400, int(dt.datetime.now().timestamp()) + 1000000, 0, 2000))
    im2 = generateChart((1521540800, int(dt.datetime.now().timestamp()) + 1000000, 0, 800))
    im1 = im1.crop((0, 0, 700, 400))
    im2 = im2.crop((0, 0, 700, 400))
    chart_image = util.get_concat_v(im1, im2)

    logger.info('generate contest result')
    rating_html = Jinja2.get_template('rating.tpl.html').render({
        'user_list': user_list,
    })

    rating_image = util.operateBrowser(
        page=rating_html,
        return_screenshot=True,
        width=640,
        height=270,
    )

    # ２つのページをくっつけて写真をとる
    contest_chart = util.get_concat_h(rating_image, chart_image)

    return contest_chart

if __name__ == '__main__':
    logging.basicConfig()
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument('contest_id_list', nargs='+',)
    args = parser.parse_args()

    config = configparser.ConfigParser()
    config.read('config.ini')

    Slack = slack.Slack(
        token=config['slack']['token'],
        name=config['slack']['name'],
        icon=config['slack']['icon'],
    )

    Jinja2 = jinja2.Environment(
        loader = jinja2.FileSystemLoader(
            searchpath='./tpl',
            encoding='utf8'
        )
    )
    Jinja2.globals.update(
        zip=zip,
        list=list,
        str=str,
        int=int,
    )

    logger.info(' '.join(args.contest_id_list))

    contest_list_path = 'data/contest_list.pickle'
    user_list_path = 'data/user_list.pickle'

    # コンテスト情報のロード
    logger.info('load contest data')
    all_contest_list = pickle.load(open(contest_list_path, 'rb'))
    contest_list = all_contest_list[all_contest_list.id.isin(args.contest_id_list)]
    if len(contest_list) != len(args.contest_id_list):
        logger.error('contest does not exist in DB.')
        exit()

    # コンテスト結果のフェッチ
    logger.info('fetch contest statistics')
    contest_statistics_list = list(map(fetchContestStatistics, args.contest_id_list))
    if all(c['result'].empty for c in contest_statistics_list):
        logger.info('No one play contest.')
        exit()

    # ユーザー情報のフェッチ
    logger.info('fetch user statistics')
    user_list = fetchUserList()

    # コンテスト結果の生成
    logger.info('generate contest result')
    result = generateContestResult(contest_list, contest_statistics_list, user_list)

    # コンテスト結果を投稿
    Slack.postImage(
        'chart-'+str(dt.datetime.now().timestamp()) + '.png',
        config['slack']['channel_name'],
        'Contest Result',
        image=result
    )
    logger.info('post ok, done!')

    # レート対象でないコンテストを除外
    contest_list = contest_list[contest_list['is_rating'] == True]
    if len(contest_list) == 0:
        logger.info('rated contest does not exist.')
        exit()

    # 前回のユーザー情報のロード
    pre_user_list = pickle.load(open(user_list_path, 'rb')) if os.path.exists(user_list_path) else user_list

    # レートが更新されるまで待つ
    logger.info('wait rating update')
    waitRatingUpdate(contest_list, contest_statistics_list, pre_user_list)

    # 更新後のユーザー情報のフェッチ、DBに保存
    logger.info('fetch and save updated user statistics')
    updated_user_list = fetchUserList()
    updated_user_list.to_pickle(user_list_path)

    # チャートの生成
    logger.info('generate contest chart')
    chart = generateContestChart(updated_user_list, pre_user_list)

    # チャートを投稿
    Slack.postImage(
        'chart-'+str(dt.datetime.now().timestamp()) + '.png',
        config['slack']['channel_name'],
        'Rating Update',
        image=chart)
    logger.info('post ok, done!')
