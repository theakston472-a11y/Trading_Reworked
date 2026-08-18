from pathlib import Path
import hashlib

BASE = Path(__file__).resolve().parents[1]

def md5(path):
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

print("Trading project audit")
print("=" * 60)
print("Base:", BASE)

py = list(BASE.rglob("*.py"))
cache = list(BASE.rglob("__pycache__"))
empty = [p for p in py if p.stat().st_size == 0]
print("Python files:", len(py))
print("__pycache__ dirs:", len(cache))
print("Empty Python files:", len(empty))

a = BASE / "quant" / "feature_database.csv"
b = BASE / "quant" / "feature_database_institutional_135.csv"
if a.exists() and b.exists():
    print("Duplicate feature DB:", md5(a) == md5(b))

print("\nReview hard-coded paths/dates in scripts manually after major changes.")
