import sys
import configparser

import util
import slack

config = configparser.ConfigParser()
config.read('config.ini')

Slack = slack.Slack(
    channel=config['slack']['channel_name'],
    token=config['slack']['token'],
    name=config['slack']['name'],
    icon=config['slack']['icon'],
)

message = sys.argv[1]

Slack.post(message)
