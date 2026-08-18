import pandas as pd



def run_walk_forward(
    filename="research/results.csv"
):

    print()
    print("=" * 50)
    print("WALK FORWARD TEST")
    print("=" * 50)



    df = pd.read_csv(
        filename
    )



    df["Index"] = range(
        len(df)
    )



    windows = 5


    size = (
        len(df)
        //
        windows
    )



    results = []



    for i in range(windows-1):


        train_start = 0

        train_end = (
            size
            *
            (i+2)
        )


        test_start = train_end


        test_end = (
            test_start
            +
            size
        )



        train = df.iloc[
            train_start:
            train_end
        ]


        test = df.iloc[
            test_start:
            test_end
        ]



        r = {

            "Window":
            i+1,


            "Train Trades":
            len(train),


            "Train R":
            train["R"].sum(),


            "Test Trades":
            len(test),


            "Test R":
            test["R"].sum(),

        }



        results.append(
            r
        )



    output = pd.DataFrame(
        results
    )



    print()

    print(output)



    output.to_csv(
        "research/walk_forward_results.csv",
        index=False
    )



    print()

    print(
        "Saved:"
    )

    print(
        "research/walk_forward_results.csv"
    )


    return output