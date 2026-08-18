import os

from quant.feature_engine import build_features


print("=" * 60)
print("QUANT FEATURE ENGINE")
print("=" * 60)


# =========================================================
# FILES
# =========================================================

INPUT_FILE = "data/GBPUSD_15_FULL.csv"

OUTPUT_FILE = "quant/feature_database.csv"


# =========================================================
# CHECK INPUT
# =========================================================

if not os.path.exists(INPUT_FILE):

    print()
    print("ERROR: INPUT FILE NOT FOUND")
    print(INPUT_FILE)

    raise SystemExit


# =========================================================
# BUILD
# =========================================================

df = build_features(
    INPUT_FILE
)


# =========================================================
# SAVE
# =========================================================

print()
print("=" * 60)
print("SAVING FEATURE DATABASE")
print("=" * 60)

df.to_csv(
    OUTPUT_FILE,
    index=False
)


# =========================================================
# RESULTS
# =========================================================

print()
print("Saved:")
print(OUTPUT_FILE)

print()
print("Rows:")
print(len(df))

print()
print("Columns:")
print(len(df.columns))


# =========================================================
# BOOLEAN STATISTICS
# =========================================================

boolean_columns = [
    column
    for column in df.columns
    if df[column].dtype == bool
]


print()
print("=" * 60)
print("FEATURE STATISTICS")
print("=" * 60)


for column in boolean_columns:

    print(
        f"{column}: {int(df[column].sum())}"
    )


print()
print("=" * 60)
print("FEATURE BUILD COMPLETE")
print("=" * 60)