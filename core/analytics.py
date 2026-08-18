import csv
import os
from collections import defaultdict


FILE_PATH = "trades/trade_history.csv"



def load_trades():

    if not os.path.exists(FILE_PATH):

        return []


    trades = []


    with open(FILE_PATH) as file:

        reader = csv.DictReader(file)


        for row in reader:


            # Ignore trades that are still open

            if row["Result"] != "OPEN":

                trades.append(row)


    return trades




def calculate_stats(trades):


    if not trades:

        return {

            "total": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0,
            "total_r": 0,
            "average_r": 0

        }



    total = len(trades)

    wins = 0

    losses = 0

    total_r = 0



    for trade in trades:


        result = trade["Result"]


        if result == "WIN":

            wins += 1


        elif result == "LOSS":

            losses += 1



        total_r += float(
            trade["R_Multiple"]
        )



    return {


        "total": total,


        "wins": wins,


        "losses": losses,


        "win_rate":
            round(
                wins / total * 100,
                1
            ),


        "total_r":
            round(
                total_r,
                2
            ),


        "average_r":
            round(
                total_r / total,
                2
            )

    }





def strategy_breakdown(trades):


    stats = defaultdict(

        lambda:
        {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "r": 0
        }

    )



    for trade in trades:


        strategy = trade["Strategy"]


        stats[strategy]["trades"] += 1



        if trade["Result"] == "WIN":

            stats[strategy]["wins"] += 1


        elif trade["Result"] == "LOSS":

            stats[strategy]["losses"] += 1



        stats[strategy]["r"] += float(
            trade["R_Multiple"]
        )



    return stats





def print_report():


    trades = load_trades()


    stats = calculate_stats(
        trades
    )



    print()

    print("=" * 50)
    print("STRATEGY PERFORMANCE")
    print("=" * 50)


    print()


    print(
        f"Total Trades : {stats['total']}"
    )


    print(
        f"Wins         : {stats['wins']}"
    )


    print(
        f"Losses       : {stats['losses']}"
    )


    print()


    print(
        f"Win Rate     : {stats['win_rate']}%"
    )


    print(
        f"Total R      : {stats['total_r']}"
    )


    print(
        f"Average R    : {stats['average_r']}"
    )



    print()

    print("=" * 50)
    print("BY STRATEGY")
    print("=" * 50)



    breakdown = strategy_breakdown(
        trades
    )



    for name, data in breakdown.items():


        print()

        print(name)


        print(
            f"Trades : {data['trades']}"
        )


        print(
            f"Wins   : {data['wins']}"
        )


        print(
            f"Losses : {data['losses']}"
        )


        print(
            f"R      : {round(data['r'],2)}"
        )