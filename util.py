import os
import time
import io
import random
import datetime as dt
import pandas as pd
import datetime
import requests
import logging
import subprocess
from selenium import webdriver
from webdriver_manager import chrome
from IPython import embed
from collections import namedtuple
import lxml.html
from PIL import Image
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def fullpage_screenshot(driver):
    page_width = driver.execute_script("return document.body.offsetWidth")
    page_height = driver.execute_script("return document.body.parentNode.scrollHeight")
    view_width = driver.execute_script("return document.body.clientWidth")
    view_height = driver.execute_script("return window.innerHeight")

    Point = namedtuple('Point', ['x','y'])
    view_list = []
    for x in range(0, page_width, view_width):
        for y in range(0, page_height, view_height):
            view_list.append(Point(x, y))

    page_image = Image.new('RGB', (page_width, page_height))

    fn = 'tmp/' + str(random.random())

    for count, view in enumerate(view_list):
        driver.execute_script("window.scrollTo({0}, {1})".format(view.x, view.y))
        time.sleep(0.2)

        file_name = fn+"part_{0}.png".format(count)
        driver.get_screenshot_as_file(file_name)
        screenshot = Image.open(file_name)

        offset = (
            view.x if view.x <= page_width - view_width else page_width - view_width,
            view.y if view.y <= page_height - view_height else page_height - view_height,
        )

        page_image.paste(screenshot, offset)

        del screenshot
        os.remove(file_name)
    return page_image

def operateBrowser(url=None, page=None, op=None, return_screenshot=False, width=1280, height=1024):
	options = webdriver.chrome.options.Options()
	options.add_argument('--headless')
	options.add_argument('--window-size='+str(width)+','+str(height))
	options.add_argument('--no-sandbox')
	driver = webdriver.Chrome(
		executable_path = chrome.ChromeDriverManager('2.41').install(),
		chrome_options = options
	)
	if page is not None:
		fn = 'tmp/' + str(random.random()) + '.html'
		with io.open(fn, 'w', encoding='utf-8') as fh:
			fh.write(page)
		url='file://'+os.getcwd()+'/'+fn
	try:
		driver.get(url)
		if op is not None:
			op(driver)
		if return_screenshot:
			return fullpage_screenshot(driver)
		page = driver.page_source
	finally:
		driver.quit()
	return page

def scrape(url, *xpath_list):
	page = requests.get(url).text
	dom = lxml.html.fromstring(page)
	result = [dom.xpath(xpath) for xpath in xpath_list]
	return result if len(result) > 1 else result[0]

def scrapeTable(url=None, page=None, op=None, tableOp=None):
	if page is None:
		if op is None:
			page = requests.get(url).text
		else:
			page = operateBrowser(url=url, op=op)

	# `pd.read_html(htmlからtableを取ってくる関数)`でテーブル上のセルに対して任意のオペレーションを掛けられるようにする
	def _extend_text_getter(self, obj):
		if tableOp is not None:
			res = tableOp(obj)
			if res is not None:
				return res
		text = obj.get_text(separator=',', strip=True)
		return text if obj.name == 'th' or obj.a is None else ','.join([obj.a.get('href'), text])
	pd.io.html._BeautifulSoupHtml5LibFrameParser._text_getter = _extend_text_getter

	data = pd.read_html(page, flavor='bs4')
	return data

def setReminder(date, command):
	date_s = date.strftime('%H:%M %m%d%Y')
	subprocess.Popen('at %s <<< \'%s\'' % (date_s, command), shell=True, executable='/bin/bash')
	logger.info('set new reminder : at %s <<< \'%s\'' % (date_s, command))

def concat_images_vertical(im1, im2):
    dst = Image.new('RGB', (max(im1.width, im2.width),
                            (im1.height + im2.height)), (255, 255, 255))
    dst.paste(im1, (0, 0))
    dst.paste(im2, (0, im1.height))
    return dst

def concat_images_horizontal(im1, im2):
    dst = Image.new('RGB', ((im1.width + im2.width),
                            max(im1.height, im2.height)), (255, 255, 255))
    dst.paste(im1, (0, 0))
    dst.paste(im2, (im1.width, 0))
    return dst
