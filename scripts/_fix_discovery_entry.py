from pathlib import Path

path = Path(r"D:\Trading\Trading_Reworked\scripts\strategy_discovery.py")
text = path.read_text(encoding="utf-8")

# ------------------------------------------------------------
# Add discovery engine / entry defaults
# ------------------------------------------------------------

old = '''DEFAULT_DIRECTION = "SELL"
DEFAULT_SESSION = "New York"
'''

new = '''DEFAULT_DIRECTION = "SELL"
DEFAULT_SESSION = "New York"
DEFAULT_ENTRY_MODE = "auto"
DEFAULT_ENTRY_WAIT_BARS = 6
DISCOVERY_ENGINE_VERSION = "2026-08-14-v3-corrected-swings-fib-touch"
'''

if old in text:
    text = text.replace(old, new, 1)

# ------------------------------------------------------------
# Add entry arguments
# ------------------------------------------------------------

old = '''    parser.add_argument(
        "--retest",
        action="store_true",
        help=(
'''

new = '''    parser.add_argument(
        "--entry-mode",
        default=DEFAULT_ENTRY_MODE,
        choices=["auto", "next_open", "signal_close", "fib_touch"],
        help="Entry model used during discovery",
    )

    parser.add_argument(
        "--entry-wait-bars",
        type=int,
        default=DEFAULT_ENTRY_WAIT_BARS,
        help="Maximum bars to wait for a Fib-touch entry",
    )

    parser.add_argument(
        "--retest",
        action="store_true",
        help=(
'''

if old not in text:
    raise SystemExit("Could not find parser insertion point.")

text = text.replace(old, new, 1)

# ------------------------------------------------------------
# Correct strategy fingerprint so different entry models
# cannot share old cached discovery IDs
# ------------------------------------------------------------

start = text.index("def strategy_fingerprint(")

end = text.index(
    "# ============================================================\n# REGISTRY",
    start,
)

replacement = '''def strategy_fingerprint(
    direction,
    session,
    conditions,
    rr,
    entry_mode="auto",
    entry_wait_bars=6,
):
    canonical = canonical_conditions(
        conditions
    )

    text = (
        f"{str(direction).upper().strip()}|"
        f"{str(session).lower().strip()}|"
        f"{canonical.lower()}|"
        f"{float(rr):.4f}|"
        f"{str(entry_mode).lower().strip()}|"
        f"{int(entry_wait_bars)}"
    )

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


'''

text = (
    text[:start]
    + replacement
    + text[end:]
)

path.write_text(
    text,
    encoding="utf-8",
)

print("Discovery entry fix installed.")
