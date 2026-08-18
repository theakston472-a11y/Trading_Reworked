import pandas as pd



def run_validation(
    filename="research/results.csv"
):

    print()
    print("=" * 50)
    print("VALIDATION TEST")
    print("=" * 50)



    df = pd.read_csv(
        filename
    )



    print()

    print(
        "Testing unseen validation conditions..."
    )



    # Split data into sections

    split = int(
        len(df) * 0.7
    )


    train = df.iloc[:split]

    validation = df.iloc[split:]



    print()

    print(
        "TRAIN DATA"
    )

    print(
        "Trades:",
        len(train)
    )


    print(
        "Total R:",
        train["R"].sum()
    )



    print()

    print(
        "VALIDATION DATA"
    )

    print(
        "Trades:",
        len(validation)
    )


    print(
        "Wins:",
        (
            validation["Result"]
            ==
            "WIN"
        ).sum()
    )


    print(
        "Losses:",
        (
            validation["Result"]
            ==
            "LOSS"
        ).sum()
    )


    print(
        "Total R:",
        validation["R"].sum()
    )


    win_rate = (

        (
            validation["Result"]
            ==
            "WIN"
        ).sum()

        /

        len(validation)

        *

        100

    )


    print(
        "Win Rate:",
        round(win_rate,2)
    )



    print()

    print(
        "Validation complete"
    )



    return validation