import csv
import os
from datetime import datetime


FILE_PATH = "trades/trade_history.csv"



def save_trade(trade):

    if trade is None:
        return


    os.makedirs(
        "trades",
        exist_ok=True
    )


    file_exists = os.path.isfile(
        FILE_PATH
    )


    with open(
        FILE_PATH,
        "a",
        newline=""
    ) as file:


        writer = csv.writer(file)


        if not file_exists:

            writer.writerow(
                [
                    "Date",
                    "Pair",
                    "Direction",
                    "Strategy",
                    "Session",
                    "Key_Area_Touches",
                    "Fib_Level",
                    "Entry",
                    "Exit",
                    "Stop",
                    "Target",
                    "Size",
                    "Result",
                    "R_Multiple"
                ]
            )


        writer.writerow(
            [
                datetime.now(),

                "GBPUSD",

                trade["direction"],

                "Key Area + EMA + Trend",

                "Unknown",

                0,

                "",

                trade["entry"],

                "",

                trade["stop"],

                trade["target"],

                trade["lots"],

                "OPEN",

                trade["risk_reward"]
            ]
        )