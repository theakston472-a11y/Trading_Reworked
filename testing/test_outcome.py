from core.loader import load_data

from core.outcome import update_trade_history



print("=" * 50)
print("TRADE OUTCOME TEST")
print("=" * 50)



df = load_data()



update_trade_history(df)



print()

print("Trade history updated")

print("=" * 50)