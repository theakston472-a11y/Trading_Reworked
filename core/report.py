def print_report(result):

    print()
    print("=" * 60)
    print("TRADING RESEARCH PLATFORM")
    print("=" * 60)


    print()

    print("MARKET STATE")
    print("-" * 40)

    print(
        f"Price        : {result['price']:.5f}"
    )

    print(
        f"Trend        : {result['trend']}"
    )

    print(
        f"EMA          : {result['ema']}"
    )

    print(
        f"EMA Position : {result['ema_position']}"
    )



    decision = result["decision"]


    print()

    print("DECISION")
    print("-" * 40)

    print(
        f"Signal : {decision['decision']}"
    )

    print(
        f"Score  : {decision['score']}/100"
    )

    print(
        f"Bias   : {decision['bias']}"
    )


    print()

    print("REASONS")

    for reason in decision["reasons"]:

        print(
            f"- {reason}"
        )



    trade = result["trade"]


    if trade:


        print()

        print("=" * 60)
        print("TRADE PLAN")
        print("=" * 60)


        print(
            f"Direction : {trade['direction']}"
        )

        print(
            f"Entry     : {trade['entry']:.5f}"
        )

        print(
            f"Stop      : {trade['stop']:.5f}"
        )

        print(
            f"Target    : {trade['target']:.5f}"
        )

        print(
            f"Lots      : {trade['lots']}"
        )

        print(
            f"R:R       : 2"
        )


    else:

        print()

        print("No trade plan generated")



    print()

    print("=" * 60)