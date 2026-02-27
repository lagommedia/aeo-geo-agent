from statistics import mean, pstdev


def _moving_average(values: list[float], window: int) -> float:
    if not values:
        return 0.0
    if len(values) < window:
        return mean(values)
    return mean(values[-window:])


def detect_rising_query(timeseries: list[dict], short_window: int = 7, long_window: int = 28) -> tuple[float, str]:
    impressions = [point.get("impressions", 0.0) for point in timeseries]
    if len(impressions) < 5:
        return 0.0, "Insufficient history"

    short_ma = _moving_average(impressions, short_window)
    long_ma = _moving_average(impressions, long_window)
    ratio = short_ma / long_ma if long_ma > 0 else 0.0
    base_std = pstdev(impressions[:-short_window] or impressions) or 1.0
    z_score = (short_ma - long_ma) / base_std
    trend_score = max(0.0, min(40.0, (ratio * 12) + (z_score * 6)))
    reason = f"short_ma={short_ma:.1f}, long_ma={long_ma:.1f}, ratio={ratio:.2f}, z={z_score:.2f}"
    return trend_score, reason


def detect_refresh_need(timeseries: list[dict]) -> tuple[bool, str]:
    # Uses true 28/56 day windows when daily data exists, and a 4/8 period fallback
    # for weekly MVP sample datasets.
    if len(timeseries) >= 56:
        recent = timeseries[-28:]
        baseline = timeseries[-56:-28]
    elif len(timeseries) >= 8:
        recent = timeseries[-4:]
        baseline = timeseries[-8:-4]
    else:
        return False, "Insufficient 56-day history"

    recent_position = mean([p.get("position", 0) for p in recent])
    baseline_position = mean([p.get("position", 0) for p in baseline])
    recent_ctr = mean([p.get("ctr", 0) for p in recent])
    baseline_ctr = mean([p.get("ctr", 0) for p in baseline])

    rank_decline = recent_position - baseline_position
    ctr_drop = baseline_ctr - recent_ctr
    refresh_needed = rank_decline > 1.2 and ctr_drop > 0.01
    reason = f"rank_delta={rank_decline:.2f}, ctr_delta={ctr_drop:.3f}"
    return refresh_needed, reason
