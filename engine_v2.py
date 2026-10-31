"""
Enhanced OHLC Monte Carlo engine (V2).

Uses contiguous historical return blocks to retain short-run serial dependence.
When OHLC bars touch both stop and target, V2 records the collision as ambiguous:
the primary estimate resolves it conservatively (stop first), while an optimistic
upper bound is reported separately. OHLC cannot reveal the true intrabar order.
This is a scenario simulator, not a walk-forward accuracy claim.
"""
import datetime
import numpy as np


def _interval_minutes(bars, supplied=None):
    if supplied:
        return int(supplied)
    if len(bars) > 1:
        delta = abs(float(bars[1]["timestamp"]) - float(bars[0]["timestamp"]))
        return 1 if delta <= 120 else max(1, int(round(delta / 60)))
    return 5


def _ratios(bars):
    rows = []
    for i in range(1, len(bars)):
        prev = float(bars[i - 1]["close"])
        bar = bars[i]
        if prev <= 0:
            continue
        o, h, l, c = (float(bar[k]) / prev for k in ("open", "high", "low", "close"))
        if 0 < l <= min(o, c) <= max(o, c) <= h and 0.90 < l <= h < 1.10:
            rows.append((o, h, l, c))
    if len(rows) < 50:
        raise ValueError("V2 requires at least 50 valid sequential OHLC returns.")
    return np.asarray(rows, dtype=np.float64)


def _bootstrap_indices(n, horizon, replays, block_length, rng):
    out = np.empty((replays, horizon), dtype=np.int32)
    blocks = (horizon + block_length - 1) // block_length
    for r in range(replays):
        cursor = 0
        for _ in range(blocks):
            start = int(rng.integers(0, n - block_length + 1))
            take = min(block_length, horizon - cursor, n - start)
            out[r, cursor:cursor + take] = np.arange(start, start + take)
            cursor += take
            if cursor >= horizon:
                break
        # A short final segment at the end of the source is filled with a new block.
        while cursor < horizon:
            start = int(rng.integers(0, n))
            take = min(block_length, horizon - cursor, n - start)
            out[r, cursor:cursor + take] = np.arange(start, start + take)
            cursor += take
    return out


def run_simulation(entry_price, stop_loss, take_profit, side="buy",
                   horizon_bars=48, replays=5000, seed=19, spread=0.25,
                   bars_data=None, block_length=10, **kwargs):
    side = str(side).lower().strip()
    if side not in ("buy", "sell"):
        raise ValueError("side must be 'buy' or 'sell'")
    entry_price, stop_loss, take_profit = map(float, (entry_price, stop_loss, take_profit))
    horizon_bars, replays = int(horizon_bars), int(replays)
    spread, block_length = max(0.0, float(spread)), max(2, int(block_length))
    risk = abs(entry_price - stop_loss)
    reward = abs(take_profit - entry_price)
    if risk <= 0 or reward <= 0 or horizon_bars < 1 or replays < 100:
        raise ValueError("Invalid risk/reward, horizon, or replay count.")
    if bars_data is None:
        raise ValueError("bars_data is required for Enhanced V2.")
    bars = bars_data.get("bars", [])
    if len(bars) < 200:
        raise ValueError("V2 requires at least 200 historical OHLC bars.")

    ratios = _ratios(bars)
    rng = np.random.default_rng(seed)
    indices = _bootstrap_indices(len(ratios), horizon_bars, replays, min(block_length, len(ratios)), rng)
    sampled = ratios[indices]
    market = np.full(replays, entry_price, dtype=np.float64)
    active = np.ones(replays, dtype=bool)
    result = np.zeros(replays, dtype=np.int8)
    exits = np.full(replays, entry_price, dtype=np.float64)
    ambiguous = np.zeros(replays, dtype=bool)
    fan = {"step_bars": [0], "interval_minutes": _interval_minutes(bars, bars_data.get("interval_minutes")),
           "p5": [entry_price], "p25": [entry_price], "p50": [entry_price],
           "p75": [entry_price], "p95": [entry_price]}
    sample_ids = np.linspace(0, replays - 1, min(12, replays), dtype=int)
    paths = [[entry_price] for _ in sample_ids]
    checkpoints = set(np.linspace(0, horizon_bars - 1, min(horizon_bars, 120), dtype=int).tolist())

    for step in range(horizon_bars):
        row = sampled[:, step, :]
        o, h, l, c = row[:, 0], row[:, 1], row[:, 2], row[:, 3]
        high, low = market * h, market * l
        close = market * c
        if side == "buy":
            hit_sl = (low <= stop_loss) & active
            hit_tp = (high >= take_profit + spread) & active
        else:
            hit_sl = (high + spread >= stop_loss) & active
            hit_tp = (low <= take_profit) & active
        both = hit_sl & hit_tp
        ambiguous |= both
        # Conservative primary outcome: ambiguous OHLC bars count as stop-first.
        hit_tp &= ~both
        market = close
        result[hit_sl] = -1
        result[hit_tp] = 1
        exits[hit_sl] = stop_loss
        exits[hit_tp] = take_profit
        active[hit_sl | hit_tp] = False
        exits[active] = market[active]
        if step in checkpoints or step == horizon_bars - 1:
            for j, idx in enumerate(sample_ids):
                paths[j].append(float(market[idx]))
            vals = np.percentile(market, [5, 25, 50, 75, 95])
            fan["step_bars"].append(step + 1)
            for key, val in zip(("p5", "p25", "p50", "p75", "p95"), vals):
                fan[key].append(float(val))

    # Optimistic collision bound: each ambiguous path is counted as TP instead of SL.
    wins = int(np.sum(result == 1))
    losses = int(np.sum(result == -1))
    open_count = int(np.sum(result == 0))
    optimistic_wins = wins + int(np.sum(ambiguous))
    optimistic_losses = max(0, losses - int(np.sum(ambiguous)))
    target_r = reward / risk
    r = np.zeros(replays, dtype=np.float64)
    r[result == 1] = target_r
    r[result == -1] = -1.0
    floating = result == 0
    r[floating] = ((exits[floating] - entry_price) / risk if side == "buy"
                  else (entry_price - exits[floating]) / risk)
    interval = fan["interval_minutes"]
    win_rate = wins / replays * 100.0
    resolved = wins + losses
    return {
        "plan": {"symbol": "XAUUSD (Gold)", "side": side.upper(), "entry": entry_price,
                 "stop": stop_loss, "target": take_profit, "risk_dollar": risk,
                 "reward_dollar": reward, "target_r": target_r, "horizon_bars": horizon_bars,
                 "horizon_hours": horizon_bars * interval / 60, "interval_minutes": interval,
                 "projection_mode": "block_bootstrap", "tie_break": "conservative_ambiguous",
                 "replays": replays, "seed": seed, "spread": spread, "block_length": block_length},
        "meta": {"interval_minutes": interval, "projection_mode": "block_bootstrap",
                 "tie_break": "conservative_ambiguous", "horizon_bars": horizon_bars,
                 "horizon_hours": horizon_bars * interval / 60, "engine": "Enhanced V2"},
        "odds": {"target_first_pct": round(win_rate, 1),
                 "stop_first_pct": round(losses / replays * 100.0, 1),
                 "neither_pct": round(open_count / replays * 100.0, 1),
                 "green_pct": round(float(np.mean(r > 0)) * 100.0, 1),
                 "win_rate_on_resolved": round(wins / resolved * 100.0, 1) if resolved else 0.0,
                 "breakeven_pct": round(100.0 / (1.0 + target_r), 1),
                 "avg_r": round(float(np.mean(r)), 3),
                 "median_terminal_price": round(float(np.median(exits)), 2),
                 "p5_terminal": round(float(np.percentile(exits, 5)), 2),
                 "p95_terminal": round(float(np.percentile(exits, 95)), 2),
                 "ambiguous_pct": round(float(np.mean(ambiguous)) * 100.0, 2),
                 "optimistic_target_first_pct": round(optimistic_wins / replays * 100.0, 1),
                 "optimistic_stop_first_pct": round(optimistic_losses / replays * 100.0, 1)},
        "verdict": ("Positive simulated expectancy; validate out-of-sample." if np.mean(r) > 0
                    else "Non-positive simulated expectancy; do not treat as a trading edge."),
        "verdict_notes": ["Ambiguous same-bar TP/SL collisions are counted as SL in the primary estimate.",
                          "Optimistic collision bound is shown separately; OHLC cannot identify intrabar order.",
                          "Block bootstrap preserves local sequence only within sampled blocks.",
                          "Simulation is not walk-forward validation or a calibrated live win probability."],
        "fan_data": fan, "sample_paths": paths
    }
