from core.loader import load_data

from core.strategy_engine import run_strategy



print("=" * 50)
print("FULL STRATEGY ENGINE TEST")
print("=" * 50)


df = load_data()


result = run_strategy(df)



print()

print("=" * 50)
print("MARKET")
print("=" * 50)


print(
    f"Price : {result['price']:.5f}"
)

print(
    f"Trend : {result['trend']}"
)

print(
    f"EMA   : {result['ema']}"
)

print(
    f"EMA Position : {result['ema_position']}"
)



print()

print("=" * 50)
print("DECISION")
print("=" * 50)


decision = result["decision"]


print(
    f"Decision : {decision['decision']}"
)

print(
    f"Score : {decision['score']}/100"
)

print(
    f"Bias : {decision['bias']}"
)



print()

print("Reasons:")

for r in decision["reasons"]:
    print("-", r)



if result["trade"]:

    print()

    print("=" * 50)
    print("TRADE PLAN")
    print("=" * 50)


    trade = result["trade"]


    print(
        f"Direction : {trade['direction']}"
    )

    print(
        f"Entry : {trade['entry']}"
    )

    print(
        f"Stop : {trade['stop']}"
    )

    print(
        f"Target : {trade['target']}"
    )

    print(
        f"Lots : {trade['lots']}"
    )


else:

    print()
    print("No trade generated")



print()

print("=" * 50)
print("TEST COMPLETE")
print("=" * 50)