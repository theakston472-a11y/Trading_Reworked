import pandas as pd


print()
print("=" * 50)
print("FILTERED STRATEGY VALIDATION")
print("=" * 50)


file = "research/filtered_results.csv"


df = pd.read_csv(file)


print()
print("TOTAL FILTERED TRADES")
print("--------------------")

trades = len(df)
wins = (df["Result"] == "WIN").sum()
losses = (df["Result"] == "LOSS").sum()

total_r = df["R"].sum()

winrate = (
    wins /
    trades *
    100
)


print("Trades:", trades)
print("Wins:", wins)
print("Losses:", losses)
print("Win Rate:", round(winrate,2))
print("Total R:", total_r)



print()
print("=" * 50)
print("SESSION TEST")
print("=" * 50)

print(
    df.groupby("Session")["R"]
    .sum()
)



print()
print("=" * 50)
print("DAY TEST")
print("=" * 50)

print(
    df.groupby("Day")["R"]
    .sum()
)



print()
print("=" * 50)
print("DIRECTION TEST")
print("=" * 50)

print(
    df.groupby("Direction")["R"]
    .sum()
)



print()
print("=" * 50)
print("VALIDATION COMPLETE")
print("=" * 50)