import pandas as pd


print()
print("=" * 50)
print("STRICT FINAL SIGNAL GENERATOR")
print("=" * 50)


rules = pd.read_csv(
    "research/final_strategy_rules.csv"
)


trades = pd.read_csv(
    "research/results.csv"
)


median_range = trades["Range"].median()


signals = []


for _, trade in trades.iterrows():


    strong_candle = (

        trade["Body Strength"]

        >=

        0.60

    )


    large_range = (

        trade["Range"]

        >=

        median_range

    )



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

        &

        (rules["Strong_Candle"] == strong_candle)

        &

        (rules["Large_Range"] == large_range)

    ]



    if len(match):

        signals.append(
            trade
        )



result = pd.DataFrame(
    signals
)



print()

print("Signals Found:")

print(len(result))


if len(result):

    print()

    print(result.head(20))



result.to_csv(

    "research/live_signals_strict.csv",

    index=False

)



print()

print("Saved:")

print(
    "research/live_signals_strict.csv"
)


print()

print("=" * 50)
print("STRICT SIGNAL GENERATOR COMPLETE")
print("=" * 50)