"""
Dual-Engine Auto-Analyzer for XAUUSD Time Machine
Computes optimal BUY LIMIT and SELL LIMIT setups using market structure (ATR & Swing Levels),
evaluates both simultaneously via Monte Carlo simulation, and outputs dual visual setups.
"""

import numpy as np
import timemachine

def calculate_market_metrics(bars, period=48):
    """Calculate ATR and recent swing levels from historical bars."""
    if len(bars) < period:
        period = max(10, len(bars) - 1)
        
    recent = bars[-period:]
    highs = np.array([b["high"] for b in recent])
    lows = np.array([b["low"] for b in recent])
    closes = np.array([b["close"] for b in recent])
    
    tr_list = []
    for i in range(1, len(recent)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i-1])
        lc = abs(lows[i] - closes[i-1])
        tr_list.append(max(hl, hc, lc))
        
    atr = float(np.mean(tr_list)) if tr_list else 5.0
    swing_high = float(np.max(highs))
    swing_low = float(np.min(lows))
    
    return {
        "atr": max(1.5, atr),
        "swing_high": swing_high,
        "swing_low": swing_low,
        "current_price": closes[-1]
    }

def find_dual_recommendations(bars_data, horizon_bars=48, replays=5000, spread=0.24, seed=19):
    """
    Simultaneously optimizes and evaluates both BUY LIMIT and SELL LIMIT setups.
    Returns full Monte Carlo results for both directions.
    """
    bars = bars_data.get("bars", [])
    if len(bars) < 100:
        raise ValueError("Not enough bars to scan setups.")
        
    metrics = calculate_market_metrics(bars, period=min(len(bars), max(48, horizon_bars)))
    cur = metrics["current_price"]
    atr = metrics["atr"]
    
    # Scale distances by horizon (longer horizon allows wider SL/TP)
    horizon_factor = max(1.0, (horizon_bars / 48.0) ** 0.5)
    effective_atr = atr * horizon_factor
    
    # ------------------ 1. BUY LIMIT CANDIDATE ------------------
    # Entry at slight pullback (discount)
    pullback_buy = round(min(effective_atr * 0.35, (cur - metrics["swing_low"]) * 0.4), 2)
    buy_entry = round(cur - max(1.5, pullback_buy), 2)
    
    # Risk based on ATR and swing low protection
    buy_risk = round(max(3.0, effective_atr * 1.0), 2)
    buy_stop = round(buy_entry - buy_risk, 2)
    
    # Reward with healthy 1:2.0 ratio
    buy_reward = round(buy_risk * 2.0, 2)
    buy_target = round(buy_entry + buy_reward, 2)
    
    buy_res = timemachine.run_simulation(
        entry_price=buy_entry,
        stop_loss=buy_stop,
        take_profit=buy_target,
        side="buy",
        horizon_bars=horizon_bars,
        replays=replays,
        spread=spread,
        seed=seed,
        bars_data=bars_data
    )
    
    # ------------------ 2. SELL LIMIT CANDIDATE ------------------
    # Entry at slight rally (premium)
    rally_sell = round(min(effective_atr * 0.35, (metrics["swing_high"] - cur) * 0.4), 2)
    sell_entry = round(cur + max(1.5, rally_sell), 2)
    
    # Risk based on ATR and swing high protection
    sell_risk = round(max(3.0, effective_atr * 1.0), 2)
    sell_stop = round(sell_entry + sell_risk, 2)
    
    # Reward with healthy 1:2.0 ratio
    sell_reward = round(sell_risk * 2.0, 2)
    sell_target = round(sell_entry - sell_reward, 2)
    
    sell_res = timemachine.run_simulation(
        entry_price=sell_entry,
        stop_loss=sell_stop,
        take_profit=sell_target,
        side="sell",
        horizon_bars=horizon_bars,
        replays=replays,
        spread=spread,
        seed=seed,
        bars_data=bars_data
    )
    
    # Determine best direction by Expectancy / Expected R
    buy_r = buy_res["odds"]["avg_r"]
    sell_r = sell_res["odds"]["avg_r"]
    
    if buy_r > sell_r:
        best_dir = "BUY"
        summary = f"Setup BUY LIMIT lebih diunggulkan secara statistik (+{buy_r:.2f}R vs {sell_r:+.2f}R pada durasi ini)."
    elif sell_r > buy_r:
        best_dir = "SELL"
        summary = f"Setup SELL LIMIT lebih diunggulkan secara statistik (+{sell_r:.2f}R vs {buy_r:+.2f}R pada durasi ini)."
    else:
        best_dir = "EQUAL"
        summary = "Kedua skenario memiliki ekspektasi statistik seimbang."
        
    return {
        "metrics": metrics,
        "best_direction": best_dir,
        "summary": summary,
        "buy": buy_res,
        "sell": sell_res
    }

if __name__ == "__main__":
    import mt5_connector
    try:
        bars_data = mt5_connector.get_mt5_gold_bars()
    except Exception:
        bars_data = timemachine.get_gold_bars(source="comex")
        
    res = find_dual_recommendations(bars_data, horizon_bars=48, replays=3000)
    print("Dual Scan Results:")
    print("Market Price:", res["metrics"]["current_price"])
    print("Best Direction:", res["best_direction"])
    print("Summary:", res["summary"])
    print("\n[BUY LIMIT]")
    print(f"Entry: ${res['buy']['plan']['entry']} | SL: ${res['buy']['plan']['stop']} | TP: ${res['buy']['plan']['target']}")
    print(f"Win Rate: {res['buy']['odds']['target_first_pct']}% | Avg R: {res['buy']['odds']['avg_r']:+.2f}R | Verdict: {res['buy']['verdict']}")
    print("\n[SELL LIMIT]")
    print(f"Entry: ${res['sell']['plan']['entry']} | SL: ${res['sell']['plan']['stop']} | TP: ${res['sell']['plan']['target']}")
    print(f"Win Rate: {res['sell']['odds']['target_first_pct']}% | Avg R: {res['sell']['odds']['avg_r']:+.2f}R | Verdict: {res['sell']['verdict']}")
