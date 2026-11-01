"""
MetaTrader 5 Connector for XAUUSD Time Machine
Direct IPC connector to local MetaTrader 5 terminal.
Handles historical M5 candle extraction, auto-symbol resolution (XAUUSD, XAUUSDc, GOLD),
live spread detection, and open position importing.
"""

import os
import time
import json
try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

CACHE_FILE_MT5 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_cache_mt5.json")

def get_mt5_connection():
    """Ensure MT5 connection is initialized and return terminal/account info."""
    if not mt5.initialize():
        err = mt5.last_error()
        return {"connected": False, "error": f"MT5 Init Error: {err}"}
    
    acc = mt5.account_info()
    term = mt5.terminal_info()
    
    account_login = acc.login if acc else "Unknown"
    broker_name = acc.company if acc else "Unknown Broker"
    server = acc.server if acc else "Unknown Server"
    
    # Auto-detect gold symbol
    gold_sym = find_gold_symbol()
    
    return {
        "connected": True,
        "login": account_login,
        "broker": broker_name,
        "server": server,
        "gold_symbol": gold_sym,
        "path": term.path if term else ""
    }

def find_gold_symbol(preferred=None):
    """Find the exact gold symbol used by the broker (e.g. XAUUSDc, XAUUSDm, XAUUSD, GOLD)."""
    if not mt5.initialize():
        return "XAUUSD"
        
    all_syms = mt5.symbols_get()
    if not all_syms:
        return "XAUUSD"
        
    sym_names = [s.name for s in all_syms]
    
    # If preferred symbol exists, use it
    if preferred and preferred in sym_names:
        return preferred
        
    # First priority: symbol with active open positions
    positions = mt5.positions_get()
    if positions:
        for p in positions:
            if "xau" in p.symbol.lower() or "gold" in p.symbol.lower():
                return p.symbol
                
    # Second priority: symbols currently visible in Market Watch
    visible_gold = [s.name for s in all_syms if s.visible and ("xau" in s.name.lower() or "gold" in s.name.lower())]
    if visible_gold:
        return visible_gold[0]
        
    # Third priority: any matching gold symbol in the broker's symbol tree
    any_gold = [s.name for s in all_syms if "xau" in s.name.lower() or "gold" in s.name.lower()]
    if any_gold:
        return any_gold[0]
        
    return "XAUUSD"

def get_mt5_gold_bars(symbol=None, timeframe="M5", count=None, force_refresh=False):
    """
    Fetch historical bars (M5 or M1) directly from MT5 terminal.
    Caches to data_cache_mt5.json or data_cache_mt5_m1.json for offline access.
    """
    tf_upper = (timeframe or "M5").upper().strip()
    is_m1 = (tf_upper == "M1")
    cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_cache_mt5_m1.json" if is_m1 else "data_cache_mt5.json")
    
    if count is None:
        count = 30000 if is_m1 else 15000
        
    tf_code = mt5.TIMEFRAME_M1 if is_m1 else mt5.TIMEFRAME_M5

    if not mt5.initialize():
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        raise ConnectionError("MetaTrader 5 terminal is not running or failed to initialize.")
        
    resolved_sym = symbol or find_gold_symbol()
    mt5.symbol_select(resolved_sym, True)
    
    rates = mt5.copy_rates_from_pos(resolved_sym, tf_code, 0, count)
    if rates is None or len(rates) == 0:
        err = mt5.last_error()
        raise ValueError(f"Could not load bars for {resolved_sym} from MT5: {err}")
        
    bars = []
    for r in rates:
        t = int(r["time"])
        o = float(r["open"])
        h = float(r["high"])
        l = float(r["low"])
        c = float(r["close"])
        if c > 0 and o > 0 and h > 0 and l > 0:
            bars.append({"timestamp": t, "open": o, "high": h, "low": l, "close": c})
            
    # Get live tick and spread directly from MT5 broker
    tick = mt5.symbol_info_tick(resolved_sym)
    info = mt5.symbol_info(resolved_sym)
    spread = 0.25
    current_price = bars[-1]["close"] if bars else 0.0
    
    if tick and tick.bid > 0:
        current_price = tick.bid
        if tick.ask > tick.bid:
            spread = round(tick.ask - tick.bid, 3)
    elif info and info.spread > 0 and info.point > 0:
        spread = round(info.spread * info.point, 3)
            
    result = {
        "source": "MT5",
        "timeframe": tf_upper,
        "interval_minutes": 1 if is_m1 else 5,
        "symbol": resolved_sym,
        "fetched_at": time.time(),
        "current_price": current_price,
        "spread": spread,
        "bars": bars
    }
    
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(result, f)
    except Exception:
        pass
        
    return result

def get_open_gold_positions(symbol=None):
    """
    Fetch active open positions for gold from MT5.
    Returns list of dicts with ticket, volume, entry, sl, tp, profit, type.
    """
    if not mt5.initialize():
        return []
        
    resolved_sym = symbol or find_gold_symbol()
    positions = mt5.positions_get(symbol=resolved_sym)
    if not positions:
        # Check all positions if symbol specific returned none
        all_pos = mt5.positions_get()
        if all_pos:
            positions = [p for p in all_pos if "xau" in p.symbol.lower() or "gold" in p.symbol.lower()]
            
    if not positions:
        return []
        
    res = []
    for p in positions:
        p_type = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
        res.append({
            "ticket": int(p.ticket),
            "symbol": p.symbol,
            "type": p_type,
            "volume": float(p.volume),
            "entry": float(p.price_open),
            "sl": float(p.sl),
            "tp": float(p.tp),
            "profit": float(p.profit),
            "price_current": float(p.price_current),
            "time": int(p.time)
        })
    return res

if __name__ == "__main__":
    status = get_mt5_connection()
    print("MT5 Status:", status)
    if status.get("connected"):
        data = get_mt5_gold_bars()
        print(f"Loaded {len(data['bars'])} bars from {data['symbol']}, Live: ${data['current_price']:.2f}, Spread: ${data['spread']:.2f}")
        pos = get_open_gold_positions()
        print(f"Active positions ({len(pos)}):", pos)
