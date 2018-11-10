import os
import time
import pickle
import argparse
import configparser
import datetime as dt
import pandas as pd
import jinja2
from PIL import Image
from IPython import embed
import util
import slack
import logging
from typing import Any, Callable, Optional, Tuple


def fetchContestStatistics(link: str) -> pd.DataFrame:
    """
    コンテスト結果を取得して返す
        :param link: コンテストへのLink (e.g. `/contest/abc100`)
        :return: {
            result: {
                rank: グループ内のランキング
                global_rank: 世界ランク
                name: ユーザー名
                score: 合計スコア
                isJoin: 参加しているか（参加登録していても一つも提出していない場合不参加扱いになる）
            }
            points: {
                (問題名): 問題別のスコア
            }
        }
    """

    def browserOp(driver: Any) -> None:
        driver.find_element_by_id('standings-panel-heading')
        input = driver.find_element_by_id('input-affiliation')
        driver.execute_script(
            "document.getElementsByClassName('form-inline')[0].style.display = 'block';"
        )
        input.send_keys(config['atcoder']['affiliation'])

    raw_contest_statistics = util.scrapeTable(
        url='https://beta.atcoder.jp' + link + '/standings?lang=en',
        op=browserOp)[0].iloc[:-2]
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
                    when 不参加(得点・ミスなし）: ???(使ってない)
                    when それ以外: [
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

    def get(i: int) -> Callable:
        def access(x: str) -> str:
            return x.split(',')[i]

        return access

    result = pd.DataFrame({
        'rank':
        raw_contest_statistics.Rank.map(get(0)),
        'global_rank':
        raw_contest_statistics.Rank.map(lambda x: get(1)(x)[1:-1]),
        'name':
        raw_contest_statistics.User.map(get(1)),
        'score':
        raw_contest_statistics.Score.map(get(0)),
    })

    del raw_contest_statistics['Rank']
    del raw_contest_statistics['User']
    del raw_contest_statistics['Score']
    isCorrect = lambda item: len(str(item).split(',')) >= 2
    points = raw_contest_statistics.applymap(isCorrect)

    result['isJoin'] = [
        any(item != '-' for i, item in row.iteritems())
        for i, row in raw_contest_statistics.iterrows()
    ]

    return {'result': result, 'points': points}


def fetchUserList() -> pd.DataFrame:
    """
    全ユーザーのデータを取得して返す
        :return: {
            name: ユーザー名
            color: 色
            rating: レーティング
            count: コンテストに参加した回数（参加登録していても不参加の場合加算されない）
        }
    """

    def op(obj: Any) -> Optional[str]:
        try:
            if 'user-' in obj.span.attrs['class'][0]:
                color = obj.span.attrs['class'][0].replace('user-', '')
                return obj.get_text(',', strip=True) + ',' + color
        except AttributeError:
            pass
        return None

    raw_user_list = util.scrapeTable(
        url='https://beta.atcoder.jp/ranking?f.Affiliation=' +
        config['atcoder']['affiliation'],
        tableOp=op)[1]

    def get(i: int) -> Callable:
        def access(x: str) -> str:
            return x.split(',')[i]

        return access

    user_list = pd.DataFrame({
        'name': raw_user_list['User'].map(get(0)),
        'color': raw_user_list['User'].map(get(2)),
        'rating': raw_user_list['Rating'],
        'count': raw_user_list['Match'],
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
        'contest_list':
        contest_list,
        'contest_statistics_list':
        contest_statistics_list,
        'user_list':
        user_list,
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
    レーティングが更新されたかチェックする
        :param contest_list: 全コンテスト名
        :param contest_statistics_list: 全コンテスト結果
        :param pre_user_list: コンテスト前の全ユーザーデータ
        :return: (bool) 更新されたか
    """

    # コンテストに参加しているレート対象者全員のレートが更新されているかチェック
    def checkChangeRate(user: pd.Series) -> Optional[bool]:
        pre_user = pre_user_list[pre_user_list['name'] == user['name']]
        if pre_user.empty:
            return None
        count_diff = int(user['count']) - int(pre_user['count'])
        if count_diff != 0:
            return True
        return False

    def getPreRating(user_result: pd.Series) -> Optional[int]:
        pre_user = pre_user_list[pre_user_list['name'] == user_result['name']]
        return (int)(pre_user['rating']) if not pre_user.empty else None

    def selectRatedUser(contest: pd.DataFrame,
                        statistics: pd.DataFrame) -> pd.DataFrame:
        def isRatedUser(user_result: pd.Series) -> bool:
            rating = getPreRating(user_result)
            if rating is None:
                return user_result['isJoin']
            else:
                return user_result['isJoin'] and (rating <= (int)(
                    contest['rating_limit']))

        return statistics['result'][[
            isRatedUser(user_result)
            for i, user_result in statistics['result'].iterrows()
        ]]

    user_list = fetchUserList()
    rated_user_name_list = set(
        user
        for (i, c), s in zip(contest_list.iterrows(), contest_statistics_list)
        for user in list(selectRatedUser(c, s)['name']))
    user_list['isRatedUser'] = user_list['name'].isin(rated_user_name_list)
    user_list['isNewUser'] = ~user_list['name'].isin(pre_user_list['name'])
    user_list['hasRateChanged'] = [
        (checkChangeRate(user) or True) if user['isRatedUser'] else False
        for i, user in user_list.iterrows()
    ]
    user_list['hasRateChanged'] = [
        (checkChangeRate(user) if checkChangeRate(user) is not None else True)
        if user['isRatedUser'] else False for i, user in user_list.iterrows()
    ]
    logger.info('rated user  : ' +
                ','.join(user_list[user_list['isRatedUser']]['name'].values))
    logger.info('change user : ' + ','.join(user_list[
        user_list['hasRateChanged']]['name'].values))
    logger.info('(new user)  : ' +
                ','.join(user_list[user_list['isNewUser']]['name'].values))
    if sum(user_list['hasRateChanged']) != sum(user_list['isRatedUser']):
        return False
    else:
        return True


def generateContestChart(uesr_list: pd.DataFrame,
                         pre_user_list: pd.DataFrame) -> Image.Image:
    """
    全ユーザーデータからレーティングチャートを作成して返す
        :param uesr_list: 全ユーザーデータ
        :param pre_user_list: コンテスト前の全ユーザーデータ
        :return: レーティングチャートの画像
    """
    user_list['rating_diff'] = [
        (user['rating'] -
         int(pre_user_list[pre_user_list['name'] == user['name']]['rating']))
        if sum(pre_user_list['name'] == user['name']) == 1 else 0
        for i, user in user_list.iterrows()
    ]
    user_list['rank_diff'] = [
        (int(pre_user_list[pre_user_list['name'] == user['name']]['rank']) -
         user['rank']) if sum(
             pre_user_list['name'] == user['name']) == 1 else 0
        for i, user in user_list.iterrows()
    ]

    logger.info('get users chart')
    user_chart_list = [
        util.scrape('https://beta.atcoder.jp/users/' + user['name'],
                    '//*[@id="main-container"]/div/div[3]/script[2]/text()')[0]
        for i, user in user_list.iterrows()
    ]

    def generateChart(chart_range: Tuple[int, int, int, int]) -> Image.Image:
        def printChartOp(driver: Any) -> None:
            driver.execute_script(
                "x_min=%d;x_max=%d;y_min=%d;y_max=%d" % chart_range)
            for ((i, u), chart) in zip(user_list.iterrows(), user_chart_list):
                driver.execute_script(chart)
                driver.execute_script('user_name="' + u['name'] +
                                      '"; user_index=' + str(i) + ';')
                driver.execute_script('initChart2()')
            driver.execute_script('stage_graph.update()')

        # Save web page with image
        return util.operateBrowser(
            # このhtmlとchart.jsはAtcoderのサイトからダウンロードしたものを適当に書き換えたもの
            url='file://' + os.getcwd() + '/chart/template.html',
            return_screenshot=True,
            op=printChartOp)

    # 左端のタイムスタンプ,右端のタイムスタンプ,レート下限,レート上限
    im1 = generateChart(
        (1502372400, int(dt.datetime.now().timestamp()) + 1000000, 0, 2000))
    im2 = generateChart((1521540800,
                         int(dt.datetime.now().timestamp()) + 1000000, 0, 800))
    im1 = im1.crop((0, 0, 700, 400))
    im2 = im2.crop((0, 0, 700, 400))
    chart_image = util.concat_images_vertical(im1, im2)

    logger.info('generate contest result')
    rating_html = Jinja2.get_template('rating.tpl.html').render({
        'user_list':
        user_list,
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
    parser.add_argument(
        'contest_id_list',
        nargs='+',
    )
    parser.add_argument('--data_path', default='data')
    args = parser.parse_args()

    config = configparser.ConfigParser()
    config.read('config.ini')

    Slack = slack.Slack(
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

    contest_list_path = args.data_path + '/contest_list.pickle'
    user_list_path = args.data_path + '/user_list.pickle'

    # コンテスト情報のロード
    logger.info('Load contest data')
    all_contest_list = pickle.load(open(contest_list_path, 'rb'))
    contest_list = all_contest_list[all_contest_list.id.isin(
        args.contest_id_list)]
    if len(contest_list) != len(args.contest_id_list):
        logger.error('A few contests does not exist in DB.')
        exit()

    # コンテスト結果のフェッチ
    logger.info('Fetch contest statistics')
    contest_statistics_list = list(
        map(fetchContestStatistics, args.contest_id_list))
    if all(cs['result'].empty for cs in contest_statistics_list):
        logger.info('No one play any contest.')
        exit()

    # ユーザー情報のフェッチ
    logger.info('Fetch user statistics')
    user_list = fetchUserList()

    # コンテスト結果画像の生成
    logger.info('Generate contest result image')
    result = generateContestResult(contest_list, contest_statistics_list,
                                   user_list)

    # コンテスト結果を投稿
    logger.info('Post contest result')
    Slack.postImage(
        'result-' + str(dt.datetime.now().timestamp()) + '.png',
        config['slack']['channel_name'],
        'Contest Result',
        image=result)

    # レート対象でないコンテストを除外
    contest_list = contest_list[contest_list['is_rating'] == True]
    if len(contest_list) == 0:
        logger.info('Rated contest does not exist. finish.')
        exit()

    # 前回のユーザー情報のロード
    pre_user_list = pickle.load(open(
        user_list_path, 'rb')) if os.path.exists(user_list_path) else user_list

    # レートが更新されるまで待つ
    logger.info('Wait rating update')
    rate_has_change = False
    for time_count in range(0, 60 * 2):
        if checkRatingUpdate(contest_list, contest_statistics_list,
                             pre_user_list):
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
        config['slack']['channel_name'],
        'Rating Update',
        image=chart)

    logger.info('Post ok, all done!')
