import os
import time
import pickle
import argparse
import configparser
import datetime as dt
import pandas as pd
import numpy as np
import jinja2
from PIL import Image
from IPython import embed
import util
import slack
import logging
from typing import Any, Callable, Optional, Tuple, Union, List


def fetchContestStatistics(link: str) -> pd.DataFrame:
    """
    コンテスト結果を取得して返す
        :param link: コンテストへのLink (e.g. `/contest/abc100`)
        :return: {
            result: {
                (int) rank: グループ内のランキング
                (int) global_rank: 世界ランク
                (object) name: ユーザー名
                (object) score: 合計スコア
                (bool) isJoin: 参加しているか（参加登録していても一つも提出していない場合不参加扱いになる）
            }
            points: {
                (object) (問題名): 問題別のスコア
            }
        }
    """

    def openResultViewOp(driver: Any) -> None:
        driver.find_element_by_id('standings-panel-heading')
        input = driver.find_element_by_id('input-affiliation')
        driver.execute_script("document.getElementsByClassName('form-inline')[0].style.display = 'block';")
        input.send_keys(config['atcoder']['affiliation'])

    raw_contest_statistics = util.scrapeTable(
        url='https://beta.atcoder.jp' + link + '/standings?lang=en',
        op=openResultViewOp
    )[0].iloc[:-2]

    """
        返ってくるテーブルの型と例（pandas側の仕様上セルに入っているのはstringなので、すべて`split(',')`して取り出す）
        raw_contest_statistics = [
            {
                Rank: [
                    (int) '1' # Rank
                    (`(`+int+`)`) '(240)'  # Global rank
                ],
                User: [
                    (link) /usres/hogehoge
                    (string) hogehoge
                ],
                Score:
                    when 不参加(得点・ミスなし）: ???
                    when 得点なし: [
                        `(0)`
                    ]
                    when 得点あり: [
                        (得点(int) :option) 1000,
                        (`(`+ミス数(int)+`)` :option) (2),
                        (タイム(h:m) :option) 30:11
                    ]
                問題名1:
                    Scoreと同じ
                問題名2:
                    ...
                ...
            }
        ]
    """

    result = pd.DataFrame({
        'rank': raw_contest_statistics.Rank.splitBy(0).astype(int),
        'global_rank': raw_contest_statistics.Rank.splitBy(1).map(lambda x: x[1:-1]).astype(int),
        'name': raw_contest_statistics.User.splitBy(1).astype(object),
        'score': raw_contest_statistics.Score.splitBy(0).astype(object),
    })

    def isCorrect(item: Any) -> bool:
        return len(str(item).split(',')) >= 2

    points = raw_contest_statistics.filter(regex="^[^(Rank|User|Score)]$")
    points = points.applymap(isCorrect)

    result['isJoin'] = [
        any(item != '-' for i, item in row.iteritems())
        for i, row in points.iterrows()
    ]

    return {'result': result, 'points': points}


def fetchUserList() -> pd.DataFrame:
    """
    全ユーザーのデータを取得して返す
        :return: {
            (object) name: ユーザー名
            (object) color: 色
            (int) rating: レーティング
            (int) count: コンテストに参加した回数（参加登録していても不参加の場合加算されない）
            (int) rank: グループ内順位
        }
    """

    def getColorOp(obj: Any) -> Optional[str]:
        try:
            if 'user-' in obj.span.attrs['class'][0]:
                color = obj.span.attrs['class'][0].replace('user-', '')
                return obj.get_text(',', strip=True) + ',' + color
        except AttributeError:
            pass
        return None

    raw_user_list = util.scrapeTable(
        url='https://beta.atcoder.jp/ranking?f.Affiliation=' + config['atcoder']['affiliation'],
        tableOp=getColorOp
    )[1]

    user_list = pd.DataFrame({
        'name': raw_user_list['User'].splitBy(0).astype(object),
        'color': raw_user_list['User'].splitBy(2).astype(object),
        'rating': raw_user_list['Rating'].splitBy(0).astype(int),
        'count': raw_user_list['Match'].splitBy(0).astype(int),
    })
    user_list['rank'] = list(range(1, len(user_list) + 1))

    return user_list


def generateContestResult(contest_list: pd.DataFrame,
                          contest_statistics_list: pd.DataFrame,
                          user_list: pd.DataFrame) -> Image.Image:
    """
    全コンテスト結果から表を作成して返す
        :param contest_list: 全コンテスト名
        :param contest_statistics_list: 全コンテスト結果
        :param user_list: 全ユーザーデータ
        :return: 表の画像
    """
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


def checkRatingUpdate(contest_list: pd.DataFrame,
                      contest_statistics_list: pd.DataFrame,
                      pre_user_list: pd.DataFrame) -> bool:
    """
    コンテストに参加しているレート対象者全員のレーティングが更新されたかチェックする
        :param contest_list: 全コンテスト名
        :param contest_statistics_list: 全コンテスト結果
        :param pre_user_list: コンテスト前の全ユーザーデータ
        :return: (bool) 更新されたか
    """
    def selectRateTargetUser(contest: pd.DataFrame, statistics: pd.DataFrame) -> pd.DataFrame:
        def isRateTargetUser(user_result: pd.Series) -> bool:
            pre_user = pre_user_list[pre_user_list['name'] == user_result['name']]
            if pre_user.empty:
                return user_result['isJoin']
            else:
                return user_result['isJoin'] and ((int)(pre_user['rating']) <= (int)(contest['rating_limit']))
        return statistics['result'][statistics['result'].apply(isRateTargetUser, axis=1)]

    def checkChangeRate(user: pd.Series) -> Optional[bool]:
        pre_user = pre_user_list[pre_user_list['name'] == user['name']]
        if pre_user.empty:
            return None
        if int(user['count']) - int(pre_user['count']) != 0:
            return True
        return False

    user_list = fetchUserList()

    target_user_name_list = set(
        user
        for (i, c), s in zip(contest_list.iterrows(), contest_statistics_list)
        for user in list(selectRateTargetUser(c, s)['name']))
    target_user_list = user_list[user_list['name'].isin(target_user_name_list)].copy()
    target_user_list['isNewUser'] = ~target_user_list['name'].isin(pre_user_list['name'])
    target_user_list['hasRateChanged'] = target_user_list.apply(checkChangeRate, axis=1)
    logger.info('rated user  : ' + ','.join(target_user_list['name'].values))
    logger.info('change user : ' + ','.join(target_user_list[target_user_list['hasRateChanged']]['name'].values))
    logger.info('(new user)  : ' + ','.join(target_user_list[target_user_list['isNewUser']]['name'].values))
    if (target_user_list['isNewUser'] | target_user_list['hasRateChanged']).all():
        return True
    else:
        return False


def generateContestChart(current_user_list: pd.DataFrame,
                         pre_user_list: pd.DataFrame) -> Image.Image:
    """
    全ユーザーデータからレーティングチャートを作成して返す
        :param uesr_list: 全ユーザーデータ
        :param pre_user_list: コンテスト前の全ユーザーデータ
        :return: レーティングチャートの画像
    """
    user_list = pd.merge(current_user_list, pre_user_list, on='name', how='left', suffixes=('_current', '_pre'))

    user_list['rating_diff'] = user_list.apply(
        lambda user: user['rating_current'] - user['rating_pre'] if not np.isnan(user['rating_pre']) else 0, axis=1)
    user_list['rank_diff'] = user_list.apply(
        lambda user: user['rank_current'] - user['rank_pre'] if not np.isnan(user['rank_pre']) else 0, axis=1)

    logger.info('get users chart')
    user_chart_list = [
        util.scrape('https://beta.atcoder.jp/users/' + user['name'],
                    '//*[@id="main-container"]/div/div[3]/script[2]/text()')[0]
        for i, user in current_user_list.iterrows()
    ]

    def generateChart(chart_range: Tuple[int, int, int, int]) -> Image.Image:
        def printChartOp(driver: Any) -> None:
            driver.execute_script(
                "date_begin=%d;date_end=%d;rate_min=%d;rate_max=%d" % chart_range)
            for ((i, u), chart) in zip(user_list.iterrows(), user_chart_list):
                driver.execute_script(chart)
                driver.execute_script('user_name="' + u['name'] + '"')
                driver.execute_script('paintNewChart()')

        # Save web page with image
        return util.operateBrowser(
            # このhtmlとchart.jsはAtcoderのサイトからダウンロードしたものを適当に書き換えたもの
            url='file://' + os.getcwd() + '/chart/template.html',
            return_screenshot=True,
            op=printChartOp)

    # 左端のタイムスタンプ,右端のタイムスタンプ,レート下限,レート上限
    im1 = generateChart(((int)(1502372400/100), (int)((int(dt.datetime.now().timestamp()) + 1000000)/100), 0, 2000))
    im2 = generateChart(((int)(1521540800/100), (int)((int(dt.datetime.now().timestamp()) + 1000000)/100), 0, 800))
    im1 = im1.crop((0, 0, 700, 400))
    im2 = im2.crop((0, 0, 700, 400))
    chart_image = util.concat_images_vertical(im1, im2)

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

    # ２つのページをくっつける
    contest_chart = util.concat_images_horizontal(rating_image, chart_image)

    return contest_chart


if __name__ == '__main__':
    logging.basicConfig()
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument('contest_id_list', nargs='+',)
    parser.add_argument('--mode', default='deployment')
    args = parser.parse_args()

    config = configparser.ConfigParser()
    config.read('config.ini')

    Slack = slack.Slack(
        channel=config['slack']['channel_name']
        if args.mode == 'deployment' else config['slack']['test_channel_name'],
        token=config['slack']['token'],
        name=config['slack']['name'],
        icon=config['slack']['icon'],
    )

    Jinja2 = jinja2.Environment(
        loader=jinja2.FileSystemLoader(searchpath='./tpl', encoding='utf8'))
    Jinja2.globals.update(
        zip=zip,
        list=list,
        str=str,
        int=int,
    )

    logger.info('Contest list: ' + ' '.join(args.contest_id_list))

    data_path = 'data' if args.mode == 'deployment' else 'tmp/data'
    contest_list_path = data_path + '/contest_list.pickle'
    user_list_path = data_path + '/user_list.pickle'

    # コンテスト情報のロード
    logger.info('Load contest data')
    all_contest_list = pickle.load(open(contest_list_path, 'rb'))
    contest_list = all_contest_list[all_contest_list.id.isin(args.contest_id_list)]
    if len(contest_list) != len(args.contest_id_list):
        logger.error('A few contests does not exist in DB.')
        exit()

    # コンテスト結果のフェッチ
    logger.info('Fetch contest statistics')
    contest_statistics_list = list(map(fetchContestStatistics, args.contest_id_list))
    if all(cs['result'].empty for cs in contest_statistics_list):
        logger.info('No one play any contest.')
        exit()

    # ユーザー情報のフェッチ
    logger.info('Fetch user statistics')
    user_list = fetchUserList()

    # コンテスト結果画像の生成
    logger.info('Generate contest result image')
    result = generateContestResult(contest_list, contest_statistics_list, user_list)

    # コンテスト結果を投稿
    logger.info('Post contest result')
    Slack.postImage(
        'result-' + str(dt.datetime.now().timestamp()) + '.png',
        'Contest Result',
        image=result
    )

    # レート対象でないコンテストを除外
    contest_list = contest_list[contest_list['is_rating'] == True]
    if len(contest_list) == 0:
        logger.info('Rated contest does not exist. finish.')
        exit()

    # 前回のユーザー情報のロード
    pre_user_list = pickle.load(open(user_list_path, 'rb')) if os.path.exists(user_list_path) else user_list

    # レートが更新されるまで待つ
    logger.info('Wait rating update')
    rate_has_change = False
    for time_count in range(0, 60 * 2):
        if checkRatingUpdate(contest_list, contest_statistics_list, pre_user_list):
            rate_has_change = True
            break
        else:
            logger.info('Not all rates have been updated yet...')
        time.sleep(60)
    if rate_has_change:
        logger.info('Rate change!')
        time.sleep(5)  # countの更新とrateの更新の間にラグがあるみたいなので少し待ってみる（５秒で足りない可能性あり）
    else:
        logger.info('Time out! cannot detect change rating... exit.')
        exit()

    # 更新後のユーザー情報のフェッチ、DBに保存
    logger.info('Fetch and save updated user statistics')
    updated_user_list = fetchUserList()
    updated_user_list.to_pickle(user_list_path)

    # チャート画像の生成
    logger.info('Generate contest chart image')
    chart = generateContestChart(updated_user_list, pre_user_list)

    # チャートを投稿
    logger.info('Post chart')
    Slack.postImage(
        'chart-' + str(dt.datetime.now().timestamp()) + '.png',
        'Rating Update',
        image=chart
    )

    logger.info('Post ok, all done!')
