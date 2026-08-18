import MetaTrader5 as mt5
import pandas as pd
import time
import os

from datetime import datetime, timedelta


print("=" * 60)
print("MT5 HISTORICAL + LIVE FEED")
print("=" * 60)


# ============================================================
# SETTINGS
# ============================================================

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

SYMBOL = "GBPUSD"

TIMEFRAME = mt5.TIMEFRAME_M15

OUTPUT_FILE = "data/GBPUSD_15.csv"

# Number of historical candles we want.
TARGET_CANDLES = 200000

# Request history in smaller chunks.
CHUNK_SIZE = 5000


# ============================================================
# CREATE DATA DIRECTORY
# ============================================================

os.makedirs(
    "data",
    exist_ok=True
)


# ============================================================
# CONNECT
# ============================================================

print()
print("Connecting to MetaTrader 5...")


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

print()
print(
    "Checking symbol:",
    SYMBOL
)


symbol_info = mt5.symbol_info(
    SYMBOL
)


if symbol_info is None:

    print()
    print("SYMBOL NOT FOUND")

    print(
        mt5.last_error()
    )

    mt5.shutdown()

    raise SystemExit


if not symbol_info.visible:

    print(
        "Selecting symbol..."
    )

    if not mt5.symbol_select(
        SYMBOL,
        True
    ):

        print(
            "Could not select symbol."
        )

        print(
            mt5.last_error()
        )

        mt5.shutdown()

        raise SystemExit


print(
    "Symbol ready."
)


# ============================================================
# DOWNLOAD ONE CHUNK
# ============================================================

def get_chunk(
    start_pos,
    count
):

    rates = mt5.copy_rates_from_pos(

        SYMBOL,

        TIMEFRAME,

        start_pos,

        count

    )


    if rates is None:

        print()
        print(
            "MT5 ERROR:"
        )

        print(
            mt5.last_error()
        )

        return None


    if len(rates) == 0:

        return None


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


    return df


# ============================================================
# DOWNLOAD HISTORY
# ============================================================

print()
print("=" * 60)
print("DOWNLOADING HISTORICAL DATA")
print("=" * 60)

print()
print(
    "Target candles:",
    TARGET_CANDLES
)

print(
    "Chunk size:",
    CHUNK_SIZE
)


all_chunks = []

position = 0


while position < TARGET_CANDLES:

    print()
    print(
        "Requesting candles:",
        position,
        "to",
        position + CHUNK_SIZE
    )


    chunk = get_chunk(

        position,

        CHUNK_SIZE

    )


    if chunk is None:

        print()
        print(
            "No more historical data available."
        )

        break


    print(
        "Received:",
        len(chunk)
    )


    all_chunks.append(
        chunk
    )


    position += len(chunk)


    if len(chunk) < CHUNK_SIZE:

        print()
        print(
            "Reached available MT5 history."
        )

        break


# ============================================================
# CHECK RESULT
# ============================================================

if not all_chunks:

    print()
    print("=" * 60)
    print("NO HISTORICAL DATA RECEIVED")
    print("=" * 60)

    print()
    print(
        "MT5 ERROR:"
    )

    print(
        mt5.last_error()
    )

    print()
    print(
        "Make sure GBPUSD exists in MT5"
    )

    print(
        "and that historical M15 data"
    )

    print(
        "is available."
    )

    mt5.shutdown()

    raise SystemExit


# ============================================================
# COMBINE
# ============================================================

df = pd.concat(
    all_chunks,
    ignore_index=True
)


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
# LIMIT TO TARGET
# ============================================================

if len(df) > TARGET_CANDLES:

    df = df.tail(
        TARGET_CANDLES
    ).reset_index(
        drop=True
    )


# ============================================================
# SAVE
# ============================================================

df.to_csv(

    OUTPUT_FILE,

    index=False

)


print()
print("=" * 60)
print("HISTORY COMPLETE")
print("=" * 60)

print()
print(
    "Candles received:",
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
# LIVE MODE
# ============================================================

last_candle = df.iloc[-1]["timestamp"]


print()
print("=" * 60)
print("LIVE MODE")
print("=" * 60)

print()
print(
    "Watching GBPUSD M15..."
)

print(
    "Press CTRL+C to stop."
)


while True:

    try:

        time.sleep(30)


        latest = get_chunk(
            0,
            5
        )


        if latest is None:

            print(
                datetime.now(),
                "- waiting for MT5"
            )

            continue


        newest_time = (
            latest.iloc[-1]["timestamp"]
        )


        if newest_time != last_candle:

            last_candle = newest_time


            # Rebuild the most recent history
            # so the CSV stays current.

            fresh = get_chunk(
                0,
                min(
                    TARGET_CANDLES,
                    5000
                )
            )


            if fresh is not None:

                # Keep existing history and
                # add the newest candles.

                combined = pd.concat(

                    [

                        df,

                        fresh

                    ],

                    ignore_index=True

                )


                combined = (
                    combined
                    .drop_duplicates(
                        subset="timestamp"
                    )
                    .sort_values(
                        "timestamp"
                    )
                )


                if len(combined) > TARGET_CANDLES:

                    combined = (
                        combined
                        .tail(
                            TARGET_CANDLES
                        )
                    )


                df = combined.reset_index(
                    drop=True
                )


                df.to_csv(

                    OUTPUT_FILE,

                    index=False

                )


            print()
            print("=" * 60)
            print("NEW M15 CANDLE")
            print("=" * 60)

            print()
            print(
                newest_time
            )

            print()
            print(
                "Total candles:",
                len(df)
            )

            print()
            print(
                "CSV UPDATED"
            )


        else:

            print(
                datetime.now(),
                "- waiting for new candle"
            )


    except KeyboardInterrupt:

        print()
        print("=" * 60)
        print("MT5 FEED STOPPED")
        print("=" * 60)

        break


    except Exception as e:

        print()
        print("=" * 60)
        print("FEED ERROR")
        print("=" * 60)

        print(
            e
        )

        time.sleep(30)


mt5.shutdown()