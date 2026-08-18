from core.loader import load_data

from backtests.engine import run_backtest


from research.collector import (
    attach_features,
    save_research
)


from research.analyzer import (
    print_analysis
)


from research.combinations import (
    test_combinations
)


from research.direction_test import (
    test_direction
)


from research.confluence_search import (
    search_confluences
)


from research.optimizer import (
    optimize_strategy
)


from research.validation import (
    run_validation
)


from research.walk_forward import (
    run_walk_forward
)



print("=" * 50)
print("BACKTEST TEST")
print("=" * 50)



df = load_data()



trades = run_backtest(
    df
)



print()

print("=" * 50)
print("COLLECTING RESEARCH DATA")
print("=" * 50)



research_trades = attach_features(
    df,
    trades
)



save_research(
    research_trades
)



print()

print_analysis(
    research_trades
)



print()

print("=" * 50)
print("COMBINATION SEARCH")
print("=" * 50)



test_combinations()



print()

print("=" * 50)
print("DIRECTION SEARCH")
print("=" * 50)



test_direction()



print()

print("=" * 50)
print("CONFLUENCE SEARCH")
print("=" * 50)



search_confluences()



print()

print("=" * 50)
print("OPTIMIZER SEARCH")
print("=" * 50)



optimize_strategy()



print()

print("=" * 50)
print("VALIDATION")
print("=" * 50)



run_validation()



print()

print("=" * 50)
print("WALK FORWARD")
print("=" * 50)



run_walk_forward()



print()

print("=" * 50)
print("RESULT")
print("=" * 50)



print(
    f"Trades generated : {len(trades)}"
)



print("=" * 50)