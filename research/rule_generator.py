import pandas as pd


print()
print("=" * 50)
print("FINAL STRATEGY RULE GENERATOR")
print("=" * 50)


df = pd.read_csv(
    "research/best_strategies.csv"
)


print()

print("Loaded strategies:")
print(len(df))


# Quality filter

rules = df[

    (df["Trades"] >= 50)

    &

    (df["Total_R"] > 10)

    &

    (df["Win Rate"] >= 40)

]



rules = rules.sort_values(

    by=[

        "Total_R",

        "Win Rate"

    ],

    ascending=False

)



print()

print("FINAL RULES")
print("----------------")


print(

    rules.head(20)

)



rules.to_csv(

    "research/final_strategy_rules.csv",

    index=False

)



print()

print("Saved:")

print(
    "research/final_strategy_rules.csv"
)


print()

print("=" * 50)
print("RULE GENERATION COMPLETE")
print("=" * 50)