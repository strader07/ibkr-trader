
class Tick(object):

    def __init__(self, limit_price, quantity, symbol, direction, entry_time):
        self.limit_price = limit_price
        self.quantity = quantity
        self.symbol = symbol
        self.direction = direction
        self.entry_time = entry_time
        self.exit_time = ""

        self.bracket_entry = {
            "limit_entry": None,
            "take_profit": None,
            "stop_loss": None
        }
        self.max_stop_exit = None
        self.market_exit = None

        self.entry_price = None
        self.exit_price = None
        self.entry_filled = False
        self.exit_filled = False
        self.max_hold_queue = []
