
import os
import requests
import json
import time
import telepot
import shelve

EXCHANGES = {
    'poloniex': {
        'name': 'Poloniex',
        'url': 'https://www.poloniex.com/exchange#{}'
    }
}
DEBUG_INFO = {
    'exchanges': {}
}

def get_tickers(exchange):
    res = requests.get('https://www.poloniex.com/public?command=returnTicker')
    return json.loads(res.text).keys()

def diff_tickers(old_tickers, new_tickers):
    new = []
    for ticker in new_tickers:
        if ticker not in old_tickers:
            new.append(ticker)
    return new

class Bot:

    def __init__(self, token):
        self.bot = telepot.Bot(token)
        self.me = self.bot.getMe()
        self.bot.message_loop(self._on_message)
        self.db = shelve.open('bot.shelve.db')

    def notify_ticker(self, ticker, exchange):
        url = exchange['url'].format(ticker)
        for user_id in self.db:
            self.bot.sendMessage(user_id, 'Detected ticker on {}! Symbol: {}, Url: {}'.format(exchange['name'], ticker, url))

    def _on_message(self, msg):
        user_id = msg['from']['id']
        self.db[str(user_id)] = msg['from']
        self.db.sync()
        if msg['text'] == '/debug':
            text = 'Debug info:\n\n'
            for exchange in DEBUG_INFO['exchanges']:
                exchange_info = EXCHANGES[exchange]
                info = DEBUG_INFO['exchanges'][exchange]
                duration = round(time.time() - info['last_check'])
                text += '{}: last check = {}s ago, num tickers = {}\n'.format(exchange_info['name'], duration, len(info['tickers']))
            self.bot.sendMessage(user_id, text)
            return
        if msg['text'] == '/tickers':
            text = 'I know about the following tickers:\n\n'
            for exchange in DEBUG_INFO['exchanges']:
                exchange_info = EXCHANGES[exchange]
                info = DEBUG_INFO['exchanges'][exchange]
                text += 'Poliniex:\n{}'.format(', '.join(info['tickers']))
            self.bot.sendMessage(user_id, text)
            return
        self.bot.sendMessage(user_id, 'Hi there. I will notify you when any new currencies hit the Poloniex exchange')

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

def run():
    bot = Bot(os.getenv('TELEGRAM_TOKEN'))
    trackers = {}
    for exchange in EXCHANGES:
        trackers[exchange] = TickerTracker(bot, exchange)
    while True:
        for exchange in EXCHANGES:
            trackers[exchange].check()
        time.sleep(3)

run()
