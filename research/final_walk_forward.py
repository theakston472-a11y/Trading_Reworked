import pandas as pd


print()
print("=" * 50)
print("FINAL WALK FORWARD TEST")
print("=" * 50)


df = pd.read_csv(
    "research/final_backtest_results.csv"
)


print()
print("Total Trades:")
print(len(df))


windows = 4


size = len(df) // windows


results = []


for i in range(windows - 1):

    train_start = 0

    train_end = size * (i + 1)

    test_end = size * (i + 2)


    train = df.iloc[
        train_start:train_end
    ]


    test = df.iloc[
        train_end:test_end
    ]


    train_r = train["R"].sum()

    test_r = test["R"].sum()


    test_win = (
        test["Result"]
        ==
        "WIN"
    ).sum()


    test_total = len(test)


    win_rate = round(
        test_win / test_total * 100,
        2
    )


    results.append(
        {
            "Window": i + 1,
            "Train Trades": len(train),
            "Train R": train_r,
            "Test Trades": len(test),
            "Test R": test_r,
            "Test Win Rate": win_rate
        }
    )


result = pd.DataFrame(
    results
)


print()

print(result)


result.to_csv(
    "research/final_walk_forward_results.csv",
    index=False
)


print()

print("Saved:")
print(
    "research/final_walk_forward_results.csv"
)


print()
print("=" * 50)
print("WALK FORWARD COMPLETE")
print("=" * 50)