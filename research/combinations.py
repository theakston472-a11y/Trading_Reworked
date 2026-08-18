import pandas as pd



def test_combinations(
    filename="research/results.csv"
):

    df = pd.read_csv(
        filename
    )


    print()

    print("="*50)
    print("TOP COMBINATIONS")
    print("="*50)



    results = []



    columns = [
        "Session",
        "Day"
    ]



    for session in df["Session"].unique():

        for day in df["Day"].unique():


            subset = df[
                (df["Session"] == session)
                &
                (df["Day"] == day)
            ]



            if len(subset) < 50:

                continue



            r = subset["R"].sum()


            wins = (
                subset["Result"]
                ==
                "WIN"
            ).sum()



            winrate = (
                wins /
                len(subset)
            ) * 100



            results.append(
                {
                    "Session":session,
                    "Day":day,
                    "Trades":len(subset),
                    "Win Rate":round(winrate,2),
                    "R":round(r,2)
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
        report.head(10)
    )


    return report