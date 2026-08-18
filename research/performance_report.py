import pandas as pd


def performance_report(
    filename="research/results.csv"
):

    print()
    print("=" * 50)
    print("PERFORMANCE REPORT")
    print("=" * 50)


    df = pd.read_csv(
        filename
    )


    print()

    print("BASIC RESULTS")
    print("-" * 50)


    trades = len(df)

    wins = (
        df["Result"]
        ==
        "WIN"
    ).sum()


    losses = (
        df["Result"]
        ==
        "LOSS"
    ).sum()


    total_r = (
        df["R"]
        .sum()
    )


    win_rate = (
        wins
        /
        trades
        *
        100
    )


    print(
        f"Trades: {trades}"
    )

    print(
        f"Wins: {wins}"
    )

    print(
        f"Losses: {losses}"
    )

    print(
        f"Win Rate: {win_rate:.2f}%"
    )

    print(
        f"Total R: {total_r}"
    )


    print()

    print("=" * 50)
    print("EXPECTANCY")
    print("=" * 50)


    expectancy = (
        total_r
        /
        trades
    )


    print(
        f"Expectancy per trade: {expectancy:.3f}R"
    )


    print()

    print("=" * 50)
    print("PROFIT FACTOR")
    print("=" * 50)


    gross_profit = (
        df[
            df["R"] > 0
        ]["R"]
        .sum()
    )


    gross_loss = abs(
        df[
            df["R"] < 0
        ]["R"]
        .sum()
    )


    if gross_loss != 0:

        profit_factor = (
            gross_profit
            /
            gross_loss
        )

    else:

        profit_factor = 0


    print(
        f"Gross Profit: {gross_profit}"
    )

    print(
        f"Gross Loss: {gross_loss}"
    )

    print(
        f"Profit Factor: {profit_factor:.2f}"
    )


    print()

    print("=" * 50)
    print("DRAWDOWN")
    print("=" * 50)


    equity = (
        df["R"]
        .cumsum()
    )


    high = (
        equity
        .cummax()
    )


    drawdown = (
        equity
        -
        high
    )


    max_dd = (
        drawdown
        .min()
    )


    print(
        f"Maximum Drawdown: {max_dd}R"
    )


    print()

    print("=" * 50)
    print("CONSECUTIVE LOSSES")
    print("=" * 50)


    max_losses = 0

    current = 0


    for result in df["Result"]:


        if result == "LOSS":

            current += 1


            if current > max_losses:

                max_losses = current


        else:

            current = 0



    print(
        f"Maximum losing streak: {max_losses}"
    )


    print()

    print("=" * 50)
    print("MONTHLY RESULTS")
    print("=" * 50)


    if "Date" in df.columns:


        df["Date"] = pd.to_datetime(
            df["Date"]
        )


        monthly = (

            df

            .groupby(
                df["Date"]
                .dt
                .to_period("M")
            )

            ["R"]

            .sum()

        )


        print(
            monthly
        )


    else:

        print(
            "No Date column found"
        )


    print()

    print("=" * 50)
    print("BEST/WORST GROUPS")
    print("=" * 50)


    for column in [
        "Session",
        "Day",
        "Direction"
    ]:


        if column in df.columns:


            print()

            print(
                column
            )


            print(

                df

                .groupby(column)

                ["R"]

                .sum()

                .sort_values(
                    ascending=False
                )

            )



    print()

    print(
        "Report complete"
    )



if __name__ == "__main__":

    performance_report()