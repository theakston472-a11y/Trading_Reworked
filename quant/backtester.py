import pandas as pd
import numpy as np

DEFAULT_RISK_REWARD = 2.0
DEFAULT_MAX_BARS = 48
DEFAULT_RISK_PERCENT = 1.0


def normalise_session(value):

    if pd.isna(value):
        return "Unknown"

    value = str(value).strip().lower()

    if "london" in value:
        return "London"

    if "new york" in value:
        return "New York"

    if "new_york" in value:
        return "New York"

    if value == "ny":
        return "New York"

    if "asia" in value:
        return "Asia"

    if "asian" in value:
        return "Asia"

    if "tokyo" in value:
        return "Asia"

    return str(value)


def condition_matches(row, conditions):

    for column, expected in conditions.items():

        if column not in row.index:
            return False

        actual = row[column]

        if isinstance(expected, bool):

            if bool(actual) != expected:
                return False

        elif isinstance(expected, str):

            if str(actual).lower() != expected.lower():
                return False

        else:

            try:
                if float(actual) != float(expected):
                    return False
            except Exception:
                return False

    return True


def calculate_stop_distance(
    row,
    stop_mode="atr",
    stop_multiplier=1.0
):

    if stop_mode == "atr":

        if "atr14" not in row.index:
            return None

        atr = float(row["atr14"])

        if not np.isfinite(atr) or atr <= 0:
            return None

        return atr * stop_multiplier

    if stop_mode == "range":

        candle_range = (
            float(row["high"])
            -
            float(row["low"])
        )

        if candle_range <= 0:
            return None

        return candle_range * stop_multiplier

    return None


def simulate_trade(
    df,
    entry_index,
    direction,
    stop_distance,
    risk_reward=DEFAULT_RISK_REWARD,
    max_bars=DEFAULT_MAX_BARS
):

    if entry_index + 1 >= len(df):
        return None

    entry_index = entry_index + 1

    entry_price = float(
        df["open"].iloc[entry_index]
    )

    stop_distance = abs(
        float(stop_distance)
    )

    if (
        not np.isfinite(stop_distance)
        or stop_distance <= 0
    ):
        return None

    target_distance = (
        stop_distance
        *
        risk_reward
    )

    if direction == "BUY":

        stop_price = (
            entry_price
            -
            stop_distance
        )

        target_price = (
            entry_price
            +
            target_distance
        )

    else:

        stop_price = (
            entry_price
            +
            stop_distance
        )

        target_price = (
            entry_price
            -
            target_distance
        )

    final_index = min(
        len(df) - 1,
        entry_index + max_bars
    )

    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values

    for i in range(
        entry_index,
        final_index + 1
    ):

        high = float(highs[i])
        low = float(lows[i])

        if direction == "BUY":

            hit_stop = (
                low <= stop_price
            )

            hit_target = (
                high >= target_price
            )

            if hit_stop:

                return {
                    "result": "LOSS",
                    "r": -1.0,
                    "exit_price": stop_price,
                    "exit_index": i,
                    "bars_held":
                        i - entry_index + 1
                }

            if hit_target:

                return {
                    "result": "WIN",
                    "r": risk_reward,
                    "exit_price": target_price,
                    "exit_index": i,
                    "bars_held":
                        i - entry_index + 1
                }

        else:

            hit_stop = (
                high >= stop_price
            )

            hit_target = (
                low <= target_price
            )

            if hit_stop:

                return {
                    "result": "LOSS",
                    "r": -1.0,
                    "exit_price": stop_price,
                    "exit_index": i,
                    "bars_held":
                        i - entry_index + 1
                }

            if hit_target:

                return {
                    "result": "WIN",
                    "r": risk_reward,
                    "exit_price": target_price,
                    "exit_index": i,
                    "bars_held":
                        i - entry_index + 1
                }

    final_close = float(
        closes[final_index]
    )

    if direction == "BUY":

        pnl_distance = (
            final_close
            -
            entry_price
        )

    else:

        pnl_distance = (
            entry_price
            -
            final_close
        )

    r = (
        pnl_distance
        /
        stop_distance
    )

    return {
        "result": "TIMEOUT",
        "r": r,
        "exit_price": final_close,
        "exit_index": final_index,
        "bars_held":
            final_index
            -
            entry_index
            +
            1
    }


def _safe_bool_mask(
    values,
):
    series = pd.Series(
        values
    )

    if pd.api.types.is_bool_dtype(
        series
    ):

        return (
            series
            .fillna(False)
            .to_numpy(
                dtype=bool
            )
        )

    if pd.api.types.is_numeric_dtype(
        series
    ):

        return (
            pd.to_numeric(
                series,
                errors="coerce",
            )
            .fillna(0)
            .astype(bool)
            .to_numpy()
        )

    return (
        series
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
        .isin(
            {
                "true",
                "1",
                "yes",
                "y",
                "on",
            }
        )
        .to_numpy()
    )


def _fib_ratios_from_condition_dict(
    conditions,
):

    found = []

    names = [
        str(
            key
        ).lower()
        for key, expected
        in conditions.items()
        if expected is not False
    ]

    for ratio in (
        382,
        500,
        618,
    ):

        token = (
            f"fib_{ratio}"
        )

        if any(
            token in name
            for name in names
        ):
            found.append(
                ratio
            )

    return found


def _resolve_backtester_entry(
    data,
    signal_i,
    conditions,
    entry_mode,
    entry_wait_bars,
):

    mode = str(
        entry_mode
    ).strip().lower()

    fib_entry = None

    ratios = _fib_ratios_from_condition_dict(
        conditions
    )

    if ratios:

        ratio = max(
            ratios
        )

        column = (
            f"fib_{ratio}"
        )

        if column in data.columns:

            try:

                price = float(
                    data.iloc[
                        signal_i
                    ][column]
                )

            except Exception:

                price = np.nan

            if np.isfinite(
                price
            ):

                fib_entry = {
                    "price": price,
                    "ratio": ratio,
                    "label": (
                        f"FIB "
                        f"{ratio / 10.0:.1f}%"
                    ),
                }

    if mode == "auto":

        mode = (
            "fib_touch"
            if fib_entry is not None
            else "next_open"
        )

    if mode == "signal_close":

        price = float(
            data.iloc[
                signal_i
            ]["close"]
        )

        if not np.isfinite(
            price
        ):
            return None

        return {
            "entry_index": signal_i,
            "entry_price": price,
            "outcome_start_index": (
                signal_i + 1
            ),
            "entry_mode": "signal_close",
            "entry_level": "SIGNAL CLOSE",
            "entry_level_ratio": None,
        }

    if mode == "fib_touch":

        if fib_entry is None:
            return None

        level = float(
            fib_entry[
                "price"
            ]
        )

        first_i = (
            signal_i + 1
        )

        last_i = min(
            len(data) - 1,
            signal_i
            + max(
                int(
                    entry_wait_bars
                ),
                1,
            ),
        )

        for entry_index in range(
            first_i,
            last_i + 1,
        ):

            low = float(
                data.iloc[
                    entry_index
                ]["low"]
            )

            high = float(
                data.iloc[
                    entry_index
                ]["high"]
            )

            if (
                np.isfinite(
                    low
                )
                and np.isfinite(
                    high
                )
                and low
                <= level
                <= high
            ):

                return {
                    "entry_index": entry_index,
                    "entry_price": level,
                    "outcome_start_index": entry_index,
                    "entry_mode": "fib_touch",
                    "entry_level": fib_entry[
                        "label"
                    ],
                    "entry_level_ratio": fib_entry[
                        "ratio"
                    ],
                }

        return None

    entry_index = (
        signal_i + 1
    )

    if entry_index >= len(
        data
    ):
        return None

    entry_price = float(
        data.iloc[
            entry_index
        ]["open"]
    )

    if not np.isfinite(
        entry_price
    ):
        return None

    return {
        "entry_index": entry_index,
        "entry_price": entry_price,
        "outcome_start_index": entry_index,
        "entry_mode": "next_open",
        "entry_level": "NEXT OPEN",
        "entry_level_ratio": None,
    }


def backtest_strategy(
    df,
    conditions,
    direction="BUY",
    risk_reward=2.0,
    stop_mode="atr",
    stop_multiplier=1.0,
    max_bars=48,
    session=None,
    entry_mode="auto",
    entry_wait_bars=6,
    max_open=5,
):

    if df is None or df.empty:

        empty = pd.DataFrame()

        return {
            "trades": empty,
            "stats":
                calculate_statistics(
                    empty
                )
        }

    required_columns = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
    ]

    if stop_mode == "atr":

        required_columns.append(
            "atr14"
        )

    for column in required_columns:

        if column not in df.columns:

            raise ValueError(
                "Missing required column: "
                + column
            )

    data = (
        df.copy()
        .reset_index(
            drop=True
        )
    )

    if not pd.api.types.is_datetime64_any_dtype(
        data["timestamp"]
    ):

        data["timestamp"] = pd.to_datetime(
            data["timestamp"],
            errors="coerce",
        )

    for column in conditions.keys():

        if column not in data.columns:

            empty = pd.DataFrame()

            return {
                "trades": empty,
                "stats":
                    calculate_statistics(
                        empty
                    )
            }

    mask = np.ones(
        len(data),
        dtype=bool,
    )

    for column, expected in conditions.items():

        values = data[
            column
        ]

        if isinstance(
            expected,
            bool,
        ):

            parsed = _safe_bool_mask(
                values
            )

            if expected:

                mask &= parsed

            else:

                mask &= ~parsed

        elif isinstance(
            expected,
            str,
        ):

            mask &= (
                values
                .fillna("")
                .astype(str)
                .str.strip()
                .str.lower()
                .to_numpy()
                ==
                expected
                .strip()
                .lower()
            )

        else:

            numeric_values = pd.to_numeric(
                values,
                errors="coerce",
            ).to_numpy()

            try:

                target = float(
                    expected
                )

                mask &= (
                    numeric_values
                    == target
                )

            except Exception:

                mask &= False

    # DIRECTIONAL FIB GATE V9
    #
    # Keep generic Fib strategies aligned with the
    # requested direction here as well.
    fib_requested = any(
        "fib" in str(column).lower()
        for column in conditions.keys()
    )

    if fib_requested:

        fib_direction_col = (
            "fib_bullish"
            if str(direction).upper().strip() == "BUY"
            else "fib_bearish"
        )

        if fib_direction_col not in data.columns:

            empty = pd.DataFrame()

            return {
                "trades": empty,
                "stats": calculate_statistics(
                    empty
                ),
            }

        mask &= _safe_bool_mask(
            data[fib_direction_col]
        )

    if session is not None:

        if "session" not in data.columns:

            empty = pd.DataFrame()

            return {
                "trades": empty,
                "stats":
                    calculate_statistics(
                        empty
                    )
            }

        target_session = normalise_session(
            session
        ).lower()

        session_mask = (
            data["session"]
            .fillna("Unknown")
            .astype(str)
            .map(
                normalise_session
            )
            .str.lower()
            .to_numpy()
            ==
            target_session
        )

        mask &= (
            session_mask
        )

    signal_indices = np.flatnonzero(
        mask
    )

    if len(
        signal_indices
    ) == 0:

        empty = pd.DataFrame()

        return {
            "trades": empty,
            "stats":
                calculate_statistics(
                    empty
                )
        }

    trades = []

    highs = data[
        "high"
    ].to_numpy(
        dtype=float
    )

    lows = data[
        "low"
    ].to_numpy(
        dtype=float
    )

    closes = data[
        "close"
    ].to_numpy(
        dtype=float
    )

    timestamps = data[
        "timestamp"
    ].to_numpy()

    if stop_mode == "atr":

        atr_values = data[
            "atr14"
        ].to_numpy(
            dtype=float
        )

    active_exits = []

    direction = (
        str(
            direction
        )
        .upper()
        .strip()
    )

    for signal_i in signal_indices:

        signal_i = int(
            signal_i
        )

        resolved = _resolve_backtester_entry(
            data,
            signal_i,
            conditions,
            entry_mode,
            entry_wait_bars,
        )

        if resolved is None:
            continue

        entry_index = int(
            resolved[
                "entry_index"
            ]
        )

        outcome_start_index = int(
            resolved[
                "outcome_start_index"
            ]
        )

        if (
            entry_index >= len(
                data
            )
            or outcome_start_index
            >= len(
                data
            )
        ):
            continue

        active_exits = [
            exit_index
            for exit_index
            in active_exits
            if exit_index
            >= entry_index
        ]

        if len(
            active_exits
        ) >= int(
            max_open
        ):
            continue

        signal_range = abs(
            float(
                highs[
                    signal_i
                ]
            )
            - float(
                lows[
                    signal_i
                ]
            )
        )

        if stop_mode == "atr":

            atr_distance = float(
                atr_values[
                    signal_i
                ]
            )

            if np.isfinite(
                atr_distance
            ):

                stop_distance = max(
                    atr_distance,
                    signal_range,
                )

            else:

                stop_distance = (
                    signal_range
                )

            stop_distance *= float(
                stop_multiplier
            )

        else:

            stop_distance = (
                signal_range
                * float(
                    stop_multiplier
                )
            )

        if (
            not np.isfinite(
                stop_distance
            )
            or stop_distance <= 0
        ):
            continue

        entry_price = float(
            resolved[
                "entry_price"
            ]
        )

        target_distance = (
            stop_distance
            * risk_reward
        )

        if direction == "BUY":

            stop_price = (
                entry_price
                - stop_distance
            )

            target_price = (
                entry_price
                + target_distance
            )

        else:

            stop_price = (
                entry_price
                + stop_distance
            )

            target_price = (
                entry_price
                - target_distance
            )

        final_index = min(
            len(data) - 1,
            outcome_start_index
            + max_bars - 1,
        )

        result = None

        for j in range(
            outcome_start_index,
            final_index + 1,
        ):

            high = float(
                highs[
                    j
                ]
            )

            low = float(
                lows[
                    j
                ]
            )

            if direction == "BUY":

                hit_stop = (
                    low <= stop_price
                )

                hit_target = (
                    high >= target_price
                )

            else:

                hit_stop = (
                    high >= stop_price
                )

                hit_target = (
                    low <= target_price
                )

            # Conservative same-candle ambiguity rule.
            if hit_stop:

                result = {
                    "result": "LOSS",
                    "r": -1.0,
                    "exit_price":
                        stop_price,
                    "exit_index": j,
                    "bars_held":
                        j
                        - entry_index
                        + 1,
                }

                break

            if hit_target:

                result = {
                    "result": "WIN",
                    "r":
                        risk_reward,
                    "exit_price":
                        target_price,
                    "exit_index": j,
                    "bars_held":
                        j
                        - entry_index
                        + 1,
                }

                break

        if result is None:

            final_close = float(
                closes[
                    final_index
                ]
            )

            if direction == "BUY":

                pnl_distance = (
                    final_close
                    - entry_price
                )

            else:

                pnl_distance = (
                    entry_price
                    - final_close
                )

            result = {
                "result": "TIMEOUT",
                "r":
                    pnl_distance
                    / stop_distance,
                "exit_price":
                    final_close,
                "exit_index":
                    final_index,
                "bars_held":
                    final_index
                    - entry_index
                    + 1,
            }

        active_exits.append(
            int(
                result[
                    "exit_index"
                ]
            )
        )

        signal_session = (
            "Unknown"
        )

        if "session" in data.columns:

            signal_session = normalise_session(
                data[
                    "session"
                ].iloc[
                    signal_i
                ]
            )

        trades.append(
            {
                "signal_time":
                    timestamps[
                        signal_i
                    ],
                "entry_time":
                    timestamps[
                        entry_index
                    ],
                "exit_time":
                    timestamps[
                        int(
                            result[
                                "exit_index"
                            ]
                        )
                    ],
                "direction":
                    direction,
                "session":
                    signal_session,
                "entry":
                    entry_price,
                "stop":
                    stop_price,
                "target":
                    target_price,
                "stop_distance":
                    stop_distance,
                "entry_mode":
                    resolved[
                        "entry_mode"
                    ],
                "entry_level":
                    resolved[
                        "entry_level"
                    ],
                "entry_level_ratio":
                    resolved[
                        "entry_level_ratio"
                    ],
                "result":
                    result[
                        "result"
                    ],
                "r":
                    result[
                        "r"
                    ],
                "exit_price":
                    result[
                        "exit_price"
                    ],
                "bars_held":
                    result[
                        "bars_held"
                    ],
            }
        )

    trades_df = pd.DataFrame(
        trades
    )

    return {
        "trades":
            trades_df,
        "stats":
            calculate_statistics(
                trades_df
            )
    }

def calculate_statistics(
    trades
):

    if (
        trades is None
        or trades.empty
    ):

        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "net_r": 0.0,
            "average_r": 0.0,
            "max_drawdown_r": 0.0,
            "average_win_r": 0.0,
            "average_loss_r": 0.0,
            "expectancy_r": 0.0
        }

    r_values = (
        trades["r"]
        .astype(float)
        .values
    )

    wins = r_values[
        r_values > 0
    ]

    losses = r_values[
        r_values < 0
    ]

    trade_count = len(
        r_values
    )

    win_count = len(
        wins
    )

    loss_count = len(
        losses
    )

    win_rate = (
        win_count
        /
        trade_count
        *
        100
    )

    gross_profit = (
        wins.sum()
        if len(wins)
        else 0.0
    )

    gross_loss = abs(
        losses.sum()
    ) if len(losses) else 0.0

    if gross_loss > 0:

        profit_factor = (
            gross_profit
            /
            gross_loss
        )

    else:

        profit_factor = 999.0

    net_r = r_values.sum()

    average_r = r_values.mean()

    average_win = (
        wins.mean()
        if len(wins)
        else 0.0
    )

    average_loss = (
        losses.mean()
        if len(losses)
        else 0.0
    )

    win_probability = (
        win_count
        /
        trade_count
    )

    loss_probability = (
        loss_count
        /
        trade_count
    )

    expectancy = (
        win_probability
        *
        average_win
    ) + (
        loss_probability
        *
        average_loss
    )

    equity = np.cumsum(
        r_values
    )

    running_max = np.maximum.accumulate(
        equity
    )

    drawdown = (
        equity
        -
        running_max
    )

    max_drawdown = abs(
        drawdown.min()
    )

    return {

        "trades":
            trade_count,

        "wins":
            win_count,

        "losses":
            loss_count,

        "win_rate":
            round(
                win_rate,
                2
            ),

        "profit_factor":
            round(
                profit_factor,
                3
            ),

        "net_r":
            round(
                net_r,
                3
            ),

        "average_r":
            round(
                average_r,
                4
            ),

        "max_drawdown_r":
            round(
                max_drawdown,
                3
            ),

        "average_win_r":
            round(
                average_win,
                3
            ),

        "average_loss_r":
            round(
                average_loss,
                3
            ),

        "expectancy_r":
            round(
                expectancy,
                4
            )
    }


def session_breakdown(
    trades
):

    if (
        trades is None
        or trades.empty
    ):

        return pd.DataFrame()

    rows = []

    for session, group in trades.groupby(
        "session"
    ):

        stats = calculate_statistics(
            group
        )

        rows.append({

            "session":
                session,

            **stats

        })

    return pd.DataFrame(
        rows
    )


def direction_breakdown(
    trades
):

    if (
        trades is None
        or trades.empty
    ):

        return pd.DataFrame()

    rows = []

    for direction, group in trades.groupby(
        "direction"
    ):

        stats = calculate_statistics(
            group
        )

        rows.append({

            "direction":
                direction,

            **stats

        })

    return pd.DataFrame(
        rows
    )


if __name__ == "__main__":

    print("=" * 60)
    print("QUANT BACKTESTER")
    print("=" * 60)
    print()
    print("Optimised backtester ready.")
    print()
    print("This module does not place live trades.")
    print("It only tests historical data.")
    print()