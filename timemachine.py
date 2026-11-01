"""
XAUUSD Time Machine - Statistical Odds Simulation Engine for Gold
Inspired by Jake Schincariol's day-trader-skill trader-timemachine.
Customized for 24-hour Gold market (XAUUSD / GC=F) with session-aware time windows,
spread modeling, and high-performance Monte Carlo simulation.
"""

import os
import sys
import re
import json
import time
import datetime
import argparse
import urllib.request
import urllib.parse
import urllib.error
import numpy as np

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_cache.json")
DEFAULT_CACHE_TTL_SECONDS = 1800  # 30 minutes

def fetch_yahoo_gold_data(range_days=60, interval="5m"):
    """Fetch 60-day 5-minute bars for COMEX Gold Futures (GC=F) from Yahoo Finance."""
    # Input validation to prevent parameter injection
    if not str(range_days).isalnum() or not str(interval).isalnum():
        raise ValueError("Invalid parameters for Yahoo Finance API.")

    params = urllib.parse.urlencode({"range": f"{range_days}d", "interval": interval})
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/GC=F?{params}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        # Fallback to query1
        url_fallback = f"https://query1.finance.yahoo.com/v8/finance/chart/GC=F?{params}"
        req_fallback = urllib.request.Request(url_fallback, headers=headers)
        with urllib.request.urlopen(req_fallback, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))

    res = data["chart"]["result"][0]
    meta = res.get("meta", {})
    timestamps = res.get("timestamp", [])
    quotes = res.get("indicators", {}).get("quote", [{}])[0]
    
    opens = quotes.get("open", [])
    highs = quotes.get("high", [])
    lows = quotes.get("low", [])
    closes = quotes.get("close", [])
    
    bars = []
    for i in range(len(timestamps)):
        t = timestamps[i]
        o = opens[i]
        h = highs[i]
        l = lows[i]
        c = closes[i]
        if None not in (t, o, h, l, c) and c > 0 and o > 0 and h > 0 and l > 0:
            bars.append({"timestamp": t, "open": o, "high": h, "low": l, "close": c})
            
    current_price = meta.get("regularMarketPrice", bars[-1]["close"] if bars else 0.0)
    return {
        "symbol": "GC=F",
        "fetched_at": time.time(),
        "current_price": current_price,
        "bars": bars
    }

def get_gold_bars(source="comex", symbol=None, csv_path=None, force_refresh=False, timeframe="M5"):
    """Load gold data from COMEX (Yahoo), MT5, or CSV."""
    if csv_path and os.path.exists(csv_path):
        # Security: Enforce CSV extension to prevent executing/reading malicious files
        if not csv_path.lower().endswith('.csv'):
            raise ValueError("Invalid file extension. Only .csv files are allowed.")

        import csv
        bars = []
        with open(csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                lower_row = {k.lower().strip(): v for k, v in row.items()}
                try:
                    c = float(lower_row.get("close", 0))
                    o = float(lower_row.get("open", c))
                    h = float(lower_row.get("high", c))
                    l = float(lower_row.get("low", c))
                    ts = time.time()
                    if c > 0:
                        bars.append({"timestamp": ts, "open": o, "high": h, "low": l, "close": c})
                except Exception:
                    continue
        if bars:
            return {"source": "CSV", "symbol": "CUSTOM_CSV", "fetched_at": time.time(), "current_price": bars[-1]["close"], "bars": bars, "interval_minutes": 5}

    # MT5 Mode
    if source == "mt5":
        try:
            import mt5_connector
            return mt5_connector.get_mt5_gold_bars(symbol=symbol, timeframe=timeframe, force_refresh=force_refresh)
        except Exception as e:
            print(f"Warning: MT5 fetch failed ({e}), falling back to COMEX cache/fetch.")

    # COMEX Mode (Default)
    if not force_refresh and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if time.time() - cached.get("fetched_at", 0) < DEFAULT_CACHE_TTL_SECONDS and len(cached.get("bars", [])) > 100:
                cached["source"] = "COMEX"
                return cached
        except Exception:
            pass

    # Fetch fresh from Yahoo
    data = fetch_yahoo_gold_data()
    data["source"] = "COMEX"
    try:
        # Sentinel: Use safe file writing by explicitly specifying absolute paths
        # (Though CACHE_FILE is already absolute, this ensures safety).
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass
    return data

def build_slot_pool(bars, window=2, interval_minutes=None, seasonality=False):
    """
    Groups historical bars into daily time-of-day slots (UTC).
    288 slots for 5-minute bars (M5), 1440 slots for 1-minute bars (M1),
    or 1440 // interval_minutes for generic timeframes.
    If seasonality is True, it multiplies total slots by 7 to distinguish day of the week.
    Each slot stores arrays of (open_r, high_r, low_r, close_r) relative to prev_close.
    """
    if interval_minutes is None:
        if len(bars) > 1:
            diff_sec = abs(bars[1]["timestamp"] - bars[0]["timestamp"])
            if diff_sec <= 120:
                interval_minutes = 1
            else:
                interval_minutes = max(1, int(round(diff_sec / 60)))
        else:
            interval_minutes = 5
    int_m = max(1, int(interval_minutes))
    time_slots_per_day = max(1, 1440 // int_m)
    total_slots = time_slots_per_day * 7 if seasonality else time_slots_per_day

    slot_pools = [[] for _ in range(total_slots)]
    
    for i in range(1, len(bars)):
        prev_close = bars[i-1]["close"]
        bar = bars[i]
        t = bar["timestamp"]
        
        # Bolt: Avoid recomputing dt.hour and dt.minute multiple times (Performance)
        dt = datetime.datetime.fromtimestamp(t, tz=datetime.timezone.utc)
        hour, minute = dt.hour, dt.minute
        time_slot = ((hour * 60 + minute) // int_m) % time_slots_per_day
        
        if seasonality:
            day_of_week = dt.weekday()
            slot = day_of_week * time_slots_per_day + time_slot
        else:
            slot = time_slot

        o_r = bar["open"] / prev_close
        h_r = bar["high"] / prev_close
        l_r = bar["low"] / prev_close
        c_r = bar["close"] / prev_close
        
        if 0.90 < l_r <= h_r < 1.10:
            slot_pools[slot].append((o_r, h_r, l_r, c_r))
            
    all_valid_bars = []
    original_pools = []
    for s in range(total_slots):
        if len(slot_pools[s]) > 0:
            arr = np.array(slot_pools[s], dtype=np.float32)
            original_pools.append(arr)
            all_valid_bars.extend(slot_pools[s])
        else:
            original_pools.append(None)
            
    fallback_pool = np.array(all_valid_bars, dtype=np.float32) if all_valid_bars else np.array([[1.0, 1.0005, 0.9995, 1.0]], dtype=np.float32)
    
    numpy_pools = []
    for s in range(total_slots):
        if original_pools[s] is not None and len(original_pools[s]) >= 5:
            numpy_pools.append(original_pools[s])
        else:
            neighbors = []
            for w in range(-window * 2, window * 2 + 1):
                idx = (s + w) % total_slots
                if original_pools[idx] is not None and len(original_pools[idx]) > 0:
                    neighbors.append(original_pools[idx])
            if neighbors:
                numpy_pools.append(np.vstack(neighbors))
            else:
                numpy_pools.append(fallback_pool)
                
    return numpy_pools, interval_minutes, time_slots_per_day, total_slots

def run_simulation(
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    side: str = "buy",
    horizon_bars: int = 48,  # bars
    replays: int = 10000,
    seed: int = 19,
    spread: float = 0.25,
    entry_slot: int = None,
    window: int = 2,
    bars_data: dict = None,
    projection_mode: str = "free_drift",  # "free_drift" (default/recommended), "frozen" (asli), "survival" (kaplan-meier)
    tie_break: str = "smart",  # "smart" (default/recommended), "conservative" (asli), "random"
    seasonality: bool = False,
    interval_minutes: int = None
):
    """
    Run high-performance Monte Carlo simulation on Gold setup.
    Includes Two-Stream Unconstrained Tracking, Smart Candle Anatomy Tie-Break,
    and Dynamic Multi-Timeframe normalization.
    """
    np.random.seed(seed)
    side = side.lower().strip()
    if side not in ("buy", "sell"):
        raise ValueError("side must be 'buy' or 'sell'")
        
    risk = abs(entry_price - stop_loss)
    reward = abs(take_profit - entry_price)
    if risk <= 0:
        raise ValueError("Stop loss cannot equal Entry price")
    target_r = reward / risk
    
    if bars_data is None:
        bars_data = get_gold_bars()
        
    bars = bars_data.get("bars", [])
    if len(bars) < 200:
        raise ValueError("Not enough historical bar data for simulation")
        
    if interval_minutes is None and isinstance(bars_data, dict):
        interval_minutes = bars_data.get("interval_minutes")

    pools, interval_minutes, time_slots_per_day, total_slots = build_slot_pool(
        bars, window=window, interval_minutes=interval_minutes, seasonality=seasonality
    )
    int_m = max(1, int(interval_minutes))
    
    if entry_slot is None:
        if bars and "timestamp" in bars[-1]:
            last_ts = float(bars[-1]["timestamp"])
            now_dt = datetime.datetime.fromtimestamp(last_ts, tz=datetime.timezone.utc)
        else:
            now_dt = datetime.datetime.now(datetime.timezone.utc)
        time_slot = ((now_dt.hour * 60 + now_dt.minute) // int_m) % time_slots_per_day
        if seasonality:
            entry_slot = now_dt.weekday() * time_slots_per_day + time_slot
        else:
            entry_slot = time_slot
        
    market_prices = np.full(replays, entry_price, dtype=np.float64)  # unconstrained price
    frozen_prices = np.full(replays, entry_price, dtype=np.float64)  # frozen at exit (asli)
    active = np.ones(replays, dtype=bool)
    results = np.zeros(replays, dtype=np.int8)  # 0: neither, 1: target, -1: stop
    exit_prices = np.full(replays, entry_price, dtype=np.float64)
    exit_steps = np.full(replays, horizon_bars, dtype=np.int32)
    
    fan_steps = min(horizon_bars, 120)
    step_indices = np.linspace(0, horizon_bars - 1, fan_steps, dtype=int)
    fan_data = {
        "step_bars": [0],
        "interval_minutes": interval_minutes,
        "p5": [entry_price],
        "p25": [entry_price],
        "p50": [entry_price],
        "p75": [entry_price],
        "p95": [entry_price]
    }
    
    sample_path_indices = np.random.choice(replays, size=min(15, replays), replace=False)
    sample_paths = [[entry_price] for _ in range(len(sample_path_indices))]
    
    for step in range(horizon_bars):
        slot = (entry_slot + step) % total_slots
        pool_arr = pools[slot]
        
        sampled_indices = np.random.randint(0, len(pool_arr), size=replays)
        step_ratios = pool_arr[sampled_indices]
        
        o_ratio = step_ratios[:, 0]
        h_ratio = step_ratios[:, 1]
        l_ratio = step_ratios[:, 2]
        c_ratio = step_ratios[:, 3]
        
        high_prices = market_prices * h_ratio
        low_prices = market_prices * l_ratio
        close_prices = market_prices * c_ratio
        
        # Advance unconstrained market price
        market_prices = close_prices
        
        # Check hits for currently active orders
        if side == "buy":
            hit_stop = (low_prices <= stop_loss) & active
            hit_target = (high_prices >= take_profit) & active
            hit_both = hit_stop & hit_target
            
            if np.any(hit_both):
                if tie_break == "conservative":
                    # Asli: Stop loss always wins
                    hit_target = hit_target & (~hit_both)
                elif tie_break == "random":
                    # 50/50 Bernoulli trial
                    flips = np.random.rand(replays) < 0.5
                    hit_stop = (hit_stop & (~hit_both)) | (hit_both & flips)
                    hit_target = (hit_target & (~hit_both)) | (hit_both & (~flips))
                else:  # "smart" (candle anatomy)
                    is_bullish = c_ratio > o_ratio
                    is_bearish = c_ratio < o_ratio
                    doji_flips = np.random.rand(replays) < 0.5
                    # Bullish candle dips to low first (SL hit first). Bearish rallies to high first (TP hit first).
                    sl_first = is_bullish | (doji_flips & (~is_bearish))
                    hit_stop = (hit_stop & (~hit_both)) | (hit_both & sl_first)
                    hit_target = (hit_target & (~hit_both)) | (hit_both & (~sl_first))
        else:  # SELL
            hit_stop = ((high_prices + spread) >= stop_loss) & active
            hit_target = ((low_prices + spread) <= take_profit) & active
            hit_both = hit_stop & hit_target
            
            if np.any(hit_both):
                if tie_break == "conservative":
                    # Asli: Stop loss always wins
                    hit_target = hit_target & (~hit_both)
                elif tie_break == "random":
                    flips = np.random.rand(replays) < 0.5
                    hit_stop = (hit_stop & (~hit_both)) | (hit_both & flips)
                    hit_target = (hit_target & (~hit_both)) | (hit_both & (~flips))
                else:  # "smart" (candle anatomy)
                    is_bullish = c_ratio > o_ratio
                    is_bearish = c_ratio < o_ratio
                    doji_flips = np.random.rand(replays) < 0.5
                    # Bearish candle rallies to high first (SL hit first). Bullish dips to low first (TP hit first).
                    sl_first = is_bearish | (doji_flips & (~is_bullish))
                    hit_stop = (hit_stop & (~hit_both)) | (hit_both & sl_first)
                    hit_target = (hit_target & (~hit_both)) | (hit_both & (~sl_first))
                    
        # Update order outcomes
        if np.any(hit_stop):
            results[hit_stop] = -1
            exit_prices[hit_stop] = stop_loss
            exit_steps[hit_stop] = step + 1
            frozen_prices[hit_stop] = stop_loss
            active[hit_stop] = False
            
        if np.any(hit_target):
            results[hit_target] = 1
            exit_prices[hit_target] = take_profit
            exit_steps[hit_target] = step + 1
            frozen_prices[hit_target] = take_profit
            active[hit_target] = False
            
        frozen_prices[active] = market_prices[active]
        
        # Determine price source for Fan Chart percentiles & sample paths
        if projection_mode == "frozen":
            chart_prices = frozen_prices
            sample_source = frozen_prices
        elif projection_mode == "survival":
            chart_prices = market_prices[active] if np.any(active) else market_prices
            sample_source = market_prices
        else:  # "free_drift" (default / recommended - two-stream tracking)
            chart_prices = market_prices
            sample_source = market_prices
            
        for idx_num, p_idx in enumerate(sample_path_indices):
            sample_paths[idx_num].append(float(sample_source[p_idx]))
            
        if step in step_indices or step == horizon_bars - 1:
            fan_data["step_bars"].append(step + 1)
            # Batch calculate percentiles to reduce overhead (Performance Optimization)
            p_vals = np.percentile(chart_prices, [5, 25, 50, 75, 95])
            fan_data["p5"].append(float(p_vals[0]))
            fan_data["p25"].append(float(p_vals[1]))
            fan_data["p50"].append(float(p_vals[2]))
            fan_data["p75"].append(float(p_vals[3]))
            fan_data["p95"].append(float(p_vals[4]))
            
    neither_mask = (results == 0)
    exit_prices[neither_mask] = market_prices[neither_mask]
    
    target_count = int(np.sum(results == 1))
    stop_count = int(np.sum(results == -1))
    neither_count = int(np.sum(results == 0))
    
    target_pct = (target_count / replays) * 100.0
    stop_pct = (stop_count / replays) * 100.0
    neither_pct = (neither_count / replays) * 100.0
    
    r_values = np.zeros(replays, dtype=np.float64)
    r_values[results == 1] = target_r
    r_values[results == -1] = -1.0
    
    if side == "buy":
        r_values[neither_mask] = (exit_prices[neither_mask] - entry_price) / risk
        green_count = int(np.sum(results == 1) + np.sum(neither_mask & (exit_prices > entry_price)))
    else:
        r_values[neither_mask] = (entry_price - exit_prices[neither_mask]) / risk
        green_count = int(np.sum(results == 1) + np.sum(neither_mask & (exit_prices < entry_price)))
        
    green_pct = (green_count / replays) * 100.0
    avg_r = float(np.mean(r_values))
    
    resolved_total = target_count + stop_count
    breakeven_pct = (1.0 / (1.0 + target_r)) * 100.0
    
    if resolved_total > 0:
        win_rate_on_resolved = (target_count / resolved_total) * 100.0
        gap = win_rate_on_resolved - breakeven_pct
        
        if abs(gap) < 5.0:
            if abs(target_r - 1.0) < 0.05:
                verdict = "Close to a coin flip"
            else:
                verdict = f"Close to break-even ({win_rate_on_resolved:.1f}% vs {breakeven_pct:.1f}% BE)"
        elif gap >= 15.0:
            verdict = f"Strongly leans toward Target ({win_rate_on_resolved:.1f}% vs {breakeven_pct:.1f}% BE)"
        elif 5.0 <= gap < 15.0:
            verdict = f"Leans toward Target ({win_rate_on_resolved:.1f}% vs {breakeven_pct:.1f}% BE)"
        elif gap <= -15.0:
            verdict = f"Strongly leans toward Stop Loss ({win_rate_on_resolved:.1f}% vs {breakeven_pct:.1f}% BE)"
        else:
            verdict = f"Leans toward Stop Loss ({win_rate_on_resolved:.1f}% vs {breakeven_pct:.1f}% BE)"
    else:
        verdict = "Trade rarely resolves within this horizon (high neither rate)"
        win_rate_on_resolved = 0.0
        
    notes = []
    if neither_pct > 35.0:
        notes.append(f"{neither_pct:.1f}% replays hit neither by the horizon end; floating price decides those.")
    if (avg_r > 0 and "Stop Loss" in verdict) or (avg_r < 0 and "Target" in verdict):
        notes.append(f"Average R ({avg_r:+.2f}R) diverges from lean due to floating terminal prices.")
        
    return {
        "plan": {
            "symbol": "XAUUSD (Gold)",
            "side": side.upper(),
            "entry": entry_price,
            "stop": stop_loss,
            "target": take_profit,
            "risk_dollar": risk,
            "reward_dollar": reward,
            "target_r": target_r,
            "horizon_bars": horizon_bars,
            "horizon_hours": horizon_bars * interval_minutes / 60,
            "interval_minutes": interval_minutes,
            "projection_mode": projection_mode,
            "tie_break": tie_break,
            "replays": replays,
            "seed": seed,
            "spread": spread
        },
        "meta": {
            "interval_minutes": interval_minutes,
            "projection_mode": projection_mode,
            "tie_break": tie_break,
            "horizon_bars": horizon_bars,
            "horizon_hours": horizon_bars * interval_minutes / 60
        },
        "odds": {
            "target_first_pct": round(target_pct, 1),
            "stop_first_pct": round(stop_pct, 1),
            "neither_pct": round(neither_pct, 1),
            "green_pct": round(green_pct, 1),
            "win_rate_on_resolved": round(win_rate_on_resolved, 1),
            "breakeven_pct": round(breakeven_pct, 1),
            "avg_r": round(avg_r, 3),
            "median_terminal_price": round(float(np.median(exit_prices)), 2),
            "p5_terminal": round(float(np.percentile(exit_prices, 5)), 2),
            "p95_terminal": round(float(np.percentile(exit_prices, 95)), 2)
        },
        "verdict": verdict,
        "verdict_notes": notes,
        "fan_data": fan_data,
        "sample_paths": sample_paths
    }

def print_cli_report(res):
    p = res["plan"]
    o = res["odds"]
    meta = res.get("meta", {})
    proj_mode = meta.get("projection_mode", "free_drift")
    tb_mode = meta.get("tie_break", "smart")
    int_m = meta.get("interval_minutes", 5)

    print("\n" + "=" * 65)
    print(f"  [XAUUSD TIME MACHINE: {p['replays']:,} REPLAYS OF THE TRADE]")
    print(f"  Setup: {p['side']} @ ${p['entry']:.2f} | Stop: ${p['stop']:.2f} | Target: ${p['target']:.2f} ({p['target_r']:.2f}R)")
    print(f"  Horizon: {p['horizon_bars']} bars ({p['horizon_hours']:.1f}h @ M{int_m}) | Spread buffer: ${p['spread']:.2f} | Seed: {p['seed']}")
    print(f"  Methodology   : Projection={proj_mode} | Tie-Break={tb_mode}")
    print("=" * 65)
    print(f"  Target First  : {o['target_first_pct']:>6.1f} %")
    print(f"  Stop First    : {o['stop_first_pct']:>6.1f} %")
    print(f"  Neither (Open): {o['neither_pct']:>6.1f} %  (still floating after {p['horizon_hours']:.1f}h)")
    print(f"  Green Outcome : {o['green_pct']:>6.1f} %  (target first or in profit at horizon)")
    print("-" * 65)
    print(f"  Price at End  : Median ${o['median_terminal_price']:.2f} (90% range: ${o['p5_terminal']:.2f} - ${o['p95_terminal']:.2f})")
    print(f"  Average Return: {o['avg_r']:+.3f} R")
    print(f"  Verdict       : {res['verdict']}")
    for note in res.get("verdict_notes", []):
        print(f"  Note          : {note}")
    print("=" * 65 + "\n")

def normalize_horizon_bars(h_str_or_num, interval_minutes=5):
    """
    Dynamically normalizes horizon string or number into bar count based on candle interval (M1 vs M5).
    """
    if isinstance(h_str_or_num, (int, float)):
        return max(1, int(h_str_or_num))
        
    h_str = str(h_str_or_num).lower().strip()
    match = re.search(r'\((\d+)\s*bars', h_str.replace(".", ""))
    if match:
        return max(1, int(match.group(1)))
        
    interval = max(1, int(interval_minutes or 5))
    
    if "minggu" in h_str or h_str.endswith("w"):
        weeks = float(re.sub(r'[^\d.]', '', h_str) or 1)
        return max(1, int(weeks * 5 * 24 * 60 / interval))
    if "hari" in h_str or h_str.endswith("d"):
        days = float(re.sub(r'[^\d.]', '', h_str) or 1)
        return max(1, int(days * 24 * 60 / interval))
    if "jam" in h_str or h_str.endswith("h"):
        hours = float(re.sub(r'[^\d.]', '', h_str) or 1)
        return max(1, int(hours * 60 / interval))
    if "menit" in h_str or h_str.endswith("m"):
        minutes = float(re.sub(r'[^\d.]', '', h_str) or 30)
        return max(1, int(minutes / interval))
        
    try:
        return max(1, int(re.sub(r'[^\d.]', '', h_str)))
    except Exception:
        return max(1, int(240 / interval))

def parse_horizon(h_str, interval_minutes=5):
    return normalize_horizon_bars(h_str, interval_minutes)

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description="XAUUSD Time Machine CLI")
    parser.add_argument("--source", choices=["comex", "mt5"], default="comex", help="Data source: comex (Yahoo) or mt5 (MetaTrader 5)")
    parser.add_argument("--mt5-symbol", help="Custom MT5 symbol (e.g. XAUUSDc, GOLD)")
    parser.add_argument("--timeframe", choices=["M5", "M1"], default="M5", help="Timeframe interval (default: M5)")
    parser.add_argument("--entry", type=float, help="Entry price in USD")
    parser.add_argument("--stop", type=float, help="Stop loss price in USD")
    parser.add_argument("--target", type=float, help="Take profit price in USD")
    parser.add_argument("--side", choices=["buy", "sell"], default="buy", help="Trade direction")
    parser.add_argument("--horizon", default="4h", help="Simulation horizon (e.g. '2h', '4h', '48bars')")
    parser.add_argument("--replays", type=int, default=10000, help="Number of Monte Carlo replays")
    parser.add_argument("--spread", type=float, default=0.25, help="Spread buffer in USD")
    parser.add_argument("--seed", type=int, default=19, help="Random seed")
    parser.add_argument("--projection-mode", choices=["free_drift", "frozen", "survival"], default="free_drift", help="Fan chart projection: free_drift (default), frozen (asli), survival")
    parser.add_argument("--tie-break", choices=["smart", "conservative", "random"], default="smart", help="Tie-break collision: smart (default), conservative (asli), random")
    parser.add_argument("--csv", help="Optional local CSV file of M5 bars")
    parser.add_argument("--refresh", action="store_true", help="Force refresh cache from Yahoo Finance")
    parser.add_argument("--json", action="store_true", help="Output result as JSON")
    parser.add_argument("--seasonality", action="store_true", help="Enable day-of-week seasonality")
    args = parser.parse_args()

    bars_data = get_gold_bars(
        source=args.source,
        symbol=args.mt5_symbol,
        timeframe=args.timeframe,
        csv_path=args.csv,
        force_refresh=args.refresh
    )
    cur = bars_data.get("current_price", 2750.0)
    spread = args.spread if args.spread is not None else bars_data.get("spread", 0.25)
    interval_m = bars_data.get("interval_minutes", 5)

    entry = args.entry if args.entry is not None else cur
    side = args.side
    if args.stop is not None:
        stop = args.stop
    else:
        stop = entry - 5.0 if side == "buy" else entry + 5.0
    if args.target is not None:
        target = args.target
    else:
        target = entry + 10.0 if side == "buy" else entry - 10.0

    bars_h = parse_horizon(args.horizon, interval_minutes=interval_m)
    res = run_simulation(
        entry_price=entry,
        stop_loss=stop,
        take_profit=target,
        side=side,
        horizon_bars=bars_h,
        replays=args.replays,
        seed=args.seed,
        spread=spread,
        bars_data=bars_data,
        projection_mode=args.projection_mode,
        tie_break=args.tie_break,
        seasonality=args.seasonality
    )

    if args.json:
        clean_doc = {k: v for k, v in res.items() if k not in ("fan_data", "sample_paths")}
        print(json.dumps(clean_doc, indent=2))
    else:
        print_cli_report(res)

if __name__ == "__main__":
    main()
