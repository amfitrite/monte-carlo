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

MAX_TPSL_COMBINATIONS = 20
MAX_CANDIDATES_PER_SIDE = 100


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
    # Snap levels to the configured price-point size when known.
    price_step = float(metrics.get("price_step", 0.01) or 0.01)
    valid = sorted(set(_round_to_step(float(x), price_step) for x in valid),
                   key=lambda x: abs(x - cur))
    if not valid:
        fallback = cur - 0.5 * atr if side == "buy" else cur + 0.5 * atr
        valid = [_round_to_step(fallback, price_step)]
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
    price_step = float(metrics.get("price_step", 0.01) or 0.01)
    return {
        "entry_price": _round_to_step(entry, price_step),
        "stop_loss": _round_to_step(stop, price_step),
        "take_profit": _round_to_step(target, price_step),
        "side": side,
        "risk_atr": float(risk_atr),
        "target_rr": float(rr),
        "interval_minutes": int(interval_minutes)
    }


def _price_precision(step):
    text = format(float(step), ".12f").rstrip("0").rstrip(".")
    return len(text.split(".", 1)[1]) if "." in text else 0


def _round_to_step(price, step):
    step = float(step)
    if not np.isfinite(step) or step <= 0:
        raise ValueError("point_size must be a finite positive number.")
    return round(round(float(price) / step) * step, _price_precision(step))


def _build_point_plan(side, entry, tp_points, sl_points, point_size, interval_minutes):
    """Build a fixed-distance plan; points are converted using price per point."""
    tp_points, sl_points = int(tp_points), int(sl_points)
    point_size = float(point_size)
    if tp_points <= 0 or sl_points <= 0 or point_size <= 0:
        raise ValueError("TP points, SL points, and point_size must all be positive.")
    entry = _round_to_step(entry, point_size)
    tp_distance, sl_distance = tp_points * point_size, sl_points * point_size
    if side == "buy":
        stop, target = entry - sl_distance, entry + tp_distance
    elif side == "sell":
        stop, target = entry + sl_distance, entry - tp_distance
    else:
        raise ValueError("side must be 'buy' or 'sell'.")
    if stop <= 0 or target <= 0:
        raise ValueError("Configured TP/SL points produce a non-positive price level.")
    return {
        "entry_price": entry,
        "stop_loss": _round_to_step(stop, point_size),
        "take_profit": _round_to_step(target, point_size),
        "side": side,
        "target_rr": float(tp_points) / float(sl_points),
        "tp_points": tp_points,
        "sl_points": sl_points,
        "point_size": point_size,
        "interval_minutes": int(interval_minutes)
    }


def _positive_integer(value, name):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a positive whole number.")
    if not np.isfinite(number) or number <= 0 or not number.is_integer():
        raise ValueError(f"{name} must be a positive whole number.")
    return int(number)


def _normalize_tpsl_config(mode, bars_data, point_size=None,
                           fixed_tp_points=2000, fixed_sl_points=1000,
                           tp_min_points=1000, tp_max_points=5000, tp_step_points=500,
                           sl_min_points=500, sl_max_points=2000, sl_step_points=250,
                           rr_ratio=2.0, rr_sl_points=1000):
    mode = str(mode or "auto").strip().lower()
    if mode in ("risk reward", "risk_reward", "rr"):
        mode = "risk_reward"
    if mode not in ("auto", "fixed", "range", "risk_reward"):
        raise ValueError("tpsl_mode must be 'auto', 'fixed', 'range', or 'risk_reward'.")
    if mode == "auto":
        return {"mode": "auto"}

    if point_size in (None, ""):
        point_size = (bars_data or {}).get("point_size")
    try:
        point_size = float(point_size)
    except (TypeError, ValueError):
        raise ValueError(
            "A valid point_size is required for Fixed TP/SL, TP/SL Range, and Risk Reward. "
            "Set it to the broker's price value for one point."
        )
    if not np.isfinite(point_size) or point_size <= 0:
        raise ValueError("point_size must be a finite positive price value.")

    if mode == "fixed":
        return {
            "mode": "fixed",
            "point_size": point_size,
            "tp_points": _positive_integer(fixed_tp_points, "fixed_tp_points"),
            "sl_points": _positive_integer(fixed_sl_points, "fixed_sl_points")
        }

    if mode == "risk_reward":
        try:
            ratio = float(rr_ratio)
        except (TypeError, ValueError):
            raise ValueError("rr_ratio must be a positive number.")
        if not np.isfinite(ratio) or ratio <= 0:
            raise ValueError("rr_ratio must be a positive number.")
        sl_pts = _positive_integer(rr_sl_points, "rr_sl_points")
        tp_pts = max(1, int(round(sl_pts * ratio)))
        return {
            "mode": "risk_reward",
            "point_size": point_size,
            "rr_ratio": ratio,
            "sl_points": sl_pts,
            "tp_points": tp_pts
        }

    tp_min = _positive_integer(tp_min_points, "tp_min_points")
    tp_max = _positive_integer(tp_max_points, "tp_max_points")
    tp_step = _positive_integer(tp_step_points, "tp_step_points")
    sl_min = _positive_integer(sl_min_points, "sl_min_points")
    sl_max = _positive_integer(sl_max_points, "sl_max_points")
    sl_step = _positive_integer(sl_step_points, "sl_step_points")
    if tp_min > tp_max or sl_min > sl_max:
        raise ValueError("Range minimum must be less than or equal to its maximum.")
    tp_values = list(range(tp_min, tp_max + 1, tp_step))
    sl_values = list(range(sl_min, sl_max + 1, sl_step))
    combinations = len(tp_values) * len(sl_values)
    if combinations > MAX_TPSL_COMBINATIONS:
        raise ValueError(
            f"TP/SL Range creates {combinations} combinations; maximum is "
            f"{MAX_TPSL_COMBINATIONS}. Increase the steps or narrow the ranges."
        )
    return {
        "mode": "range",
        "point_size": point_size,
        "tp_values": tp_values,
        "sl_values": sl_values
    }


def _build_candidate_plans(side, entries, metrics, interval_minutes, config):
    plans = []
    mode = config["mode"]
    if mode == "auto":
        for entry in entries:
            for risk_atr in (0.80, 1.10):
                for rr in (1.50, 2.0):
                    plans.append(_build_plan(
                        side, entry, metrics, risk_atr, rr, interval_minutes
                    ))
    elif mode in ("fixed", "risk_reward"):
        for entry in entries:
            plans.append(_build_point_plan(
                side, entry, config["tp_points"], config["sl_points"],
                config["point_size"], interval_minutes
            ))
    else:
        for entry in entries:
            for tp_points in config["tp_values"]:
                for sl_points in config["sl_values"]:
                    plans.append(_build_point_plan(
                        side, entry, tp_points, sl_points,
                        config["point_size"], interval_minutes
                    ))
    if len(plans) > MAX_CANDIDATES_PER_SIDE:
        raise ValueError(
            f"Candidate grid creates {len(plans)} plans per side; "
            f"maximum is {MAX_CANDIDATES_PER_SIDE}."
        )
    for plan in plans:
        plan["tpsl_mode"] = mode
    return plans


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
               seed, projection_mode, tie_break, seasonality, engine_mode,
               tpsl_config):
    interval = int(bars_data.get("interval_minutes", 5) or 5)
    entries = _candidate_entries(side, metrics)
    plans = _build_candidate_plans(side, entries, metrics, interval, tpsl_config)
    candidates = []
    for index, plan in enumerate(plans):
        result = _run_one(
            plan, bars_data, horizon_bars, search_replays, spread,
            seed + index, projection_mode, tie_break, seasonality, engine_mode
        )
        distance_atr = abs(metrics["current_price"] - plan["entry_price"]) / metrics["atr"]
        touch = _estimate_entry_touch(bars_data["bars"], side, distance_atr, horizon_bars)
        candidates.append((_rank_score(result, touch), plan, result, touch))
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
    touch_rate = float(touch["touch_probability_pct"]) / 100.0
    adjusted_r = float(result["odds"]["avg_r"]) * touch_rate

    result["plan"]["order_type"] = "LIMIT"
    result["plan"]["tpsl_mode"] = plan.get("tpsl_mode", "auto")
    for key in ("tp_points", "sl_points", "point_size", "target_rr"):
        if key in plan:
            result["plan"][key] = plan[key]
    result["plan"]["candidate_count_scanned"] = candidate_count
    result["plan"]["candidate_search_replays"] = int(coarse["plan"]["replays"])
    result["plan"]["entry_fill_probability"] = None
    result["plan"]["entry_touch_probability_pct"] = float(touch["touch_probability_pct"])
    result["plan"]["entry_touch_samples"] = int(touch["samples"])
    result["plan"]["median_bars_to_touch"] = touch["median_bars_to_touch"]
    result["plan"]["fill_adjusted_simulated_avg_r"] = adjusted_r
    result["plan"]["entry_fill_assumption"] = (
        "Conditional on the proposed limit order being filled; historical OHLC touch proxy does not guarantee fill."
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
    engine_mode="legacy", tpsl_mode="auto", point_size=None,
    fixed_tp_points=2000, fixed_sl_points=1000,
    tp_min_points=1000, tp_max_points=5000, tp_step_points=500,
    sl_min_points=500, sl_max_points=2000, sl_step_points=250,
    rr_ratio=2.0, rr_sl_points=1000
):
    """
    Search and rank BUY LIMIT and SELL LIMIT candidates.

    auto derives TP/SL from ATR and structure; fixed holds user distances constant;
    range searches a bounded grid of TP/SL point distances; risk_reward locks a
    specific target R:R ratio (e.g. 1:2, 1:10) and searches for optimal limit entries.
    point_size is the price value of one broker point and may differ by broker/symbol.
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
    if point_size is None:
        point_size = normalized.get("point_size")
    tpsl_config = _normalize_tpsl_config(
        tpsl_mode, normalized, point_size,
        fixed_tp_points, fixed_sl_points,
        tp_min_points, tp_max_points, tp_step_points,
        sl_min_points, sl_max_points, sl_step_points,
        rr_ratio, rr_sl_points
    )
    metrics = calculate_market_metrics(bars, period=min(len(bars), max(48, horizon_bars)))
    interval = int(normalized.get("interval_minutes", 5) or 5)
    metrics["interval_minutes"] = interval
    metrics["price_step"] = float(tpsl_config.get("point_size", point_size or 0.01))

    horizon_bars = max(1, int(horizon_bars))
    replays = max(100, int(replays))
    search_replays = min(replays, 600)
    primary_mode = "legacy" if engine_mode == "compare" else engine_mode

    buy_selected, buy_count = _scan_side(
        "buy", metrics, normalized, horizon_bars, search_replays, spread, seed,
        projection_mode, tie_break, seasonality, primary_mode, tpsl_config
    )
    sell_selected, sell_count = _scan_side(
        "sell", metrics, normalized, horizon_bars, search_replays, spread, seed + 1000,
        projection_mode, tie_break, seasonality, primary_mode, tpsl_config
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
    if tpsl_config["mode"] == "auto":
        tpsl_label = "Auto ATR/structure"
    elif tpsl_config["mode"] == "fixed":
        tpsl_label = f"Fixed TP {tpsl_config['tp_points']} / SL {tpsl_config['sl_points']} points"
    elif tpsl_config["mode"] == "risk_reward":
        tpsl_label = f"Risk Reward 1:{tpsl_config['rr_ratio']:g} (TP {tpsl_config['tp_points']} / SL {tpsl_config['sl_points']} pts)"
    else:
        tpsl_label = (
            f"TP range {tpsl_config['tp_values'][0]}-{tpsl_config['tp_values'][-1]}; "
            f"SL range {tpsl_config['sl_values'][0]}-{tpsl_config['sl_values'][-1]} points"
        )
    tpsl_report = dict(tpsl_config)
    tpsl_report["label"] = tpsl_label
    return {
        "metrics": metrics,
        "best_direction": best_dir,
        "summary": summary,
        "engine_mode": engine_mode,
        "tpsl_config": tpsl_report,
        "search": {
            "method": "ATR pullback + recent swing-structure candidate grid",
            "buy_candidates_scanned": buy_count,
            "sell_candidates_scanned": sell_count,
            "search_replays_per_candidate": search_replays,
            "final_replays": replays,
            "ranking": "touch-adjusted simulated average R; target probability and RR are secondary descriptors",
            "fill_model": "historical_ohlc_touch_proxy_not_broker_fill_probability"
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
