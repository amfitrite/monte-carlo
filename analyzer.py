"""
Dual Auto Analyzer for XAUUSD.

Manual Monte Carlo evaluates a user-supplied Entry/SL/TP.
Dual Auto Analyzer does the inverse: it searches a candidate grid for BUY LIMIT
and SELL LIMIT setups, ranks candidates by simulated expectancy, then evaluates
the selected candidates with the chosen Monte Carlo engine.

Important limitation: historical OHLC touch rates are only a fill proxy. They do
not model queue priority, bid/ask execution, liquidity, or guaranteed fills.
"""
import numpy as np
import timemachine
import engine_v2


def _valid_bars(bars):
    clean = []
    for bar in bars:
        try:
            ts = float(bar["timestamp"])
            o, h, l, c = (float(bar[k]) for k in ("open", "high", "low", "close"))
            if ts > 0 and min(o, h, l, c) > 0 and l <= min(o, c) <= max(o, c) <= h:
                clean.append({"timestamp": ts, "open": o, "high": h, "low": l, "close": c})
        except (KeyError, TypeError, ValueError):
            continue
    clean.sort(key=lambda x: x["timestamp"])
    # Drop duplicate timestamps, keeping the last valid record.
    by_time = {b["timestamp"]: b for b in clean}
    return [by_time[t] for t in sorted(by_time)]


def calculate_market_metrics(bars, period=48):
    """Calculate recent ATR and structural extremes using only supplied history."""
    if len(bars) < 20:
        raise ValueError("At least 20 valid bars are required to calculate market structure.")
    recent = bars[-min(len(bars), max(20, int(period))):]
    highs = np.asarray([b["high"] for b in recent], dtype=float)
    lows = np.asarray([b["low"] for b in recent], dtype=float)
    closes = np.asarray([b["close"] for b in recent], dtype=float)
    prev = np.asarray([b["close"] for b in recent[:-1]], dtype=float)
    tr = np.maximum(highs[1:] - lows[1:],
                    np.maximum(np.abs(highs[1:] - prev), np.abs(lows[1:] - prev)))
    atr = float(np.mean(tr)) if len(tr) else float(np.mean(highs - lows))
    if not np.isfinite(atr) or atr <= 0:
        raise ValueError("ATR could not be calculated from the supplied OHLC history.")
    return {
        "atr": atr,
        "swing_high": float(np.max(highs)),
        "swing_low": float(np.min(lows)),
        "current_price": float(closes[-1]),
        "structure_range": float(np.max(highs) - np.min(lows)),
        "lookback_bars": len(recent)
    }


def _candidate_entries(side, metrics):
    """Build a compact set of limit prices around ATR pullbacks and swing structure."""
    cur, atr = metrics["current_price"], metrics["atr"]
    lo, hi = metrics["swing_low"], metrics["swing_high"]
    span = max(hi - lo, atr)
    if side == "buy":
        raw = [cur - atr * x for x in (0.25, 0.40, 0.60, 0.80, 1.0)]
        raw += [lo + span * x for x in (0.15, 0.25, 0.35)]
        valid = [x for x in raw if cur - 2.0 * atr <= x <= cur - 0.10 * atr]
    else:
        raw = [cur + atr * x for x in (0.25, 0.40, 0.60, 0.80, 1.0)]
        raw += [hi - span * x for x in (0.15, 0.25, 0.35)]
        valid = [x for x in raw if cur + 0.10 * atr <= x <= cur + 2.0 * atr]
    # Round to cents, de-duplicate and keep candidates ordered nearest to market first.
    valid = sorted(set(round(float(x), 2) for x in valid),
                   key=lambda x: abs(x - cur))
    if not valid:
        valid = [round(cur - 0.5 * atr, 2) if side == "buy"
                 else round(cur + 0.5 * atr, 2)]
    return valid[:5]



def _estimate_entry_touch(bars, side, entry_distance_atr, horizon_bars,
                          atr_period=14, max_samples=500):
    """Estimate historical price-touch frequency for the same ATR-normalized limit distance.

    This is a touch proxy, not an exchange/broker fill probability. It assumes a
    touch of the OHLC extreme is sufficient and cannot model queue priority.
    """
    n = len(bars)
    horizon = max(1, int(horizon_bars))
    period = max(2, int(atr_period))
    if n <= period + horizon:
        return {
            "touch_probability_pct": 0.0, "touches": 0, "samples": 0,
            "median_bars_to_touch": None, "distance_atr": float(entry_distance_atr)
        }

    highs = np.asarray([b["high"] for b in bars], dtype=float)
    lows = np.asarray([b["low"] for b in bars], dtype=float)
    closes = np.asarray([b["close"] for b in bars], dtype=float)
    prev = np.r_[closes[0], closes[:-1]]
    true_ranges = np.maximum(highs - lows,
        np.maximum(np.abs(highs - prev), np.abs(lows - prev)))

    # Use historical anchor bars with a complete, strictly forward observation window.
    indices = np.arange(period - 1, n - horizon - 1, dtype=int)
    if len(indices) > max_samples:
        pick = np.linspace(0, len(indices) - 1, max_samples, dtype=int)
        indices = indices[pick]

    touched_times = []
    for idx in indices:
        atr = float(np.mean(true_ranges[idx - period + 1:idx + 1]))
        if not np.isfinite(atr) or atr <= 0:
            continue
        anchor = closes[idx]
        if side == "buy":
            limit_level = anchor - float(entry_distance_atr) * atr
            future = np.flatnonzero(lows[idx + 1:idx + 1 + horizon] <= limit_level)
        else:
            limit_level = anchor + float(entry_distance_atr) * atr
            future = np.flatnonzero(highs[idx + 1:idx + 1 + horizon] >= limit_level)
        if len(future):
            touched_times.append(int(future[0]) + 1)

    samples = len(indices)
    touches = len(touched_times)
    # Beta(1,1) smoothing avoids reporting exact 0% or 100% from a small sample.
    probability = (touches + 1.0) / (samples + 2.0) if samples else 0.0
    return {
        "touch_probability_pct": probability * 100.0,
        "touches": touches,
        "samples": samples,
        "median_bars_to_touch": (
            float(np.median(touched_times)) if touched_times else None
        ),
        "distance_atr": float(entry_distance_atr)
    }


def _build_plan(side, entry, metrics, risk_atr, rr, interval_minutes):
    atr = metrics["atr"]
    if side == "buy":
        structural_risk = max(0.0, entry - metrics["swing_low"]) + 0.10 * atr
        risk = max(atr * risk_atr, structural_risk)
        stop, target = entry - risk, entry + risk * rr
    else:
        structural_risk = max(0.0, metrics["swing_high"] - entry) + 0.10 * atr
        risk = max(atr * risk_atr, structural_risk)
        stop, target = entry + risk, entry - risk * rr
    return {
        "entry_price": round(entry, 2),
        "stop_loss": round(stop, 2),
        "take_profit": round(target, 2),
        "side": side,
        "risk_atr": float(risk_atr),
        "target_rr": float(rr),
        "interval_minutes": int(interval_minutes)
    }


def _run_one(plan, bars_data, horizon_bars, replays, spread, seed,
             projection_mode, tie_break, seasonality, engine_mode):
    common = dict(
        entry_price=plan["entry_price"], stop_loss=plan["stop_loss"],
        take_profit=plan["take_profit"], side=plan["side"],
        horizon_bars=horizon_bars, replays=replays, spread=spread,
        seed=seed, bars_data=bars_data
    )
    if engine_mode == "v2":
        return engine_v2.run_simulation(**common)
    return timemachine.run_simulation(
        **common, projection_mode=projection_mode,
        tie_break=tie_break, seasonality=seasonality
    )


def _rank_score(result, touch_stats):
    odds = result["odds"]
    # Expected R is conditional on entry. Weight it by historical touch frequency
    # to penalize attractive-looking limits that are rarely reached in the horizon.
    touch_rate = float(touch_stats["touch_probability_pct"]) / 100.0
    adjusted_r = float(odds["avg_r"]) * touch_rate
    return (adjusted_r, touch_rate, float(odds["avg_r"]),
            float(odds["target_first_pct"]), float(result["plan"]["target_r"]))


def _scan_side(side, metrics, bars_data, horizon_bars, search_replays, spread,
               seed, projection_mode, tie_break, seasonality, engine_mode):
    interval = int(bars_data.get("interval_minutes", 5) or 5)
    entries = _candidate_entries(side, metrics)
    risk_multipliers = (0.80, 1.10)
    rr_values = (1.50, 2.0)
    candidates = []
    index = 0
    for entry in entries:
        for risk_atr in risk_multipliers:
            for rr in rr_values:
                plan = _build_plan(side, entry, metrics, risk_atr, rr, interval)
                result = _run_one(
                    plan, bars_data, horizon_bars, search_replays, spread,
                    seed + index, projection_mode, tie_break, seasonality, engine_mode
                )
                distance_atr = abs(metrics["current_price"] - entry) / metrics["atr"]
                touch = _estimate_entry_touch(
                    bars_data["bars"], side, distance_atr, horizon_bars
                )
                candidates.append((_rank_score(result, touch), plan, result, touch))
                index += 1
    candidates.sort(key=lambda x: x[0], reverse=True)
    if not candidates:
        raise ValueError(f"No valid {side.upper()} LIMIT candidates could be generated.")
    return candidates[0], len(candidates)


def _finalize_recommendation(side, selected, candidate_count, bars_data,
                             metrics, horizon_bars, replays, spread, seed,
                             projection_mode, tie_break, seasonality, engine_mode):
    _, plan, coarse, touch = selected
    # Re-run the winning candidate at the requested replay count.
    primary_mode = "legacy" if engine_mode == "compare" else engine_mode
    result = _run_one(
        plan, bars_data, horizon_bars, replays, spread, seed + (101 if side == "buy" else 202),
        projection_mode, tie_break, seasonality, primary_mode
    )
    if engine_mode == "compare":
        v2 = _run_one(
            plan, bars_data, horizon_bars, replays, spread,
            seed + (101 if side == "buy" else 202),
            projection_mode, tie_break, seasonality, "v2"
        )
        result["comparison"] = {
            "engine": "Enhanced V2",
            "target_first_pct": v2["odds"]["target_first_pct"],
            "stop_first_pct": v2["odds"]["stop_first_pct"],
            "neither_pct": v2["odds"]["neither_pct"],
            "avg_r": v2["odds"]["avg_r"],
            "ambiguous_pct": v2["odds"].get("ambiguous_pct", 0.0),
            "optimistic_target_first_pct": v2["odds"].get("optimistic_target_first_pct", 0.0)
        }
    result["plan"]["order_type"] = "LIMIT"
    result["plan"]["candidate_count_scanned"] = candidate_count
    result["plan"]["candidate_search_replays"] = int(coarse["plan"]["replays"])
    result["plan"]["entry_fill_probability"] = None
    result["plan"]["entry_fill_assumption"] = (
        "Conditional on the proposed limit order being filled; OHLC scan does not estimate fill probability."
    )
    result["recommendation"] = {
        "status": "candidate" if result["odds"]["avg_r"] > 0 else "no_positive_expectancy",
        "ranking_metric": "touch_adjusted_simulated_average_R",
        "simulated_average_R": result["odds"]["avg_r"],
        "touch_adjusted_simulated_average_R": adjusted_r,
        "target_first_probability_pct": result["odds"]["target_first_pct"],
        "breakeven_probability_pct": result["odds"]["breakeven_pct"],
        "fill_probability": None,
        "historical_touch_probability_pct": result["plan"]["entry_touch_probability_pct"],
        "historical_touch_samples": result["plan"]["entry_touch_samples"],
        "median_bars_to_touch": result["plan"]["median_bars_to_touch"],
        "warning": "Touch rate is a historical OHLC proxy, not actual fill probability. TP/SL odds are conditional on fill and are not live calibrated."
    }
    return result


def find_dual_recommendations(
    bars_data, horizon_bars=48, replays=5000, spread=0.24, seed=19,
    projection_mode="free_drift", tie_break="smart", seasonality=False,
    engine_mode="legacy"
):
    """
    Search and rank multiple BUY LIMIT and SELL LIMIT candidates.

    The candidate scan uses a lower replay count for speed, then re-runs each
    selected side's best candidate at the requested replay count. Compare mode
    selects candidates using Legacy V1 and evaluates the same final plans with V2.
    """
    if engine_mode not in ("legacy", "v2", "compare"):
        raise ValueError("engine_mode must be 'legacy', 'v2', or 'compare'.")
    bars = _valid_bars((bars_data or {}).get("bars", []))
    if len(bars) < 200:
        raise ValueError("Dual Auto Analyzer requires at least 200 valid chronological OHLC bars.")
    normalized = dict(bars_data)
    normalized["bars"] = bars
    if "interval_minutes" not in normalized:
        delta = bars[-1]["timestamp"] - bars[-2]["timestamp"]
        normalized["interval_minutes"] = 1 if delta <= 120 else max(1, int(round(delta / 60)))
    metrics = calculate_market_metrics(bars, period=min(len(bars), max(48, horizon_bars)))
    interval = int(normalized.get("interval_minutes", 5) or 5)
    metrics["interval_minutes"] = interval

    horizon_bars = max(1, int(horizon_bars))
    replays = max(100, int(replays))
    search_replays = min(replays, 600)
    primary_mode = "legacy" if engine_mode == "compare" else engine_mode

    buy_selected, buy_count = _scan_side(
        "buy", metrics, normalized, horizon_bars, search_replays, spread, seed,
        projection_mode, tie_break, seasonality, primary_mode
    )
    sell_selected, sell_count = _scan_side(
        "sell", metrics, normalized, horizon_bars, search_replays, spread, seed + 1000,
        projection_mode, tie_break, seasonality, primary_mode
    )
    buy_res = _finalize_recommendation(
        "buy", buy_selected, buy_count, normalized, metrics, horizon_bars,
        replays, spread, seed, projection_mode, tie_break, seasonality, engine_mode
    )
    sell_res = _finalize_recommendation(
        "sell", sell_selected, sell_count, normalized, metrics, horizon_bars,
        replays, spread, seed, projection_mode, tie_break, seasonality, engine_mode
    )

    buy_r = float(buy_res["plan"]["fill_adjusted_simulated_avg_r"])
    sell_r = float(sell_res["plan"]["fill_adjusted_simulated_avg_r"])
    viable_buy, viable_sell = buy_r > 0, sell_r > 0
    if not viable_buy and not viable_sell:
        best_dir = "NO TRADE"
        summary = (
            f"Belum ada setup BUY/SELL dengan simulated expectancy positif "
            f"(BUY {buy_r:+.2f}R; SELL {sell_r:+.2f}R). Tidak ada rekomendasi entry aktif."
        )
    elif viable_buy and viable_sell and abs(buy_r - sell_r) < 0.03:
        best_dir = "EQUAL"
        summary = (
            f"BUY dan SELL sama-sama memiliki simulated expectancy positif dan relatif seimbang "
            f"(BUY {buy_r:+.2f}R; SELL {sell_r:+.2f}R). Tunggu konfirmasi kondisi pasar."
        )
    elif viable_buy and (not viable_sell or buy_r > sell_r):
        best_dir = "BUY"
        summary = f"BUY LIMIT menjadi kandidat teratas ({buy_r:+.2f}R vs SELL {sell_r:+.2f}R)."
    else:
        best_dir = "SELL"
        summary = f"SELL LIMIT menjadi kandidat teratas ({sell_r:+.2f}R vs BUY {buy_r:+.2f}R)."

    if engine_mode == "compare":
        summary += (
            f" V2 pada setup yang sama: BUY {buy_res['comparison']['avg_r']:+.2f}R; "
            f"SELL {sell_res['comparison']['avg_r']:+.2f}R."
        )
    summary += (
        " Touch rate berasal dari frekuensi sentuhan level pada OHLC historis; "
        "bukan jaminan order terisi atau probabilitas fill broker."
    )
    return {
        "metrics": metrics,
        "best_direction": best_dir,
        "summary": summary,
        "engine_mode": engine_mode,
        "search": {
            "method": "ATR pullback + recent swing-structure candidate grid",
            "buy_candidates_scanned": buy_count,
            "sell_candidates_scanned": sell_count,
            "search_replays_per_candidate": search_replays,
            "final_replays": replays,
            "ranking": "simulated average R; target probability and RR are secondary descriptors",
            "fill_model": "not_estimated"
        },
        "buy": buy_res,
        "sell": sell_res
    }


if __name__ == "__main__":
    try:
        bars_data = timemachine.get_gold_bars(source="mt5")
    except Exception:
        bars_data = timemachine.get_gold_bars(source="comex")
    result = find_dual_recommendations(bars_data, horizon_bars=48, replays=3000)
    print("Dual Auto Analyzer:", result["best_direction"])
    print(result["summary"])
    for label in ("buy", "sell"):
        r = result[label]
        p, o = r["plan"], r["odds"]
        print(f"{label.upper()} LIMIT: Entry {p['entry']} | SL {p['stop']} | TP {p['target']} | "
              f"TP-first {o['target_first_pct']:.1f}% | Avg R {o['avg_r']:+.2f}R")
