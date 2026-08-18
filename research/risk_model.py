import pandas as pd
import numpy as np


print()
print("=" * 50)
print("RISK MODEL TEST")
print("=" * 50)


df = pd.read_csv(
    "research/filtered_results.csv"
)


trades = df["R"].values


risk_levels = [

    0.25,
    0.50,
    1.00

]


starting_balance = 10000


print()

print("Starting Balance:")
print(starting_balance)


print()

print("=" * 50)
print("RISK RESULTS")
print("=" * 50)



results = []



for risk in risk_levels:


    balance = starting_balance

    peak = balance

    max_drawdown = 0

    wins = 0

    losses = 0



    for r in trades:


        change = (

            balance

            *

            (risk / 100)

            *

            r

        )


        balance += change



        if r > 0:

            wins += 1

        else:

            losses += 1



        if balance > peak:

            peak = balance



        drawdown = (

            balance

            -

            peak

        )


        if drawdown < max_drawdown:

            max_drawdown = drawdown



    profit = (

        balance

        -

        starting_balance

    )


    results.append({

        "Risk %":

        risk,


        "Final Balance":

        round(balance,2),


        "Profit":

        round(profit,2),


        "Return %":

        round(

            profit /

            starting_balance *

            100,

            2

        ),


        "Max Drawdown":

        round(max_drawdown,2)

    })



result_df = pd.DataFrame(results)



print()

print(result_df)



result_df.to_csv(

    "research/risk_results.csv",

    index=False

)



print()

print("Saved:")

print(

    "research/risk_results.csv"

)


print()

print("=" * 50)
print("RISK MODEL COMPLETE")
print("=" * 50)