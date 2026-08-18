import pandas as pd



def search_confluences(
    filename="research/results.csv"
):
    """
    Searches combinations of:
    Session
    Day
    Direction
    Trend
    EMA position
    Candle strength
    """


    df = pd.read_csv(
        filename
    )


    print()
    print("=" * 50)
    print("ADVANCED CONFLUENCE SEARCH")
    print("=" * 50)



    # Check required columns

    required = [
        "Session",
        "Day",
        "Direction",
        "Trend",
        "EMA",
        "Body Strength",
        "Result",
        "R"
    ]


    for col in required:

        if col not in df.columns:

            print(
                f"Missing column: {col}"
            )

            return



    # Candle strength filter

    df["Strong_Candle"] = (
        df["Body Strength"]
        >=
        0.60
    )



    # Search combinations

    results = (

        df

        .groupby(
            [
                "Session",
                "Day",
                "Direction",
                "Trend",
                "EMA",
                "Strong_Candle"
            ]
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



    # Calculate win rate

    results["Win Rate"] = (

        results["Wins"]

        /

        results["Trades"]

        *

        100

    ).round(2)



    # Remove tiny samples

    results = results[
        results["Trades"]
        >=
        30
    ]



    # Rank by profitability

    results = results.sort_values(

        by="Total_R",

        ascending=False

    )



    print()

    print(
        "TOP CONFLUENCE SYSTEMS"
    )

    print()


    print(
        results.head(30)
    )


    return results