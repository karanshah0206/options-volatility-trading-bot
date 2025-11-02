# Algorithmic Volatility Trading (Rotman Trading Simulator)
# Uses options strategies to trade volatility for profit by exploiting mismatches in implied and realized volatility
# Written by: Karan Manoj Shah
# Written on: 19 September 2025

import requests
import pandas as pd
from time import sleep
from scipy.stats import norm
import numpy as np

# networking constants (adjust as required)
SOURCE_URL = "http://localhost:9999/v1/"
CASE_PATH = "case"
SECURITIES_PATH = "securities"
ORDERS_PATH = "orders"
TRADER_PATH = "trader"
NEWS_PATH = "news"
API_KEY = {"X-API-Key": "KEY_HERE"}
ACTIVE_STATUS = "ACTIVE"

# strategy constants (adjust as required)
MKT_FEE = 0.02
SHARES_PER_CONTRACT = 100
OPTIONS_QTY_PER_TRADE = 90
MAX_TICKS_IN_SESSION = 300
REQ_FIELDS = ["ticker", "type", "last", "bid", "ask", "position", "vwap"]
NET_DELTA_RISK_LIMIT = 5000 # +/-
SHARES_ORDER_LIMIT = 10000

# get market tick count and check if market is currently inactive
def get_tick(session):
    res = session.get(SOURCE_URL + CASE_PATH)
    if not res.ok:
        raise Exception(f"failed to get case data: {res.status_code} {res.text}")
    return res.json()["tick"], res.json()["status"] != ACTIVE_STATUS

# get securities via JSON
def get_securities(session):
    res = session.get(SOURCE_URL + SECURITIES_PATH)
    if not res.ok:
        raise Exception(f"failed to get securities data: {res.status_code} {res.text}")
    return res.json()

# get net liquidation value of trader
def get_profit_loss(session):
    res = session.get(SOURCE_URL + TRADER_PATH)
    if not res.ok:
        raise Exception(f"failed to get trader data: {res.status_code} {res.text}")
    return res.json()["nlv"]

# get realized volatility from weekly announcements
def get_realized_volatility(session):
    res = session.get(SOURCE_URL + NEWS_PATH)
    if not res.ok:
        raise Exception(f"failed to get news: {res.status_code} {res.text}")
    latest_news = res.json()[0]
    news_body = latest_news["body"].split()
    # we use if condition here because first announcement comes with a different format
    try:
        if len(news_body) == 16:
            return float(news_body[-1][:-1]) / 100.0
        else:
            return float(news_body[29][:-2]) / 100.0
    except:
        return -1

# buy a stock or option at market price
def buy(session, ticker, quantity):
    session.post(f"{SOURCE_URL}{ORDERS_PATH}?ticker={ticker}&type=MARKET&quantity={quantity}&action=BUY")

# sell a stock or option at market price
def sell(session, ticker, quantity):
    session.post(f"{SOURCE_URL}{ORDERS_PATH}?ticker={ticker}&type=MARKET&quantity={quantity}&action=SELL")

# convert ticker time to time in years
def get_time(tick):
    return (300. - tick) / 3600

# Black-Scholes pricing model
# S = stock price, K = strike price, r = risk-free rate, sigma = volatility, T = time to expiration in years
def black_scholes_price(S, K, r, sigma, T, is_call=True):
    if T <= 0 or sigma <= 0:
        return max(S - K, 0.0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if is_call:
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

# Delta calculation (Greeks)
# S = stock price, K = strike price, r = risk-free rate, sigma = volatility, T = time to expiration in years
def calculate_delta(S, K, r, sigma, T, is_call=True, h=0.01):
    return (black_scholes_price(S + h, K, r, sigma, T, is_call) - black_scholes_price(S - h, K, r, sigma, T, is_call)) / (2 * h)

# execute trades based on options mispricing
def perform_options_trades(session, stats):
    for ticker, data in stats.items():
        if ticker == "RTM":
            continue

        market_price = data["market"]
        target_price = data["target"]
        position = data["position"]

        if position == 0: # no current position
            if abs(market_price - target_price) >= 0.04:
                if market_price < target_price: # take a long position
                    buy(session, ticker, OPTIONS_QTY_PER_TRADE)
                    data["position"] = 1
                    print(f"Opened Long {ticker} at {market_price} with target {target_price}")
                else: # take a short position
                    sell(session, ticker, OPTIONS_QTY_PER_TRADE)
                    data["position"] = 2
                    print(f"Opened Short {ticker} at {market_price} with target {target_price}")
        elif position == 1: # long position
            if market_price >= target_price or abs(market_price - target_price) <= 0.01: # book profit
                sell(session, ticker, OPTIONS_QTY_PER_TRADE)
                data["position"] = 0
                print(f"Closed long {ticker} at {market_price} with target {target_price}")
        elif position == 2: # short position
            if market_price <= target_price or abs(market_price - target_price) <= 0.01: # book profit
                buy(session, ticker, OPTIONS_QTY_PER_TRADE)
                data["position"] = 0
                print(f"Closed short {ticker} at {market_price} with target {target_price}")

# hedge Delta risk by trading underlying shares to build Delta-neutral portfolio
def manage_risk(session, stats):
    net_delta = 0.0

    for ticker, data in stats.items():
        if ticker == "RTM":
            continue

        delta = data["delta"]
        position = data["position"]

        if position == 1: #long
            net_delta += delta * OPTIONS_QTY_PER_TRADE * SHARES_PER_CONTRACT
        elif position == 2: #short
            net_delta -= delta * OPTIONS_QTY_PER_TRADE * SHARES_PER_CONTRACT

    position = stats["RTM"]["position"]
    net_delta += position

    # Over Delta risk limit: Delta neutralization required
    if abs(net_delta) > NET_DELTA_RISK_LIMIT:
        shares_to_trade = abs(int(net_delta)) * 0.7

        if net_delta > 0: # Too long, sell shares
            print(f"Delta hedge: Sold {shares_to_trade} shares")
            while shares_to_trade > SHARES_ORDER_LIMIT:
                sell(session, "RTM", SHARES_ORDER_LIMIT)
                shares_to_trade -= SHARES_ORDER_LIMIT
            if shares_to_trade > 0:
                sell(session, "RTM", shares_to_trade)
        else: # Too short, buy shares
            print(f"Delta hedge: Bought {shares_to_trade} shares")
            while shares_to_trade > SHARES_ORDER_LIMIT:
                buy(session, "RTM", SHARES_ORDER_LIMIT)
                shares_to_trade -= SHARES_ORDER_LIMIT
            if shares_to_trade > 0:
                buy(session, "RTM", shares_to_trade)
    # Settling hedge for profit if previous hedge position is no longer required
    elif position > 0 and stats["RTM"]["vwap"] < stats["RTM"]["market"] - MKT_FEE * position:
        something = net_delta - position
        if abs(something) < NET_DELTA_RISK_LIMIT:
            print(f"Delta hedge: Sold {position} shares for {stats["RTM"]["market"] - stats["RTM"]["vwap"] - 0.01} profit")
            sell(session, "RTM", position)
    elif position < 0 and stats["RTM"]["vwap"] > stats["RTM"]["market"] + MKT_FEE * abs(position):
        something = net_delta - position
        if abs(something) < NET_DELTA_RISK_LIMIT:
            print(f"Delta hedge: Bought {abs(position)} shares for {stats["RTM"]["vwap"] - stats["RTM"]["market"] - 0.01} profit")
            buy(session, "RTM", abs(position))

if __name__ == "__main__":
    with requests.Session() as session:
        session.headers.update(API_KEY)

        sigma = -1 # realized volatility

        current_tick, shutdown = get_tick(session)
        previous_tick = 0

        stats = {
            # ETF
            "RTM": {
                "position": 0, # 0 = no position, 1 = long, 2 = short
                "target": 0, # settle at this price
                "market": 0, # current buy/sell market price
                "vwap": 0, # Volume-weighted average price
            },
            # Options
            "RTM48C": {
                "position": 0, # 0 = no position, 1 = long, 2 = short
                "target": 0, # settle at this price
                "market": 0, # current buy/sell market price
                "delta": 0 # Delta (Greeks)
            },
            "RTM49C": {"position": 0, "target": 0, "market": 0, "delta": 0},
            "RTM50C": {"position": 0, "target": 0, "market": 0, "delta": 0},
            "RTM51C": {"position": 0, "target": 0, "market": 0, "delta": 0},
            "RTM52C": {"position": 0, "target": 0, "market": 0, "delta": 0},
            "RTM48P": {"position": 0, "target": 0, "market": 0, "delta": 0},
            "RTM49P": {"position": 0, "target": 0, "market": 0, "delta": 0},
            "RTM50P": {"position": 0, "target": 0, "market": 0, "delta": 0},
            "RTM51P": {"position": 0, "target": 0, "market": 0, "delta": 0},
            "RTM52P": {"position": 0, "target": 0, "market": 0, "delta": 0},
        }

        # wait for trading session to start
        while shutdown:
            sleep(0.4)
            current_tick, shutdown = get_tick(session)

        # main loop
        while current_tick < MAX_TICKS_IN_SESSION and not shutdown:
            if current_tick != previous_tick:
                # get securities data
                assets = pd.DataFrame(get_securities(session))[REQ_FIELDS]

                # get time to expiration in years
                T = get_time(current_tick)

                # update realized volatility
                if current_tick in [1, 2, 74, 75, 149, 150, 224, 225]:
                    temp = get_realized_volatility(session)
                    if (temp > 0):
                        sigma = temp
                    # realized_volatility = get_realized_volatility(session)
                        print("Realized for this week:", sigma)

                # get underlying asset's last price
                S = assets.loc[assets["ticker"] == "RTM", "last"].iloc[0]
                stats["RTM"]["market"] = S
                stats["RTM"]["position"] = assets.loc[assets["ticker"] == "RTM", "position"].iloc[0]
                stats["RTM"]["vwap"] = assets.loc[assets["ticker"] == "RTM", "vwap"].iloc[0]

                # update market prices, identify mispriced options opportunities using Black-Scholes and Greeks (Delta)
                for K in [48, 49, 50, 51, 52]:
                    if sigma < 0: # cannot make decisions without Sigma
                        break

                    for option_type in ["C", "P"]:
                        ticker = f"RTM{K}{option_type}"
                        is_call = option_type == "C"

                        stats[ticker]["market"] = assets.loc[assets["ticker"] == ticker, "last"].iloc[0]
                        stats[ticker]["delta"] = calculate_delta(S, K, 0.0, sigma, T, is_call)

                        black_scholes = black_scholes_price(S, K, 0.0, sigma, T, is_call)
                        if stats[ticker]["position"] == 0: # no position
                            stats[ticker]["target"] = black_scholes
                        elif stats[ticker]["position"] == 1: # long position
                            stats[ticker]["target"] = max(black_scholes, stats[ticker]["target"])
                        elif stats[ticker]["position"] == 2: # short position
                            stats[ticker]["target"] = min(black_scholes, stats[ticker]["target"])

                # make trades and hedge Delta risk if required
                perform_options_trades(session, stats)
                manage_risk(session, stats)

            sleep(0.4)
            previous_tick = current_tick
            current_tick, shutdown = get_tick(session)

        print("TERMINATED with", get_profit_loss(session))
