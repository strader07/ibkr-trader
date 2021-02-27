from ib_insync import *
from config import *
import clib
import asyncio

# loop = asyncio.new_event_loop()
# asyncio.set_event_loop(loop)
ib = IB()
ib.connect("127.0.0.1", 7497, clientId=23)

contracts = [Stock("MU", "SMART", "USD")]
ib.qualifyContracts(*contracts)
ib.reqMarketDataType(4)

bracket_entry = {}
bracket = ib.bracketOrder("BUY", 20, 87.6, 87.9, 86.6)
bracket_entry["limit_entry"] = ib.placeOrder(contracts[0], bracket[0])
bracket_entry["take_profit"] = ib.placeOrder(contracts[0], bracket[1])
bracket_entry["stop_loss"] = ib.placeOrder(contracts[0], bracket[2])
print("first order success")
ib.sleep(20)

tp_price = 87.96
sl_price = 85.4
contract = bracket_entry["limit_entry"].contract
tp_order = bracket_entry["take_profit"].order
sl_order = bracket_entry["stop_loss"].order

tp_order.lmtPrice = tp_price
tp_order.transmit = True
sl_order.auxPrice = sl_price

bracket_entry["take_profit"] = ib.placeOrder(contract, tp_order)
bracket_entry["stop_loss"] = ib.placeOrder(contract, sl_order)
print("second order success")
ib.sleep(4)
