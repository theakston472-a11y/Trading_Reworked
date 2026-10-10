# Public SMC guide feature map

Source reviewed: `https://www.mql5.com/en/blogs/post/769000`

The source describes a commercial indicator's concepts and settings, but does
not publish its source code or exact thresholds.  This project therefore uses
explicit, independently implemented definitions.  All signals are calculated
from the current or already-closed candles; confirmed swings are emitted only
after their right-hand confirmation bars have closed.

| Guide concept | Project implementation |
| --- | --- |
| Internal trend, BOS and CHoCH | Existing structure engine, exposed with `internal_*` names |
| Swing trend, BOS and CHoCH | Five-bar-radius confirmed swing structure (`swing_*`) |
| Strong/weak highs and lows | Trend-labelled confirmed swing points |
| Internal order/breaker blocks | Existing structure-confirmed blocks, exposed as `*_internal_*` |
| Swing order/breaker blocks | Opposite candle before confirmed swing break plus displacement; failure becomes breaker |
| Equal highs/lows | Existing equal-level and sweep features |
| BSL/SSL | Last confirmed swing high/low, proximity and sweep features |
| Fair value gaps | Existing three-candle FVG, displacement, mitigation and retest logic |
| Inverse FVG | Original FVG invalidated by a closing-price break, then tracked for retest |
| Implied FVG | Large rejection-wick imbalance with ATR and close-location filters |
| Balanced price range | Overlap of opposing active FVGs, with zone, fill and retest state |
| Liquidity void | Three strong same-direction candles, limited overlap and at least two ATR displacement |
| BMS-filtered liquidity void | Liquidity void accompanied by a recent BOS/CHoCH |
| Opening gap | Session/day discontinuity above an ATR threshold, with fill/retest state |
| Premium/discount/equilibrium | Position relative to the midpoint of the active confirmed Fib swing range |
| OTE | Directional 62%-79% retracement zone plus the 70.5% midpoint |
| Multi-timeframe imbalance | Closed H1/H4 FVG, implied FVG, inverse FVG and BPR state |
| Higher-timeframe OHLC | Current-day running OHLC and previous day/week/month OHLC and sweeps |
| Sessions | DST-aware Sydney, Tokyo, Frankfurt, London and New York windows |
| Kill zones and overlap | DST-aware London/New York kill zones and London-New York overlap |
| Silver Bullet | New York 10:00-11:00 local-time candidate requiring sweep, FVG/OB interaction and structure confluence |
| Alerts | Existing paper-bot signal, pending-entry, entry, close and health email path |

Display-only settings such as colors, opacity, font size and historical drawing
limits are intentionally not treated as strategy conditions.  Discovery and
Strategy Lab engine versions were advanced so old cached results cannot be
mistaken for tests of these definitions.
