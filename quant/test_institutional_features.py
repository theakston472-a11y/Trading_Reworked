import pandas as pd

from institutional_features import add_institutional_features


FEATURE_FILE = r"D:\Trading\quant\feature_database.csv"


print("=" * 70)
print("INSTITUTIONAL FEATURE TEST")
print("=" * 70)
print()

print("Loading feature database...")

df = pd.read_csv(FEATURE_FILE)

print("Rows:", len(df))
print("Columns before:", len(df.columns))
print()

print("Adding institutional features...")

df = add_institutional_features(df)

print("Columns after:", len(df.columns))
print()


# ============================================================
# FEATURE COUNTS
# ============================================================

FEATURES = [

    # Displacement
    "bullish_displacement",
    "bearish_displacement",
    "strong_bullish_displacement",
    "strong_bearish_displacement",

    # Order blocks
    "bullish_order_block",
    "bearish_order_block",
    "bullish_order_block_retest",
    "bearish_order_block_retest",

    # Supply / demand
    "bullish_demand_zone",
    "bearish_supply_zone",
    "demand_zone_retest",
    "supply_zone_retest",

    # Breakers
    "bullish_breaker_block",
    "bearish_breaker_block",
    "bullish_breaker_retest",
    "bearish_breaker_retest",

    # Liquidity confluence
    "bullish_order_block_liquidity",
    "bearish_order_block_liquidity",
    "bullish_demand_liquidity",
    "bearish_supply_liquidity",

    # Fib confluence
    "bullish_ob_fib_confluence",
    "bearish_ob_fib_confluence",

    # Master setups
    "bullish_institutional_setup",
    "bearish_institutional_setup",
]


print("=" * 70)
print("FEATURE COUNTS")
print("=" * 70)
print()

for feature in FEATURES:

    if feature not in df.columns:

        print(
            f"{feature:<40} MISSING"
        )

        continue

    count = int(
        df[feature]
        .fillna(False)
        .astype(bool)
        .sum()
    )

    percentage = (
        count / len(df) * 100
        if len(df) > 0
        else 0
    )

    print(
        f"{feature:<40}"
        f"{count:>10,}"
        f"  ({percentage:>6.2f}%)"
    )


# ============================================================
# INSTITUTIONAL COUNTS
# ============================================================

print()
print("=" * 70)
print("INSTITUTIONAL COMPONENT COUNTS")
print("=" * 70)
print()

print(
    "Bullish institutional candles:",
    int(
        (df["bullish_institutional_count"] >= 1)
        .sum()
    )
)

print(
    "Bullish 2+ concept candles:",
    int(
        (df["bullish_institutional_count"] >= 2)
        .sum()
    )
)

print()

print(
    "Bearish institutional candles:",
    int(
        (df["bearish_institutional_count"] >= 1)
        .sum()
    )
)

print(
    "Bearish 2+ concept candles:",
    int(
        (df["bearish_institutional_count"] >= 2)
        .sum()
    )
)


# ============================================================
# IMPORTANT CONFLUENCE COUNTS
# ============================================================

print()
print("=" * 70)
print("KEY CONFLUENCES")
print("=" * 70)
print()

confluences = {

    "Bullish OB + liquidity":
        "bullish_order_block_liquidity",

    "Bearish OB + liquidity":
        "bearish_order_block_liquidity",

    "Bullish demand + liquidity":
        "bullish_demand_liquidity",

    "Bearish supply + liquidity":
        "bearish_supply_liquidity",

    "Bullish OB + Fibonacci":
        "bullish_ob_fib_confluence",

    "Bearish OB + Fibonacci":
        "bearish_ob_fib_confluence",

}

for name, feature in confluences.items():

    count = int(
        df[feature]
        .fillna(False)
        .astype(bool)
        .sum()
    )

    print(
        f"{name:<35} {count:>10,}"
    )


# ============================================================
# DATE RANGE
# ============================================================

if "timestamp" in df.columns:

    timestamps = pd.to_datetime(
        df["timestamp"],
        errors="coerce"
    )

    print()
    print("=" * 70)
    print("DATA RANGE")
    print("=" * 70)
    print()

    print(
        "First:",
        timestamps.min()
    )

    print(
        "Last:",
        timestamps.max()
    )


print()
print("=" * 70)
print("TEST COMPLETE")
print("=" * 70)