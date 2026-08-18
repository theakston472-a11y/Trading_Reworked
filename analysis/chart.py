import pandas as pd
import mplfinance as mpf

df = pd.read_csv("data/GBPUSD_15.csv")

df.rename(columns={"Etc/UTC": "Date"}, inplace=True)

df["Date"] = pd.to_datetime(df["Date"])

df = df.set_index("Date")

mpf.plot(
    df,
    type="candle",
    volume=False
)