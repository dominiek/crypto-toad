
import os
import requests
import logging
import time
import json
import math


# Only play when price meets these bounds:
BUY_MAXIMUM_ASK = 3.0
BUY_MINUMUM_ASK = 0.0000000001

BETS = [
    {
        'btc_budget': 0.01,
        'buy_markup_factor': 2,
        'sell_markup_factor': 100
    },
    {
        'btc_budget': 0.01,
        'buy_markup_factor': 1.5,
        'sell_markup_factor': 20
    }
]

COOKIE_HEADER = os.getenv('COOKIE_HEADER', None)
if COOKIE_HEADER == None:
    raise Exception('Need COOKIE_HEADER')

PAIR = os.getenv('PAIR', None)
if PAIR == None:
    raise Exception('Need PAIR (e.g. BTC_ETH)')

SYMBOL = os.getenv('SYMBOL', None)
if SYMBOL == None:
    raise Exception('Need COOKIE_HEADER (e.g. ETH)')

headers = {
    'accept-encoding': 'gzip, deflate, sdch, br',
    'accept-language': 'en-US,en;q=0.8',
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/54.0.2840.71 Safari/537.36',
    'accept': '*/*',
    'referer': 'https://www.poloniex.com/exchange',
    'x-requested-with': 'XMLHttpRequest',
    'cookie': COOKIE_HEADER
}

class TradeError(Exception):
    pass

class NoTickerError(Exception):
    pass

class NoBalanceError(Exception):
    pass

class NoSaneTickerError(Exception):
    pass

def get_balance(symbol):
    res = requests.get('https://poloniex.com/private?command=returnDepositsAndWithdrawalsMobile')
    result = json.loads(res.text)
    balances = result['balances']
    if balances.has_key(symbol):
        raise NoBalanceError('No balance entry exists yet')
    return float(balances[symbol])

def get_ticker(pair):
    res = requests.get('https://www.poloniex.com/public?command=returnTicker')
    tickers = json.loads(res.text)
    if not tickers.has_key(pair):
        raise NoTickerError('Ticker for pair does not exist yet')
    ticker = tickers[pair]
    for key in ticker:
        if key == 'id':
            continue
        ticker[key] = float(ticker[key])
    return ticker

def get_orders(pair, order_type):
    #https://poloniex.com/private?command=returnAllOpenOrders
    res = requests.get('https://www.poloniex.com/public?command=returnTicker')
    tickers = json.loads(res.text)['limit']
    if not tickers.has_key(pair):
        return []
    orders = tickers[pair]
    filtered_orders = []
    for order in orders:
        for key in ticker:
            if key == 'type':
                continue
            if key == 'orderID':
                continue
            if key == 'date':
                continue
            order[key] = float(order[key])
        if order['type'] == order_type:
            filtered_orders.append(order)
    return filtered_orders

def order_is_already_pending(orders, amount, rate):
    for order in orders:
        if order_compare(order, amount, rate) == True:
            return True
    return False

def order_compare(order, amount, rate):
    if round(order['rate'] * 100) == round(rate * 100) and round(order['amount']) == round(amount * 100):
        return True
    return False

def check_ticker_buy_sanity(ticker):
    if not ticker.has_key('lowestAsk'):
        raise NoSaneTickerError('No lowest ask yet')
    if not ticker.has_key('last'):
        raise NoSaneTickerError('No last yet')
    if ticker['lowestAsk'] > BUY_MAXIMUM_ASK:
        raise NoSaneTickerError('Asking price {} is more than maximum bound {}'.format(type(ticker['lowestAsk']), MAXIMUM_ASK))
    if ticker['lowestAsk'] < BUY_MINUMUM_ASK:
        raise NoSaneTickerError('Asking price {} is less than minumum bound {}'.format(ticker['lowestAsk'], MINUMUM_ASK))


def check_ticker_sell_sanity(ticker):
    if not ticker.has_key('lowestAsk'):
        raise NoSaneTickerError('No lowest ask yet')
    if not ticker.has_key('last'):
        raise NoSaneTickerError('No last yet')

def do_trade(pair, command, rate, amount):
    url = 'https://www.poloniex.com/private.php?currencyPair={}&rate={}&amount={}&command={}'.format(pair, rate, amount, command)
    res = requests.get(url, headers=headers)
    text = res.text.lower()
    if res.status_code == 200 and 'order' in text and 'placed' in text:
        logging.info('Trade made (order placed): {}'.format(res.text))
        return True
    if res.status_code == 200 and 'bought' in text:
        logging.info('Trade made (instant): {}'.format(res.text))
        return True
    raise TradeError("Bad response while making trade: {}:{}".format(res.status_code, res.text))

BASE_LOWEST_ASK = None

def perform_buys(pair):
    global BASE_LOWEST_ASK
    logging.warning('Attempting to place buy orders')
    ticker = None
    try:
        ticker = get_ticker(pair)
    except NoTickerError as e:
        logging.warning('No ticker yet ({}), waiting for 1 second to try again'.format(e.message))
        time.sleep(1)
        return perform_buys(pair)
    try:
        check_ticker_buy_sanity(ticker)
    except NoSaneTickerError as e:
        logging.warning('No SANE ticker yet ({}), waiting for 1 second to try again'.format(e.message))
        time.sleep(1)
        return perform_buys(pair)
    BASE_LOWEST_ASK = ticker['lowestAsk']
    for bet in BETS:
        rate = ticker['lowestAsk'] * bet['buy_markup_factor']
        amount = bet['btc_budget'] / rate
        success = False
        while success == False:
            logging.warning('Attempting to place bet with lowestAsk={}, rate={}, amount={}, btc_budget={}'.format(ticker['lowestAsk'], str(rate), str(amount), bet['btc_budget']))
            try:
                do_trade(pair, 'buy', rate, amount)
                success = True
                bet['buy_rate'] = rate
                bet['buy_amount'] = amount
            except TradeError as e:
                logging.warning('Trade error: {}, trying again in 1 second'.format(e.message))
                success = False
                time.sleep(2.5)

def perform_sells(pair, symbol):
    logging.warning('Attempting to place sell orders')
    for bet in BETS:
        rate = BASE_LOWEST_ASK * bet['sell_markup_factor']
        amount = bet['buy_amount']
        success = False
        while success == False:
            logging.warning('Attempting to place sell_order with BASE_LOWEST_ASK={}, rate={}, amount={}'.format(BASE_LOWEST_ASK, str(rate), str(amount)))
            try:
                do_trade(pair, 'sell', rate, amount)
                success = True
            except TradeError as e:
                logging.warning('Trade error: {}, trying again in 1 second'.format(e.message))
                success = False
                time.sleep(2.5)

perform_buys(PAIR)
perform_sells(PAIR, SYMBOL)
logging.warning('All bets are ON')
