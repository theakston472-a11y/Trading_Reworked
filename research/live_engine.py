import time
import os
import subprocess
from datetime import datetime

import pandas as pd

from research.email_alert import send_email_alert


print("=" * 50)
print("LIVE TRADING ENGINE")
print("=" * 50)


# ==================================
# SETTINGS
# ==================================

FEED_FILE = "data/GBPUSD_15.csv"

ALERT_FILE = "research/live_alerts.csv"


last_modified = None

last_alert = None



# ==================================
# MAIN LOOP
# ==================================

while True:

    try:

        # Check MT5 feed exists

        if not os.path.exists(FEED_FILE):

            print("Waiting for MT5 feed...")

            time.sleep(60)

            continue



        # Check for new candle update

        modified = os.path.getmtime(FEED_FILE)



        if modified != last_modified:


            last_modified = modified



            print()

            print("=" * 50)

            print("NEW MARKET UPDATE")

            print(datetime.now())

            print("=" * 50)



            # Run strategy scanner

            subprocess.run(
                [
                    "python",
                    "-m",
                    "research.live_monitor_csv"
                ]
            )



            time.sleep(2)



            # Check alert file

            if not os.path.exists(ALERT_FILE):

                print("No alert file")

                time.sleep(60)

                continue



            # Ignore empty files

            if os.path.getsize(ALERT_FILE) == 0:

                print("No signals yet")

                time.sleep(60)

                continue



            # Read signals safely

            try:

                alerts = pd.read_csv(
                    ALERT_FILE
                )


            except pd.errors.EmptyDataError:


                print(
                    "Alert file empty - waiting"
                )

                time.sleep(60)

                continue



            if alerts.empty:


                print(
                    "No signals"
                )

                time.sleep(60)

                continue



            # Get newest signal

            latest = alerts.iloc[-1]



            alert_id = (

                str(latest.get("Candle Time"))

                +

                str(latest.get("Direction"))

                +

                str(latest.get("Entry"))

            )



            # Stop duplicate emails

            if alert_id != last_alert:


                last_alert = alert_id



                signal = {


                    "Direction":
                    latest.get("Direction"),


                    "Entry":
                    latest.get("Entry"),


                    "Stop":
                    latest.get("Stop"),


                    "Target":
                    latest.get("Target"),


                    "Session":
                    latest.get("Session"),


                    "Day":
                    latest.get("Day"),


                    "Trend":
                    latest.get("Trend"),


                    "EMA":
                    latest.get("EMA"),


                    "Body Strength":
                    latest.get("Body Strength"),


                    "Range":
                    latest.get("Range")

                }



                print()

                print("=" * 50)

                print("NEW SIGNAL")

                print("=" * 50)

                print(signal)



                send_email_alert(
                    signal
                )



            else:


                print(
                    "Signal already sent"
                )



        else:


            print(

                datetime.now(),

                "- waiting for candle"

            )



        time.sleep(60)




    except KeyboardInterrupt:


        print()

        print(
            "ENGINE STOPPED"
        )

        break




    except Exception as e:


        print()

        print(
            "ENGINE ERROR:"
        )

        print(e)


        time.sleep(60)