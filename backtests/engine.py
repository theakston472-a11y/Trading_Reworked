from core.strategy import check_rejection, find_key_area
from core.backtest_trade import create_trade, check_trade_result

from analysis.trend import get_trend
from analysis.ema import add_emas, ema_direction



def run_backtest(df):

    trades = []


    print("=" * 50)
    print("BACKTEST ENGINE")
    print("=" * 50)

    print()

    print(
        f"Candles tested : {len(df)}"
    )

    print()



    # Standardise columns

    df = df.copy()

    df.columns = [
        c.lower()
        for c in df.columns
    ]



    # Add indicators once

    df = add_emas(df)



    # Initial zones

    zones = find_key_area(
        df.iloc[:500]
    )


    print(
        f"Initial zones : {len(zones)}"
    )



    wins = 0
    losses = 0
    opens = 0

    total_r = 0



    for i in range(500, len(df)-50):


        history = df.iloc[i-100:i]

        candle = df.iloc[i]



        # refresh zones

        if i % 100 == 0:

            zones = find_key_area(
                history
            )



        trend = get_trend(
            history
        )


        ema = ema_direction(
            history
        )



        direction = None



        if (
            trend["direction"] == "bullish"
            and ema == "bullish"
        ):

            direction = "BUY"



        elif (
            trend["direction"] == "bearish"
            and ema == "bearish"
        ):

            direction = "SELL"



        if direction is None:

            continue



        for zone in zones:



            if check_rejection(
                candle,
                zone,
                direction
            ):



                trade = create_trade(
                    direction,
                    candle
                )



                outcome = check_trade_result(
                    df,
                    i,
                    trade
                )



                trade.update(
                    outcome
                )


                trades.append(
                    trade
                )



                if outcome["Result"] == "WIN":

                    wins += 1



                elif outcome["Result"] == "LOSS":

                    losses += 1



                else:

                    opens += 1



                total_r += outcome["R"]


                break



    print()

    print("=" * 50)
    print("BACKTEST RESULTS")
    print("=" * 50)

    print()

    print(
        f"Trades : {len(trades)}"
    )

    print(
        f"Wins   : {wins}"
    )

    print(
        f"Losses : {losses}"
    )

    print(
        f"Open   : {opens}"
    )



    if wins + losses > 0:

        win_rate = (
            wins /
            (wins + losses)
        ) * 100

    else:

        win_rate = 0



    print()

    print(
        f"Win Rate : {round(win_rate,2)}%"
    )

    print(
        f"Total R  : {round(total_r,2)}"
    )


    print("=" * 50)



    return trades