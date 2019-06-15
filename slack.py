import util
import urllib.parse
import requests
from PIL import Image
from IPython import embed
import logging
import io
import os
from datetime import datetime
from typing import Any
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Slack():
    """SNS communication tool APIs"""

    def __init__(self,
                 channel: str,
                 token: str
                 ) -> None:
        self.channel = channel
        self.token = token

    def post(self, text: str) -> None:
        requests.post(
            'https://slack.com/api/chat.postMessage', {
                'token': self.token,
                'channel': self.channel,
                'text': text,
            }
        )

    def postImage(self,
                  name: str,
                  title: str,
                  image_url: str = None,
                  image: Any = None) -> None:
        if image is not None and type(image) == Image.Image:
            image_io = io.BytesIO()
            image.save(image_io, format='png')
            image = image_io.getvalue()
        elif image_url is not None:
            image = open(image_url, 'rb')
        requests.post(
            'https://slack.com/api/files.upload',
            data={
                'token': self.token,
                'channels': self.channel,
                'title': title,
            },
            files={
                'file': (name, image, 'image/png'),
            }
        )

    def setReminder(self, date: datetime, comment: str) -> None:
        util.setReminder(date, 'cd ' + os.getcwd() + ' && python3 sendMessage.py "' + comment
                         + '" >> log/slack.log 2>&1')
