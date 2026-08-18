import os
import pandas as pd
import config


def load_data():
    """
    Loads and validates historical market data.
    Returns a cleaned pandas DataFrame.
    """

    print("=" * 50)
    print("Trading Research Platform")
    print("=" * 50)

    print("\nLoading data...\n")

    # -----------------------------
    # Check file exists
    # -----------------------------

    if not os.path.exists(config.DATA_FILE):
        raise FileNotFoundError(
            f"Data file not found:\n{config.DATA_FILE}"
        )

    print("✓ Data file found")

    # -----------------------------
    # Load CSV
    # -----------------------------

    df = pd.read_csv(config.DATA_FILE)

    # -----------------------------
    # Validate columns
    # -----------------------------

    required = [
        "timestamp",
        "open",
        "high",
        "low",
        "close"
    ]

    for column in required:
        if column not in df.columns:
            raise ValueError(f"Missing column: {column}")

    print("✓ Required columns found")

    # -----------------------------
    # Convert timestamp
    # -----------------------------

    df["Date"] = pd.to_datetime(
        df["timestamp"],
        unit="ms"
    )

    df = df.set_index("Date")

    # -----------------------------
    # Rename columns
    # -----------------------------

    df = df.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close"
        }
    )

    # -----------------------------
    # Keep only price columns
    # -----------------------------

    df = df[
        [
            "Open",
            "High",
            "Low",
            "Close"
        ]
    ]

    # -----------------------------
    # Remove duplicate timestamps
    # -----------------------------

    duplicates = df.index.duplicated().sum()

    df = df[~df.index.duplicated(keep="first")]

    # -----------------------------
    # Sort dates
    # -----------------------------

    df = df.sort_index()

    # -----------------------------
    # Missing values
    # -----------------------------

    missing = df.isna().sum().sum()

    print("✓ Data cleaned\n")

    print(f"Pair:        {config.PAIR}")
    print(f"Timeframe:   {config.TIMEFRAME}")
    print(f"Candles:     {len(df):,}")
    print(f"Start Date:  {df.index.min()}")
    print(f"End Date:    {df.index.max()}")
    print(f"Missing:     {missing}")
    print(f"Duplicates:  {duplicates}")

    print("\nStatus: READY")

    print("=" * 50)

    return df


if __name__ == "__main__":
    load_data()