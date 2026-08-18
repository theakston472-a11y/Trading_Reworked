def evaluate_trade(
    zone,
    entry,
    rejection,
    trend,
    ema,
    price
):
    """
    Final trade decision engine.
    """

    score = 0
    reasons = []


    # -------------------------
    # SCORE CONDITIONS
    # -------------------------

    if zone:
        score += 25
        reasons.append("Inside key zone")


    if entry:
        score += 20
        reasons.append("At entry level")


    if rejection:
        score += 25
        reasons.append("Rejection confirmed")


    if trend == ema:
        score += 15
        reasons.append("Trend aligned")


    if ema in ["bullish", "bearish"]:
        score += 15
        reasons.append("EMA aligned")



    # -------------------------
    # MARKET BIAS
    # -------------------------

    if trend == "bearish" and ema == "bearish":
        bias = "SELL"

    elif trend == "bullish" and ema == "bullish":
        bias = "BUY"

    else:
        bias = "NO TRADE"



    # -------------------------
    # DECISION
    # -------------------------

    if score >= 80:
        decision = "TAKE TRADE"

    elif score >= 60:
        decision = "WATCH"

    else:
        decision = "WAIT"



    # -------------------------
    # TRADE PLAN
    # -------------------------

    trade = None


    if bias == "SELL" and zone and entry:

        stop = zone["high"]

        risk = stop - entry


        target = entry - (risk * 2)


        trade = {

            "direction": "SELL",

            "entry": round(entry,5),

            "stop": round(stop,5),

            "target": round(target,5),

            "risk_reward": 2

        }



    elif bias == "BUY" and zone and entry:

        stop = zone["low"]

        risk = entry - stop


        target = entry + (risk * 2)


        trade = {

            "direction": "BUY",

            "entry": round(entry,5),

            "stop": round(stop,5),

            "target": round(target,5),

            "risk_reward": 2

        }



    return {

        "score": score,

        "decision": decision,

        "bias": bias,

        "reasons": reasons,

        "trade": trade

    }