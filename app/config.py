
import json


class Config:

    def __init__(self):
        try:
            with open("settings/generalParams.json", "r") as f:
                params = json.load(f)
        except:
            params = {}
        if not params:
            params = {
                "products": "ESM1, CLK1, NGK1",
                "timeframe": "15 mins",
                "size": "2",
                "max_current_high_prd": "20",
                "max_past_high_lag": "10",
                "max_past_high_prd": "10",
                "min_current_low_prd": "20",
                "min_past_low_lag": "10",
                "min_past_low_prd": "10",
                "percent_change_lag": "1.0",
                "sd_lag": "10",
                "tick": "1.0",
                "stop_limit_ticks": "3.0",
                "norm_threshold": "0.7",
                "max_prd_hold": "10",
                "target_sd": "2.0",
                "stop_sd": "4.0",
                "max_stop_sd": "6.0"
            }

        try:
            with open("settings/productSpecificParams.json", "r") as f:
                prod_params = json.load(f)
        except:
            prod_params = {}
        if not prod_params:
            prod_params = {
                "ESM1": "tick = 0.25",
                "CLK1": "tick = 0.01"
            }

        self.params = params
        self.prod_params = prod_params

    def update_prod_params(self):
        try:
            with open("settings/productSpecificParams.json", "r") as f:
                prod_params = json.load(f)
        except:
            prod_params = {}
        if not prod_params:
            prod_params = {
                "ESM1": "tick = 0.25",
                "CLK1": "tick = 0.01"
            }

        self.prod_params = prod_params


MONTH_DICT = {"F": "01", "G": "02", "H": "03", "J": "04", "K": "05", "M": "06", "N": "07", "Q": "08", "U": "09",
              "V": "10", "X": "11", "Z": "12"}

LOG_LEVEL = "VERBOSE"

EXCHANGES = {
    "GLOBEX": ["ES"],
    "NYMEX": ["CL", "NG"]
}
