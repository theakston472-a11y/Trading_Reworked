import pandas as pd
import os
from datetime import datetime


print()
print("=" * 50)
print("LIVE STRATEGY MONITOR")
print("=" * 50)


RULE_FILE = "research/final_strategy_rules.csv"
DATA_FILE = "research/results.csv"
OUTPUT_FILE = "research/live_alerts.csv"



def load_data():

    if not os.path.exists(RULE_FILE):

        print("Missing:")
        print(RULE_FILE)
        return None, None


    if not os.path.exists(DATA_FILE):

        print("Missing:")
        print(DATA_FILE)
        return None, None


    rules = pd.read_csv(
        RULE_FILE
    )


    data = pd.read_csv(
        DATA_FILE
    )


    return rules, data




def check_signal(rules, data):


    median_range = (
        data["Range"]
        .median()
    )


    signals = []


    for _, candle in data.iterrows():


        strong = (

            candle["Body Strength"]

            >=

            0.60

        )


        large_range = (

            candle["Range"]

            >=

            median_range

        )



        match = rules[

            (rules["Session"] == candle["Session"])

            &

            (rules["Day"] == candle["Day"])

            &

            (rules["Direction"] == candle["Direction"])

            &

            (rules["Trend"] == candle["Trend"])

            &

            (rules["EMA"] == candle["EMA"])

            &

            (rules["Strong_Candle"] == strong)

            &

            (rules["Large_Range"] == large_range)

        ]



        if len(match):


            signal = {

                "Time Checked":
                datetime.now(),


                "Direction":
                candle["Direction"],


                "Entry":
                candle["Entry"],


                "Stop":
                candle["Stop"],


                "Target":
                candle["Target"],


                "Session":
                candle["Session"],


                "Day":
                candle["Day"],


                "Trend":
                candle["Trend"],


                "EMA":
                candle["EMA"],


                "Body Strength":
                candle["Body Strength"],


                "Range":
                candle["Range"]

            }


            signals.append(signal)



    return pd.DataFrame(signals)




rules, data = load_data()



if rules is None:

    exit()



print()

print("Rules loaded:")

print(len(rules))


print()

print("Candles checked:")

print(len(data))



signals = check_signal(
    rules,
    data
)



print()

print("=" * 50)
print("SIGNALS")
print("=" * 50)


print()

print(
    "Signals found:",
    len(signals)
)



if len(signals):

    print()

    print(
        signals.tail(10)
    )


    signals.to_csv(

        OUTPUT_FILE,

        index=False

    )


    print()

    print("Saved:")

    print(
        OUTPUT_FILE
    )


else:

    print()

    print(
        "No valid signals"
    )



print()

print("=" * 50)
print("MONITOR COMPLETE")
print("=" * 50)