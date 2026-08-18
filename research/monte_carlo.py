import pandas as pd
import numpy as np


print()
print("=" * 50)
print("MONTE CARLO TEST V2")
print("=" * 50)


df = pd.read_csv(
    "research/filtered_results.csv"
)


trades = df["R"].values


simulations = 5000


final_results = []
drawdowns = []
losing_streaks = []


for i in range(simulations):

    shuffled = np.random.choice(
        trades,
        size=len(trades),
        replace=True
    )


    equity = np.cumsum(
        shuffled
    )


    final_results.append(
        equity[-1]
    )


    peak = np.maximum.accumulate(
        equity
    )


    dd = equity - peak


    drawdowns.append(
        dd.min()
    )


    losses = 0
    max_losses = 0


    for r in shuffled:

        if r < 0:
            losses += 1
        else:
            losses = 0


        if losses > max_losses:
            max_losses = losses


    losing_streaks.append(
        max_losses
    )



print()

print("SIMULATIONS")
print(simulations)


print()

print("FINAL R RESULTS")
print("----------------")

print(
    "Best:",
    round(max(final_results),2),
    "R"
)


print(
    "Worst:",
    round(min(final_results),2),
    "R"
)


print(
    "Median:",
    round(
        np.median(final_results),
        2
    ),
    "R"
)


print(
    "5% Worst Case:",
    round(
        np.percentile(final_results,5),
        2
    ),
    "R"
)


print(
    "95% Best Case:",
    round(
        np.percentile(final_results,95),
        2
    ),
    "R"
)



print()

print("DRAWDOWN")
print("----------------")

print(
    "Average:",
    round(
        np.mean(drawdowns),
        2
    ),
    "R"
)


print(
    "Worst:",
    round(
        min(drawdowns),
        2
    ),
    "R"
)



print()

print("LOSING STREAK")
print("----------------")


print(
    "Average:",
    round(
        np.mean(losing_streaks),
        1
    )
)


print(
    "Worst:",
    max(losing_streaks)
)



results = pd.DataFrame({

    "Final_R":
    final_results,

    "Drawdown":
    drawdowns,

    "Losing_Streak":
    losing_streaks

})


results.to_csv(
    "research/monte_carlo_v2_results.csv",
    index=False
)


print()

print("Saved:")
print(
    "research/monte_carlo_v2_results.csv"
)


print()

print("=" * 50)
print("MONTE CARLO COMPLETE")
print("=" * 50)