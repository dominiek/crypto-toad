
# Crypto Toad

Dockerized Telegram bot for Crypto currency intelligence.

## Features

* Alert when new currencies hit on Poloniex, Bittrex, Liqui.io and Tidex
* Alert when ICO related rumors happen on Reddit

## Use

Hit up @CryptoToadBot on Telegram.


## Build

```bash
docker build -t crypto-toad .
```

## Development Run

```bash
mkdir -p data
docker start \
  --env TELEGRAM_TOKEN=$ID:$HASH \
  --volume `pwd`:/workdir/data
  crypto-toad
```
