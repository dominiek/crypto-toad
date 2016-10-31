
import os
import requests
import json
import time
import telepot
import shelve

def get_tickers():
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

    def notify_ticker(self, ticker):
        url = 'https://www.poloniex.com/exchange#{}'.format(ticker)
        for user_id in self.db:
            self.bot.sendMessage(user_id, 'Detected ticker on Poloniex! Symbol: {}, Url: {}'.format(ticker, url))

    def _on_message(self, msg):
        user_id = msg['from']['id']
        self.db[str(user_id)] = msg['from']
        self.db.sync()
        self.bot.sendMessage(user_id, 'Hi there. I will notify you when any new currencies hit the Poloniex exchange')

def run():
    bot = Bot(os.getenv('TELEGRAM_TOKEN'))
    old_tickers = get_tickers()
    while True:
        new_tickers = get_tickers()
        new = diff_tickers(old_tickers, new_tickers)
        if len(new) > 0:
            print('New tickers!', new)
            for ticker in new:
                bot.notify_ticker(ticker)
        old_tickers = new_tickers
        time.sleep(3)

run()
