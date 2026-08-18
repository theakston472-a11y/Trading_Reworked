import sqlite3

p = r".\results\strategy_registry.sqlite"
c = sqlite3.connect(p)

print("DISCOVERY COUNTS")
print("=" * 60)

rows = c.execute("""
    SELECT session, direction, COUNT(*)
    FROM discoveries
    GROUP BY session, direction
    ORDER BY session, direction
""").fetchall()

for row in rows:
    print(f"{row[0]:12} {row[1]:6} {row[2]:6} strategies")

print()
print("TOTAL:", c.execute("SELECT COUNT(*) FROM discoveries").fetchone()[0])

c.close()