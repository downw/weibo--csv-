#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import codecs
import csv
import json
import math
import os
import random
import sys
import traceback
from collections import OrderedDict
from datetime import date, datetime, timedelta
from time import sleep

from collections import defaultdict
import re

import requests
from lxml import etree
from requests.adapters import HTTPAdapter
from tqdm import tqdm


class Weibo(object):
    def __init__(self, config):
        """Weibo类初始化"""
        self.validate_config(config)
        self.filter = config[
            'filter']  # 取值范围为0、1,程序默认值为0,代表要爬取用户的全部微博,1代表只爬取用户的原创微博
        since_date = str(config['since_date'])
        if since_date.isdigit():
            since_date = str(date.today() - timedelta(int(since_date)))
        self.since_date = since_date  # 起始时间，即爬取发布日期从该值到现在的微博，形式为yyyy-mm-dd
        self.write_mode = config[
            'write_mode']  # 结果信息保存类型，为list形式，可包含csv、mongo和mysql三种类型
        self.pic_download = config[
            'pic_download']  # 取值范围为0、1,程序默认值为0,代表不下载微博原始图片,1代表下载
        self.video_download = config[
            'video_download']  # 取值范围为0、1,程序默认为0,代表不下载微博视频,1代表下载
        self.mysql_config = config['mysql_config']  # MySQL数据库连接配置，可以不填
        self.cookie = config['cookie']
        question_list = config['question_list']
        if not isinstance(question_list, list):
            if not os.path.isabs(question_list):
                question_list = os.path.split(
                    os.path.realpath(__file__))[0] + os.sep + question_list
            question_list = self.get_user_list(question_list)
        self.question_list = question_list  # 要爬取的微博话题列表
        self.question = ''  # 用户id,如昵称为"Dear-迪丽热巴"的id为'1669879400'
        self.user = {}  # 存储目标微博用户信息
        self.got_count = 0  # 存储爬取到的微博数
        self.weibo = []  # 存储爬取到的所有微博信息
        self.weibo_id_list = []  # 存储爬取到的所有微博id

    def validate_config(self, config):
        """验证配置是否正确"""

        # 验证filter、pic_download、video_download
        argument_lsit = ['filter', 'pic_download', 'video_download']
        for argument in argument_lsit:
            if config[argument] != 0 and config[argument] != 1:
                sys.exit(u'%s值应为0或1,请重新输入' % config[argument])

        # 验证since_date
        since_date = str(config['since_date'])
        if (not self.is_date(since_date)) and (not since_date.isdigit()):
            sys.exit(u'since_date值应为yyyy-mm-dd形式或整数,请重新输入')

        # 验证write_mode
        write_mode = ['csv', 'mongo', 'mysql']
        if not isinstance(config['write_mode'], list):
            sys.exit(u'write_mode值应为list类型')
        for mode in config['write_mode']:
            if mode not in write_mode:
                sys.exit(u'%s为无效模式，请从txt、csv、mongo和mysql挑选一个或多个作为write_mode' %
                         mode)

        # 验证question_list
        question_list = config['question_list']
        if (not isinstance(question_list,
                           list)) and (not question_list.endswith('.txt')):
            sys.exit(u'question_list值应为list类型或txt文件路径')
        if not isinstance(question_list, list):
            if not os.path.isabs(question_list):
                question_list = os.path.split(
                    os.path.realpath(__file__))[0] + os.sep + question_list
            if not os.path.isfile(question_list):
                sys.exit(
                    u'当前路径：%s 不存在question_list.txt文件' %
                    (os.path.split(os.path.realpath(__file__))[0] + os.sep))

    def is_date(self, since_date):
        """判断日期格式是否正确"""
        try:
            datetime.strptime(since_date, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def get_json(self, params):
        """获取网页中json数据"""
        url = 'https://m.weibo.cn/api/container/getIndex?'
        r = requests.get(url, params=params)
        return r.json()

    def get_weibo_json(self, page):
        """获取网页中微博json数据"""
        params =  {'containerid': '100103type=1&q=' + str(self.question)+'&t=0','page_type': 'searchall','page': page}
        js = self.get_json(params)
        return js

    def user_to_mongodb(self):
        """将爬取的用户信息写入MongoDB数据库"""
        user_list = [self.user]
        self.info_to_mongodb('user', user_list)
        print(u'%s信息写入MongoDB数据库完毕' % self.user['screen_name'])

    def user_to_mysql(self):
        """将爬取的用户信息写入MySQL数据库"""
        mysql_config = {
            'host': 'localhost',
            'port': 3306,
            'user': 'root',
            'password': 'gLIN726()',
            'charset': 'utf8mb4'
        }
        # 创建'weibo'数据库
        create_database = """CREATE DATABASE IF NOT EXISTS weibo DEFAULT
                         CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"""
        self.mysql_create_database(mysql_config, create_database)
        # 创建'user'表
        create_table = """
                CREATE TABLE IF NOT EXISTS user (
                id varchar(20) NOT NULL,
                screen_name varchar(30),
                gender varchar(10),
                statuses_count INT,
                followers_count INT,
                follow_count INT,
                description varchar(140),
                profile_url varchar(200),
                profile_image_url varchar(200),
                avatar_hd varchar(200),
                urank INT,
                mbrank INT,
                verified BOOLEAN DEFAULT 0,
                verified_type INT,
                verified_reason varchar(140),
                PRIMARY KEY (id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
        self.mysql_create_table(mysql_config, create_table)
        self.mysql_insert(mysql_config, 'user', [self.user])
        print(u'%s信息写入MySQL数据库完毕' % self.user['screen_name'])

    def user_to_database(self):
        """将用户信息写入数据库"""
        if 'mysql' in self.write_mode:
            self.user_to_mysql()
        if 'mongo' in self.write_mode:
            self.user_to_mongodb()

    def get_pagenum_info(self):
        """获取页数信息"""
        params = {'containerid': '100103type=1&q=' + str(self.question)+'&t=0','page_type': 'searchall'}
        js = self.get_json(params)
        if js['ok']:
            #info = js['data']['userInfo']
            user_info = {}
            # user_info['id'] = info.get('id', '')
            # user_info['screen_name'] =  js['data']['cardlistInfo']['cardlist_head_cards'][0]['channel_list'][0].get('name', '')
            # user_info['gender'] = info.get('gender', '')
            user_info['statuses_count'] =  js['data']['cardlistInfo'].get('total', 0)      #获取总页数
            print('共{}条' .format(user_info['statuses_count']))
            # user_info['followers_count'] = info.get('followers_count', 0)
            # user_info['follow_count'] = info.get('follow_count', 0)
            # user_info['description'] = info.get('description', '')
            # user_info['profile_url'] = info.get('profile_url', '')
            # user_info['profile_image_url'] = info.get('profile_image_url', '')
            # user_info['avatar_hd'] = info.get('avatar_hd', '')
            # user_info['urank'] = info.get('urank', 0)
            # user_info['mbrank'] = info.get('mbrank', 0)
            # user_info['verified'] = info.get('verified', False)
            # user_info['verified_type'] = info.get('verified_type', 0)
            # user_info['verified_reason'] = info.get('verified_reason', '')
            user = self.standardize_info(user_info)
            self.user = user
            self.user_to_database()
            return user

    def get_long_weibo(self, id):
        """获取长微博"""
        url = 'https://m.weibo.cn/detail/%s' % id
        html = requests.get(url).text
        html = html[html.find('"status":'):]
        html = html[:html.rfind('"hotScheme"')]
        html = html[:html.rfind(',')]
        html = '{' + html + '}'
        js = json.loads(html, strict=False)
        weibo_info = js.get('status')
        if weibo_info:
            weibo = self.parse_weibo(weibo_info)
            return weibo

    
    def get_pics(self, weibo_info):
        """获取微博原始图片url"""
        if weibo_info.get('pics'):
            pic_info = weibo_info['pics']
            pic_list = [pic['large']['url'] for pic in pic_info]
            pics = ','.join(pic_list)
        else:
            pics = ''
        return pics

    def get_video_url(self, weibo_info):
        """获取微博视频url"""
        video_url = ''
        if weibo_info.get('page_info'):
            if weibo_info['page_info'].get('media_info'):
                media_info = weibo_info['page_info']['media_info']
                video_url = media_info.get('mp4_720p_mp4')
                if not video_url:
                    video_url = media_info.get('mp4_hd_url')
                    if not video_url:
                        video_url = media_info.get('mp4_sd_url')
                        if not video_url:
                            video_url = ''
        return video_url

    def download_one_file(self, url, file_path, type, weibo_id):
        """下载单个文件(图片/视频)"""
        try:
            if not os.path.isfile(file_path):
                s = requests.Session()
                s.mount(url, HTTPAdapter(max_retries=5))
                downloaded = s.get(url, timeout=(5, 10))
                with open(file_path, 'wb') as f:
                    f.write(downloaded.content)
        except Exception as e:
            error_file = self.get_filepath(
                type) + os.sep + 'not_downloaded.txt'
            with open(error_file, 'ab') as f:
                url = str(weibo_id) + ':' + url + '\n'
                f.write(url.encode(sys.stdout.encoding))
            print('Error: ', e)
            traceback.print_exc()

    def download_files(self, type):
        """下载文件(图片/视频)"""
        try:
            if type == 'img':
                describe = u'图片'
                key = 'pics'
            else:
                describe = u'视频'
                key = 'video_url'
            print(u'即将进行%s下载' % describe)
            file_dir = self.get_filepath(type)
            for w in tqdm(self.weibo, desc='Download progress'):
                if w[key]:
                    file_prefix = w['created_at'][:11].replace(
                        '-', '') + '_' + str(w['id'])
                    if type == 'img' and ',' in w[key]:
                        w[key] = w[key].split(',')
                        for j, url in enumerate(w[key]):
                            file_suffix = url[url.rfind('.'):]
                            file_name = file_prefix + '_' + str(
                                j + 1) + file_suffix
                            file_path = file_dir + os.sep + file_name
                            self.download_one_file(url, file_path, type,
                                                   w['id'])
                    else:
                        if type == 'video':
                            file_suffix = '.mp4'
                        else:
                            file_suffix = w[key][w[key].rfind('.'):]
                        file_name = file_prefix + file_suffix
                        file_path = file_dir + os.sep + file_name
                        self.download_one_file(w[key], file_path, type,
                                               w['id'])
            print(u'%s下载完毕,保存路径:' % describe)
            print(file_dir)
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_location(self, selector):
        """获取微博发布位置"""
        location_icon = 'timeline_card_small_location_default.png'
        span_list = selector.xpath('//span')
        location = ''
        for i, span in enumerate(span_list):
            if span.xpath('img/@src'):
                if location_icon in span.xpath('img/@src')[0]:
                    location = span_list[i + 1].xpath('string(.)')
                    break
        return location

    def get_topics(self, selector):
        """获取参与的微博话题"""
        span_list = selector.xpath("//span[@class='surl-text']")
        topics = ''
        topic_list = []
        for span in span_list:
            text = span.xpath('string(.)')
            if len(text) > 2 and text[0] == '#' and text[-1] == '#':
                topic_list.append(text[1:-1])
        if topic_list:
            topics = ','.join(topic_list)
        return topics

    def get_at_users(self, selector):
        """获取@用户"""
        a_list = selector.xpath('//a')
        at_users = ''
        at_list = []
        for a in a_list:
            if '@' + a.xpath('@href')[0][3:] == a.xpath('string(.)'):
                at_list.append(a.xpath('string(.)')[1:])
        if at_list:
            at_users = ','.join(at_list)
        return at_users

    def string_to_int(self, string):
        """字符串转换为整数"""
        if isinstance(string, int):
            return string
        elif string.endswith(u'万+'):
            string = int(string[:-2] + '0000')
        elif string.endswith(u'万'):
            string = int(string[:-1] + '0000')
        return int(string)

    def standardize_date(self, created_at):
        """标准化微博发布时间"""
        if u"刚刚" in created_at:
            created_at = datetime.now().strftime("%Y-%m-%d")
        elif u"分钟" in created_at:
            minute = created_at[:created_at.find(u"分钟")]
            minute = timedelta(minutes=int(minute))
            created_at = (datetime.now() - minute).strftime("%Y-%m-%d")
        elif u"小时" in created_at:
            hour = created_at[:created_at.find(u"小时")]
            hour = timedelta(hours=int(hour))
            created_at = (datetime.now() - hour).strftime("%Y-%m-%d")
        elif u"昨天" in created_at:
            day = timedelta(days=1)
            created_at = (datetime.now() - day).strftime("%Y-%m-%d")
        elif created_at.count('-') == 1:
            year = datetime.now().strftime("%Y")
            created_at = year + "-" + created_at
        return created_at

    def standardize_info(self, weibo):
        """标准化信息，去除乱码"""
        for k, v in weibo.items():
            if 'int' not in str(type(v)) and 'long' not in str(
                    type(v)) and 'bool' not in str(type(v)):
                weibo[k] = v.replace(u"\u200b", "").encode(
                    sys.stdout.encoding, "ignore").decode(sys.stdout.encoding)
        return weibo
    def get_review(self,id):
        max_id = ""
        try:
            i=0 # 评论的页数
            while True:
                if max_id=="":
                    url = 'https://m.weibo.cn/comments/hotflow?id=%s&mid=%s&max_id_type=0'% (id, id)
                else:
                    url = 'https://m.weibo.cn/comments/hotflow?id=%s&mid=%s&max_id=%s&max_id_type=0'% (id, id, max_id)
                headers = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3534.4 Safari/537.36',
                    'cookie' :self.cookie 
                        }
                
                comment_num=1 # 爬取的评论总数量
                req=requests.get(url,headers=headers)
                comment_page=req.json()['data']['data']
                if req.status_code==200:
                    print('读取%s页的评论：'%str(i+1))
                    for j in range(0,len(comment_page)):
                        # print('第%s条评论'%comment_num)
                        weibo_info = defaultdict(defaultdict)
                        user = comment_page[j]
                        weibo_info['user_id'] = user['user']['id']      #用户id
                        weibo_info['screen_name'] = user['user']['screen_name']    #发表评论的用户名
                        weibo_info['id'] = user['id']     #微博文本的编号
                        weibo_info['bid'] = ''
                        # text=re.sub('<.*?>|回复<.*?>:|[\U00010000-\U0010ffff]|[\uD800-\uDBFF][\uDC00-\uDFFF]','',user['text'])
                        text = user['text']
                        text = re.sub('<.*?alt=|回复<.*?alt=|src.*?png', '', text)
                        # fliter_text =re.sub('[\U00010000-\U0010ffff]|[\uD800-\uDBFF][\uDC00-\uDFFF]','',text) # 去除评论中表情等的特殊字符
                        """必须包含表情,且不能只有一个表情"""
                        # if fliter_text != text and fliter_text != "": 
                        text = re.sub('style.*?span>','',text)
                        """做一个匹配"""
                        text = re.sub('\n','',text)
                        weibo_info['text'] = text
                        
                        # print(text)
                        weibo_info['location'] = ''
                        weibo_info['created_at'] = user['created_at']#发表时间
                        weibo_info['source'] = ''
                        weibo_info['attitudes_count']=user['like_count']#点赞数
                        # print('点赞数'+str(weibo_info['attitudes_count']))
                        weibo_info['comments_count'] = 0
                        weibo_info['reposts_count'] = 0
                        weibo_info['topics'] = ''
                        weibo_info['at_users'] = ''
                        
    
                    
                        comment_num+=1
                        wb = weibo_info
                        """这个地方可能需要进行修改，修改为可以对评论文本进行进一步处理的内容"""
                        if wb:
                            self.weibo.append(wb)
                            self.weibo_id_list.append(wb['id'])
                            self.got_count = self.got_count + 1
                            self.print_weibo(wb)
                        # else:
                        #     continue
                    i+=1
                    result = req.json()
                    max_id = result.get("data").get("max_id")
                    if max_id==0:
                        break
                    sleep(random.randint(2,4))  #防止反爬虫机制，停止一会~~~~
                else:
                    break
            return ''
        except Exception as e:
            print("Error: ", e)
            traceback.print_exc()
            
            # https://m.weibo.cn/api/comments/show?id=4525451148756558&page=2


    def parse_weibo(self, weibo_info):
        weibo = OrderedDict()
        if weibo_info['user']:
            weibo['user_id'] = weibo_info['user']['id']
            weibo['screen_name'] = weibo_info['user']['screen_name']
        else:
            weibo['user_id'] = ''
            weibo['screen_name'] = ''
        weibo['id'] = int(weibo_info['id'])
        weibo['bid'] = weibo_info['bid']
        text_body = weibo_info['text']
        selector = etree.HTML(text_body)
        weibo['text'] = etree.HTML(text_body).xpath('string(.)')
        weibo['pics'] = self.get_pics(weibo_info)
        weibo['video_url'] = self.get_video_url(weibo_info)
        weibo['location'] = self.get_location(selector)
        weibo['created_at'] = weibo_info['created_at']
        weibo['source'] = weibo_info['source']
        weibo['attitudes_count'] = self.string_to_int(  #获赞数
            weibo_info['attitudes_count'])
        weibo['comments_count'] = self.string_to_int(
            weibo_info['comments_count'])
        weibo['reposts_count'] = self.string_to_int(
            weibo_info['reposts_count'])
        weibo['topics'] = self.get_topics(selector)
        weibo['at_users'] = self.get_at_users(selector)
        return self.standardize_info(weibo)

    def print_user_info(self):
        """打印用户信息"""
        print('+' * 100)
        print(u'用户信息')
        print(u'用户id：%s' % self.user['id'])
        print(u'用户昵称：%s' % self.user['screen_name'])
        gender = u'女' if self.user['gender'] == 'f' else u'男'
        print(u'性别：%s' % gender)
        print(u'微博数：%d' % self.user['statuses_count'])
        print(u'粉丝数：%d' % self.user['followers_count'])
        print(u'关注数：%d' % self.user['follow_count'])
        if self.user.get('verified_reason'):
            print(self.user['verified_reason'])
        print(self.user['description'])
        print('+' * 100)

    def print_one_weibo(self, weibo):
        """打印一条微博"""
        print(u'微博id：%s' % weibo['id'])
        print(u'微博正文：%s' % weibo['text'])
        print(u'原始图片url：%s' % weibo['pics'])
        print(u'微博位置：%s' % weibo['location'])
        print(u'发布时间：%s' % weibo['created_at'])
        print(u'发布工具：%s' % weibo['source'])
        print(u'点赞数：%d' % weibo['attitudes_count'])
        print(u'评论数：%d' % weibo['comments_count'])
        print(u'转发数：%d' % weibo['reposts_count'])
        print(u'话题：%s' % weibo['topics'])
        print(u'@用户：%s' % weibo['at_users'])

    def print_weibo(self, weibo):
        """打印微博，若为转发微博，会同时打印原创和转发部分"""
        if weibo.get('retweet'):
            print('*' * 100)
            print(u'转发部分：')
            self.print_one_weibo(weibo['retweet'])
            print('*' * 100)
            print(u'原创部分：')
        self.print_one_weibo(weibo)
        print('-' * 120)
        
    def get_one_weibo(self, info):
        """获取一条微博的全部信息"""
        #try:
        weibo_info = info['mblog']
        weibo_id = weibo_info['id']
        if weibo_info['comments_count']>0: 
            self.get_review(weibo_id)
        # print("\n\n*************开始提取正文了1\n\n")
        retweeted_status = weibo_info.get('retweeted_status')
        is_long = weibo_info['isLongText']
        if retweeted_status:  # 转发
            retweet_id = retweeted_status['id']
            is_long_retweet = retweeted_status['isLongText']
            if is_long:
                weibo = self.get_long_weibo(weibo_id)  #长微博处理函数
                if not weibo:
                    weibo = self.parse_weibo(weibo_info)  #微博存在内存中，暂时还没有写入文件或数据库
            else:
                weibo = self.parse_weibo(weibo_info)
            if is_long_retweet:                                          #retweet代表是否为转发微博
                retweet = self.get_long_weibo(retweet_id)
                if not retweet:
                    retweet = self.parse_weibo(retweeted_status)
            else:
                retweet = self.parse_weibo(retweeted_status)
            retweet['created_at'] = self.standardize_date(
                retweeted_status['created_at'])
            weibo['retweet'] = retweet
        else:  # 原创
            if is_long:
                weibo = self.get_long_weibo(weibo_id)
                if not weibo:
                    weibo = self.parse_weibo(weibo_info)
            else:
                weibo = self.parse_weibo(weibo_info)
        weibo['created_at'] = self.standardize_date(
            weibo_info['created_at'])
        # fliter_text =re.sub('[\U00010000-\U0010ffff]|[\uD800-\uDBFF][\uDC00-\uDFFF]','',weibo["text"]) # 去除评论中表情等的特殊字符
        # """必须包含表情,且不能只有一个表情"""
        # if fliter_text != weibo["text"] and fliter_text != "": 
        #     weibo = None
        return weibo
        #except Exception as e:
            #print("Error: ", e)
            #traceback.print_exc()
            
    
    

    def is_pinned_weibo(self, info):
        """判断微博是否为置顶微博"""
        weibo_info = info['mblog']
        title = weibo_info.get('title')
        if title and title.get('text') == u'置顶':
            return True
        else:
            return False

    def get_one_page(self, page):
        """获取一页的全部微博"""
        try:
            js = self.get_weibo_json(page)
            if js['ok']:
                weibos = js['data']['cards']
                for w in weibos:
                    if w['card_type'] == 9:
                        wb = self.get_one_weibo(w)
                        if wb==None:
                            continue
                        """接收判断是否为含表情的文本"""
                        

                        # print("\n\n*************开始提取正文了2\n\n")
                        # if wb:
                        #     #continue
                        #     created_at = datetime.strptime(
                        #         wb['created_at'], "%Y-%m-%d")
                        #     since_date = datetime.strptime(
                        #         self.since_date, "%Y-%m-%d")
                        #     if created_at < since_date:        
                        #         #created_at是微博创建时间，since_date是自己指定的微博最早发布时间
                        #         if self.is_pinned_weibo(w):  
                        #             #判断是否为置顶微博，话题里置顶微博创建时间如果早于最早发布时间，那么跳过这一页循环
                        #             continue
                        #         else:
                        #             return True
                        if (not self.filter) or (
                                'retweet' not in wb.keys()):
                            # print("\n\n*************开始提取正文了3\n\n")
                            self.weibo.append(wb)                                        #self.weibo = []  # 存储爬取到的所有微博信息
                            self.weibo_id_list.append(wb['id'])
                            self.got_count = self.got_count + 1
                            # print(self.got_count)
                            # self.print_weibo(wb)
        except Exception as e:
            print("Error: ", e)
            traceback.print_exc()

    def get_page_count(self):
        """获取微博页数"""
        weibo_count = self.user['statuses_count']
        page_count = int(math.ceil(weibo_count / 10.0))
        return page_count

    def get_write_info(self, wrote_count):
        """获取要写入的微博信息"""
        write_info = []
        for w in self.weibo[wrote_count:]:
            wb = OrderedDict()
            for k, v in w.items():
                if k not in ['user_id', 'screen_name', 'retweet']:
                    if 'unicode' in str(type(v)):
                        v = v.encode('utf-8')
                    wb[k] = v
            if not self.filter:
                if w.get('retweet'):
                    wb['is_original'] = False
                    for k2, v2 in w['retweet'].items():
                        if 'unicode' in str(type(v2)):
                            v2 = v2.encode('utf-8')
                        wb['retweet_' + k2] = v2
                else:
                    wb['is_original'] = True
            write_info.append(wb)
        return write_info

    def get_filepath(self, type):
        """获取结果文件路径"""
        try:
            file_dir = os.path.split(
                os.path.realpath(__file__)
            )[0] + os.sep + 'weibo' + os.sep + self.question
            if type == 'img' or type == 'video':
                file_dir = file_dir + os.sep + type
            if not os.path.isdir(file_dir):
                os.makedirs(file_dir)
            if type == 'img' or type == 'video':
                return file_dir
            file_path = file_dir + os.sep + self.question + '.' + type
            return file_path
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_result_headers(self):
        """获取要写入结果文件的表头"""
        result_headers = [
            'id', 'bid', '正文', '原始图片url', '视频url', '位置', '日期', '工具', '点赞数',
            '评论数', '转发数', '话题', '@用户'
        ]
        if not self.filter:
            result_headers2 = ['是否原创', '源用户id', '源用户昵称']
            result_headers3 = ['源微博' + r for r in result_headers]
            result_headers = result_headers + result_headers2 + result_headers3
        return result_headers

    def write_csv(self, wrote_count):
        """将爬到的信息写入csv文件"""
        write_info = self.get_write_info(wrote_count)
        result_headers = self.get_result_headers()
        result_data = [w.values() for w in write_info]
        if sys.version < '3':  # python2.x
            with open(self.get_filepath('csv'), 'ab') as f:
                f.write(codecs.BOM_UTF8)
                writer = csv.writer(f)
                if wrote_count == 0:
                    writer.writerows([result_headers])
                writer.writerows(result_data)
        else:  # python3.x
            with open(self.get_filepath('csv'),
                      'a',
                      encoding='utf-8-sig',
                      newline='') as f:
                writer = csv.writer(f)
                if wrote_count == 0:
                    writer.writerows([result_headers])
                writer.writerows(result_data)
        print(u'%d条微博写入csv文件完毕,保存路径:' % self.got_count)
        print(self.get_filepath('csv'))

    def info_to_mongodb(self, collection, info_list):
        """将爬取的信息写入MongoDB数据库"""
        try:
            import pymongo
        except ImportError:
            sys.exit(u'系统中可能没有安装pymongo库，请先运行 pip install pymongo ，再运行程序')
        try:
            from pymongo import MongoClient

            client = MongoClient()
            db = client['weibo']
            collection = db[collection]
            for info in info_list:
                if not collection.find_one({'id': info['id']}):
                    collection.insert_one(info)
                else:
                    collection.update_one({'id': info['id']}, {'$set': info})
        except pymongo.errors.ServerSelectionTimeoutError:
            sys.exit(u'系统中可能没有安装或启动MongoDB数据库，请先根据系统环境安装或启动MongoDB，再运行程序')

    def weibo_to_mongodb(self, wrote_count):
        """将爬取的微博信息写入MongoDB数据库"""
        self.info_to_mongodb('weibo', self.weibo[wrote_count:])
        print(u'%d条微博写入MongoDB数据库完毕' % self.got_count)

    def mysql_create(self, connection, sql):
        """创建MySQL数据库或表"""
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql)
        finally:
            connection.close()

    def mysql_create_database(self, mysql_config, sql):
        """创建MySQL数据库"""
        try:
            import pymysql
        except ImportError:
            sys.exit(u'系统中可能没有安装pymysql库，请先运行 pip install pymysql ，再运行程序')
        try:
            if self.mysql_config:
                mysql_config = self.mysql_config
            connection = pymysql.connect(**mysql_config)
            self.mysql_create(connection, sql)
        except pymysql.OperationalError:
            sys.exit(u'系统中可能没有安装或正确配置MySQL数据库，请先根据系统环境安装或配置MySQL，再运行程序')

    def mysql_create_table(self, mysql_config, sql):
        """创建MySQL表"""
        import pymysql

        if self.mysql_config:
            mysql_config = self.mysql_config
        mysql_config['db'] = 'weibo'
        connection = pymysql.connect(**mysql_config)
        self.mysql_create(connection, sql)

    def mysql_insert(self, mysql_config, table, data_list):
        """向MySQL表插入或更新数据"""
        import pymysql

        if len(data_list) > 0:
            keys = ', '.join(data_list[0].keys())
            values = ', '.join(['%s'] * len(data_list[0]))
            if self.mysql_config:
                mysql_config = self.mysql_config
            mysql_config['db'] = 'weibo'
            connection = pymysql.connect(**mysql_config)
            cursor = connection.cursor()
            sql = """INSERT INTO {table}({keys}) VALUES ({values}) ON
                     DUPLICATE KEY UPDATE""".format(table=table,
                                                    keys=keys,
                                                    values=values)
            update = ','.join([
                " {key} = values({key})".format(key=key)
                for key in data_list[0]
            ])
            sql += update
            try:
                cursor.executemany(
                    sql, [tuple(data.values()) for data in data_list])
                connection.commit()
            except Exception as e:
                connection.rollback()
                print('Error: ', e)
                traceback.print_exc()
            finally:
                connection.close()

    def weibo_to_mysql(self, wrote_count):
        """将爬取的用户信息写入MySQL数据库"""
        mysql_config = {
            'host': 'localhost',
            'port': 3306,
            'user': 'root',
            'password': '123456',
            'charset': 'utf8mb4'
        }
        # 创建'weibo'表
        create_table = """
                CREATE TABLE IF NOT EXISTS weibo (
                id varchar(20) NOT NULL,
                bid varchar(12) NOT NULL,
                user_id varchar(20),
                screen_name varchar(20),
                text varchar(2000),
                topics varchar(200),
                at_users varchar(200),
                pics varchar(1000),
                video_url varchar(300),
                location varchar(100),
                created_at DATETIME,
                source varchar(30),
                attitudes_count INT,
                comments_count INT,
                reposts_count INT,
                retweet_id varchar(20),
                PRIMARY KEY (id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
        self.mysql_create_table(mysql_config, create_table)
        weibo_list = []
        retweet_list = []
        for w in self.weibo[wrote_count:]:
            if 'retweet' in w:
                w['retweet']['retweet_id'] = ''
                retweet_list.append(w['retweet'])
                w['retweet_id'] = w['retweet']['id']
                del w['retweet']
            else:
                w['retweet_id'] = ''
            weibo_list.append(w)
        # 在'weibo'表中插入或更新微博数据
        self.mysql_insert(mysql_config, 'weibo', retweet_list)
        self.mysql_insert(mysql_config, 'weibo', weibo_list)
        print(u'%d条微博写入MySQL数据库完毕' % self.got_count)

    def write_data(self, wrote_count):
        """将爬到的信息写入文件或数据库"""
        if self.got_count > wrote_count:
            if 'csv' in self.write_mode:
                self.write_csv(wrote_count)
            if 'mysql' in self.write_mode:
                self.weibo_to_mysql(wrote_count)
            if 'mongo' in self.write_mode:
                self.weibo_to_mongodb(wrote_count)

    def get_pages(self):
        """获取全部微博"""
        self.get_pagenum_info()
        page_count = self.get_page_count()
        # print(page_count)
        wrote_count = 0
        page1 = 0
        random_pages = random.randint(1, 5)
        for page in tqdm(range(1, page_count + 1), desc='Progress'):
            print(u'第%d页' % page)
            #self.print_user_info()
            is_end = self.get_one_page(page)
            if is_end:
                break

            if page % 1 == 0:  # 每页写入一次文件
                self.write_data(wrote_count)
                wrote_count = self.got_count

            # 通过加入随机等待避免被限制。爬虫速度过快容易被系统限制(一段时间后限
            # 制会自动解除)，加入随机等待模拟人的操作，可降低被系统限制的风险。默
            # 认是每爬取1到5页随机等待6到10秒，如果仍然被限，可适当增加sleep时间
            if page - page1 == random_pages and page < page_count:
                sleep(random.randint(6, 10))
                page1 = page
                random_pages = random.randint(1, 5)
        self.write_data(wrote_count)  # 将剩余不足20页的微博写入文件
        print(u'微博爬取完成，共爬取%d条微博' % self.got_count)

    def get_user_list(self, file_name):
        """获取文件中的微博id信息"""
        with open(file_name, 'rb') as f:
            lines = f.read().splitlines()
            lines = [line.decode('utf-8') for line in lines]
            question_list = [
                line.split(' ')[0] for line in lines
                if len(line.split(' ')) > 0 and line.split(' ')[0].isdigit()
            ]
        return question_list

    def initialize_info(self, question): 
        """初始化爬虫信息"""
        self.weibo = []
        self.user = {}
        self.got_count = 0
        self.question = question
        self.weibo_id_list = []

    def start(self):
        """运行爬虫"""
        try:
            for question in self.question_list:
                self.initialize_info(question)            #初始化爬虫信息
                self.get_pages()                                #应当在此页获取initialize里的一些信息
                print(u'信息抓取完毕')
                print('*' * 100)
                if self.pic_download == 1:
                    self.download_files('img')
                if self.video_download == 1:
                    self.download_files('video')
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()


def main():
    try:
        config_path = os.path.split(
            os.path.realpath(__file__))[0] + os.sep + 'config.json'
        if not os.path.isfile(config_path):
            sys.exit(u'当前路径：%s 不存在配置文件config.json' %
                     (os.path.split(os.path.realpath(__file__))[0] + os.sep))
        with open(config_path) as f:
            config = json.loads(f.read())
        wb = Weibo(config)
        wb.start()  # 爬取微博信息
    except ValueError:
        print(u'config.json 格式不正确，请参考 '
              u'https://github.com/dataabc/weibo-crawler#3程序设置')
    except Exception as e:
        print('Error: ', e)
        traceback.print_exc()


if __name__ == '__main__':
    main()
