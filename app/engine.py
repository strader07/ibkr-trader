from tick import Tick

import json
from sortedcontainers import SortedDict
from datetime import date, datetime
from pytz.reference import Eastern
import time
import logging

from ib_insync import *


def get_prod_params():
    try:
        with open("settings/productSpecificParams.json", "r") as f:
            data = json.load(f)
    except:
        data = {}
    if not data:
        return {}
    # data = data.replace("\n", "")
    # prods = [param.strip() for param in data.split(";")]
    # keys = [prod.split(":")[0].strip(",. ") for prod in prods]
    # values = [prod.split(":")[1].strip(",. ") for prod in prods]
    keys = list(data.keys())
    values = list(data.values())

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
        prod_params[key] = value

    return prod_params


class Engine:
    prod_params = {}

    def __init__(self, params):
        self.params = params
        self.tickers = SortedDict()
        print("??-", self.params)

    def start(self):
        self.prod_params = get_prod_params()
        print(f"current products specific parameters: \n")
        print(json.dumps(self.prod_params, indent=4))
