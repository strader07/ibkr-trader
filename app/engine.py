
import json
import pickle
import pandas as pd
from scipy.stats import norm
from sortedcontainers import SortedDict
from datetime import datetime
from threading import Thread
import logging

from ib_insync import *
from config import *
from gui import main
from tick import Tick
import clib

import asyncio

# loop = asyncio.new_event_loop()
# asyncio.set_event_loop(loop)
ib = IB()
ib.connect("127.0.0.1", 7497, clientId=23)
global tickers
try:
    with open("tradeout/trades.pkl", "rb") as f:
        tickers = pickle.load(f)
except:
    tickers = SortedDict()


def get_prod_params(prod_params, params):
    keys = list(prod_params.keys())
    values = list(prod_params.values())

    values_processed = []
    for val in values:
        try:
            pairs = [item.strip(",. ") for item in val.split(",")]
            val_processed = {item.split("=")[0].strip(",. "): eval(item.split("=")[1].strip("(),. ")) for item in pairs}
            values_processed.append(val_processed)
        except:
            values_processed.append({})

    prod_params = {}
    for key, value in zip(keys, values_processed):
        temp = params.copy()
        temp.update(value)
        prod_params[key] = temp
        prod_params[key]["LATEST_BAR_SEEN"] = ""

    return prod_params


def get_bar_duration_size(mins):
    bar_sizes = ["1 min", "2 mins", "3 mins", "5 mins", "10 mins", "15 mins", "20 mins", "30 mins", "1 hour", "2 hours",
                 "3 hours", "4 hours", "8 hours", "1 day", "1 week", "1 month"]

    bar_size = mins
    if str(mins).isnumeric():
        hour = int(mins / 60)
        minute = mins % 60
        if minute == 1:
            bar_size = "1 min"
        if hour == 0 and minute > 1:
            bar_size = f"{minute} mins"
        if hour == 1:
            bar_size = "1 hour"
        if 1 < hour <= 8:
            bar_size = f"{hour} hours"
        if 24 > hour > 8:
            bar_size = "8 hours"
        if 7 * 24 >= hour >= 24:
            bar_size = "1 week"
        if hour > 7 * 24:
            bar_size = "1 month"
    else:
        bar_size = str(mins)

    if bar_size not in bar_sizes:
        bar_size = "15 mins"

    idx = bar_sizes.index(bar_size)
    duration = "1 D"
    if idx < 2:
        duration = "1 D"
    if 2 <= idx < 7:
        duration = "1 W"
    if 7 <= idx < 12:
        duration = "1 M"
    if idx == 12:
        duration = "2 M"
    if idx > 12:
        duration = "1 Y"

    return bar_size, duration


class Engine:
    prod_params = {}

    def __init__(self, params):
        self.config = Config()
        self.tickers = SortedDict()
        self.dfs = {}
        self.processed_params = {}
        self.latest_bar_seen = {}
        self.app_status = "OFF"
        try:
            with open("settings/app_status.txt", "w") as f:
                f.write(self.app_status)
                f.close()
        except Exception as e:
            print(e)

        # print("\n??-", self.config.params)

    def run_cycle(self):
        while True:
            if self.app_status == "ON":
                ib.sleep(5)
                print("\n\n=================== Cycle start! =====================\n")
                print(f"\nCurrent time: {datetime.now()}\n")
                print(f"\nCurrent trades: {self.tickers}\n")

                self.check_exit_trigger()
                self.config.update_prod_params()
                self.data_analysis()
                self.check_entry_trigger()

                print("\n=================== Cycle end! =====================\n")

            try:
                with open("settings/app_status.txt", "r") as fb:
                    self.app_status = fb.readlines()[0]
                    f.close()
            except Exception as e:
                self.app_status = "OFF"

    def check_exit_trigger(self):
        ib.reqExecutions()
        for key in self.tickers:
            print(key)
            ticker = self.tickers[key]
            entry_price = ticker.limit_price
            symbol = ticker.symbol
            direction = ticker.direction

            if not ticker.entry_filled and ticker.bracket_entry["limit_entry"].orderStatus.status == "Filled":
                ticker.entry_filled = True
                curr_bar_id = str(self.dfs[symbol].iloc[-1]["date"])
                if curr_bar_id not in self.tickers[key].max_hold_queue:
                    self.tickers[key].max_hold_queue.append(curr_bar_id)

                if not ticker.max_stop_exit:
                    max_stop_price = round(entry_price - (float(self.processed_params[symbol]["max_stop_sd"])) * (
                        float(self.processed_params[symbol]["sd_px"])), 2)
                    side = "SELL" if direction == "LONG" else "BUY"
                    max_stop_order = StopOrder(side, ticker.quantity, max_stop_price)
                    self.tickers[key].max_stop_exit = ib.placeOrder(ticker.bracket_entry["limit_entry"].contract,
                                                                    max_stop_order)

            if ticker.bracket_entry["limit_entry"].orderStatus.status != "Filled":
                print(f"{symbol} - entry not filled!")
                continue

            if ticker.max_stop_exit:
                if ticker.max_stop_exit.orderStatus.status == "Filled":
                    print(f"{symbol} - max stop order has been triggered.\nCancelling bracket order...")
                    ticker.exit_filled = True
                    ticker.exit_time = str(datetime.now())
                    ticker.bracket_entry["take_profit"] = ib.cancelOrder(ticker.bracket_entry["take_profit"].order)
                    continue

            if (ticker.bracket_entry["take_profit"].orderStatus.status == "Filled") or \
                    (ticker.bracket_entry["stop_loss"].orderStatus.status == "Filled"):
                print(f"{symbol} - exit triggered!")
                ticker.exit_filled = True
                ticker.exit_time = str(datetime.now())
                ticker.max_stop_exit = ib.cancelOrder(ticker.max_stop_exit.order)
                continue

            if ticker.market_exit and ticker.market_exit.orderStatus == "Filled":
                ticker.exit_filled = True

            if ticker.exit_filled:
                continue

            if len(ticker.max_hold_queue) >= float(self.processed_params[symbol]["max_prd_hold"]):
                print(f"{symbol} - passed max hold period without trade exit!\nLets close this position.")

                # closing the position at market
                side = "SELL" if ticker.direction == "LONG" else "BUY"
                _order = MarketOrder(side, ticker.quantity)
                ticker.market_exit = ib.placeOrder(ticker.bracket_entry["limit_entry"].contract, _order)
                ticker.exit_time = str(datetime.now())
                ib.sleep(4)
                if ticker.market_exit.orderStatus == "Filled":
                    ticker.exit_filled = True

                ticker.bracket_entry["take_profit"] = ib.cancelOrder(ticker.bracket_entry["take_profit"].order)
                ticker.max_stop_exit = ib.cancelOrder(ticker.max_stop_exit.order)
                continue

            current_bar_id = str(self.dfs["symbol"].iloc[-1]["date"])
            if current_bar_id in ticker.max_hold_queue:
                continue
            ticker.max_hold_queue.append(current_bar_id)

            # update take profit and stop loss order
            tp_price = round(entry_price + (float(self.processed_params[symbol]["target_sd"])) * (self.dfs[symbol].iloc[-1]["sd_px"]), 2)
            sl_price = round(entry_price - (float(self.processed_params[symbol]["stop_sd"])) * (self.dfs[symbol].iloc[-1]["sd_px"]), 2)
            contract = ticker.bracket_entry["limit_entry"].contract
            tp_order = ticker.bracket_entry["take_profit"].order
            sl_order = ticker.bracket_entry["stop_loss"].order
            tp_order.lmtPrice = tp_price
            tp_order.transmit = True
            sl_order.auxPrice = sl_price

            ticker.bracket_entry["take_profit"] = ib.placeOrder(contract, tp_order)
            ticker.bracket_entry["stop_loss"] = ib.placeOrder(contract, sl_order)
            ib.sleep(4)

    def data_analysis(self):

        params = self.config.params
        prod_params = self.config.prod_params
        self.processed_params = get_prod_params(prod_params, params)
        # print(f"current products specific parameters: \n")
        # print(json.dumps(self.processed_params, indent=4))
        symbols = [symbol.strip(",. ") for symbol in params["products"].split(",")]
        # symbols_in_trade = [key.split("_")[0].strip(",. ") for key in self.tickers.keys()]
        # symbols = [symbol for symbol in symbols if symbol not in symbols_in_trade]

        contracts = []
        for symbol in symbols:
            contracts.append(Stock(symbol, "SMART", 'USD'))
        ib.qualifyContracts(*contracts)
        ib.reqMarketDataType(4)

        for contract, symbol in zip(contracts, symbols):
            # print(contract)
            bar_size, duration = get_bar_duration_size(self.processed_params[symbol]["timeframe"])
            print(f"{symbol} - Bar size and duration: {bar_size}, {duration}")
            try:
                bars = ib.reqHistoricalData(
                    contract,
                    endDateTime='',
                    durationStr=duration,
                    barSizeSetting=bar_size,
                    whatToShow='TRADES',
                    useRTH=False,
                    formatDate=1,
                    keepUpToDate=False)
            except Exception as e:
                # print("historical data rek error: ", e)
                continue

            try:
                df = util.df(bars)[['date', 'open', 'high', 'low', 'close']].tail(100).reset_index(drop=True)
            except Exception as e:
                # print("dataframe convert error: ", e)
                continue

            df["percent_change"] = df.close.pct_change(int(float(self.processed_params[symbol]["percent_change_lag"])))
            # df["sd_percent"] = clib.std(df, "percent_change", int(float(processed_params[symbol]["sd_lag"])))
            df["sd_percent"] = df["percent_change"].rolling(int(float(self.processed_params[symbol]["sd_lag"]))).std()
            # df["sd_px"] = clib.std(df, "close", int(float(processed_params[symbol]["sd_lag"])))
            df["sd_px"] = df["close"].rolling(int(float(self.processed_params[symbol]["sd_lag"]))).std()
            df["percent_change_mean"] = df["percent_change"].rolling(
                int(float(self.processed_params[symbol]["sd_lag"]))).mean()
            df["percent_change_norm_ppf"] = norm.ppf(df["percent_change"], df["percent_change_mean"], df["sd_percent"])
            df["percent_change_norm_cdf"] = norm.cdf(float(self.processed_params[symbol]["norm_threshold"]), df["percent_change_mean"],
                                                     df["sd_percent"])
            # df["percent_change_norm_ppf"] = df["percent_change_norm_ppf"].fillna(method="ffill")
            # df["percent_change_norm_cdf"] = df["percent_change_norm_cdf"].fillna(method="ffill")

            df["current_max"] = df["high"].rolling(
                int(float(self.processed_params[symbol]["max_current_high_prd"]))).max()
            df["current_min"] = df["low"].rolling(
                int(float(self.processed_params[symbol]["min_current_low_prd"]))).min()
            df["spread"] = df["current_max"] - df["current_min"]

            df["past_period_max_high"] = df["high"].shift(
                int(float(self.processed_params[symbol]["max_past_high_lag"]))).rolling(
                int(float(self.processed_params[symbol]["max_past_high_prd"]))).max()
            df["past_period_min_low"] = df["low"].shift(
                int(float(self.processed_params[symbol]["min_past_low_lag"]))).rolling(
                int(float(self.processed_params[symbol]["min_past_low_prd"]))).min()

            df["long_entry_px"] = round(df["current_max"], 2)
            df["short_entry_px"] = round(df["current_min"], 2)
            print(f"{symbol} - current bar statistics:\n{dict(df.iloc[-1])}\n")
            print(df["percent_change_norm_ppf"].tolist())

            self.dfs[symbol] = df

    def check_entry_trigger(self):
        print("\n============== Checking for entries long/short...")
        for symbol in self.dfs.keys():
            df = self.dfs[symbol]
            current_bar = str(df.iloc[-1]["date"]) + "_" + str(self.processed_params[symbol]["timeframe"])
            if symbol in self.latest_bar_seen.keys() and current_bar == self.latest_bar_seen[symbol]:
                print(f"{symbol} - current bar already seen - {current_bar}\n")
                continue

            long_cond = (df.iloc[-1]["current_max"] == df.iloc[-1]["past_period_max_high"]) and \
                        (df.iloc[-1]["percent_change_norm_ppf"] >= float(
                            self.processed_params[symbol]["norm_threshold"])) and \
                        (df.iloc[-1]["open"] <= df.iloc[-1]["long_entry_px"])

            print("\n")
            print(f"{symbol} - Current max:{df.iloc[-1]['current_max']}, Past period max high:{df.iloc[-1]['past_period_max_high']}")
            print(f"{symbol} - Percent change norm ppf:{df.iloc[-1]['percent_change_norm_ppf']}, Norm threshold:{float(self.processed_params[symbol]['norm_threshold'])}")
            print(f"{symbol} - Current open:{df.iloc[-1]['open']}, Long entry px:{df.iloc[-1]['long_entry_px']}")
            print(f"{symbol} - Long condition: {long_cond}\n")
            if long_cond:
                self.enter_trades(symbol, "LONG", df.iloc[-1]["long_entry_px"])

            short_cond = (df.iloc[-1]["current_min"] == df.iloc[-1]["past_period_min_low"]) and \
                         (df.iloc[-1]["percent_change_norm_ppf"] >= float(
                             self.processed_params[symbol]["norm_threshold"])) and \
                         (df.iloc[-1]["open"] >= df.iloc[-1]["short_entry_px"])

            print(f"{symbol} - Current min:{df.iloc[-1]['current_min']}, Past period min low:{df.iloc[-1]['past_period_min_low']}")
            print(f"{symbol} - Percent change norm ppf:{df.iloc[-1]['percent_change_norm_ppf']}, Norm threshold:{float(self.processed_params[symbol]['norm_threshold'])}")
            print(f"{symbol} - Current open:{df.iloc[-1]['open']}, Short entry px:{df.iloc[-1]['short_entry_px']}")
            print(f"{symbol} - short condition: {short_cond}")
            if short_cond:
                self.enter_trades(symbol, "SHORT", df.iloc[-1]["short_entry_px"])

            self.latest_bar_seen[symbol] = str(df.iloc[-1]["date"]) + "_" + str(self.processed_params[symbol]["timeframe"])

    def enter_trades(self, symbol, direction, entry_price):
        num_trades_product = len([key for key in self.tickers.keys() if symbol in key and direction in key])
        if num_trades_product >= 10:
            print(f"We have already 10 {direction} positions for {symbol}.\nLets skip this entry!")
            return None

        print(f"Hey, there is a new entry: {symbol}-{direction}-{entry_price}\n")

        contracts = [Stock(symbol, "SMART", 'USD')]
        ib.qualifyContracts(*contracts)
        ib.reqExecutions()

        if direction == "LONG":
            side = "BUY"
            lmt_price = round(entry_price + float(self.processed_params[symbol]["tick"]) * float(
                self.processed_params[symbol]["stop_limit_ticks"]), 2)
        else:
            side = "SELL"
            lmt_price = round(entry_price - float(self.processed_params[symbol]["tick"]) * float(
                self.processed_params[symbol]["stop_limit_ticks"]), 2)
        size = float(self.processed_params[symbol]["size"])
        tp_price = round(
            entry_price + (float(self.processed_params[symbol]["target_sd"])) * (self.dfs[symbol].iloc[-1]["sd_px"]), 2)
        sl_price = round(
            entry_price - (float(self.processed_params[symbol]["stop_sd"])) * (self.dfs[symbol].iloc[-1]["sd_px"]), 2)

        ticker = Tick(lmt_price, size, symbol, direction, str(datetime.now()))
        key = symbol + "_" + direction + "_" + str(self.dfs[symbol].iloc[-1]["date"])
        self.tickers[key] = ticker

        bracket = ib.bracketOrder(side, size, lmt_price, tp_price, sl_price)
        self.tickers[key].bracket_entry["limit_entry"] = ib.placeOrder(contracts[0], bracket[0])
        self.tickers[key].bracket_entry["take_profit"] = ib.placeOrder(contracts[0], bracket[1])
        self.tickers[key].bracket_entry["stop_loss"] = ib.placeOrder(contracts[0], bracket[2])
        ib.sleep(4)

        if self.tickers[key].bracket_entry["limit_entry"].orderStatus.status == "Filled":
            self.tickers[key].entry_filled = True
            curr_bar_id = str(self.dfs[symbol].iloc[-1]["date"])
            if curr_bar_id not in self.tickers[key].max_hold_queue:
                self.tickers[key].max_hold_queue.append(curr_bar_id)

            max_stop_price = round(entry_price - (float(self.processed_params[symbol]["max_stop_sd"])) * (
                float(self.processed_params[symbol]["sd_px"])), 2)
            _side = "SELL" if side == "BUY" else "BUY"
            max_stop_order = StopOrder(_side, size, max_stop_price)
            self.tickers[key].max_stop_exit = ib.placeOrder(contracts[0], max_stop_order)

        print(self.tickers[key].bracket_entry)


th = Thread(target=main)
th.start()
engine = Engine(None)
engine.run_cycle()
