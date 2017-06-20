
import os
import requests
import json
import sys
import time
import telepot
import shelve
import logging

DB_FILE = 'data/bot.shelve.db'
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
    'reddit_forums': {},
    'uptime': time.time()
}
DEFAULT_REPLY_MARKUP = {'keyboard': [['Rumors', 'Help']], 'resize_keyboard': True}

root = logging.getLogger()
root.setLevel(logging.DEBUG)

ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
root.addHandler(ch)

def post_is_interesting(post, forum):
    title = post.get('title', '').lower()
    exact_keywords = [
        'new listing', 'new pre-sale', 'new coin',
        'now trading', 'now listing', 'now selling', 'went live',
        'coin added', 'symbol added', 'market added', 'new market',
        'new coins', 'coins added', 'will add', 'start selling'
    ]
    for keyword in exact_keywords:
        if keyword in title:
            return True
    combo_keywords = [
        'listing', 'ico', 'adding', 'listed', 'added', 'listings',
        'symbols', 'trading',
    ]
    for exchange in EXCHANGES:
        for keyword in combo_keywords:
            if exchange in title and keyword in title:
                return True
    return False

def get_tickers(exchange):
    if exchange == 'poloniex':
        res = requests.get('https://www.poloniex.com/public?command=returnTicker', timeout=4)
        return json.loads(res.text).keys()
    if exchange == 'bittrex':
        res = requests.get('https://bittrex.com/api/v1.1/public/getmarketsummaries', timeout=4)
        return map(lambda x: x['MarketName'], json.loads(res.text)['result'])
    if exchange == 'liqui.io':
        res = requests.get('https://api.liqui.io/api/3/info', timeout=4)
        return json.loads(res.text)['pairs'].keys()
    if exchange == 'tidex':
        res = requests.get('https://api.tidex.com/api/3/info', timeout=4)
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
    res = requests.get('https://www.reddit.com/r/{}/new/.json'.format(forum), headers={'User-agent': 'CryptoToad v0.1'}, timeout=4)
    result = json.loads(res.text)
    if result.has_key('error') and result['error']:
        logging.warning('API error', result)
        raise Exception('API Error: {}'.format(result['message']))
    return map(lambda x: x['data'], result['data']['children'])

class Bot:

    def __init__(self, token):
        self.bot = telepot.Bot(token)
        self.me = self.bot.getMe()
        self.bot.message_loop(self._on_message)
        self.db = shelve.open(DB_FILE)

    def notify_ticker(self, ticker, exchange):
        url_ticker = ticker
        if exchange.get('lowercase', False) == True:
            url_ticker = url_ticker.lower()
        if exchange.get('uppercase', False) == True:
            url_ticker = url_ticker.upper()
        url = exchange['url'].format(url_ticker)
        for user_id in self.db:
            self.bot.sendMessage(user_id, 'Detected ticker on {}! Symbol: {}, Url: {}'.format(exchange['name'], ticker, url), reply_markup=DEFAULT_REPLY_MARKUP)

    def notify_post(self, post, forum):
        text = 'New potential rumor on r/{}:\n\n{}'.format(forum,  'https://reddit.com{}'.format(post['permalink'].encode('utf-8')))
        for user_id in self.db:
            self.bot.sendMessage(user_id, text, reply_markup=DEFAULT_REPLY_MARKUP)

    def _on_message(self, msg):
        user_id = msg['from']['id']
        self.db[str(user_id)] = msg['from']
        self.db.sync()
        command = msg['text'].split(' ')
        if len(command) > 0 and (command[0] == '/help' or command[0] == 'Help'):
            text = """You can use the following commands:

/rumors - See latest rumors from Reddit
/tickers - List out all tickers being tracked
/debug - Internal info for nerds
            """
            self.bot.sendMessage(user_id, text, reply_markup=DEFAULT_REPLY_MARKUP)
            return
        if len(command) > 0 and command[0] == '/debug':
            text = 'Debug info:\n\n'
            for exchange in DEBUG_INFO['exchanges']:
                exchange_info = EXCHANGES[exchange]
                info = DEBUG_INFO['exchanges'][exchange]
                duration = round(time.time() - info['last_check'])
                text += '{}: last check = {}s ago, num tickers = {}\n'.format(exchange_info['name'], duration, len(info['tickers']))
            text += '\nUptime: {}h'.format(round(((time.time() - DEBUG_INFO['uptime'])/3600)*10)/10)
            self.bot.sendMessage(user_id, text, reply_markup=DEFAULT_REPLY_MARKUP)
            return
        if len(command) > 0 and (command[0] == '/rumors' or command[0] == 'Rumors'):
            self.bot.sendMessage(user_id, 'I have read these posts recently:\n\n')
            for forum in DEBUG_INFO['reddit_forums']:
                info = DEBUG_INFO['reddit_forums'][forum]
                text = '\n'
                for post in reversed(info['posts'][0:10]):
                    duration = int(round((time.time() - float(post['created_utc'])) / 60))
                    text = '{} minutes ago, {}\n: {}\n\n'.format(duration, post['title'].encode('utf-8'), 'https://reddit.com{}'.format(post['permalink'].encode('utf-8')))
                    self.bot.sendMessage(user_id, text, reply_markup=DEFAULT_REPLY_MARKUP)
            return
        if len(command) > 0 and command[0] == '/tickers':
            self.bot.sendMessage(user_id, 'I know about the following tickers:')
            for exchange in DEBUG_INFO['exchanges']:
                exchange_info = EXCHANGES[exchange]
                info = DEBUG_INFO['exchanges'][exchange]
                text = '\n{}:\n{}\n'.format(exchange_info['name'], ', '.join(info['tickers']))
                self.bot.sendMessage(user_id, text, reply_markup=DEFAULT_REPLY_MARKUP)
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
        text = ''
        if len(exchange_names) > 0:
            text = 'Hello Dear Sir, I am currently tracking {} tickers in real-time on {} and {} as well as rumors on Reddit.\n'.format(total_tickers, ', '.join(exchange_names[0:-1]), exchange_names[-1])
        text += '\nI will notify you instantly when I detect a new ticker or hear a rumor! Type /help for a full list of commands'
        self.bot.sendMessage(user_id, text, reply_markup=DEFAULT_REPLY_MARKUP)

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
            logging.info('New tickers on {}!'.format(self.exchange), new)
            for ticker in new:
                self.bot.notify_ticker(ticker, EXCHANGES[self.exchange])
            self.tickers = new_tickers
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
        self.posts = posts
        if len(new) > 0:
            for post in new:
                if not post_is_interesting(post, self.forum):
                    continue
                logging.info('New rumor on {}!'.format(self.forum))
                self.bot.notify_post(post, self.forum)
            return True
        return False

def run():
    logging.info('Initializing bot')
    bot = Bot(os.getenv('TELEGRAM_TOKEN'))
    trackers = {}
    for exchange in EXCHANGES:
        trackers[exchange] = TickerTracker(bot, exchange)
    trackers['reddit_ethtrader'] = RedditRumorTracker(bot, 'ethtrader')
    i = 0
    while True:
        for item in trackers:
            if 'reddit' in item and (i % 10) != 0:
                continue
            try:
                logging.info('Checking {} to see what\'s new'.format(item))
                trackers[item].check()
            except:
                logging.warning('Oops, received a little error when checking {} ({}), ignoring'.format(item, sys.exc_info()[0]))
        i+= 1
        time.sleep(5)

run()
