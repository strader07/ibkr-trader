import pandas as pd
import numpy as np
from scipy.stats import norm
from sortedcontainers import SortedDict
from datetime import datetime
from threading import Thread
import re
import logging
import verboselogs

from ib_insync import *
from config import *
from gui import main
from tick import Tick

logger = verboselogs.VerboseLogger('verbose')
logger.addHandler(logging.StreamHandler())
if LOG_LEVEL == "VERBOSE":
    logger.setLevel(logging.VERBOSE)
else:
    logger.setLevel(logging.DEBUG)
if LOG_LEVEL == "VERBOSE":
    logger.verbose("\n\n====================== START! ========================\n")
logger.debug("\n\n====================== START! ========================\n")

ib = IB()
host = "127.0.0.1"
port = 7497
clientId = 23
ib.connect(host, port, clientId=clientId)


def get_prod_params(prod_params, params):
    products = [product.strip(",. ") for product in params["products"].split(",")]
    prod_params_update = {}
    for product in products:
        if product in prod_params:
            val = prod_params[product]
            try:
                pairs = [item.strip(",. ") for item in val.split(",")]
                val_processed = {item.split("=")[0].strip(",. "): eval(item.split("=")[1].strip("(),. ")) for item in
                                 pairs}
            except Exception as err:
                logger.debug(err)
                val_processed = {}
            temp = params.copy()
            temp.update(val_processed)
            prod_params_update[product] = temp
        else:
            prod_params_update[product] = params

    return prod_params_update


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


# def is_crossed(last, entry, current):
#     if (max(last, entry) == entry and max(entry, current) == current) or \
#             (min(last, entry) == entry and min(entry, current) == current):
#         return True
#     return False


def is_crossed(last, entry, current):
    if str(last) == "NaN":
        print(last)
    if current > entry or current < entry:
        return True
    return False


def get_contract(symbol):
    m = re.findall(r"\d+\s*$", symbol)
    if m:
        _type = "future"
        _month = str(int(m[0]) + 2020) + MONTH_DICT[symbol.replace(m[0], "")[-1]]
        _symbol = symbol.replace(m[0], "")[:-1]
    else:
        _type = "stock"
        _month = ""
        _symbol = symbol
    if _type == "future":
        exchange = [key for key in EXCHANGES if _symbol in EXCHANGES[key]][0]
        _contract = Future(_symbol, _month, exchange)
    else:
        _contract = Stock(_symbol, "SMART", 'USD')

    return _contract


def get_market_price(symbol):
    contracts = [get_contract(symbol)]
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
        self.connection_status = True
        self.host = host
        self.port = port
        self.clientId = clientId
        try:
            with open("settings/app_status.txt", "w") as fp:
                fp.write(self.app_status)
                fp.close()
        except Exception as err:
            logger.debug(err)

    def run_cycle(self):
        while True:
            if self.app_status != "$$$":
                logger.debug("\n\n=================== Cycle begin! =====================\n")
                logger.debug(f"\nCurrent time: {datetime.now()}")
                if LOG_LEVEL != "VERBOSE":
                    print(f"\nCurrent trades: {self.tickers}")

                self.handle_connection_issue()
                self.check_exit_trigger()
                self.trade_summary()
                self.update_params()
                self.data_analysis()
                self.check_entry_trigger()
                self.listen_for_entry()

                logger.debug("\n=================== Cycle end! =====================\n\n")

            try:
                with open("settings/app_status.txt", "r") as fp:
                    self.app_status = fp.readlines()[0]
            except Exception as err:
                logger.debug(err)
                self.app_status = "OFF"

    def handle_connection_issue(self):
        if self.connection_status:
            return None

        print("\nwaiting for ib to reconnect...\n")
        ib.disconnect()
        ib.waitOnUpdate(timeout=0.1)
        ib.sleep(5)
        while True:
            try:
                ib.connect(host, port, clientId=self.clientId)
                print("connection re-established")
                break
            except Exception as e:
                logger.error(e)
                ib.disconnect()
                ib.waitOnUpdate(timeout=0.1)
                ib.sleep(5)

        del_keys = []
        ib.reqExecutions()
        for key in self.tickers:
            _ticker = self.tickers[key]
            if not _ticker.bracket_entry["limit_entry"]:
                del_keys.append(key)
                continue
            if _ticker.bracket_entry["limit_entry"] and \
                    _ticker.bracket_entry["limit_entry"].orderStatus.status != "Filled":
                try:
                    ib.cancelOrder(self.tickers[key].bracket_entry["limit_entry"].order)
                except Exception as e:
                    print(e)
                    self.update_connection_status()
                    return None
                del_keys.append(key)
                continue

        for key in del_keys:
            del self.tickers[key]

        self.connection_status = True
        return None

    def update_params(self):
        self.config.update_prod_params()
        params = self.config.params
        prod_params = self.config.prod_params
        self.processed_params = get_prod_params(prod_params, params)
        # print(f"current products specific parameters: \n")
        # print(json.dumps(self.processed_params, indent=4))

    def trade_summary(self):
        logger.debug("\n============== Updating trade summary =============")
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
                trade_summary["ExitTime"] = trade_summary["ExitTime"].split(" ")[1].split(".")[0]
            if _ticker.entry_filled:
                if _ticker.exit_filled:
                    if _ticker.direction == "LONG":
                        if _ticker.exit_price:
                            trade_summary["RealizedPNL"] = _ticker.quantity * (_ticker.exit_price - _ticker.entry_price)
                    else:
                        if _ticker.exit_price:
                            trade_summary["RealizedPNL"] = _ticker.quantity * \
                                                           (_ticker.exit_price - _ticker.entry_price) * (-1)
                    trade_summary["UnrealizedPNL"] = ""
                else:
                    try:
                        current_price = get_market_price(_ticker.symbol)
                    except Exception as e:
                        logger.debug(e)
                        continue
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
            logger.debug(err)
            dfs = pd.DataFrame(columns=["Product", "TradeID", "Side", "Size", "EntryTime", "EntryPrice", "ExitTime",
                                        "ExitPrice", "ExitChannel", "RealizedPNL", "UnrealizedPNL"])
        dfs = dfs.fillna("")
        df = pd.DataFrame(trade_summaries)
        df = df.fillna("")
        dfs = dfs.append(df)
        dfs = dfs.drop_duplicates(subset=["TradeID"], keep="last").reset_index(drop=True)
        # print(dfs)
        dfs.to_csv(f"trades/trade-summary-{datetime.now().date()}.csv", index=False)

    def check_exit_trigger(self):
        logger.debug("\n============== Checking for trade exits =============")
        if not self.tickers:
            logger.debug("There are no trades yet!")
            return None

        del_keys = []
        timed_exits = {}
        try:
            ib.reqExecutions()
        except Exception as e:
            print(f"ib connection issue - {e}")
            self.update_connection_status()
            return None
        for key in self.tickers:
            logger.debug(key)
            _ticker = self.tickers[key]
            if _ticker.exit_filled:
                continue
            entry_price = _ticker.limit_price
            symbol = _ticker.symbol
            direction = _ticker.direction

            if _ticker.bracket_entry["limit_entry"].orderStatus.status != "Filled":
                current_bar_id = str(self.dfs[symbol].iloc[-1]["date"])
                if current_bar_id not in _ticker.max_hold_queue and len(_ticker.max_hold_queue) > 0:
                    if LOG_LEVEL == "VERBOSE":
                        logger.verbose(f"\n[{datetime.now()}]: {key} "
                                       f"- entry not filled within the first bar. Cancel orders!")
                    logger.debug(f"{key} - entry not filled within the first bar. Cancel orders!")
                    try:
                        ib.cancelOrder(_ticker.bracket_entry["limit_entry"].order)
                    except Exception as e:
                        print(f"ib connection issue - {e}")
                        self.update_connection_status()
                        return None
                    del_keys.append(key)
                    continue
                if current_bar_id not in _ticker.max_hold_queue and len(_ticker.max_hold_queue) == 0:
                    _ticker.max_hold_queue.append(current_bar_id)
                continue

            if not _ticker.entry_filled and _ticker.bracket_entry["limit_entry"].orderStatus.status == "Filled":
                _ticker.entry_filled = True
                _ticker.entry_price = self.tickers[key].bracket_entry["limit_entry"].orderStatus.avgFillPrice
                curr_bar_id = str(self.dfs[symbol].iloc[-1]["date"])
                if curr_bar_id not in self.tickers[key].max_hold_queue:
                    self.tickers[key].max_hold_queue.append(curr_bar_id)

            if (_ticker.bracket_entry["take_profit"].orderStatus.status == "Filled") or \
                    (_ticker.bracket_entry["stop_loss"].orderStatus.status == "Filled"):
                _ticker.exit_filled = True
                _ticker.exit_time = str(datetime.now())
                if _ticker.bracket_entry["take_profit"].orderStatus.status == "Filled":
                    _ticker.exit_price = _ticker.bracket_entry["take_profit"].orderStatus.avgFillPrice
                    _ticker.exit_channel = "TP"
                if _ticker.bracket_entry["stop_loss"].orderStatus.status == "Filled":
                    _ticker.exit_price = _ticker.bracket_entry["stop_loss"].orderStatus.avgFillPrice
                    _ticker.exit_channel = "SL"
                if LOG_LEVEL == "VERBOSE":
                    logger.verbose(f"\n[{datetime.now()}]: {symbol} - exit triggered by {_ticker.exit_channel}!")
                logger.debug(f"{symbol} - exit triggered by {_ticker.exit_channel}!")
                continue

            if not _ticker.exit_filled and _ticker.market_exit and _ticker.market_exit.orderStatus.status == "Filled":
                if LOG_LEVEL == "VERBOSE":
                    logger.verbose(f"\n[{datetime.now()}]: {key} - Position closed at market!")
                logger.debug("Position closed at market!")
                _ticker.exit_filled = True
                _ticker.exit_time = str(datetime.now())
                _ticker.exit_price = _ticker.market_exit.orderStatus.avgFillPrice
                _ticker.exit_channel = "MKT"

            if _ticker.exit_filled:
                continue

            if not _ticker.market_exit and len(_ticker.max_hold_queue) >= \
                    float(self.processed_params[symbol]["max_prd_hold"]):
                if LOG_LEVEL == "VERBOSE":
                    logger.verbose(f"\n[{datetime.now()}]: {key} - "
                                   f"passed max hold period without trade exit!\nLets close this position.")
                logger.debug(f"{key} - passed max hold period without trade exit!\nLets close this position.")

                exit_symbol = key.split("_")[0]
                exit_direction = key.split("_")[1]
                if exit_symbol not in timed_exits.keys():
                    timed_exits[exit_symbol] = [{
                        "key": key,
                        "direction": exit_direction
                    }]
                else:
                    timed_exits[exit_symbol].append({
                        "key": key,
                        "direction": exit_direction
                    })
                continue

            current_bar_id = str(self.dfs[symbol].iloc[-1]["date"])
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
                tp_price = custom_round(entry_price - (float(self.processed_params[symbol]["target_sd"])) * (
                    self.dfs[symbol].iloc[-1]["sd_px"]), tick)
                sl_price = custom_round(entry_price + (float(self.processed_params[symbol]["stop_sd"])) * (
                    self.dfs[symbol].iloc[-1]["sd_px"]), tick)

            if LOG_LEVEL == "VERBOSE":
                logger.verbose(f"\n[{datetime.now()}]: {key} - updating tp and sl orders")
            logger.debug("updating tp and sl orders")
            logger.debug(f'tp order original status: {_ticker.bracket_entry["take_profit"].orderStatus.status}')
            logger.debug(f'sl order original status: {_ticker.bracket_entry["stop_loss"].orderStatus.status}')
            _contract = _ticker.bracket_entry["limit_entry"].contract
            tp_order = _ticker.bracket_entry["take_profit"].order
            sl_order = _ticker.bracket_entry["stop_loss"].order
            tp_order.lmtPrice = tp_price
            tp_order.transmit = True
            sl_order.auxPrice = sl_price

            try:
                _ticker.bracket_entry["take_profit"] = ib.placeOrder(_contract, tp_order)
                _ticker.bracket_entry["stop_loss"] = ib.placeOrder(_contract, sl_order)
            except Exception as e:
                print(f"ib connection issue - {e}")
                self.update_connection_status()
                return None

            ib.sleep(2)
            if LOG_LEVEL == "VERBOSE":
                logger.verbose(f"\n[{datetime.now()}]: {key} - Take profit and stop loss updated!")
            logger.debug("Take profit and stop loss updated!")

        for key in del_keys:
            del self.tickers[key]

        for exit_symbol in timed_exits.keys():
            if len(timed_exits[exit_symbol]) > 2:
                print(timed_exits[exit_symbol])
                print("ERROR!!!")
                exit()
            if len(timed_exits[exit_symbol]) == 2:
                if timed_exits[exit_symbol][0]["direction"] == timed_exits[exit_symbol][1]["direction"]:
                    print(timed_exits[exit_symbol])
                    print("ERROR!!!")
                    exit()
                else:
                    if LOG_LEVEL == "VERBOSE":
                        logger.verbose(f"\n[{datetime.now()}]: {exit_symbol} - trying to timed exit, but its net flat!")
                    logger.debug(f"\n[{datetime.now()}]: {exit_symbol} - trying to timed exit, but its net flat!")
                    print(timed_exits[exit_symbol])
                    continue
            if len(timed_exits[exit_symbol]) == 1:
                # timed exit
                key = timed_exits[exit_symbol][0]["key"]
                symbol = exit_symbol
                _ticker = self.tickers[key]
                if _ticker.bracket_entry["limit_entry"].orderStatus.status == "Filled":
                    if self.is_net_flat(symbol):
                        if LOG_LEVEL == "VERBOSE":
                            logger.verbose(f"\n[{datetime.now()}]: {symbol} - is currently in a net flat! Skip closing")
                        logger.debug(f"{symbol} - is currently in a net flat! Skip closing")
                        continue
                    side = "SELL" if _ticker.direction == "LONG" else "BUY"
                    try:
                        _order = MarketOrder(side, _ticker.quantity)
                        _ticker.market_exit = ib.placeOrder(_ticker.bracket_entry["limit_entry"].contract, _order)
                    except Exception as e:
                        print(f"ib connection issue - {e}")
                        self.update_connection_status()
                        return None
                    ib.sleep(4)
                    if _ticker.market_exit.orderStatus.status == "Filled":
                        _ticker.exit_filled = True
                        _ticker.exit_channel = "MKT"
                        _ticker.exit_time = str(datetime.now())
                        _ticker.exit_price = _ticker.market_exit.orderStatus.avgFillPrice

                    _ticker.bracket_entry["take_profit"] = ib.cancelOrder(_ticker.bracket_entry["take_profit"].order)

    def is_net_flat(self, symbol):
        keys = [key for key in self.tickers if self.tickers[key].entry_filled]
        keys = [key for key in keys if symbol in key]

        longs = [key for key in keys if "LONG" in key]
        shorts = [key for key in keys if "SHORT" in key]

        if len(longs) == len(shorts):
            return True
        else:
            return False

    def data_analysis(self):
        logger.debug("\n============== Data analysis =============")
        # print(self.processed_params)
        symbols = list(self.processed_params.keys())

        contracts = []
        for symbol in symbols:
            _contract = get_contract(symbol)
            contracts.append(_contract)
            # print(contract)

        try:
            ib.qualifyContracts(*contracts)
        except Exception as e:
            print(f"ib connection issue - {e}")
            self.update_connection_status()
            return None

        for _contract, symbol in zip(contracts, symbols):
            bar_size, duration = get_bar_duration_size(self.processed_params[symbol]["timeframe"])
            tick = float(self.processed_params[symbol]["tick"])
            logger.debug(f"{symbol} - Bar size and duration: {bar_size}, {duration}")
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
                logger.debug("historical data rek error: ", err)
                continue

            try:
                df = util.df(bars)[['date', 'open', 'high', 'low', 'close']].tail(100).reset_index(drop=True)
            except Exception as err:
                logger.debug("dataframe convert error: ", err)
                continue

            df = df.dropna().reset_index(drop=True)

            df["percent_change"] = df.close.pct_change(int(float(self.processed_params[symbol]["percent_change_lag"])))
            df["sd_percent"] = df["percent_change"].rolling(int(float(self.processed_params[symbol]["sd_lag"]))).std()
            df["sd_px"] = df["close"].rolling(int(float(self.processed_params[symbol]["sd_lag"]))).std()
            df["percent_change_mean"] = df["percent_change"].rolling(
                int(float(self.processed_params[symbol]["sd_lag"]))).mean()
            df["percent_change_norm_ppf"] = norm.ppf(float(self.processed_params[symbol]["norm_threshold"]),
                                                     df["percent_change_mean"], df["sd_percent"])
            df["percent_change_norm_cdf"] = norm.cdf(df["percent_change"],
                                                     df["percent_change_mean"], df["sd_percent"])

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
            logger.debug(f"{symbol} - current bar statistics:\n{dict(df.iloc[-1])}\n")

            self.dfs[symbol] = df

    def check_entry_trigger(self):
        logger.debug("\n============== Checking for entries long/short condition =============")
        for symbol in self.dfs.keys():
            df = self.dfs[symbol]
            current_bar = str(df.iloc[-1]["date"]) + "_" + str(self.processed_params[symbol]["timeframe"])
            if symbol in self.product_live_states.keys() and \
                    current_bar == self.product_live_states[symbol]["last_bar"]:
                logger.debug(f"{symbol} - current bar already seen - {current_bar}\n")
                continue
            curr_bar_id = str(self.dfs[symbol].iloc[-1]["date"])
            key_long = symbol + "_" + "LONG" + "_" + str(self.dfs[symbol].iloc[-1]["date"])
            key_short = symbol + "_" + "SHORT" + "_" + str(self.dfs[symbol].iloc[-1]["date"])
            if key_long in self.tickers:
                if curr_bar_id in self.tickers[key_long].max_hold_queue:
                    continue
            if key_short in self.tickers:
                if curr_bar_id in self.tickers[key_short].max_hold_queue:
                    continue

            product_state = {
                "last_bar": str(df.iloc[-1]["date"]) + "_" + str(self.processed_params[symbol]["timeframe"]),
                "long_cond": False, "short_cond": False, "last_price": None}

            long_cond = (df.iloc[-1]["open"] <= df.iloc[-1][
                "long_entry_px"])  # and (df.iloc[-1]["current_max"] == df.iloc[-1]["past_period_max_high"]) and \
            # (df.iloc[-1]["percent_change_norm_cdf"] >= float(
            #     self.processed_params[symbol]["norm_threshold"])) and \

            logger.debug("\n")
            logger.debug(
                f"{symbol} - Current max:{df.iloc[-1]['current_max']}, "
                f"Past period max high:{df.iloc[-1]['past_period_max_high']}")
            logger.debug(
                f"{symbol} - Percent change norm cdf:{df.iloc[-1]['percent_change_norm_cdf']}, "
                f"Norm threshold:{float(self.processed_params[symbol]['norm_threshold'])}")
            logger.debug(f"{symbol} - Current open:{df.iloc[-1]['open']}, Long entry px:{df.iloc[-1]['long_entry_px']}")
            logger.debug(f"{symbol} - Long condition: {long_cond}\n")
            if long_cond:
                product_state["long_cond"] = True

            short_cond = (df.iloc[-1]["open"] >= df.iloc[-1][
                "short_entry_px"])  # and (df.iloc[-1]["current_min"] == df.iloc[-1]["past_period_min_low"])  # and \
            # (df.iloc[-1]["percent_change_norm_cdf"] >= float(
            #     self.processed_params[symbol]["norm_threshold"])) and \

            logger.debug(
                f"{symbol} - Current min:{df.iloc[-1]['current_min']}, "
                f"Past period min low:{df.iloc[-1]['past_period_min_low']}")
            logger.debug(
                f"{symbol} - Percent change norm cdf:{df.iloc[-1]['percent_change_norm_cdf']}, "
                f"Norm threshold:{float(self.processed_params[symbol]['norm_threshold'])}")
            logger.debug(
                f"{symbol} - Current open:{df.iloc[-1]['open']}, Short entry px:{df.iloc[-1]['short_entry_px']}")
            logger.debug(f"{symbol} - short condition: {short_cond}")
            if short_cond:
                product_state["short_cond"] = True

            if long_cond or short_cond:
                try:
                    product_state["last_price"] = get_market_price(symbol)
                    self.product_live_states[symbol] = product_state
                except Exception as e:
                    print(f"{symbol} - connection issue (check_entry_trigger) - {e}")
                    self.product_live_states[symbol] = product_state
                    self.update_connection_status()
                    continue

    def listen_for_entry(self):
        logger.debug("\n============== Listening for entry =============")
        for symbol in self.dfs.keys():
            df = self.dfs[symbol]
            long_key = symbol + "_" + "LONG" + "_" + str(self.dfs[symbol].iloc[-1]["date"])
            short_key = symbol + "_" + "SHORT" + "_" + str(self.dfs[symbol].iloc[-1]["date"])
            if long_key in self.tickers:
                logger.debug(f"{symbol} - currently in a long position as - {long_key}!")
            else:
                if not self.product_live_states[symbol]["long_cond"]:
                    logger.debug(f"{symbol} - long condition false")
                else:
                    logger.debug(f"{symbol} - long condition true. Listening for a long entry.")
                    last_price = self.product_live_states[symbol]["last_price"]
                    try:
                        current_price = get_market_price(symbol)
                    except Exception as e:
                        print(f"{symbol} - connection issue (listen_for_entry) - {e}")
                        self.update_connection_status()
                        return None
                    entry_price = df.iloc[-1]["long_entry_px"]
                    logger.debug(f"Last_price: {last_price}, current_price: {current_price}, "
                                 f"long_entry_price: {entry_price}")
                    if is_crossed(last_price, entry_price, current_price):
                        logger.debug(f"{symbol} - entry price crossed. Entering a long position.")
                        try:
                            self.enter_trades(symbol, "LONG", entry_price, current_price)
                        except Exception as e:
                            print(f"{symbol} - connection issue (listen_for_entry) - {e}")
                            self.update_connection_status()
                            return None

            if short_key in self.tickers:
                logger.debug(f"{symbol} - currently in a short position as - {short_key}!")
            else:
                if not self.product_live_states[symbol]["short_cond"]:
                    logger.debug(f"{symbol} - short condition false")
                else:
                    logger.debug(f"{symbol} - short condition true. Listening for a short entry.")
                    last_price = self.product_live_states[symbol]["last_price"]
                    try:
                        current_price = get_market_price(symbol)
                    except Exception as e:
                        print(f"{symbol} - connection issue (listen_for_entry) - {e}")
                        self.update_connection_status()
                        return None
                    entry_price = df.iloc[-1]["short_entry_px"]
                    logger.debug(f"Last_price: {last_price}, current_price: {current_price}, "
                                 f"short_entry_price: {entry_price}")
                    if is_crossed(last_price, entry_price, current_price):
                        logger.debug(f"{symbol} - entry price crossed. Entering a short position.")
                        try:
                            self.enter_trades(symbol, "SHORT", entry_price, current_price)
                        except Exception as e:
                            print(f"{symbol} - connection issue (listen_for_entry) - {e}")
                            self.update_connection_status()
                            return None

    def enter_trades(self, symbol, direction, entry_price, current_price):
        num_trades_product = len([key for key in self.tickers.keys() if symbol in key and direction in key and
                                  not self.tickers[key].exit_filled])
        if num_trades_product >= 10:
            if LOG_LEVEL == "VERBOSE":
                logger.verbose(f"\n[{datetime.now()}]: We have already 10 {direction} positions for {symbol}.\n"
                               f"Lets skip this entry!")
            logger.debug(f"We have already 10 {direction} positions for {symbol}.\nLets skip this entry!")
            return None

        contracts = [get_contract(symbol)]
        ib.qualifyContracts(*contracts)
        ib.reqExecutions()

        tick = float(self.processed_params[symbol]["tick"])

        if direction == "LONG":
            side = "BUY"
            lmt_price = custom_round(entry_price - float(self.processed_params[symbol]["tick"]) * float(
                self.processed_params[symbol]["stop_limit_ticks"]), tick)
            tp_price = custom_round(entry_price + (float(self.processed_params[symbol]["target_sd"])) * (
                self.dfs[symbol].iloc[-1]["sd_px"]), tick)
            sl_price = custom_round(
                entry_price - (float(self.processed_params[symbol]["stop_sd"])) * (self.dfs[symbol].iloc[-1]["sd_px"]),
                tick)
        else:
            side = "SELL"
            lmt_price = custom_round(entry_price + float(self.processed_params[symbol]["tick"]) * float(
                self.processed_params[symbol]["stop_limit_ticks"]), tick)
            tp_price = custom_round(entry_price - (float(self.processed_params[symbol]["target_sd"])) * (
                self.dfs[symbol].iloc[-1]["sd_px"]), tick)
            sl_price = custom_round(
                entry_price + (float(self.processed_params[symbol]["stop_sd"])) * (self.dfs[symbol].iloc[-1]["sd_px"]),
                tick)

        if LOG_LEVEL == "VERBOSE":
            logger.verbose(f"\n[{datetime.now()}]: A new entry: {symbol}-{direction}-{lmt_price}-{tp_price}-{sl_price}")
        logger.debug(f"Hey, there is a new entry: {symbol}-{direction}-{lmt_price}-{tp_price}-{sl_price}")

        size = float(self.processed_params[symbol]["size"])
        _ticker = Tick(lmt_price, size, symbol, direction, str(datetime.now()))
        key = symbol + "_" + direction + "_" + str(self.dfs[symbol].iloc[-1]["date"])
        self.tickers[key] = _ticker
        curr_bar_id = str(self.dfs[symbol].iloc[-1]["date"])
        if curr_bar_id not in self.tickers[key].max_hold_queue:
            self.tickers[key].max_hold_queue.append(curr_bar_id)
        if lmt_price <= current_price:
            if direction == "LONG":
                bracket = ib.bracketOrder(side, size, lmt_price, tp_price, sl_price, outsideRth=True)
                self.tickers[key].bracket_entry["limit_entry"] = ib.placeOrder(contracts[0], bracket[0])
                self.tickers[key].bracket_entry["take_profit"] = ib.placeOrder(contracts[0], bracket[1])
                self.tickers[key].bracket_entry["stop_loss"] = ib.placeOrder(contracts[0], bracket[2])
                ib.sleep(4)
            else:
                bracket = ib.bracketOrderByStop(side, size, lmt_price, tp_price, sl_price, outsideRth=True)
                self.tickers[key].bracket_entry["limit_entry"] = ib.placeOrder(contracts[0], bracket[0])
                self.tickers[key].bracket_entry["take_profit"] = ib.placeOrder(contracts[0], bracket[1])
                self.tickers[key].bracket_entry["stop_loss"] = ib.placeOrder(contracts[0], bracket[2])
                ib.sleep(4)
        else:
            if direction == "LONG":
                bracket = ib.bracketOrderByStop(side, size, lmt_price, tp_price, sl_price, outsideRth=True)
                self.tickers[key].bracket_entry["limit_entry"] = ib.placeOrder(contracts[0], bracket[0])
                self.tickers[key].bracket_entry["take_profit"] = ib.placeOrder(contracts[0], bracket[1])
                self.tickers[key].bracket_entry["stop_loss"] = ib.placeOrder(contracts[0], bracket[2])
                ib.sleep(4)
            else:
                bracket = ib.bracketOrder(side, size, lmt_price, tp_price, sl_price, outsideRth=True)
                self.tickers[key].bracket_entry["limit_entry"] = ib.placeOrder(contracts[0], bracket[0])
                self.tickers[key].bracket_entry["take_profit"] = ib.placeOrder(contracts[0], bracket[1])
                self.tickers[key].bracket_entry["stop_loss"] = ib.placeOrder(contracts[0], bracket[2])
                ib.sleep(4)

        if self.tickers[key].bracket_entry["limit_entry"].orderStatus.status == "Filled":
            self.tickers[key].entry_filled = True
            self.tickers[key].entry_price = self.tickers[key].bracket_entry["limit_entry"].orderStatus.avgFillPrice

        if LOG_LEVEL != "VERBOSE":
            print(self.tickers[key].bracket_entry, "\n")

    def check_entry_overlap(self, symbol, new_entry_price, direction):
        if direction == "LONG":
            entries = [self.tickers[key].limit_price for key in self.tickers if not self.tickers[key].exit_filled and
                       self.tickers[key].direction == "SHORT" and symbol in key]
        else:
            entries = [self.tickers[key].limit_price for key in self.tickers if not self.tickers[key].exit_filled and
                       self.tickers[key].direction == "LONG" and symbol in key]

        # print(entries)
        return new_entry_price in entries

    def update_connection_status(self):
        self.connection_status = False


if __name__ == "__main__":
    th = Thread(target=main)
    th.start()
    engine = Engine()
    engine.run_cycle()
