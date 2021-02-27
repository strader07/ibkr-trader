# import json
import pickle
import pandas as pd
import numpy as np
from scipy.stats import norm
from sortedcontainers import SortedDict
from datetime import datetime
from threading import Thread
# import math
# import logging

from ib_insync import *
from config import *
from gui import main
from tick import Tick

# import clib

ib = IB()
ib.connect("127.0.0.1", 7497, clientId=23)
global tickers
try:
    with open("trades/trades.pkl", "rb") as f:
        tickers = pickle.load(f)
except Exception as er:
    print(er)
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
        except Exception as err:
            print(err)
            values_processed.append({})

    prod_params = {}
    for key, value in zip(keys, values_processed):
        temp = params.copy()
        temp.update(value)
        prod_params[key] = temp
        prod_params[key]["LATEST_BAR_SEEN"] = ""

    return prod_params


def get_bar_duration_size(mins):
    bar_sizes = ["1 min", "2 mins", "3 mins", "5 mins", "10 mins", "15 mins", "20 mins", "30 mins", "1 hour",
                 "2 hours", "3 hours", "4 hours", "8 hours", "1 day", "1 week", "1 month"]

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


def custom_round(data, tick):
    round_factor = int(1 / tick)
    return np.floor(data * round_factor) / round_factor


def is_crossed(last, entry, current):
    if (max(last, entry) == entry and max(entry, current) == current) or \
            (min(last, entry) == entry and min(entry, current) == current):
        return True
    return False


def get_market_price(symbol):
    contracts = [Stock(symbol, "SMART", 'USD')]
    ib.qualifyContracts(*contracts)
    # ib.reqMarketDataType(4)
    ib.reqMktData(contracts[0], '', False, False)
    ib.sleep(2)

    tick = ib.ticker(contracts[0])
    price = float(tick.marketPrice())

    return price


class Engine:
    prod_params = {}

    def __init__(self):
        self.config = Config()
        self.tickers = SortedDict()
        self.dfs = {}
        self.processed_params = {}
        self.product_live_states = {}
        self.app_status = "OFF"
        try:
            with open("settings/app_status.txt", "w") as fp:
                fp.write(self.app_status)
                fp.close()
        except Exception as err:
            print(err)

    def run_cycle(self):
        while True:
            if self.app_status == "ON":
                ib.sleep(1)
                print("\n\n=================== Cycle begin! =====================\n")
                print(f"\nCurrent time: {datetime.now()}")
                print(f"\nCurrent trades: {self.tickers}")

                self.check_exit_trigger()
                self.trade_summary()
                self.update_params()
                self.data_analysis()
                self.check_entry_trigger()
                self.listen_for_entry()

                print("\n=================== Cycle end! =====================\n\n")

            try:
                with open("settings/app_status.txt", "r") as fp:
                    self.app_status = fp.readlines()[0]
            except Exception as err:
                print(err)
                self.app_status = "OFF"

    def update_params(self):
        self.config.update_prod_params()
        params = self.config.params
        prod_params = self.config.prod_params
        self.processed_params = get_prod_params(prod_params, params)
        # print(f"current products specific parameters: \n")
        # print(json.dumps(self.processed_params, indent=4))

    def trade_summary(self):
        print("\n============== Updating trade summary =============")
        trade_summaries = []
        for key in self.tickers:
            _ticker = self.tickers[key]
            trade_summary = {
                "Product": _ticker.symbol,
                "TradeID": key,
                "Side": _ticker.direction,
                "Size": _ticker.quantity,
                "EntryTime": _ticker.entry_time,
                "EntryPrice": _ticker.entry_price,
                "ExitTime": _ticker.exit_time,
                "ExitPrice": _ticker.exit_price,
                "ExitChannel": _ticker.exit_channel
            }
            if trade_summary["EntryTime"]:
                trade_summary["EntryTime"] = trade_summary["EntryTime"].split(" ")[1].split(".")[0]
            if trade_summary["ExitTime"]:
                trade_summary["ExitTime"] = trade_summary["EntryTime"].split(" ")[1].split(".")[0]
            if _ticker.entry_filled:
                if _ticker.exit_filled:
                    if _ticker.direction == "LONG":
                        trade_summary["RealizedPNL"] = _ticker.quantity * (_ticker.exit_price - _ticker.entry_price)
                    else:
                        trade_summary["RealizedPNL"] = _ticker.quantity * (_ticker.exit_price - _ticker.entry_price) * (-1)
                    trade_summary["UnrealizedPNL"] = ""
                else:
                    current_price = get_market_price(_ticker.symbol)
                    if _ticker.direction == "LONG":
                        trade_summary["UnrealizedPNL"] = _ticker.quantity * (current_price - _ticker.entry_price)
                    else:
                        trade_summary["UnrealizedPNL"] = _ticker.quantity * (current_price - _ticker.entry_price) * (-1)
                    trade_summary["RealizedPNL"] = ""
            else:
                trade_summary["RealizedPNL"] = ""
                trade_summary["UnrealizedPNL"] = ""

            trade_summaries.append(trade_summary)

        if len(trade_summaries) == 0:
            return None

        try:
            dfs = pd.read_csv(f"trade-summary-{datetime.now().date()}.csv")
        except Exception as err:
            print(err)
            dfs = pd.DataFrame(columns=["Product", "TradeID", "Side", "Size", "EntryTime", "EntryPrice", "ExitTime",
                                        "ExitPrice", "ExitChannel", "RealizedPNL", "UnrealizedPNL"])
        dfs = dfs.fillna("")
        df = pd.DataFrame(trade_summaries)
        df = df.fillna("")
        dfs = dfs.append(df)
        dfs = dfs.drop_duplicates(subset=["TradeID"], keep="last").reset_index(drop=True)
        print(dfs)
        dfs.to_csv(f"trades/trade-summary-{datetime.now().date()}.csv", index=False)

    def check_exit_trigger(self):
        print("\n============== Checking for trade exits =============")
        if not self.tickers:
            print("There are no trades yet!")
            return None

        del_keys = []
        ib.reqExecutions()
        for key in self.tickers:
            print(key)
            _ticker = self.tickers[key]
            entry_price = _ticker.limit_price
            symbol = _ticker.symbol
            direction = _ticker.direction

            if not _ticker.entry_filled and _ticker.bracket_entry["limit_entry"].orderStatus.status == "Filled":
                _ticker.entry_filled = True
                curr_bar_id = str(self.dfs[symbol].iloc[-1]["date"])
                if curr_bar_id not in self.tickers[key].max_hold_queue:
                    self.tickers[key].max_hold_queue.append(curr_bar_id)

                if not _ticker.max_stop_exit:
                    max_stop_price = round(entry_price - (float(self.processed_params[symbol]["max_stop_sd"])) * (
                        float(self.processed_params[symbol]["sd_px"])), 2)
                    side = "SELL" if direction == "LONG" else "BUY"
                    max_stop_order = StopOrder(side, _ticker.quantity, max_stop_price)
                    self.tickers[key].max_stop_exit = ib.placeOrder(_ticker.bracket_entry["limit_entry"].contract,
                                                                    max_stop_order)

            if _ticker.bracket_entry["limit_entry"].orderStatus.status != "Filled":
                print(f"{symbol} - entry not filled!")
                continue

            if _ticker.max_stop_exit:
                if _ticker.max_stop_exit.orderStatus.status == "Filled":
                    print(f"{symbol} - max stop order has been triggered.\nCancelling bracket order...")
                    _ticker.exit_filled = True
                    _ticker.exit_time = str(datetime.now())
                    _ticker.exit_price = _ticker.max_stop_exit.orderStatus.avgFillPrice
                    _ticker.exit_channel = "MSL"
                    _ticker.bracket_entry["take_profit"] = ib.cancelOrder(_ticker.bracket_entry["take_profit"].order)
                    continue

            if (_ticker.bracket_entry["take_profit"].orderStatus.status == "Filled") or \
                    (_ticker.bracket_entry["stop_loss"].orderStatus.status == "Filled"):
                print(f"{symbol} - exit triggered!")
                _ticker.exit_filled = True
                _ticker.exit_time = str(datetime.now())
                if _ticker.bracket_entry["take_profit"].orderStatus.status == "Filled":
                    _ticker.exit_price = _ticker.bracket_entry["take_profit"].orderStatus.avgFillPrice
                    _ticker.exit_channel = "TP"
                if _ticker.bracket_entry["stop_loss"].orderStatus.status == "Filled":
                    _ticker.exit_price = _ticker.bracket_entry["stop_loss"].orderStatus.avgFillPrice
                    _ticker.exit_channel = "SL"
                _ticker.max_stop_exit = ib.cancelOrder(_ticker.max_stop_exit.order)
                continue

            if _ticker.market_exit and _ticker.market_exit.orderStatus == "Filled":
                _ticker.exit_filled = True
                _ticker.exit_time = str(datetime.now())
                _ticker.exit_price = _ticker.market_exit.orderStatus.avgFillPrice
                _ticker.exit_channel = "MKT"

            if _ticker.exit_filled:
                continue

            if len(_ticker.max_hold_queue) >= float(self.processed_params[symbol]["max_prd_hold"]):
                print(f"{symbol} - passed max hold period without trade exit!\nLets close this position.")

                # closing the position at market
                if _ticker.bracket_entry["limit_entry"].orderStatus.status == "Filled":
                    side = "SELL" if _ticker.direction == "LONG" else "BUY"
                    _order = MarketOrder(side, _ticker.quantity)
                    _ticker.market_exit = ib.placeOrder(_ticker.bracket_entry["limit_entry"].contract, _order)
                    ib.sleep(4)
                    if _ticker.market_exit.orderStatus == "Filled":
                        _ticker.exit_filled = True
                        _ticker.exit_time = str(datetime.now())
                        _ticker.exit_price = _ticker.market_exit.orderStatus.avgFillPrice

                    _ticker.bracket_entry["take_profit"] = ib.cancelOrder(_ticker.bracket_entry["take_profit"].order)
                else:
                    print(f"{symbol} - {key}: entry limit order hasn't been triggered yet. Cancel the order.")
                    _ticker.bracket_entry["limit_entry"] = ib.cancelOrder(_ticker.bracket_entry["limit_entry"].order)
                    del_keys.append(key)

                _ticker.max_stop_exit = ib.cancelOrder(_ticker.max_stop_exit.order)
                continue

            current_bar_id = str(self.dfs["symbol"].iloc[-1]["date"])
            if current_bar_id in _ticker.max_hold_queue:
                continue
            _ticker.max_hold_queue.append(current_bar_id)

            # update take profit and stop loss order
            tick = float(self.processed_params[symbol]["tick"])
            if direction == "LONG":
                tp_price = custom_round(entry_price + (float(self.processed_params[symbol]["target_sd"])) * (
                    self.dfs[symbol].iloc[-1]["sd_px"]), tick)
                sl_price = custom_round(entry_price - (float(self.processed_params[symbol]["stop_sd"])) * (
                    self.dfs[symbol].iloc[-1]["sd_px"]), tick)
            else:
                tp_price = custom_round(entry_price + (float(self.processed_params[symbol]["target_sd"])) * (
                    self.dfs[symbol].iloc[-1]["sd_px"]), tick)
                sl_price = custom_round(entry_price - (float(self.processed_params[symbol]["stop_sd"])) * (
                    self.dfs[symbol].iloc[-1]["sd_px"]), tick)

            _contract = _ticker.bracket_entry["limit_entry"].contract
            tp_order = _ticker.bracket_entry["take_profit"].order
            sl_order = _ticker.bracket_entry["stop_loss"].order
            tp_order.lmtPrice = tp_price
            tp_order.transmit = True
            sl_order.auxPrice = sl_price

            _ticker.bracket_entry["take_profit"] = ib.placeOrder(_contract, tp_order)
            _ticker.bracket_entry["stop_loss"] = ib.placeOrder(_contract, sl_order)
            ib.sleep(2)

        for key in del_keys:
            del self.tickers[key]

    def data_analysis(self):
        print("\n============== Data analysis =============")
        symbols = list(self.processed_params.keys())
        # symbols_in_trade = [key.split("_")[0].strip(",. ") for key in self.tickers.keys()]
        # symbols = [symbol for symbol in symbols if symbol not in symbols_in_trade]

        contracts = []
        for symbol in symbols:
            contracts.append(Stock(symbol, "SMART", 'USD'))
        ib.qualifyContracts(*contracts)
        ib.reqMarketDataType(4)

        for _contract, symbol in zip(contracts, symbols):
            # print(contract)
            bar_size, duration = get_bar_duration_size(self.processed_params[symbol]["timeframe"])
            tick = float(self.processed_params[symbol]["tick"])
            print(f"{symbol} - Bar size and duration: {bar_size}, {duration}")
            try:
                bars = ib.reqHistoricalData(
                    _contract,
                    endDateTime='',
                    durationStr=duration,
                    barSizeSetting=bar_size,
                    whatToShow='TRADES',
                    useRTH=False,
                    formatDate=1,
                    keepUpToDate=False)
            except Exception as err:
                print("historical data rek error: ", err)
                continue

            try:
                df = util.df(bars)[['date', 'open', 'high', 'low', 'close']].tail(100).reset_index(drop=True)
            except Exception as err:
                print("dataframe convert error: ", err)
                continue

            df["percent_change"] = df.close.pct_change(int(float(self.processed_params[symbol]["percent_change_lag"])))
            # df["sd_percent"] = clib.std(df, "percent_change", int(float(processed_params[symbol]["sd_lag"])))
            df["sd_percent"] = df["percent_change"].rolling(int(float(self.processed_params[symbol]["sd_lag"]))).std()
            # df["sd_px"] = clib.std(df, "close", int(float(processed_params[symbol]["sd_lag"])))
            df["sd_px"] = df["close"].rolling(int(float(self.processed_params[symbol]["sd_lag"]))).std()
            df["percent_change_mean"] = df["percent_change"].rolling(
                int(float(self.processed_params[symbol]["sd_lag"]))).mean()
            df["percent_change_norm_ppf"] = norm.ppf(float(self.processed_params[symbol]["norm_threshold"]),
                                                     df["percent_change_mean"], df["sd_percent"])
            df["percent_change_norm_cdf"] = norm.cdf(df["percent_change"],
                                                     df["percent_change_mean"], df["sd_percent"])
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

            df["long_entry_px"] = custom_round(df["current_max"], tick)
            df["short_entry_px"] = custom_round(df["current_min"], tick)
            print(f"{symbol} - current bar statistics:\n{dict(df.iloc[-1])}\n")

            self.dfs[symbol] = df

    def check_entry_trigger(self):
        print("\n============== Checking for entries long/short condition =============")
        for symbol in self.dfs.keys():
            df = self.dfs[symbol]
            current_bar = str(df.iloc[-1]["date"]) + "_" + str(self.processed_params[symbol]["timeframe"])
            if symbol in self.product_live_states.keys() and current_bar == self.product_live_states[symbol][
                    "last_bar"]:
                print(f"{symbol} - current bar already seen - {current_bar}\n")
                continue

            product_state = dict()
            product_state["last_bar"] = str(df.iloc[-1]["date"]) + "_" + str(self.processed_params[symbol]["timeframe"])
            product_state["long_cond"] = False
            product_state["short_cond"] = False
            product_state["last_price"] = None

            long_cond = (df.iloc[-1]["current_max"] == df.iloc[-1]["past_period_max_high"]) and \
                        (df.iloc[-1]["percent_change_norm_cdf"] >= float(
                            self.processed_params[symbol]["norm_threshold"])) and \
                        (df.iloc[-1]["open"] <= df.iloc[-1]["long_entry_px"])

            print("\n")
            print(
                f"{symbol} - Current max:{df.iloc[-1]['current_max']}, "
                f"Past period max high:{df.iloc[-1]['past_period_max_high']}")
            print(
                f"{symbol} - Percent change norm cdf:{df.iloc[-1]['percent_change_norm_cdf']}, "
                f"Norm threshold:{float(self.processed_params[symbol]['norm_threshold'])}")
            print(f"{symbol} - Current open:{df.iloc[-1]['open']}, Long entry px:{df.iloc[-1]['long_entry_px']}")
            print(f"{symbol} - Long condition: {long_cond}\n")
            if long_cond:
                product_state["long_cond"] = True
                # self.enter_trades(symbol, "LONG", df.iloc[-1]['long_entry_px'])

            short_cond = (df.iloc[-1]["current_min"] == df.iloc[-1]["past_period_min_low"]) and \
                         (df.iloc[-1]["percent_change_norm_cdf"] >= float(
                             self.processed_params[symbol]["norm_threshold"])) and \
                         (df.iloc[-1]["open"] >= df.iloc[-1]["short_entry_px"])

            print(
                f"{symbol} - Current min:{df.iloc[-1]['current_min']}, "
                f"Past period min low:{df.iloc[-1]['past_period_min_low']}")
            print(
                f"{symbol} - Percent change norm cdf:{df.iloc[-1]['percent_change_norm_cdf']}, "
                f"Norm threshold:{float(self.processed_params[symbol]['norm_threshold'])}")
            print(f"{symbol} - Current open:{df.iloc[-1]['open']}, Short entry px:{df.iloc[-1]['short_entry_px']}")
            print(f"{symbol} - short condition: {short_cond}")
            if short_cond:
                product_state["short_cond"] = True
                # self.enter_trades(symbol, "SHORT", df.iloc[-1]["short_entry_px"])

            if long_cond or short_cond:
                product_state["last_price"] = get_market_price(symbol)
            self.product_live_states[symbol] = product_state

    def listen_for_entry(self):
        print("\n============== Listening for entry =============")
        for symbol in self.dfs.keys():
            df = self.dfs[symbol]
            long_key = symbol + "_" + "LONG" + "_" + str(self.dfs[symbol].iloc[-1]["date"])
            short_key = symbol + "_" + "SHORT" + "_" + str(self.dfs[symbol].iloc[-1]["date"])
            if long_key in self.tickers:
                print(f"{symbol} - currently in a long position as - {long_key}!")
            else:
                if not self.product_live_states[symbol]["long_cond"]:
                    print(f"{symbol} - long condition false")
                else:
                    print(f"{symbol} - long condition true. Listening for a long entry.")
                    last_price = self.product_live_states[symbol]["last_price"]
                    current_price = get_market_price(symbol)
                    entry_price = df.iloc[-1]["long_entry_px"]
                    print(f"Last_price: {last_price}, current_price: {current_price}, long_entry_price: {entry_price}")
                    if is_crossed(last_price, entry_price, current_price):
                        print(f"{symbol} - entry price crossed. Entering a long position.")
                        self.enter_trades(symbol, "LONG", entry_price)
                    # else:
                    #     self.product_live_states[symbol]["last_price"] = current_price

            if short_key in self.tickers:
                print(f"{symbol} - currently in a short position as - {short_key}!")
            else:
                if not self.product_live_states[symbol]["short_cond"]:
                    print(f"{symbol} - short condition false")
                else:
                    print(f"{symbol} - short condition true. Listening for a short entry.")
                    last_price = self.product_live_states[symbol]["last_price"]
                    current_price = get_market_price(symbol)
                    entry_price = df.iloc[-1]["short_entry_px"]
                    print(f"Last_price: {last_price}, current_price: {current_price}, short_entry_price: {entry_price}")
                    if is_crossed(last_price, entry_price, current_price):
                        print(f"{symbol} - entry price crossed. Entering a short position.")
                        self.enter_trades(symbol, "SHORT", entry_price)
                    # else:
                    #     self.product_live_states[symbol]["last_price"] = current_price

    def enter_trades(self, symbol, direction, entry_price):
        num_trades_product = len([key for key in self.tickers.keys() if symbol in key and direction in key])
        if num_trades_product >= 10:
            print(f"We have already 10 {direction} positions for {symbol}.\nLets skip this entry!")
            return None

        print(f"Hey, there is a new entry: {symbol}-{direction}-{entry_price}")

        contracts = [Stock(symbol, "SMART", 'USD')]
        ib.qualifyContracts(*contracts)
        ib.reqExecutions()
        tick = float(self.processed_params[symbol]["tick"])

        if direction == "LONG":
            side = "BUY"
            lmt_price = custom_round(entry_price + float(self.processed_params[symbol]["tick"]) * float(
                self.processed_params[symbol]["stop_limit_ticks"]), tick)
            tp_price = custom_round(entry_price + (float(self.processed_params[symbol]["target_sd"])) * (
                self.dfs[symbol].iloc[-1]["sd_px"]), tick)
            sl_price = custom_round(
                entry_price - (float(self.processed_params[symbol]["stop_sd"])) * (self.dfs[symbol].iloc[-1]["sd_px"]),
                tick)
        else:
            side = "SELL"
            lmt_price = custom_round(entry_price - float(self.processed_params[symbol]["tick"]) * float(
                self.processed_params[symbol]["stop_limit_ticks"]), tick)
            tp_price = custom_round(entry_price - (float(self.processed_params[symbol]["target_sd"])) * (
                self.dfs[symbol].iloc[-1]["sd_px"]), tick)
            sl_price = custom_round(
                entry_price + (float(self.processed_params[symbol]["stop_sd"])) * (self.dfs[symbol].iloc[-1]["sd_px"]),
                tick)

        size = float(self.processed_params[symbol]["size"])
        _ticker = Tick(lmt_price, size, symbol, direction, str(datetime.now()))
        key = symbol + "_" + direction + "_" + str(self.dfs[symbol].iloc[-1]["date"])
        self.tickers[key] = _ticker

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

            max_stop_price = custom_round(entry_price - (float(self.processed_params[symbol]["max_stop_sd"])) * (
                float(self.processed_params[symbol]["sd_px"])), tick)
            _side = "SELL" if side == "BUY" else "BUY"
            max_stop_order = StopOrder(_side, size, max_stop_price)
            self.tickers[key].max_stop_exit = ib.placeOrder(contracts[0], max_stop_order)

        print(self.tickers[key].bracket_entry, "\n")


th = Thread(target=main)
th.start()
engine = Engine()
engine.run_cycle()
