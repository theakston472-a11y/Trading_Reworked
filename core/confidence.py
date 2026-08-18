def calculate_confidence(
    in_zone=False,
    near_entry=False,
    rejection=False,
    trend=False,
    impulse=False,
):
    """
    Returns:
        score (0-100)
        decision
    """

    score = 0

    if in_zone:
        score += 30

    if near_entry:
        score += 20

    if rejection:
        score += 20

    if trend:
        score += 15

    if impulse:
        score += 15

    if score >= 80:
        decision = "BUY / SELL"

    elif score >= 60:
        decision = "WATCH"

    else:
        decision = "WAIT"

    return {
        "score": score,
        "decision": decision,
    }