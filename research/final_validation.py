import pandas as pd


print()
print("=" * 50)
print("FINAL STRATEGY VALIDATION")
print("=" * 50)


# Load final backtest trades

filename = "research/final_backtest_results.csv"


df = pd.read_csv(filename)


print()
print("LOADED RESULTS")
print("----------------")

print("Trades:", len(df))


# Basic stats

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


total_r = df["R"].sum()


win_rate = round(
    wins / len(df) * 100,
    2
)


print(
    "Wins:",
    wins
)

print(
    "Losses:",
    losses
)

print(
    "Win Rate:",
    win_rate
)

print(
    "Total R:",
    total_r
)


# Split validation

split = int(
    len(df) * 0.70
)


train = df.iloc[:split]

test = df.iloc[split:]


print()
print("=" * 50)
print("TRAIN / VALIDATION SPLIT")
print("=" * 50)


print()
print("TRAIN")

print(
    "Trades:",
    len(train)
)

print(
    "R:",
    train["R"].sum()
)


print()
print("VALIDATION")


print(
    "Trades:",
    len(test)
)

print(
    "Wins:",
    (
        test["Result"]=="WIN"
    ).sum()
)


print(
    "Losses:",
    (
        test["Result"]=="LOSS"
    ).sum()
)


print(
    "R:",
    test["R"].sum()
)


print(
    "Win Rate:",
    round(
        (
            test["Result"]=="WIN"
        ).sum()
        /
        len(test)
        *
        100,
        2
    )
)


# Yearly if date exists

print()
print("=" * 50)
print("YEAR TEST")
print("=" * 50)


if "Date" in df.columns:

    df["Date"] = pd.to_datetime(
        df["Date"]
    )

    yearly = (
        df
        .groupby(
            df["Date"].dt.year
        )
        ["R"]
        .sum()
    )

    print(yearly)

else:

    print(
        "No Date column found"
    )


# Session stability

print()
print("=" * 50)
print("SESSION STABILITY")
print("=" * 50)


if "Session" in df.columns:

    print(
        df
        .groupby("Session")
        ["R"]
        .sum()
    )


# Drawdown

print()
print("=" * 50)
print("DRAWDOWN")
print("=" * 50)


equity = (
    df["R"]
    .cumsum()
)


peak = (
    equity
    .cummax()
)


drawdown = (
    equity - peak
)


print(
    "Maximum Drawdown:",
    drawdown.min()
)


print()
print("=" * 50)
print("VALIDATION COMPLETE")
print("=" * 50)