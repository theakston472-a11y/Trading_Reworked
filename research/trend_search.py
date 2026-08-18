import pandas as pd



def search_trend(
    filename="research/results.csv"
):

    df = pd.read_csv(
        filename
    )


    print()
    print("="*50)
    print("TREND CONFLUENCE SEARCH")
    print("="*50)



    if "Trend" not in df.columns:

        print(
            "Trend column missing"
        )

        return



    results = []



    for trend in df["Trend"].unique():

        subset = df[
            df["Trend"] == trend
        ]



        if len(subset) < 50:

            continue



        wins = (
            subset["Result"]
            ==
            "WIN"
        ).sum()



        results.append(
            {
                "Trend":trend,
                "Trades":len(subset),
                "Win Rate":round(
                    wins / len(subset) * 100,
                    2
                ),
                "R":round(
                    subset["R"].sum(),
                    2
                )
            }
        )



    report = pd.DataFrame(
        results
    )


    report = report.sort_values(
        "R",
        ascending=False
    )


    print(
        report
    )


    return report