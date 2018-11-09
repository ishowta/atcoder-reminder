import util
import urllib
import requests
from PIL import Image
from IPython import embed
import logging
import io
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class Slack():
	"""SNS communication tool APIs"""
	def __init__(self, token, name, icon, legacy_token=None):
		self.token = token
		self.name = name
		self.icon = icon
		self.legacy_token = legacy_token
	def post(self, channel, text):
		requests.post(
			'https://slack.com/api/chat.postMessage',
			{
				'token': self.token,
				'channel': channel,
				'username': self.name,
				'icon_emoji': ':'+self.icon+':',
				'text': text,
			}
		)
	def postImage(self, name, channel, title, image_url=None, image=None):
		if image is not None:
			if type(image) == Image.Image:
				image_io = io.BytesIO()
				image.save(image_io, format='png')
				image_bin = image_io.getvalue()
			else:
				image_bin = image
		else:
			image_bin = open(image_url, 'rb')
		requests.post(
			'https://slack.com/api/files.upload',
			data = {
				'token': self.token,
				'channels': channel,
				'title': title,
			},
			files = {
				'file': (name, image_bin, 'image/png'),
			}
		)
	def setReminder(self, channel, date, command):
		util.setReminder(date, 'curl -X POST -d "token='+self.legacy_token+'" -d "channel='+channel+'" -d "username='+self.name+'" -d "icon_emoji=%3A'+self.icon+'%3A" -d "text='+urllib.parse.quote(command)+'" https://slack.com/api/chat.postMessage >> log/slack.txt 2>&1')
