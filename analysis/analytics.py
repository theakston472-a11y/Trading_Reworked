import pandas as pd
import os


TRADE_FILE = "trades/trade_history.csv"


def load_trades():

    if not os.path.exists(TRADE_FILE):
        raise FileNotFoundError(
            "Trade journal not found"
        )

    df = pd.read_csv(TRADE_FILE)

    return df



def generate_report():

    print("=" * 40)
    print("BACKTEST ANALYTICS")
    print("=" * 40)


    df = load_trades()


    total_trades = len(df)

    wins = len(
        df[df["Result"] == "WIN"]
    )

    losses = len(
        df[df["Result"] == "LOSS"]
    )


    if total_trades > 0:

        win_rate = round(
            (wins / total_trades) * 100,
            2
        )

    else:

        win_rate = 0


    total_r = round(
        df["R_Multiple"].sum(),
        2
    )


    average_r = round(
        df["R_Multiple"].mean(),
        2
    )


    print()

    print("Total Trades:", total_trades)

    print("Wins:", wins)

    print("Losses:", losses)

    print("Win Rate:", win_rate, "%")

    print("Total R:", total_r)

    print("Average R:", average_r)

    print()

    print("=" * 40)



if __name__ == "__main__":

    generate_report()