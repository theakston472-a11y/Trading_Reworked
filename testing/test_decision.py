from core.loader import load_data

from analysis.key_areas import (
    find_key_areas,
    find_entry_levels,
)

from analysis.rejection import (
    bullish_rejection,
    bearish_rejection,
    inside_zone,
    touching_entry,
)

from analysis.trend import get_trend

from analysis.ema import (
    add_emas,
    ema_direction,
    price_position,
)

from core.decision import evaluate_trade



print("=" * 50)
print("DECISION ENGINE TEST")
print("=" * 50)



# =========================
# LOAD DATA
# =========================

df = load_data()

df.columns = [c.lower() for c in df.columns]


print()
print("✓ Data loaded")



# =========================
# EMA
# =========================

df = add_emas(df)



# =========================
# CURRENT PRICE
# =========================

current = df.iloc[-1]

price = current["close"]



# =========================
# TREND
# =========================

trend_data = get_trend(df)

trend_dir = trend_data["direction"]



# =========================
# EMA STATE
# =========================

ema_dir = ema_direction(df)

ema_pos = price_position(df)



print()
print("=" * 50)
print("MARKET STATE")
print("=" * 50)

print(f"Price : {price:.5f}")
print(f"Trend : {trend_dir}")
print(f"EMA   : {ema_dir}")
print(f"EMA Position : {ema_pos}")



# =========================
# FIND ZONE
# =========================

zones = find_key_areas(
    df,
    tolerance=0.0005,
    minimum_rejections=3,
    max_zones=50,
)



active_zone = None
entry_price = None



for zone in zones:

    if inside_zone(price, zone):

        active_zone = zone


        entries = find_entry_levels(
            zone,
            max_entries=3
        )


        entry = touching_entry(
            price,
            entries
        )


        if entry:

            entry_price = entry["price"]


        break



# =========================
# REJECTION
# =========================

bull = bullish_rejection(current)

bear = bearish_rejection(current)


rejection = bull or bear



# =========================
# DECISION
# =========================

result = evaluate_trade(

    zone=active_zone,

    entry=entry_price,

    rejection=rejection,

    trend=trend_dir,

    ema=ema_dir,

    price=price

)



print()
print("=" * 50)
print("DECISION")
print("=" * 50)


print(f"Decision : {result['decision']}")

print(f"Score    : {result['score']}/100")

print(f"Bias     : {result['bias']}")



print()
print("Reasons:")

for reason in result["reasons"]:

    print(f"- {reason}")



# =========================
# TRADE PLAN
# =========================

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
        f"Entry     : {trade['entry']:.5f}"
    )

    print(
        f"Stop      : {trade['stop']:.5f}"
    )

    print(
        f"Target    : {trade['target']:.5f}"
    )

    print(
        f"Risk/Reward : {trade['risk_reward']}"
    )


else:

    print()
    print("No trade plan generated")



print()
print("=" * 50)
print("TEST COMPLETE")
print("=" * 50)