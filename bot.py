
import os
import requests
import json
import sys
import time
import telepot
import shelve

EXCHANGES = {
    'poloniex': {
        'name': 'Poloniex',
        'url': 'https://www.poloniex.com/exchange#{}',
        'lowercase': True
    },
    'bittrex': {
        'name': 'Bittrex',
        'url': 'https://bittrex.com/Market/Index?MarketName={}'
    },
    'liqui.io': {
        'name': 'Liqui.io',
        'url': 'https://liqui.io/#/exchange/{}',
        'uppercase': True
    },
    'tidex': {
        'name': 'Tidex',
        'url': 'https://tidex.com/exchange/#/pair/{}',
        'uppercase': True
    }
}
DEBUG_INFO = {
    'exchanges': {},
    'reddit_forums': {}
}

def get_tickers(exchange):
    if exchange == 'poloniex':
        res = requests.get('https://www.poloniex.com/public?command=returnTicker')
        return json.loads(res.text).keys()
    if exchange == 'bittrex':
        res = requests.get('https://bittrex.com/api/v1.1/public/getmarketsummaries')
        return map(lambda x: x['MarketName'], json.loads(res.text)['result'])
    if exchange == 'liqui.io':
        res = requests.get('https://api.liqui.io/api/3/info')
        return json.loads(res.text)['pairs'].keys()
    if exchange == 'tidex':
        res = requests.get('https://api.tidex.com/api/3/info')
        return json.loads(res.text)['pairs'].keys()

def diff_tickers(old_tickers, new_tickers):
    new = []
    for ticker in new_tickers:
        if ticker not in old_tickers:
            new.append(ticker)
    return new

def diff_posts(old_posts, new_posts):
    new = []
    old_post_ids = map(lambda p: p['id'], old_posts)
    for post in new_posts:
        if post['id'] not in old_post_ids:
            new.append(post)
    return new

def get_reddit_rumors(forum):
    res = requests.get('https://www.reddit.com/r/{}/new/.json'.format(forum))
    result = json.loads(res.text)
    if result.has_key('error') and result['error']:
        print('API error: ', result)
        return []
        #raise Exception('API Error: {}'.format(result['message']))
    return map(lambda x: x['data'], result['data']['children'])

class Bot:

    def __init__(self, token):
        self.bot = telepot.Bot(token)
        self.me = self.bot.getMe()
        self.bot.message_loop(self._on_message)
        self.db = shelve.open('bot.shelve.db')

    def notify_ticker(self, ticker, exchange):
        url_ticker = ticker
        if exchange.get('lowercase', False) == True:
            url_ticker = url_ticker.lower()
        if exchange.get('uppercase', False) == True:
            url_ticker = url_ticker.upper()
        url = exchange['url'].format(url_ticker)
        for user_id in self.db:
            self.bot.sendMessage(user_id, 'Detected ticker on {}! Symbol: {}, Url: {}'.format(exchange['name'], ticker, url))

    def notify_post(self, post, forum):
        text = 'New potential rumor on r/{}:\n\n{}'.format(forum, 'https://reddit.com{}'.format(post['permalink']))
        for user_id in self.db:
            self.bot.sendMessage(user_id, text)

    def _on_message(self, msg):
        user_id = msg['from']['id']
        self.db[str(user_id)] = msg['from']
        self.db.sync()
        command = msg['text'].split(' ')
        if len(command) > 0 and command[0] == '/debug':
            text = 'Debug info:\n\n'
            for exchange in DEBUG_INFO['exchanges']:
                exchange_info = EXCHANGES[exchange]
                info = DEBUG_INFO['exchanges'][exchange]
                duration = round(time.time() - info['last_check'])
                text += '{}: last check = {}s ago, num tickers = {}\n'.format(exchange_info['name'], duration, len(info['tickers']))
            self.bot.sendMessage(user_id, text)
            return
        if len(command) > 0 and command[0] == '/posts':
            self.bot.sendMessage(user_id, 'I have read these posts recently:\n\n')
            for forum in DEBUG_INFO['reddit_forums']:
                info = DEBUG_INFO['reddit_forums'][forum]
                text = '\n'
                for post in info['posts']:
                    duration = round(time.time() - float(post['created']))
                    text += '{}\n: {}\n\n'.format(post['title'], 'https://reddit.com{}'.format(post['permalink']))
                self.bot.sendMessage(user_id, text)
            return
        if len(command) > 0 and command[0] == '/tickers':
            self.bot.sendMessage(user_id, 'I know about the following tickers:')
            for exchange in DEBUG_INFO['exchanges']:
                exchange_info = EXCHANGES[exchange]
                info = DEBUG_INFO['exchanges'][exchange]
                text = '\n{}:\n{}\n'.format(exchange_info['name'], ', '.join(info['tickers']))
                self.bot.sendMessage(user_id, text)
            return
        if len(command) > 2 and command[0] == '/simulate':
            exchange = command[1]
            if EXCHANGES.has_key(exchange):
                exchange_info = EXCHANGES[exchange]
                self.notify_ticker(command[2], exchange_info)
            return
        total_tickers = 0
        exchange_names = []
        for exchange in DEBUG_INFO['exchanges']:
            exchange_info = EXCHANGES[exchange]
            info = DEBUG_INFO['exchanges'][exchange]
            total_tickers += len(info['tickers'])
            exchange_names.append(exchange_info['name'])
        text = 'Hi there, I am currently tracking {} tickers in real-time on {} and {} as well as rumors on Reddit.\n'.format(total_tickers, ', '.join(exchange_names[0:-1]), exchange_names[-1])
        text += '\nI will notify you instantly when I detect a new ticker!'
        self.bot.sendMessage(user_id, text)

class TickerTracker:

    def __init__(self, bot, exchange):
        self.bot = bot
        self.exchange = exchange
        self.tickers = get_tickers(exchange)

    def check(self):
        new_tickers = get_tickers(self.exchange)
        new = diff_tickers(self.tickers, new_tickers)
        DEBUG_INFO['exchanges'][self.exchange] = {
            'last_check': time.time(),
            'tickers': new_tickers
        }
        if len(new) > 0:
            print('New tickers on {}!'.format(self.exchange), new)
            for ticker in new:
                self.bot.notify_ticker(ticker, EXCHANGES[self.exchange])
            self.tickers = new_tickers
            return True
        return False

def post_is_interesting(post, forum):
    title = post.get('title', '').lower()
    keywords = ['exchange', 'listing', 'ico', 'new coin', 'listed', 'adding']
    for keyword in keywords:
        if keyword in title:
            return True
    for exchange in EXCHANGES:
        if exchange in title:
            return True
    return False

class RedditRumorTracker:

    def __init__(self, bot, forum):
        self.bot = bot
        self.forum = forum
        self.posts = get_reddit_rumors(forum)

    def check(self):
        posts = get_reddit_rumors(self.forum)
        new = diff_posts(self.posts, posts)
        DEBUG_INFO['reddit_forums'][self.forum] = {
            'last_check': time.time(),
            'posts': posts
        }
        if len(new) > 0:
            for post in new:
                if not post_is_interesting(post, self.forum):
                    continue
                print('New rumor on {}!'.format(self.forum))
                self.bot.notify_post(post, self.forum)
            self.posts = posts
            return True
        return False

def run():
    bot = Bot(os.getenv('TELEGRAM_TOKEN'))
    trackers = {}
    for exchange in EXCHANGES:
        trackers[exchange] = TickerTracker(bot, exchange)
    trackers['reddit_ethtrader'] = RedditRumorTracker(bot, 'ethtrader')
    i = 0
    while True:
        for item in trackers:
            if 'reddit' in item and (i % 2) == 1:
                continue
            trackers[item].check()
            #try:
            #    trackers[item].check()
            #except:
            #    print('Oops, received a little error when checking {} ({}), ignoring'.format(item, sys.exc_info()[0]))
        i+= 1
        time.sleep(3)

run()
