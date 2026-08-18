import pandas as pd



def optimize_strategy(
    filename="research/results.csv"
):

    print()
    print("=" * 50)
    print("STRATEGY OPTIMIZER V2")
    print("=" * 50)



    df = pd.read_csv(
        filename
    )



    df["Strong_Candle"] = (

        df["Body Strength"]

        >=

        0.60

    )



    df["Large_Range"] = (

        df["Range"]

        >=

        df["Range"].median()

    )



    rules = [

        "Session",

        "Day",

        "Direction",

        "Trend",

        "EMA",

        "Strong_Candle",

        "Large_Range"

    ]



    print()

    print(
        "Testing complete strategies..."
    )



    results = (

        df

        .groupby(
            rules
        )

        .agg(

            Trades=(
                "R",
                "count"
            ),

            Wins=(
                "Result",
                lambda x:
                (x == "WIN").sum()
            ),

            Losses=(
                "Result",
                lambda x:
                (x == "LOSS").sum()
            ),

            Total_R=(
                "R",
                "sum"
            )

        )

    )



    results["Win Rate"] = (

        results["Wins"]

        /

        results["Trades"]

        *

        100

    ).round(2)



    results = results.reset_index()



    results = results[

        results["Trades"]

        >=

        50

    ]



    results = results[

        results["Total_R"]

        >

        0

    ]



    results = results.sort_values(

        by=[

            "Total_R",

            "Win Rate",

            "Trades"

        ],

        ascending=False

    )



    print()

    print(
        "BEST COMPLETE STRATEGIES"
    )

    print()


    print(
        results.head(30)
    )



    results.to_csv(

        "research/best_strategies.csv",

        index=False

    )



    print()

    print(
        "Saved:"
    )

    print(
        "research/best_strategies.csv"
    )



    return results