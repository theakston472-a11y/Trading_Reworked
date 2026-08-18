import pandas as pd



def test_direction(
    filename="research/results.csv"
):

    df = pd.read_csv(
        filename
    )


    print()
    print("="*50)
    print("DIRECTION ANALYSIS")
    print("="*50)


    results = (
        df
        .groupby(
            [
                "Session",
                "Day",
                "Direction"
            ]
        )
        .agg(
            Trades=("R","count"),
            Wins=(
                "Result",
                lambda x:
                (x=="WIN").sum()
            ),
            Total_R=(
                "R",
                "sum"
            )
        )
        .sort_values(
            "Total_R",
            ascending=False
        )
    )


    print(
        results.head(20)
    )


    return results