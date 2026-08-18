import pandas as pd
import time
import os
from datetime import datetime


DATA_FILE = "data/GBPUSD_15.csv"
RULE_FILE = "research/final_strategy_rules.csv"
ALERT_FILE = "research/live_alerts.csv"



def load_data():

    if not os.path.exists(DATA_FILE):

        print("Missing data file")
        exit()


    df = pd.read_csv(
        DATA_FILE
    )


    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        unit="ms"
    )


    df = df.sort_values(
        "timestamp"
    )


    return df




def add_features(df):


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



    df["EMA_Value"] = (

        df["close"]
        .ewm(
            span=50
        )
        .mean()

    )


    df["EMA"] = "Below"


    df.loc[
        df["close"] >
        df["EMA_Value"],
        "EMA"
    ] = "Above"



    df["Trend"] = "Bearish"


    df.loc[
        df["close"] >
        df["EMA_Value"],
        "Trend"
    ] = "Bullish"



    df["Day"] = (
        df["timestamp"]
        .dt.day_name()
    )



    def session(hour):

        if 0 <= hour < 8:
            return "Asia"

        elif 8 <= hour < 13:
            return "London"

        elif 13 <= hour < 21:
            return "New York"

        else:
            return "Other"



    df["Session"] = (

        df["timestamp"]
        .dt.hour
        .apply(session)

    )


    return df




def check_signal(df):


    rules = pd.read_csv(
        RULE_FILE
    )


    candle = df.iloc[-1]


    signals = []



    for _, rule in rules.iterrows():


        if candle["Session"] != rule["Session"]:
            continue


        if candle["Day"] != rule["Day"]:
            continue


        if candle["Trend"] != rule["Trend"]:
            continue


        if candle["EMA"] != rule["EMA"]:
            continue



        entry = candle["close"]


        risk = candle["Range"] * 0.5


        if risk <= 0:
            continue



        if rule["Direction"] == "BUY":


            stop = entry - risk


            target = entry + (risk * 2)



        else:


            stop = entry + risk


            target = entry - (risk * 2)




        signals.append({

            "Time":
                datetime.now(),

            "Candle":
                candle["timestamp"],

            "Direction":
                rule["Direction"],

            "Entry":
                round(entry,5),

            "Stop":
                round(stop,5),

            "Target":
                round(target,5),

            "Session":
                candle["Session"],

            "Day":
                candle["Day"],

            "Trend":
                candle["Trend"],

            "EMA":
                candle["EMA"]

        })



    return signals




def save_alerts(signals):


    if len(signals) == 0:

        print(
            "No signal"
        )

        return



    df = pd.DataFrame(
        signals
    )


    df.to_csv(
        ALERT_FILE,
        index=False
    )


    print()
    print("="*50)
    print("NEW SIGNAL")
    print("="*50)

    print(df)

    print()

    print("Saved:")
    print(ALERT_FILE)




print("="*50)
print("LIVE TRADER STARTED")
print("="*50)



last_candle = None



while True:


    try:


        df = load_data()


        df = add_features(
            df
        )


        current = df.iloc[-1]["timestamp"]



        if current != last_candle:


            print()
            print(
                "New candle:"
            )

            print(
                current
            )


            last_candle = current



            signals = check_signal(
                df
            )


            save_alerts(
                signals
            )



        else:


            print(
                datetime.now(),
                "- waiting"
            )



        time.sleep(
            60
        )



    except Exception as e:


        print()

        print(
            "ERROR:"
        )

        print(
            e
        )


        time.sleep(
            60
        )