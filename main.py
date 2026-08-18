from core.loader import load_data

from core.strategy_engine import run_strategy

from core.report import print_report

from core.trade_logger import save_trade



def main():

    print()

    print("=" * 60)
    print("STARTING TRADING SYSTEM")
    print("=" * 60)


    # Load market data
    df = load_data()


    # Run full strategy
    result = run_strategy(df)


    # Display report
    print_report(result)


    # Save trade if one exists
    save_trade(
        result["trade"]
    )



if __name__ == "__main__":

    main()