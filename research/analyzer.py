import pandas as pd



def performance_summary(trades):

    """
    Basic strategy statistics.
    """


    df = pd.DataFrame(trades)


    if df.empty:

        return None



    total = len(df)


    wins = (
        df["Result"]
        ==
        "WIN"
    ).sum()


    losses = (
        df["Result"]
        ==
        "LOSS"
    ).sum()



    total_r = (
        df["R"]
        .sum()
    )



    win_rate = 0


    if wins + losses > 0:

        win_rate = (
            wins /
            (wins + losses)
        ) * 100



    return {

        "Trades": total,

        "Wins": wins,

        "Losses": losses,

        "Win Rate": round(
            win_rate,
            2
        ),

        "Total R": round(
            total_r,
            2
        )
    }





def analyze_column(
    trades,
    column
):

    """
    Finds best performing categories.
    """


    df = pd.DataFrame(trades)


    if column not in df.columns:

        return None



    result = (
        df
        .groupby(column)
        .agg(
            Trades=("R","count"),
            Wins=("Result",
                  lambda x:
                  (x=="WIN").sum()),
            Total_R=("R","sum")
        )
        .sort_values(
            "Total_R",
            ascending=False
        )
    )


    return result





def print_analysis(trades):

    print()

    print("="*50)

    print("RESEARCH ANALYSIS")

    print("="*50)



    summary = performance_summary(
        trades
    )


    for key,value in summary.items():

        print(
            f"{key}: {value}"
        )



    print()

    print("BY SESSION")

    print(
        analyze_column(
            trades,
            "Session"
        )
    )



    print()

    print("BY DAY")

    print(
        analyze_column(
            trades,
            "Day"
        )
    )