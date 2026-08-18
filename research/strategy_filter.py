import pandas as pd


def apply_filter(
    filename="research/results.csv",
    strategy_file="research/best_strategies.csv"
):

    print()
    print("="*50)
    print("STRATEGY FILTER")
    print("="*50)


    df = pd.read_csv(filename)

    best = pd.read_csv(strategy_file)


    if len(best) == 0:
        print("No strategies found")
        return df


    print()
    print("Loaded strategies:")
    print(len(best))


    selected = best.head(10)


    filtered = pd.DataFrame()


    for _, row in selected.iterrows():

        temp = df.copy()


        for col in [
            "Session",
            "Day",
            "Direction",
            "Trend",
            "EMA"
        ]:

            if pd.notna(row[col]):

                temp = temp[
                    temp[col]
                    ==
                    row[col]
                ]


        if row["Strong_Candle"] == True:

            temp = temp[
                temp["Body Strength"]
                >=
                0.60
            ]


        if row["Large_Range"] == True:

            temp = temp[
                temp["Range"]
                >=
                df["Range"].median()
            ]


        filtered = pd.concat(
            [
                filtered,
                temp
            ]
        )


    filtered = (
        filtered
        .drop_duplicates()
    )


    print()
    print("FILTERED RESULTS")
    print("----------------")

    print(
        "Trades:",
        len(filtered)
    )


    print(
        "Total R:",
        filtered["R"].sum()
    )


    print(
        "Win Rate:",
        round(
            (filtered["Result"]=="WIN").mean()*100,
            2
        )
    )


    filtered.to_csv(
        "research/filtered_results.csv",
        index=False
    )


    print()
    print(
        "Saved:"
    )

    print(
        "research/filtered_results.csv"
    )


    return filtered



if __name__ == "__main__":

    apply_filter()