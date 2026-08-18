import csv
import os


FILE_PATH = "trades/trade_history.csv"



def check_trade_result(df, trade):

    """
    Checks if an open trade hit
    target or stop.
    """


    # make columns consistent

    df.columns = [
        c.lower()
        for c in df.columns
    ]


    direction = trade["Direction"]

    entry = float(trade["Entry"])
    stop = float(trade["Stop"])
    target = float(trade["Target"])



    for _, candle in df.iterrows():


        high = candle["high"]
        low = candle["low"]



        if direction == "SELL":


            if high >= stop:

                return {
                    "result": "LOSS",
                    "exit": stop,
                    "r": -1
                }


            if low <= target:

                return {
                    "result": "WIN",
                    "exit": target,
                    "r": 2
                }




        if direction == "BUY":


            if low <= stop:

                return {
                    "result": "LOSS",
                    "exit": stop,
                    "r": -1
                }


            if high >= target:

                return {
                    "result": "WIN",
                    "exit": target,
                    "r": 2
                }



    return {
        "result": "OPEN",
        "exit": "",
        "r": 0
    }




def update_trade_history(df):


    if not os.path.exists(FILE_PATH):

        return



    rows = []


    with open(FILE_PATH) as file:

        reader = csv.DictReader(file)


        for trade in reader:


            if trade["Result"] == "OPEN":


                outcome = check_trade_result(
                    df,
                    trade
                )


                trade["Result"] = outcome["result"]

                trade["Exit"] = outcome["exit"]

                trade["R_Multiple"] = outcome["r"]



            rows.append(trade)




    if rows:


        with open(
            FILE_PATH,
            "w",
            newline=""
        ) as file:


            writer = csv.DictWriter(
                file,
                fieldnames=rows[0].keys()
            )


            writer.writeheader()

            writer.writerows(rows)