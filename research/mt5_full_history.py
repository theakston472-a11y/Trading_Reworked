import MetaTrader5 as mt5
import pandas as pd
import os
from datetime import datetime, timezone, timedelta


print("=" * 60)
print("MT5 FULL HISTORICAL DOWNLOAD")
print("=" * 60)


# ============================================================
# SETTINGS
# ============================================================

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

SYMBOL = "GBPUSD"

TIMEFRAME = mt5.TIMEFRAME_M15

OUTPUT_FILE = "data/GBPUSD_15_FULL.csv"


# ============================================================
# DATE RANGE
# ============================================================

# We go back far enough to capture the available history.

START_DATE = datetime(
    2020,
    1,
    1,
    tzinfo=timezone.utc
)

END_DATE = datetime.now(
    timezone.utc
)


# ============================================================
# CONNECT
# ============================================================

print()
print("Connecting to MT5...")


if not mt5.initialize(
    path=MT5_PATH
):

    print()
    print("MT5 CONNECTION FAILED")

    print(
        mt5.last_error()
    )

    raise SystemExit


print()
print("MT5 connected")


# ============================================================
# SYMBOL
# ============================================================

symbol_info = mt5.symbol_info(
    SYMBOL
)


if symbol_info is None:

    print()
    print("GBPUSD NOT FOUND")

    print(
        mt5.last_error()
    )

    mt5.shutdown()

    raise SystemExit


if not symbol_info.visible:

    mt5.symbol_select(
        SYMBOL,
        True
    )


print()
print(
    "Symbol ready:",
    SYMBOL
)


# ============================================================
# DOWNLOAD IN DATE CHUNKS
# ============================================================

current_start = START_DATE

all_data = []

chunk_number = 0


print()
print("=" * 60)
print("DOWNLOADING HISTORY")
print("=" * 60)


while current_start < END_DATE:

    current_end = current_start + timedelta(
        days=180
    )


    if current_end > END_DATE:

        current_end = END_DATE


    chunk_number += 1


    print()
    print(
        "Chunk:",
        chunk_number
    )

    print(
        "From:",
        current_start
    )

    print(
        "To:",
        current_end
    )


    rates = mt5.copy_rates_range(

        SYMBOL,

        TIMEFRAME,

        current_start,

        current_end

    )


    if rates is None:

        print()
        print(
            "MT5 ERROR:"
        )

        print(
            mt5.last_error()
        )

        current_start = current_end

        continue


    if len(rates) == 0:

        print(
            "No candles returned."
        )

        current_start = current_end

        continue


    df = pd.DataFrame(
        rates
    )


    df["timestamp"] = pd.to_datetime(

        df["time"],

        unit="s",

        utc=True

    )


    df = df[

        [

            "timestamp",

            "open",

            "high",

            "low",

            "close"

        ]

    ]


    print(
        "Candles received:",
        len(df)
    )


    all_data.append(
        df
    )


    current_start = current_end


# ============================================================
# CHECK RESULT
# ============================================================

print()
print("=" * 60)
print("COMBINING HISTORY")
print("=" * 60)


if not all_data:

    print()
    print(
        "NO HISTORICAL DATA WAS DOWNLOADED."
    )

    print(
        "MT5 ERROR:"
    )

    print(
        mt5.last_error()
    )

    mt5.shutdown()

    raise SystemExit


df = pd.concat(

    all_data,

    ignore_index=True

)


# ============================================================
# CLEAN DATA
# ============================================================

df = df.drop_duplicates(

    subset="timestamp"

)


df = df.sort_values(

    "timestamp"

)


df = df.reset_index(

    drop=True

)


# ============================================================
# SAVE
# ============================================================

os.makedirs(
    "data",
    exist_ok=True
)


df.to_csv(

    OUTPUT_FILE,

    index=False

)


# ============================================================
# RESULTS
# ============================================================

print()
print("=" * 60)
print("DOWNLOAD COMPLETE")
print("=" * 60)

print()
print(
    "Total candles:",
    len(df)
)

print()
print(
    "First candle:"
)

print(
    df.iloc[0]["timestamp"]
)

print()
print(
    "Last candle:"
)

print(
    df.iloc[-1]["timestamp"]
)

print()
print(
    "Saved:"
)

print(
    OUTPUT_FILE
)


# ============================================================
# SHUTDOWN
# ============================================================

mt5.shutdown()


print()
print(
    "MT5 connection closed."
)