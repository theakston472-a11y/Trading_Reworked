from pathlib import Path
import re

path = Path(r"D:\Trading\Trading_Reworked\scripts\strategy_lab.py")
text = path.read_text(encoding="utf-8")

new_function = r'''def save_trade_charts(
    df: pd.DataFrame,
    final_df: pd.DataFrame,
    outdir: str,
):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    output_dir = Path(outdir)
    output_dir.mkdir(parents=True, exist_ok=True)

    work = df.copy()

    work["timestamp"] = pd.to_datetime(
        work["timestamp"],
        utc=True,
        errors="coerce",
    )

    work = (
        work
        .dropna(subset=["timestamp"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    for col in [
        "open", "high", "low", "close",
        "ema20", "ema50", "ema100", "ema200",
        "fib_382", "fib_500", "fib_618",
    ]:
        if col in work.columns:
            work[col] = pd.to_numeric(
                work[col],
                errors="coerce",
            )

    def number(value):
        try:
            value = float(value)
            return value if np.isfinite(value) else None
        except Exception:
            return None

    def boolean(value):
        if pd.isna(value):
            return False

        if isinstance(value, (bool, np.bool_)):
            return bool(value)

        return str(value).strip().lower() in {
            "true", "1", "yes", "y"
        }

    def nearest_index(value):
        try:
            stamp = pd.to_datetime(
                value,
                utc=True,
                errors="coerce",
            )

            if pd.isna(stamp):
                return None

            delta = (
                work["timestamp"] - stamp
            ).abs()

            if delta.empty:
                return None

            idx = int(delta.idxmin())

            if delta.loc[idx] > pd.Timedelta(minutes=20):
                return None

            return idx

        except Exception:
            return None

    def conditions_set(row):
        return {
            x.strip().lower()
            for x in str(
                row.get("conditions", "")
            ).split("+")
            if x.strip()
        }

    def find_anchor(
        signal_i,
        target_price,
        marker_column,
        price_column,
        lookback=100,
    ):
        if (
            marker_column not in work.columns
            or price_column not in work.columns
        ):
            return None

        start = max(
            0,
            signal_i - lookback,
        )

        candidates = []

        for i in range(start, signal_i + 1):

            if not boolean(
                work.iloc[i][marker_column]
            ):
                continue

            value = number(
                work.iloc[i][price_column]
            )

            if value is None:
                continue

            candidates.append(
                (
                    abs(value - target_price),
                    i,
                )
            )

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: item[0]
        )

        return candidates[0][1]

    for _, row in final_df.iterrows():

        trades = row.get("_detail")

        if not trades:
            continue

        conditions = conditions_set(row)

        direction = str(
            row.get("direction", "")
        ).upper()

        for trade_number, trade in enumerate(
            trades[:2],
            start=1,
        ):

            entry_i = nearest_index(
                trade.get("entry_time")
            )

            exit_i = nearest_index(
                trade.get("exit_time")
            )

            if entry_i is None:
                continue

            if exit_i is None:
                exit_i = min(
                    len(work) - 1,
                    entry_i + 12,
                )

            exit_i = max(
                entry_i,
                exit_i,
            )

            signal_i = max(
                0,
                entry_i - 1,
            )

            entry_price = number(
                trade.get("entry")
            )

            stop_price = number(
                trade.get("sl")
            )

            target_price = number(
                trade.get("tp")
            )

            if None in (
                entry_price,
                stop_price,
                target_price,
            ):
                continue

            # ==================================================
            # RECONSTRUCT THE EXACT FIB RANGE USED BY THE ENGINE
            # ==================================================

            uses_fib = any(
                "fib" in condition
                for condition in conditions
            )

            fib_info = None

            if uses_fib:

                signal_row = work.iloc[
                    signal_i
                ]

                f382 = number(
                    signal_row.get("fib_382")
                )

                f500 = number(
                    signal_row.get("fib_500")
                )

                f618 = number(
                    signal_row.get("fib_618")
                )

                fib_bullish = boolean(
                    signal_row.get("fib_bullish")
                )

                fib_bearish = boolean(
                    signal_row.get("fib_bearish")
                )

                if (
                    f382 is not None
                    and f500 is not None
                    and f618 is not None
                ):

                    # Difference between 38.2% and 61.8%
                    # is 23.6% of the full swing.
                    if fib_bullish:

                        fib_range = (
                            f382 - f618
                        ) / 0.236

                        swing_high = (
                            f382
                            + fib_range * 0.382
                        )

                        swing_low = (
                            swing_high
                            - fib_range
                        )

                    elif fib_bearish:

                        fib_range = (
                            f618 - f382
                        ) / 0.236

                        swing_low = (
                            f382
                            - fib_range * 0.382
                        )

                        swing_high = (
                            swing_low
                            + fib_range
                        )

                    else:

                        fib_range = None
                        swing_low = None
                        swing_high = None

                    if (
                        fib_range is not None
                        and fib_range > 0
                    ):

                        low_anchor_i = find_anchor(
                            signal_i,
                            swing_low,
                            "swing_low",
                            "low",
                        )

                        high_anchor_i = find_anchor(
                            signal_i,
                            swing_high,
                            "swing_high",
                            "high",
                        )

                        fib_info = {
                            "bullish": fib_bullish,
                            "bearish": fib_bearish,
                            "low": swing_low,
                            "high": swing_high,
                            "382": f382,
                            "500": f500,
                            "618": f618,
                            "low_i": low_anchor_i,
                            "high_i": high_anchor_i,
                        }

            # ==================================================
            # WINDOW
            # ==================================================

            start_i = max(
                0,
                entry_i - 18,
            )

            # Include Fib anchors where sensible.
            if fib_info:

                anchor_indices = [
                    i
                    for i in [
                        fib_info["low_i"],
                        fib_info["high_i"],
                    ]
                    if i is not None
                ]

                if anchor_indices:

                    anchor_start = min(
                        anchor_indices
                    )

                    # Don't allow hundreds of candles
                    # to destroy readability.
                    if (
                        entry_i - anchor_start
                        <= 60
                    ):
                        start_i = min(
                            start_i,
                            max(
                                0,
                                anchor_start - 3,
                            ),
                        )

            end_i = min(
                len(work) - 1,
                max(
                    exit_i + 8,
                    entry_i + 14,
                ),
            )

            chart = (
                work.iloc[
                    start_i:end_i + 1
                ]
                .copy()
                .reset_index(drop=True)
            )

            if chart.empty:
                continue

            entry_x = (
                entry_i - start_i
            )

            exit_x = (
                exit_i - start_i
            )

            # ==================================================
            # FIGURE
            # ==================================================

            fig, ax = plt.subplots(
                figsize=(18, 10),
                dpi=170,
            )

            fig.patch.set_facecolor(
                "black"
            )

            ax.set_facecolor(
                "black"
            )

            # ==================================================
            # RISK / REWARD BOXES
            # ==================================================

            box_left = (
                entry_x - 0.35
            )

            box_right = (
                exit_x + 0.45
            )

            box_width = max(
                box_right - box_left,
                1.5,
            )

            profit_low = min(
                entry_price,
                target_price,
            )

            profit_high = max(
                entry_price,
                target_price,
            )

            risk_low = min(
                entry_price,
                stop_price,
            )

            risk_high = max(
                entry_price,
                stop_price,
            )

            ax.add_patch(
                Rectangle(
                    (
                        box_left,
                        profit_low,
                    ),
                    box_width,
                    profit_high - profit_low,
                    facecolor="#168f5b",
                    edgecolor="#42d392",
                    linewidth=1.0,
                    alpha=0.18,
                    zorder=1,
                )
            )

            ax.add_patch(
                Rectangle(
                    (
                        box_left,
                        risk_low,
                    ),
                    box_width,
                    risk_high - risk_low,
                    facecolor="#9f3030",
                    edgecolor="#ff6868",
                    linewidth=1.0,
                    alpha=0.20,
                    zorder=1,
                )
            )

            # ==================================================
            # CYAN FIBONACCI
            # ==================================================

            if fib_info:

                cyan = "#00e5ff"

                fib_low = fib_info[
                    "low"
                ]

                fib_high = fib_info[
                    "high"
                ]

                fib382 = fib_info[
                    "382"
                ]

                fib500 = fib_info[
                    "500"
                ]

                fib618 = fib_info[
                    "618"
                ]

                low_anchor_i = fib_info[
                    "low_i"
                ]

                high_anchor_i = fib_info[
                    "high_i"
                ]

                if (
                    low_anchor_i is not None
                    and high_anchor_i is not None
                ):

                    low_x = (
                        low_anchor_i
                        - start_i
                    )

                    high_x = (
                        high_anchor_i
                        - start_i
                    )

                    if (
                        0 <= low_x < len(chart)
                        and
                        0 <= high_x < len(chart)
                    ):

                        # Swing anchor line
                        ax.plot(
                            [
                                low_x,
                                high_x,
                            ],
                            [
                                fib_low,
                                fib_high,
                            ],
                            color=cyan,
                            linewidth=1.4,
                            alpha=0.85,
                            zorder=4,
                        )

                        ax.scatter(
                            [
                                low_x,
                                high_x,
                            ],
                            [
                                fib_low,
                                fib_high,
                            ],
                            s=45,
                            facecolors=cyan,
                            edgecolors="black",
                            linewidths=0.7,
                            zorder=10,
                        )

                        fib_left = min(
                            low_x,
                            high_x,
                        )

                    else:

                        fib_left = 0

                else:

                    fib_left = 0

                fib_right = min(
                    len(chart) - 1,
                    entry_x + 2,
                )

                if fib_right <= fib_left:

                    fib_left = 0

                # Faint retracement rectangle
                zone_low = min(
                    fib382,
                    fib618,
                )

                zone_high = max(
                    fib382,
                    fib618,
                )

                ax.add_patch(
                    Rectangle(
                        (
                            fib_left,
                            zone_low,
                        ),
                        max(
                            fib_right - fib_left,
                            1,
                        ),
                        zone_high - zone_low,
                        facecolor=cyan,
                        edgecolor=cyan,
                        linewidth=0.7,
                        alpha=0.055,
                        zorder=2,
                    )
                )

                fib_levels = [
                    (
                        fib_high
                        if fib_info["bullish"]
                        else fib_low,
                        "0.0%",
                    ),
                    (
                        fib382,
                        "38.2%",
                    ),
                    (
                        fib500,
                        "50.0%",
                    ),
                    (
                        fib618,
                        "61.8%",
                    ),
                    (
                        fib_low
                        if fib_info["bullish"]
                        else fib_high,
                        "100%",
                    ),
                ]

                for price, label in fib_levels:

                    ax.hlines(
                        price,
                        fib_left,
                        fib_right,
                        colors=cyan,
                        linestyles="--",
                        linewidth=0.9,
                        alpha=0.65,
                        zorder=3,
                    )

                    ax.text(
                        fib_right + 0.20,
                        price,
                        (
                            f"{label}  "
                            f"{price:.5f}"
                        ),
                        color=cyan,
                        fontsize=8.5,
                        va="center",
                        zorder=9,
                    )

            # ==================================================
            # RELEVANT EMA ONLY
            # ==================================================

            for ema_column, label in [
                ("ema20", "EMA 20"),
                ("ema50", "EMA 50"),
                ("ema100", "EMA 100"),
                ("ema200", "EMA 200"),
            ]:

                if not any(
                    ema_column in condition
                    for condition in conditions
                ):
                    continue

                if ema_column not in chart.columns:
                    continue

                values = pd.to_numeric(
                    chart[ema_column],
                    errors="coerce",
                )

                ax.plot(
                    range(len(chart)),
                    values,
                    linewidth=1.1,
                    alpha=0.75,
                    label=label,
                    zorder=3,
                )

            # ==================================================
            # LIQUIDITY SWEEP — ONLY RELEVANT ONE
            # ==================================================

            for sweep_column, price_column, label in [
                (
                    "liquidity_sweep_high",
                    "high",
                    "LIQUIDITY SWEEP HIGH",
                ),
                (
                    "liquidity_sweep_low",
                    "low",
                    "LIQUIDITY SWEEP LOW",
                ),
            ]:

                if sweep_column not in conditions:
                    continue

                search_start = max(
                    0,
                    signal_i - 8,
                )

                found = None

                for i in range(
                    signal_i,
                    search_start - 1,
                    -1,
                ):

                    if boolean(
                        work.iloc[i].get(
                            sweep_column,
                            False,
                        )
                    ):

                        found = i
                        break

                if found is None:
                    continue

                local_x = (
                    found - start_i
                )

                sweep_price = number(
                    work.iloc[
                        found
                    ][price_column]
                )

                if (
                    sweep_price is None
                    or local_x < 0
                    or local_x >= len(chart)
                ):
                    continue

                left = max(
                    0,
                    local_x - 4,
                )

                right = min(
                    len(chart) - 1,
                    local_x + 4,
                )

                ax.hlines(
                    sweep_price,
                    left,
                    right,
                    colors="0.65",
                    linestyles=":",
                    linewidth=1.0,
                    alpha=0.65,
                    zorder=3,
                )

                ax.text(
                    left,
                    sweep_price,
                    " " + label,
                    color="0.65",
                    fontsize=8,
                    va=(
                        "bottom"
                        if price_column == "high"
                        else "top"
                    ),
                    zorder=5,
                )

            # ==================================================
            # CANDLES
            # ==================================================

            candle_width = 0.68

            highs = []
            lows = []

            for x, candle in chart.iterrows():

                o = number(candle["open"])
                h = number(candle["high"])
                l = number(candle["low"])
                c = number(candle["close"])

                if None in (
                    o,
                    h,
                    l,
                    c,
                ):
                    continue

                highs.append(h)
                lows.append(l)

                ax.vlines(
                    x,
                    l,
                    h,
                    color="white",
                    linewidth=1.15,
                    zorder=7,
                )

                body_low = min(
                    o,
                    c,
                )

                body_height = abs(
                    c - o
                )

                body_height = max(
                    body_height,
                    max(
                        h - l,
                        1e-8,
                    )
                    * 0.03,
                )

                bullish = (
                    c >= o
                )

                body = Rectangle(
                    (
                        x
                        - candle_width / 2,
                        body_low,
                    ),
                    candle_width,
                    body_height,
                    facecolor=(
                        "white"
                        if bullish
                        else "black"
                    ),
                    edgecolor="white",
                    linewidth=1.05,
                    zorder=8,
                )

                ax.add_patch(body)

            # ==================================================
            # ENTRY / STOP / TARGET
            # ==================================================

            ax.hlines(
                entry_price,
                box_left,
                box_right,
                colors="white",
                linewidth=1.4,
                zorder=10,
            )

            ax.hlines(
                stop_price,
                box_left,
                box_right,
                colors="#ff6868",
                linestyles="--",
                linewidth=1.2,
                zorder=10,
            )

            ax.hlines(
                target_price,
                box_left,
                box_right,
                colors="#42d392",
                linestyles="--",
                linewidth=1.2,
                zorder=10,
            )

            ax.text(
                box_right + 0.25,
                entry_price,
                f"ENTRY {entry_price:.5f}",
                color="white",
                fontsize=9,
                va="center",
                fontweight="bold",
            )

            ax.text(
                box_right + 0.25,
                stop_price,
                f"SL {stop_price:.5f}",
                color="#ff7777",
                fontsize=9,
                va="center",
                fontweight="bold",
            )

            ax.text(
                box_right + 0.25,
                target_price,
                f"TP {target_price:.5f}",
                color="#55dd99",
                fontsize=9,
                va="center",
                fontweight="bold",
            )

            # ==================================================
            # ENTRY MARKER
            # ==================================================

            if highs and lows:

                visible_range = max(
                    max(highs) - min(lows),
                    1e-8,
                )

                marker_offset = (
                    visible_range * 0.04
                )

                if direction == "BUY":

                    ax.annotate(
                        "BUY",
                        xy=(
                            entry_x,
                            entry_price,
                        ),
                        xytext=(
                            entry_x,
                            entry_price
                            - marker_offset,
                        ),
                        color="white",
                        fontsize=9,
                        fontweight="bold",
                        ha="center",
                        va="top",
                        arrowprops=dict(
                            arrowstyle="-|>",
                            color="white",
                            linewidth=1.2,
                        ),
                        zorder=13,
                    )

                else:

                    ax.annotate(
                        "SELL",
                        xy=(
                            entry_x,
                            entry_price,
                        ),
                        xytext=(
                            entry_x,
                            entry_price
                            + marker_offset,
                        ),
                        color="white",
                        fontsize=9,
                        fontweight="bold",
                        ha="center",
                        va="bottom",
                        arrowprops=dict(
                            arrowstyle="-|>",
                            color="white",
                            linewidth=1.2,
                        ),
                        zorder=13,
                    )

            # ==================================================
            # EXACT EXIT
            # ==================================================

            reason = str(
                trade.get(
                    "reason",
                    "TIME",
                )
            ).upper()

            if reason == "TP":

                displayed_exit = (
                    target_price
                )

                exit_label = (
                    f"TP HIT  +{float(row['rr']):.1f}R"
                )

                exit_color = (
                    "#55dd99"
                )

            elif reason == "SL":

                displayed_exit = (
                    stop_price
                )

                exit_label = (
                    "SL HIT  -1.00R"
                )

                exit_color = (
                    "#ff7777"
                )

            else:

                displayed_exit = number(
                    work.iloc[
                        exit_i
                    ]["close"]
                )

                result_r = number(
                    trade.get(
                        "outcome_r"
                    )
                )

                if result_r is None:
                    result_r = 0.0

                exit_label = (
                    f"TIME EXIT  "
                    f"{result_r:+.2f}R"
                )

                exit_color = (
                    "white"
                )

            if displayed_exit is not None:

                ax.scatter(
                    [exit_x],
                    [displayed_exit],
                    marker="X",
                    s=90,
                    color=exit_color,
                    edgecolors="black",
                    linewidths=0.8,
                    zorder=15,
                )

                ax.text(
                    exit_x + 0.35,
                    displayed_exit,
                    exit_label,
                    color=exit_color,
                    fontsize=9,
                    fontweight="bold",
                    va="center",
                    zorder=15,
                )

            # ==================================================
            # AXIS SCALE
            # ==================================================

            y_values = (
                highs
                + lows
                + [
                    entry_price,
                    stop_price,
                    target_price,
                ]
            )

            if fib_info:

                y_values.extend(
                    [
                        fib_info["low"],
                        fib_info["high"],
                    ]
                )

            y_min = min(y_values)
            y_max = max(y_values)

            y_range = max(
                y_max - y_min,
                1e-8,
            )

            ax.set_ylim(
                y_min - y_range * 0.07,
                y_max + y_range * 0.07,
            )

            ax.set_xlim(
                -1,
                len(chart) + 5,
            )

            # ==================================================
            # TIME LABELS
            # ==================================================

            tick_count = min(
                9,
                len(chart),
            )

            if tick_count > 1:

                positions = np.linspace(
                    0,
                    len(chart) - 1,
                    tick_count,
                    dtype=int,
                )

                labels = [
                    chart.iloc[
                        i
                    ]["timestamp"].strftime(
                        "%d %b\n%H:%M"
                    )
                    for i in positions
                ]

                ax.set_xticks(
                    positions
                )

                ax.set_xticklabels(
                    labels,
                    fontsize=8,
                    color="0.75",
                )

            ax.grid(
                True,
                linestyle=":",
                linewidth=0.55,
                alpha=0.10,
                color="white",
            )

            ax.tick_params(
                axis="y",
                colors="0.75",
                labelsize=9,
            )

            ax.tick_params(
                axis="x",
                colors="0.75",
            )

            ax.spines["top"].set_visible(
                False
            )

            ax.spines["right"].set_visible(
                False
            )

            ax.spines["left"].set_color(
                "0.30"
            )

            ax.spines["bottom"].set_color(
                "0.30"
            )

            ax.set_ylabel(
                "PRICE",
                color="0.70",
                fontsize=9,
            )

            # ==================================================
            # TITLE
            # ==================================================

            rank_value = int(
                row.get(
                    "rank",
                    0,
                )
            )

            rr_value = float(
                row.get(
                    "rr",
                    0,
                )
            )

            result_r = number(
                trade.get(
                    "outcome_r"
                )
            )

            if result_r is None:
                result_r = 0.0

            ax.set_title(
                (
                    f"RANK {rank_value}  |  "
                    f"{direction}  |  "
                    f"{row.get('session', '')}  |  "
                    f"RR {rr_value:.1f}\n"
                    f"{row.get('conditions', '')}  |  "
                    f"TRADE {trade_number}  |  "
                    f"{reason}  |  "
                    f"{result_r:+.2f}R"
                ),
                loc="left",
                color="white",
                fontsize=13.5,
                fontweight="bold",
                pad=14,
            )

            # ==================================================
            # INFO BOX
            # ==================================================

            info = (
                f"Entry: {entry_price:.5f}\n"
                f"Stop: {stop_price:.5f}\n"
                f"Target: {target_price:.5f}\n"
                f"RR: {rr_value:.1f}\n"
                f"Result: {result_r:+.2f}R"
            )

            ax.text(
                0.985,
                0.975,
                info,
                transform=ax.transAxes,
                ha="right",
                va="top",
                color="white",
                fontsize=9,
                bbox=dict(
                    boxstyle="round,pad=0.5",
                    facecolor="black",
                    edgecolor="0.35",
                    alpha=0.88,
                ),
                zorder=20,
            )

            handles, labels = (
                ax.get_legend_handles_labels()
            )

            if handles:

                legend = ax.legend(
                    handles,
                    labels,
                    loc="upper left",
                    frameon=False,
                    fontsize=8,
                )

                for item in legend.get_texts():

                    item.set_color(
                        "0.75"
                    )

            fig.subplots_adjust(
                left=0.07,
                right=0.90,
                top=0.88,
                bottom=0.10,
            )

            filename = (
                f"rank_"
                f"{rank_value:03d}"
                f"_trade_"
                f"{trade_number}.png"
            )

            fig.savefig(
                output_dir / filename,
                dpi=170,
                facecolor="black",
                edgecolor="none",
            )

            plt.close(fig)

    print(
        f"Trade charts saved to: {output_dir}"
    )
'''

pattern = re.compile(
    r"def save_trade_charts\(.*?(?=# ============================================================\n# MAIN)",
    re.S,
)

match = pattern.search(text)

if not match:
    raise SystemExit(
        "Could not find save_trade_charts() section."
    )

new_text = (
    text[:match.start()]
    + new_function
    + "\n\n"
    + text[match.end():]
)

path.write_text(
    new_text,
    encoding="utf-8",
)

print("Updated:", path)
