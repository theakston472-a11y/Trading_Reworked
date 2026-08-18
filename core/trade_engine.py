from datetime import datetime
import trade_logger


class Trade:
    """
    Represents one trade.
    """

    def __init__(
        self,
        pair,
        direction,
        entry,
        stop,
        target,
        size,
        strategy,
        session,
        key_area_touches,
        fib_level
    ):

        self.pair = pair
        self.direction = direction

        self.entry = entry
        self.stop = stop
        self.target = target

        self.size = size

        # Strategy information
        self.strategy = strategy
        self.session = session
        self.key_area_touches = key_area_touches
        self.fib_level = fib_level

        self.status = "OPEN"

        self.exit = None
        self.result = None
        self.r_multiple = 0

        self.open_time = datetime.now()
        self.close_time = None


    def check_trade(self, high, low):
        """
        Checks whether stop or target was hit.
        """

        if self.status != "OPEN":
            return


        # BUY trade
        if self.direction == "BUY":

            if low <= self.stop:

                self.close_trade(
                    self.stop,
                    "LOSS"
                )


            elif high >= self.target:

                self.close_trade(
                    self.target,
                    "WIN"
                )


        # SELL trade
        else:

            if high >= self.stop:

                self.close_trade(
                    self.stop,
                    "LOSS"
                )


            elif low <= self.target:

                self.close_trade(
                    self.target,
                    "WIN"
                )


    def close_trade(self, exit_price, result):
        """
        Closes the trade.
        """

        self.exit = exit_price
        self.result = result

        self.status = "CLOSED"

        self.close_time = datetime.now()


        if self.direction == "BUY":

            movement = self.exit - self.entry

        else:

            movement = self.entry - self.exit


        risk = abs(self.entry - self.stop)

        self.r_multiple = round(
            movement / risk,
            2
        )

        trade_logger.save_trade(self)


    def summary(self):

        print("=" * 40)
        print("TRADE SUMMARY")
        print("=" * 40)

        print("Pair:", self.pair)
        print("Direction:", self.direction)

        print("Strategy:", self.strategy)
        print("Session:", self.session)
        print("Key Area Touches:", self.key_area_touches)
        print("Fib Level:", self.fib_level)

        print("Entry:", self.entry)
        print("Stop:", self.stop)
        print("Target:", self.target)

        print("Size:", self.size)

        print("Status:", self.status)

        if self.status == "CLOSED":

            print("Result:", self.result)
            print("Exit:", self.exit)
            print("R Multiple:", self.r_multiple)

        print("=" * 40)



if __name__ == "__main__":


    trade = Trade(
        pair="GBPUSD",
        direction="BUY",
        entry=1.27000,
        stop=1.26940,
        target=1.27180,
        size=1.67,
        strategy="Fib Rejection",
        session="London",
        key_area_touches=3,
        fib_level=0.618
    )


    trade.summary()


    trade.check_trade(
        high=1.27200,
        low=1.27020
    )


    trade.summary()