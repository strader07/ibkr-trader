
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
                "products": "ESH1, ZNH1, AAPL",
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
                "MU": "tick = 0.25, percent_entry = 0.1",
                "CSCO": "tick = (1/64)",
                "AAPL": "tick = 0.02, size = 25, max_past_high_lag = 5, min_past_low_lag = 5, bar_size = 60"
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
                "MU": "tick = 0.25, percent_entry = 0.1",
                "CSCO": "tick = (1/64)",
                "AAPL": "tick = 0.02, size = 25, max_past_high_lag = 5, min_past_low_lag = 5, bar_size = 60"
            }

        self.prod_params = prod_params


PAPER_ACCOUNT = 'DU1640258'
PAPER_USERNAME = 'bmdf1970p'
PAPER_PASSWORD = 'k1LL3R97!!'

# user: dakuh927
# pass: Elephantdrive345!