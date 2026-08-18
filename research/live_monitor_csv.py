import pandas as pd
import os
from datetime import datetime


print("=" * 50)
print("CSV LIVE STRATEGY MONITOR")
print("=" * 50)


DATA_FILE = "data/GBPUSD_15.csv"
RULE_FILE = "research/final_strategy_rules.csv"
OUTPUT_FILE = "research/live_alerts.csv"



# ==========================
# LOAD DATA
# ==========================

if not os.path.exists(DATA_FILE):

    print("Missing data file:")
    print(DATA_FILE)
    exit()



df = pd.read_csv(DATA_FILE)



print()
print("Candles loaded:")
print(len(df))



# ==========================
# TIME FIX
# ==========================

df["timestamp"] = pd.to_datetime(
    df["timestamp"],
    unit="ms"
)


df = df.sort_values(
    "timestamp"
)



# ==========================
# FEATURES
# ==========================

df["Range"] = (
    df["high"]
    -
    df["low"]
)



df["Body Strength"] = (

    abs(
        df["close"]
        -
        df["open"]
    )

    /

    df["Range"]

).fillna(0)



# EMA

df["EMA_Value"] = (

    df["close"]
    .ewm(
        span=50
    )
    .mean()

)



df["EMA"] = "Below"



df.loc[
    df["close"] > df["EMA_Value"],
    "EMA"
] = "Above"



# TREND

df["Trend"] = "Bearish"



df.loc[
    df["close"] > df["EMA_Value"],
    "Trend"
] = "Bullish"




# DAY

df["Day"] = (

    df["timestamp"]
    .dt.day_name()

)



# SESSION

def get_session(hour):

    if hour < 8:
        return "Asia"

    elif hour < 13:
        return "London"

    elif hour < 21:
        return "New York"

    else:
        return "Other"



df["Session"] = (

    df["timestamp"]
    .dt.hour
    .apply(get_session)

)




# ==========================
# LOAD RULES
# ==========================

if not os.path.exists(RULE_FILE):

    print("Missing rules:")
    print(RULE_FILE)
    exit()



rules = pd.read_csv(
    RULE_FILE
)



print()
print("Rules loaded:")
print(len(rules))



# ==========================
# LAST CANDLE ONLY
# ==========================

latest = df.iloc[-1]



print()
print("LATEST CANDLE")
print("----------------")
print(latest["timestamp"])



signals = []



for _, rule in rules.iterrows():



    if latest["Session"] != rule["Session"]:
        continue



    if latest["Day"] != rule["Day"]:
        continue



    if latest["Trend"] != rule["Trend"]:
        continue



    if latest["EMA"] != rule["EMA"]:
        continue




    entry = latest["close"]



    risk = latest["Range"] * 0.5



    if risk == 0:
        continue




    if rule["Direction"] == "BUY":


        stop = entry - risk

        target = entry + (risk * 2)



    else:


        stop = entry + risk

        target = entry - (risk * 2)




    signals.append({

        "Time Checked":
            datetime.now(),

        "Candle Time":
            latest["timestamp"],

        "Direction":
            rule["Direction"],

        "Entry":
            round(entry,5),

        "Stop":
            round(stop,5),

        "Target":
            round(target,5),

        "Session":
            latest["Session"],

        "Day":
            latest["Day"],

        "Trend":
            latest["Trend"],

        "EMA":
            latest["EMA"],

        "Body Strength":
            round(
                latest["Body Strength"],
                2
            ),

        "Range":
            round(
                latest["Range"],
                5
            )

    })





# ==========================
# SAVE
# ==========================


result = pd.DataFrame(
    signals
)



print()
print("=" * 50)
print("SIGNALS")
print("=" * 50)



print()

print(
    "Signals found:",
    len(result)
)



if len(result) > 0:

    print(result)



result.to_csv(
    OUTPUT_FILE,
    index=False
)



print()

print("Saved:")
print(OUTPUT_FILE)



print()
print("=" * 50)
print("MONITOR COMPLETE")
print("=" * 50)