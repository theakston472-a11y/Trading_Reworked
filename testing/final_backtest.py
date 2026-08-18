import pandas as pd
import os


print()
print("=" * 50)
print("FINAL FILTERED BACKTEST")
print("=" * 50)


# Load research trades

filename = "research/results.csv"


if not os.path.exists(filename):

    print("Missing research/results.csv")

    exit()



df = pd.read_csv(filename)



print()

print("Original Trades:")
print(len(df))



# Load final rules

rules = pd.read_csv(

    "research/final_strategy_rules.csv"

)



print()

print("Active Rules:")
print(len(rules))



filtered = []



for _, trade in df.iterrows():


    match = rules[

        (rules["Session"] == trade["Session"])

        &

        (rules["Day"] == trade["Day"])

        &

        (rules["Direction"] == trade["Direction"])

        &

        (rules["Trend"] == trade["Trend"])

        &

        (rules["EMA"] == trade["EMA"])

    ]



    if len(match):


        strong = (

            trade["Body Strength"]

            >=

            0.60

        )


        large = (

            trade["Range"]

            >=

            df["Range"].median()

        )



        if (

            strong == bool(match.iloc[0]["Strong_Candle"])

            and

            large == bool(match.iloc[0]["Large_Range"])

        ):


            filtered.append(trade)



result = pd.DataFrame(filtered)



print()

print("=" * 50)
print("FINAL RESULTS")
print("=" * 50)



if len(result) == 0:

    print("No trades found")

    exit()



trades = len(result)

wins = (

    result["Result"]

    ==

    "WIN"

).sum()


losses = (

    result["Result"]

    ==

    "LOSS"

).sum()



winrate = round(

    wins /

    trades *

    100,

    2

)



total_r = result["R"].sum()



print()

print("Trades:", trades)

print("Wins:", wins)

print("Losses:", losses)

print("Win Rate:", winrate)

print("Total R:", total_r)



# Equity curve


equity = 0

curve = []


for r in result["R"]:

    equity += r

    curve.append(equity)



result["Equity"] = curve



drawdown = (

    result["Equity"]

    -

    result["Equity"].cummax()

).min()



print()

print("Maximum Drawdown:")

print(round(drawdown,2))



result.to_csv(

    "research/final_backtest_results.csv",

    index=False

)



print()

print("Saved:")

print(

    "research/final_backtest_results.csv"

)



print()

print("=" * 50)
print("FINAL BACKTEST COMPLETE")
print("=" * 50)