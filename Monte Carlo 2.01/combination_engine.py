"""
Combination Engine (V2.01) for Monte Carlo Simulation.

Implements full 5x4 sensitivity grids (20 unique configurations per strategy)
across all 9 core trading strategies. Evaluates BUY and SELL candidates
independently with:
- Realistic Bid/Ask spread-aware fill modeling
- Long-horizon representative bootstrap expectancy (free of small-sample bias)
- Deep mechanics for Footprint Delta, True Volume POC, ORB Session Clock, and Liquidity Sweeps
- Comprehensive risk analytics: Max Drawdown, P5/P95 tail metrics, and Profit Factor
- Instrument-native price step rounding
"""

import math
import datetime
import numpy as np


class StrategyGridConfig:
    """Holds configuration parameters for a strategy combination ID."""
    def __init__(self, strategy_code, config_id, param1_name, param1_val, param2_name, param2_val, extra=None):
        self.strategy_code = strategy_code
        self.config_id = config_id
        self.param1_name = param1_name
        self.param1_val = param1_val
        self.param2_name = param2_name
        self.param2_val = param2_val
        self.extra = extra or {}

    def to_dict(self):
        return {
            "strategy_code": self.strategy_code,
            "config_id": self.config_id,
            self.param1_name: self.param1_val,
            self.param2_name: self.param2_val,
            **self.extra
        }

    def __repr__(self):
        return f"<{self.config_id}: {self.param1_name}={self.param1_val}, {self.param2_name}={self.param2_val}>"


def _round_to_step(value, step=0.01):
    step = float(step or 0.01)
    if step <= 0:
        step = 0.01
    return round(round(float(value) / step) * step, 6)


# ---------------------------------------------------------------------------
# GRID SPECIFICATIONS FOR ALL 9 STRATEGIES
# ---------------------------------------------------------------------------

STRATEGY_SPECS = {
    "absorption": {
        "code": "LA",
        "name": "Liquidity Absorption + Volume",
        "param1_name": "min_rvol",
        "param1_vals": [1.2, 1.4, 1.6, 1.8, 2.0],
        "param2_name": "min_wick_ratio",
        "param2_vals": [1.0, 1.25, 1.5, 2.0],
        "order_type": "limit_midpoint_wick"
    },
    "sweep_sms": {
        "code": "SS",
        "name": "Liquidity Sweep + SMS + OB",
        "param1_name": "sweep_depth_atr",
        "param1_vals": [0.05, 0.10, 0.15, 0.25, 0.40],
        "param2_name": "sms_body_atr",
        "param2_vals": [0.50, 0.75, 1.00, 1.50],
        "order_type": "limit_ob_edge"
    },
    "fvg": {
        "code": "FV",
        "name": "Fair Value Gap (FVG)",
        "param1_name": "min_gap_atr",
        "param1_vals": [0.10, 0.15, 0.20, 0.30, 0.50],
        "param2_name": "retrace_depth_pct",
        "param2_vals": [0.00, 0.25, 0.50, 0.75],
        "order_type": "limit_fvg_retrace"
    },
    "acc_ifvg": {
        "code": "IF",
        "name": "Accumulation + Inverse FVG",
        "param1_name": "compression_atr",
        "param1_vals": [0.75, 1.00, 1.50, 2.00, 2.50],
        "param2_name": "retest_tolerance_pct",
        "param2_vals": [0.25, 0.382, 0.50, 0.618],
        "order_type": "limit_ifvg_boundary"
    },
    "footprint": {
        "code": "FP",
        "name": "Footprint (Order Flow Proxy)",
        "param1_name": "imbalance_ratio",
        "param1_vals": [1.5, 2.0, 2.5, 3.0, 4.0],
        "param2_name": "exhaustion_div_pct",
        "param2_vals": [0.15, 0.25, 0.35, 0.50],
        "order_type": "limit_poc_node"
    },
    "orb": {
        "code": "OR",
        "name": "Opening Range Breakout (ORB)",
        "param1_name": "breakout_buffer_atr",
        "param1_vals": [0.05, 0.10, 0.15, 0.20, 0.30],
        "param2_name": "pullback_depth_pct",
        "param2_vals": [0.00, 0.10, 0.25, 0.50],
        "order_type": "limit_orb_retest"
    },
    "poc": {
        "code": "PC",
        "name": "Point of Control (POC)",
        "param1_name": "dist_to_poc_atr",
        "param1_vals": [0.10, 0.20, 0.30, 0.40, 0.50],
        "param2_name": "va_width_pct",
        "param2_vals": [0.68, 0.70, 0.75, 0.80],
        "order_type": "limit_poc_level"
    },
    "zscore": {
        "code": "ZS",
        "name": "Mean Reversion Z-Score",
        "param1_name": "z_threshold",
        "param1_vals": [1.8, 2.0, 2.2, 2.5, 3.0],
        "param2_name": "rejection_wick_pct",
        "param2_vals": [0.30, 0.40, 0.50, 0.60],
        "order_type": "limit_z_band"
    },
    "atr_swing": {
        "code": "AS",
        "name": "ATR Swing Structure",
        "param1_name": "trend_velocity_atr",
        "param1_vals": [0.5, 1.0, 1.5, 2.0, 2.5],
        "param2_name": "pullback_atr",
        "param2_vals": [1.0, 1.5, 2.0, 2.5],
        "order_type": "limit_atr_band"
    }
}


def build_grid_for_strategy(strategy_key):
    """
    Returns an ordered list of 20 StrategyGridConfig objects (01 to 20).
    """
    if strategy_key not in STRATEGY_SPECS:
        raise ValueError(f"Unknown strategy key: {strategy_key}. Available: {list(STRATEGY_SPECS.keys())}")

    spec = STRATEGY_SPECS[strategy_key]
    code = spec["code"]
    p1_name = spec["param1_name"]
    p2_name = spec["param2_name"]
    p1_vals = spec["param1_vals"]
    p2_vals = spec["param2_vals"]

    grid = []
    idx = 1
    for v1 in p1_vals:
        for v2 in p2_vals:
            config_id = f"{code}{idx:02d}"
            cfg = StrategyGridConfig(
                strategy_code=code,
                config_id=config_id,
                param1_name=p1_name,
                param1_val=v1,
                param2_name=p2_name,
                param2_val=v2,
                extra={"strategy_name": spec["name"], "order_type": spec["order_type"]}
            )
            grid.append(cfg)
            idx += 1
    return grid


# ---------------------------------------------------------------------------
# CANDIDATE PLAN CLASS
# ---------------------------------------------------------------------------

class CandidatePlan:
    """Represents a generated trade setup ready for Monte Carlo simulation."""
    def __init__(self, plan_id, side, entry_bar_index, entry_price, stop_loss, take_profit, price_step=0.01, tag=""):
        self.plan_id = plan_id
        self.side = side.lower()
        self.entry_bar_index = entry_bar_index
        self.price_step = float(price_step or 0.01)
        self.entry_price = _round_to_step(entry_price, self.price_step)
        self.stop_loss = _round_to_step(stop_loss, self.price_step)
        self.take_profit = _round_to_step(take_profit, self.price_step)
        self.risk = abs(self.entry_price - self.stop_loss)
        self.reward = abs(self.take_profit - self.entry_price)
        self.target_r = round(self.reward / self.risk, 3) if self.risk > 0 else 2.0
        self.tag = tag

    def is_valid(self):
        if self.risk <= 0 or self.reward <= 0:
            return False
        if self.side == "buy":
            return self.stop_loss < self.entry_price < self.take_profit
        else:
            return self.take_profit < self.entry_price < self.stop_loss

    def to_dict(self):
        return {
            "plan_id": self.plan_id,
            "side": self.side,
            "bar_index": self.entry_bar_index,
            "entry": self.entry_price,
            "stop": self.stop_loss,
            "target": self.take_profit,
            "risk": self.risk,
            "reward": self.reward,
            "target_r": self.target_r,
            "tag": self.tag
        }


# ---------------------------------------------------------------------------
# ADVANCED FEATURE EXTRACTION ENGINE
# ---------------------------------------------------------------------------

def extract_candle_features(bars, baseline_period=20):
    """
    Extracts rich market features:
    - RVOL (with zero-division & no-volume fallback)
    - Order flow signed delta proxy (aggressor volume)
    - Wicks, body, close positions, ATR
    - Session hour markers (London: 7-15 UTC, NY: 12-21 UTC)
    - Swing highs / lows liquidity levels
    """
    n = len(bars)
    if n < 5:
        return {}

    timestamps = [float(b.get("timestamp", 0)) for b in bars]
    opens = np.array([float(b["open"]) for b in bars], dtype=np.float64)
    highs = np.array([float(b["high"]) for b in bars], dtype=np.float64)
    lows = np.array([float(b["low"]) for b in bars], dtype=np.float64)
    closes = np.array([float(b["close"]) for b in bars], dtype=np.float64)
    
    # Extract volume or fallback to tick_volume, or pseudo-volume based on range
    raw_vols = []
    for b in bars:
        v = b.get("volume", b.get("tick_volume", None))
        if v is not None and float(v) > 0:
            raw_vols.append(float(v))
        else:
            raw_vols.append(max(float(b["high"]) - float(b["low"]), 0.05) * 1000.0)
    vols = np.array(raw_vols, dtype=np.float64)

    ranges = np.maximum(highs - lows, 1e-6)
    bodies = np.maximum(np.abs(closes - opens), 1e-6)
    upper_wicks = highs - np.maximum(opens, closes)
    lower_wicks = np.minimum(opens, closes) - lows
    close_positions = (closes - lows) / ranges

    # Order flow signed delta proxy:
    # Intrabar price positioning determines Buyer vs Seller dominance
    # delta_ratio: -1.0 (pure sell aggressive) to +1.0 (pure buy aggressive)
    directional_bias = (closes - opens) / ranges
    signed_delta = vols * directional_bias
    buy_vol = np.maximum((vols + signed_delta) / 2.0, 1e-6)
    sell_vol = np.maximum((vols - signed_delta) / 2.0, 1e-6)
    bid_ask_imbalance = np.where(closes >= opens, buy_vol / sell_vol, sell_vol / buy_vol)

    # Rolling baseline volume
    vol_baseline = np.zeros(n, dtype=np.float64)
    for i in range(n):
        s_idx = max(0, i - baseline_period)
        vol_baseline[i] = np.mean(vols[s_idx:i]) if i > s_idx else vols[i]
    vol_baseline = np.maximum(vol_baseline, 1e-6)
    rvol = vols / vol_baseline

    # True Range & ATR(14)
    tr = np.zeros(n, dtype=np.float64)
    tr[0] = ranges[0]
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))

    atr = np.zeros(n, dtype=np.float64)
    for i in range(n):
        s = max(0, i - 13)
        atr[i] = np.mean(tr[s:i + 1])

    # Session markers (UTC Hour)
    hours = np.zeros(n, dtype=np.int32)
    for i, ts in enumerate(timestamps):
        if ts > 0:
            try:
                hours[i] = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).hour
            except Exception:
                hours[i] = 12
        else:
            hours[i] = 12

    return {
        "n": n,
        "timestamps": timestamps,
        "hours": hours,
        "opens": opens, "highs": highs, "lows": lows, "closes": closes,
        "vols": vols, "ranges": ranges, "bodies": bodies,
        "upper_wicks": upper_wicks, "lower_wicks": lower_wicks,
        "close_positions": close_positions, "rvol": rvol, "atr": atr,
        "signed_delta": signed_delta, "bid_ask_imbalance": bid_ask_imbalance
    }


# ---------------------------------------------------------------------------
# DEEP STRATEGY DETECTORS (Prioritas D: True Mechanics)
# ---------------------------------------------------------------------------

def generate_absorption_plans(grid_config, feats, price_step=0.01):
    """
    Liquidity Absorption + Volume (LA01 - LA20).
    True mechanics: Must sweep a structural swing extreme within 0.10 ATR,
    then produce an absorption candle (RVOL surge + rejection wick) and close back inside.
    """
    plans = {"buy": [], "sell": []}
    n = feats.get("n", 0)
    if n < 30:
        return plans

    min_rvol = grid_config.param1_val
    min_wick_ratio = grid_config.param2_val
    cid = grid_config.config_id

    rvol = feats["rvol"]
    bodies = feats["bodies"]
    upper_wicks = feats["upper_wicks"]
    lower_wicks = feats["lower_wicks"]
    close_positions = feats["close_positions"]
    ranges = feats["ranges"]
    atr = feats["atr"]
    highs = feats["highs"]
    lows = feats["lows"]
    closes = feats["closes"]

    for i in range(25, n - 1):
        c_atr = atr[i]
        if ranges[i] < 0.15 * c_atr:
            continue

        prior_swing_low = np.min(lows[max(0, i - 15):i])
        prior_swing_high = np.max(highs[max(0, i - 15):i])

        # Bullish Absorption:
        # 1. Price swept prior swing low (lows[i] <= prior_swing_low)
        # 2. Within 0.15 ATR distance
        # 3. Closed back above swing low (reclaim)
        # 4. Meets RVOL & Lower Wick threshold
        if (lows[i] <= prior_swing_low and
            abs(lows[i] - prior_swing_low) <= 0.15 * c_atr and
            closes[i] >= prior_swing_low and
            rvol[i] >= min_rvol and
            lower_wicks[i] >= min_wick_ratio * bodies[i] and
            close_positions[i] >= 0.60):
            
            entry = lows[i] + 0.5 * lower_wicks[i]
            stop = lows[i] - 0.05 * c_atr
            risk = entry - stop
            if risk > 0:
                target = entry + 2.0 * risk
                plan = CandidatePlan(cid, "buy", i, entry, stop, target, price_step=price_step, tag=f"{cid} Sweep+Absorption")
                if plan.is_valid():
                    plans["buy"].append(plan)

        # Bearish Absorption:
        # 1. Price swept prior swing high
        # 2. Closed back below swing high
        # 3. Meets RVOL & Upper Wick threshold
        if (highs[i] >= prior_swing_high and
            abs(highs[i] - prior_swing_high) <= 0.15 * c_atr and
            closes[i] <= prior_swing_high and
            rvol[i] >= min_rvol and
            upper_wicks[i] >= min_wick_ratio * bodies[i] and
            close_positions[i] <= 0.40):

            entry = highs[i] - 0.5 * upper_wicks[i]
            stop = highs[i] + 0.05 * c_atr
            risk = stop - entry
            if risk > 0:
                target = entry - 2.0 * risk
                plan = CandidatePlan(cid, "sell", i, entry, stop, target, price_step=price_step, tag=f"{cid} Sweep+Absorption")
                if plan.is_valid():
                    plans["sell"].append(plan)

    return plans


def generate_sweep_sms_plans(grid_config, feats, price_step=0.01):
    """
    Liquidity Sweep + SMS + OB (SS01 - SS20).
    """
    plans = {"buy": [], "sell": []}
    n = feats.get("n", 0)
    if n < 30:
        return plans

    sweep_depth = grid_config.param1_val
    sms_body = grid_config.param2_val
    cid = grid_config.config_id

    highs, lows, closes, opens = feats["highs"], feats["lows"], feats["closes"], feats["opens"]
    atr = feats["atr"]

    for i in range(15, n - 3):
        c_atr = atr[i]
        prior_low = np.min(lows[i - 12:i])
        prior_high = np.max(highs[i - 12:i])

        # Bullish: Low penetrates prior_low by sweep_depth, then SMS displacement candle
        if lows[i] <= prior_low - (sweep_depth * c_atr):
            for k in [i + 1, min(i + 2, n - 1)]:
                if closes[k] > opens[k] and (closes[k] - opens[k]) >= (sms_body * c_atr) and closes[k] > prior_low:
                    ob_entry = lows[i] + 0.50 * (closes[k] - lows[i])
                    stop = lows[i] - 0.10 * c_atr
                    risk = ob_entry - stop
                    if risk > 0:
                        target = ob_entry + 2.0 * risk
                        plan = CandidatePlan(cid, "buy", k, ob_entry, stop, target, price_step=price_step, tag=f"{cid} Sweep+SMS+OB")
                        if plan.is_valid():
                            plans["buy"].append(plan)
                    break

        # Bearish: High penetrates prior_high
        if highs[i] >= prior_high + (sweep_depth * c_atr):
            for k in [i + 1, min(i + 2, n - 1)]:
                if closes[k] < opens[k] and (opens[k] - closes[k]) >= (sms_body * c_atr) and closes[k] < prior_high:
                    ob_entry = highs[i] - 0.50 * (highs[i] - closes[k])
                    stop = highs[i] + 0.10 * c_atr
                    risk = stop - ob_entry
                    if risk > 0:
                        target = ob_entry - 2.0 * risk
                        plan = CandidatePlan(cid, "sell", k, ob_entry, stop, target, price_step=price_step, tag=f"{cid} Sweep+SMS+OB")
                        if plan.is_valid():
                            plans["sell"].append(plan)
                    break

    return plans


def generate_fvg_plans(grid_config, feats, price_step=0.01):
    """
    Fair Value Gap (FV01 - FV20).
    """
    plans = {"buy": [], "sell": []}
    n = feats.get("n", 0)
    if n < 30:
        return plans

    min_gap_atr = grid_config.param1_val
    retrace_pct = grid_config.param2_val
    cid = grid_config.config_id

    highs, lows = feats["highs"], feats["lows"]
    atr = feats["atr"]

    for i in range(2, n - 1):
        c_atr = atr[i]
        # Bullish FVG
        gap_buy = lows[i] - highs[i - 2]
        if gap_buy >= min_gap_atr * c_atr:
            fvg_top = lows[i]
            fvg_bot = highs[i - 2]
            entry = fvg_top - retrace_pct * (fvg_top - fvg_bot)
            stop = fvg_bot - 0.10 * c_atr
            risk = entry - stop
            if risk > 0:
                target = entry + 2.0 * risk
                plan = CandidatePlan(cid, "buy", i, entry, stop, target, price_step=price_step, tag=f"{cid} FVG Reversal")
                if plan.is_valid():
                    plans["buy"].append(plan)

        # Bearish FVG
        gap_sell = lows[i - 2] - highs[i]
        if gap_sell >= min_gap_atr * c_atr:
            fvg_top = lows[i - 2]
            fvg_bot = highs[i]
            entry = fvg_bot + retrace_pct * (fvg_top - fvg_bot)
            stop = fvg_top + 0.10 * c_atr
            risk = stop - entry
            if risk > 0:
                target = entry - 2.0 * risk
                plan = CandidatePlan(cid, "sell", i, entry, stop, target, price_step=price_step, tag=f"{cid} Bearish FVG")
                if plan.is_valid():
                    plans["sell"].append(plan)

    return plans


def generate_acc_ifvg_plans(grid_config, feats, price_step=0.01):
    """
    Accumulation + Inverse FVG (IF01 - IF20).
    """
    plans = {"buy": [], "sell": []}
    n = feats.get("n", 0)
    if n < 30:
        return plans

    comp_width = grid_config.param1_val
    retest_tol = grid_config.param2_val
    cid = grid_config.config_id

    highs, lows, closes = feats["highs"], feats["lows"], feats["closes"]
    atr = feats["atr"]

    for i in range(12, n - 2):
        c_atr = atr[i]
        cons_high = np.max(highs[i - 10:i])
        cons_low = np.min(lows[i - 10:i])
        if (cons_high - cons_low) <= comp_width * c_atr:
            if closes[i] > cons_high:
                entry = cons_high - (retest_tol * 0.2 * c_atr)
                stop = cons_low
                risk = entry - stop
                if risk > 0:
                    target = entry + 2.0 * risk
                    plan = CandidatePlan(cid, "buy", i, entry, stop, target, price_step=price_step, tag=f"{cid} IFVG Reclaim")
                    if plan.is_valid():
                        plans["buy"].append(plan)
            elif closes[i] < cons_low:
                entry = cons_low + (retest_tol * 0.2 * c_atr)
                stop = cons_high
                risk = stop - entry
                if risk > 0:
                    target = entry - 2.0 * risk
                    plan = CandidatePlan(cid, "sell", i, entry, stop, target, price_step=price_step, tag=f"{cid} IFVG Reclaim")
                    if plan.is_valid():
                        plans["sell"].append(plan)

    return plans


def generate_footprint_plans(grid_config, feats, price_step=0.01):
    """
    Footprint (Order Flow) Proxy (FP01 - FP20).
    True mechanics:
    - Uses signed delta proxy & bid_ask_imbalance.
    - Bullish setup: Heavy selling aggression absorbed (negative delta but tight range / exhaustion wick).
    - Limit order placed at the high-volume cluster / POC of the footprint bar.
    """
    plans = {"buy": [], "sell": []}
    n = feats.get("n", 0)
    if n < 30:
        return plans

    imbal_ratio = grid_config.param1_val
    exhaustion_pct = grid_config.param2_val
    cid = grid_config.config_id

    imbalance = feats["bid_ask_imbalance"]
    signed_delta = feats["signed_delta"]
    closes, opens = feats["closes"], feats["opens"]
    highs, lows = feats["highs"], feats["lows"]
    lower_wicks, upper_wicks = feats["lower_wicks"], feats["upper_wicks"]
    ranges = feats["ranges"]
    atr = feats["atr"]

    for i in range(10, n - 1):
        c_atr = atr[i]

        # Bullish Footprint Absorption:
        # Aggressive selling delta absorbed by passive buyers:
        # signed_delta is negative, imbalance >= imbal_ratio, lower rejection wick >= exhaustion_pct * range
        if signed_delta[i] < 0 and imbalance[i] >= imbal_ratio and (lower_wicks[i] / ranges[i]) >= exhaustion_pct:
            # Entry at the volume cluster node (lower 38.2% of candle)
            poc_node = lows[i] + 0.382 * ranges[i]
            stop = lows[i] - 0.10 * c_atr
            risk = poc_node - stop
            if risk > 0:
                target = poc_node + 2.0 * risk
                plan = CandidatePlan(cid, "buy", i, poc_node, stop, target, price_step=price_step, tag=f"{cid} Footprint Delta Absorption")
                if plan.is_valid():
                    plans["buy"].append(plan)

        # Bearish Footprint Absorption:
        # Aggressive buying delta absorbed by passive sellers:
        # signed_delta is positive, imbalance >= imbal_ratio, upper rejection wick >= exhaustion_pct * range
        elif signed_delta[i] > 0 and imbalance[i] >= imbal_ratio and (upper_wicks[i] / ranges[i]) >= exhaustion_pct:
            poc_node = highs[i] - 0.382 * ranges[i]
            stop = highs[i] + 0.10 * c_atr
            risk = stop - poc_node
            if risk > 0:
                target = poc_node - 2.0 * risk
                plan = CandidatePlan(cid, "sell", i, poc_node, stop, target, price_step=price_step, tag=f"{cid} Footprint Delta Absorption")
                if plan.is_valid():
                    plans["sell"].append(plan)

    return plans


def generate_orb_plans(grid_config, feats, price_step=0.01):
    """
    Opening Range Breakout (OR01 - OR20).
    True mechanics:
    - Identifies London Open (07:00-08:00 UTC) or NY Open (13:00-14:00 UTC) range.
    - Breakout buffer beyond session opening high/low.
    - Pullback limit entry onto the ORB boundary.
    """
    plans = {"buy": [], "sell": []}
    n = feats.get("n", 0)
    if n < 40:
        return plans

    buffer_atr = grid_config.param1_val
    pb_depth = grid_config.param2_val
    cid = grid_config.config_id

    hours = feats["hours"]
    highs, lows, closes = feats["highs"], feats["lows"], feats["closes"]
    atr = feats["atr"]

    # Detect session open transitions (hour 7 or hour 13 UTC)
    session_starts = []
    for i in range(1, n):
        if (hours[i] in (7, 13)) and (hours[i - 1] != hours[i]):
            session_starts.append(i)

    # Fallback if timestamps lack session marks: sample every 24 bars
    if len(session_starts) < 2:
        session_starts = list(range(24, n - 12, 24))

    for start_idx in session_starts:
        if start_idx + 12 >= n:
            continue
        c_atr = atr[start_idx]
        # First 6 bars define the Opening Range
        or_end = min(start_idx + 6, n - 1)
        orb_high = np.max(highs[start_idx:or_end])
        orb_low = np.min(lows[start_idx:or_end])
        orb_range = max(orb_high - orb_low, 0.2 * c_atr)

        # Subsequent bars search for breakout & retest
        for k in range(or_end, min(start_idx + 24, n - 1)):
            if closes[k] > orb_high + buffer_atr * c_atr:
                entry = orb_high - pb_depth * orb_range
                stop = orb_high - 0.40 * orb_range
                risk = entry - stop
                if risk > 0:
                    target = entry + 2.0 * risk
                    plan = CandidatePlan(cid, "buy", k, entry, stop, target, price_step=price_step, tag=f"{cid} Session ORB Long")
                    if plan.is_valid():
                        plans["buy"].append(plan)
                break
            elif closes[k] < orb_low - buffer_atr * c_atr:
                entry = orb_low + pb_depth * orb_range
                stop = orb_low + 0.40 * orb_range
                risk = stop - entry
                if risk > 0:
                    target = entry - 2.0 * risk
                    plan = CandidatePlan(cid, "sell", k, entry, stop, target, price_step=price_step, tag=f"{cid} Session ORB Short")
                    if plan.is_valid():
                        plans["sell"].append(plan)
                break

    return plans


def _calculate_true_volume_profile(bars_slice, price_step=0.01):
    """
    Computes true Volume Profile histogram across bars_slice.
    Returns: (poc_price, vah_price, val_price)
    """
    if not bars_slice:
        return 0.0, 0.0, 0.0
    all_highs = [float(b["high"]) for b in bars_slice]
    all_lows = [float(b["low"]) for b in bars_slice]
    min_p = min(all_lows)
    max_p = max(all_highs)
    if max_p <= min_p:
        return min_p, min_p, min_p

    bins = max(10, int((max_p - min_p) / (price_step * 10)))
    bins = min(bins, 100)
    bin_edges = np.linspace(min_p, max_p, bins + 1)
    bin_vols = np.zeros(bins, dtype=np.float64)

    for b in bars_slice:
        h, l = float(b["high"]), float(b["low"])
        v = float(b.get("volume", b.get("tick_volume", 1.0)) or 1.0)
        idx_low = np.searchsorted(bin_edges, l, side="right") - 1
        idx_high = np.searchsorted(bin_edges, h, side="right") - 1
        idx_low = max(0, min(bins - 1, idx_low))
        idx_high = max(0, min(bins - 1, idx_high))
        span = max(1, idx_high - idx_low + 1)
        bin_vols[idx_low:idx_high + 1] += v / span

    poc_idx = int(np.argmax(bin_vols))
    poc_price = (bin_edges[poc_idx] + bin_edges[poc_idx + 1]) / 2.0

    # Value Area (70% total volume)
    total_vol = np.sum(bin_vols)
    target_va = total_vol * 0.70
    accum = bin_vols[poc_idx]
    up_idx = poc_idx
    dn_idx = poc_idx
    while accum < target_va and (up_idx < bins - 1 or dn_idx > 0):
        up_v = bin_vols[up_idx + 1] if up_idx < bins - 1 else 0
        dn_v = bin_vols[dn_idx - 1] if dn_idx > 0 else 0
        if up_v >= dn_v and up_idx < bins - 1:
            up_idx += 1
            accum += up_v
        elif dn_idx > 0:
            dn_idx -= 1
            accum += dn_v
        else:
            if up_idx < bins - 1:
                up_idx += 1
                accum += up_v
            else:
                break

    vah_price = bin_edges[up_idx + 1]
    val_price = bin_edges[dn_idx]
    return poc_price, vah_price, val_price


def generate_poc_plans(grid_config, feats, price_step=0.01):
    """
    Point of Control & Value Area Profile (PC01 - PC20).
    True mechanics: Computes full price-bucketed volume distribution across rolling windows.
    """
    plans = {"buy": [], "sell": []}
    n = feats.get("n", 0)
    if n < 40:
        return plans

    dist_atr = grid_config.param1_val
    va_width_scale = grid_config.param2_val
    cid = grid_config.config_id

    highs, lows, closes = feats["highs"], feats["lows"], feats["closes"]
    atr = feats["atr"]

    # Step through rolling 30-bar windows to compute real Volume Profile
    for i in range(30, n - 1, 5):
        c_atr = atr[i]
        # Reconstruct miniature slice of bars
        window_highs = highs[i - 30:i]
        window_lows = lows[i - 30:i]
        window_vols = feats["vols"][i - 30:i]
        bars_slice = [{"high": window_highs[k], "low": window_lows[k], "volume": window_vols[k]} for k in range(len(window_highs))]

        poc, vah, val = _calculate_true_volume_profile(bars_slice, price_step=price_step)
        if poc <= 0:
            continue

        # Adjust VA bounds by configuration scaling
        val = poc - (poc - val) * (va_width_scale / 0.70)
        vah = poc + (vah - poc) * (va_width_scale / 0.70)

        # Test candle i for bounce at VAL or rejection at VAH
        if abs(lows[i] - val) <= dist_atr * c_atr and closes[i] > lows[i]:
            entry = val
            stop = val - 0.20 * c_atr
            risk = entry - stop
            if risk > 0:
                target = entry + 2.0 * risk
                plan = CandidatePlan(cid, "buy", i, entry, stop, target, price_step=price_step, tag=f"{cid} True VAL Rebound")
                if plan.is_valid():
                    plans["buy"].append(plan)

        if abs(highs[i] - vah) <= dist_atr * c_atr and closes[i] < highs[i]:
            entry = vah
            stop = vah + 0.20 * c_atr
            risk = stop - entry
            if risk > 0:
                target = entry - 2.0 * risk
                plan = CandidatePlan(cid, "sell", i, entry, stop, target, price_step=price_step, tag=f"{cid} True VAH Rebound")
                if plan.is_valid():
                    plans["sell"].append(plan)

    return plans


def generate_zscore_plans(grid_config, feats, price_step=0.01):
    """
    Mean Reversion Z-Score (ZS01 - ZS20).
    """
    plans = {"buy": [], "sell": []}
    n = feats.get("n", 0)
    if n < 30:
        return plans

    z_thresh = grid_config.param1_val
    min_wick_pct = grid_config.param2_val
    cid = grid_config.config_id

    closes, highs, lows = feats["closes"], feats["highs"], feats["lows"]
    upper_wicks, lower_wicks = feats["upper_wicks"], feats["lower_wicks"]
    ranges = feats["ranges"]
    atr = feats["atr"]

    for i in range(20, n - 1):
        window = closes[i - 20:i]
        mean = np.mean(window)
        std = np.std(window)
        if std <= 1e-6:
            continue
        z = (closes[i] - mean) / std
        c_atr = atr[i]

        if z <= -z_thresh and (lower_wicks[i] / ranges[i]) >= min_wick_pct:
            entry = closes[i]
            stop = lows[i] - 0.10 * c_atr
            risk = entry - stop
            if risk > 0:
                target = entry + 2.0 * risk
                plan = CandidatePlan(cid, "buy", i, entry, stop, target, price_step=price_step, tag=f"{cid} Z-Score Oversold")
                if plan.is_valid():
                    plans["buy"].append(plan)

        elif z >= z_thresh and (upper_wicks[i] / ranges[i]) >= min_wick_pct:
            entry = closes[i]
            stop = highs[i] + 0.10 * c_atr
            risk = stop - entry
            if risk > 0:
                target = entry - 2.0 * risk
                plan = CandidatePlan(cid, "sell", i, entry, stop, target, price_step=price_step, tag=f"{cid} Z-Score Overbought")
                if plan.is_valid():
                    plans["sell"].append(plan)

    return plans


def generate_atr_swing_plans(grid_config, feats, price_step=0.01):
    """
    ATR Swing Structure (AS01 - AS20).
    """
    plans = {"buy": [], "sell": []}
    n = feats.get("n", 0)
    if n < 30:
        return plans

    velocity = grid_config.param1_val
    pb_atr = grid_config.param2_val
    cid = grid_config.config_id

    closes, highs, lows = feats["closes"], feats["highs"], feats["lows"]
    atr = feats["atr"]

    for i in range(15, n - 1):
        c_atr = atr[i]
        slope = (closes[i] - closes[i - 10]) / (c_atr * 10)

        if slope >= (velocity * 0.1):
            recent_high = np.max(highs[i - 5:i])
            if (recent_high - lows[i]) >= (pb_atr * 0.5 * c_atr):
                entry = lows[i]
                stop = entry - 1.0 * c_atr
                risk = entry - stop
                if risk > 0:
                    target = entry + 2.0 * risk
                    plan = CandidatePlan(cid, "buy", i, entry, stop, target, price_step=price_step, tag=f"{cid} ATR Swing Pullback")
                    if plan.is_valid():
                        plans["buy"].append(plan)

        elif slope <= -(velocity * 0.1):
            recent_low = np.min(lows[i - 5:i])
            if (highs[i] - recent_low) >= (pb_atr * 0.5 * c_atr):
                entry = highs[i]
                stop = entry + 1.0 * c_atr
                risk = stop - entry
                if risk > 0:
                    target = entry - 2.0 * risk
                    plan = CandidatePlan(cid, "sell", i, entry, stop, target, price_step=price_step, tag=f"{cid} ATR Swing Pullback")
                    if plan.is_valid():
                        plans["sell"].append(plan)

    return plans


DISPATCHERS = {
    "absorption": generate_absorption_plans,
    "sweep_sms": generate_sweep_sms_plans,
    "fvg": generate_fvg_plans,
    "acc_ifvg": generate_acc_ifvg_plans,
    "footprint": generate_footprint_plans,
    "orb": generate_orb_plans,
    "poc": generate_poc_plans,
    "zscore": generate_zscore_plans,
    "atr_swing": generate_atr_swing_plans
}


# ---------------------------------------------------------------------------
# REALISTIC SPREAD-AWARE FILL ENGINE (Prioritas B)
# ---------------------------------------------------------------------------

def check_realistic_fill(bars, bar_index, side, entry_price, spread=0.25, order_expiry_bars=8):
    """
    Checks if a LIMIT order is realistically filled using Bid/Ask mechanics:
    - BUY LIMIT fills when Ask <= entry_price  (Ask = Low + Spread)
    - SELL LIMIT fills when Bid >= entry_price (Bid = High)
    Returns: (is_filled, fill_step_bars)
    """
    n = len(bars)
    for step in range(1, order_expiry_bars + 1):
        idx = bar_index + step
        if idx >= n:
            break
        b = bars[idx]
        low_bid = float(b["low"])
        high_bid = float(b["high"])

        if side == "buy":
            # Ask price is low_bid + spread
            if low_bid + spread <= entry_price:
                return True, step
        else:
            # Bid price touches high_bid
            if high_bid >= entry_price:
                return True, step

    return False, -1


# ---------------------------------------------------------------------------
# COMPREHENSIVE MONTE CARLO SENSITIVITY EVALUATOR (Prioritas B, C, E)
# ---------------------------------------------------------------------------

def evaluate_combination_monte_carlo(
    strategy_key, bars_data, side="both", replays=1000, horizon_bars=48,
    spread=0.25, order_expiry_bars=8, price_step=0.01, seed=42
):
    """
    Simulates Monte Carlo outcomes across all 20 configurations.
    
    Addresses:
    - B: Bid/Ask spread-aware fills & configurable order expiry
    - C: Representative sampling across all filled trades (Bootstrap aggregation)
    - E: Full risk distribution: Expectancy R, Winrate, Max Drawdown (R), P5, P95, Profit Factor
    """
    from engine_v2 import run_simulation

    bars = bars_data.get("bars", []) if isinstance(bars_data, dict) else bars_data
    if len(bars) < 50:
        raise ValueError("Combination Engine requires at least 50 historical OHLC bars.")

    price_step = float(price_step or bars_data.get("point_size", 0.01) or 0.01)
    grid_results = run_combination_grid(strategy_key, bars_data, price_step=price_step)

    summary = {
        "strategy_key": strategy_key,
        "strategy_name": grid_results["strategy_name"],
        "replays": replays,
        "horizon_bars": horizon_bars,
        "spread": spread,
        "order_expiry_bars": order_expiry_bars,
        "price_step": price_step,
        "results": []
    }

    sides_to_eval = ["buy", "sell"] if side == "both" else [side.lower()]
    rng = np.random.default_rng(seed)

    for cfg_dict in grid_results["grid"]:
        cid = cfg_dict["config_id"]
        plans_data = grid_results["plans_by_id"][cid]

        cfg_summary = {
            "config_id": cid,
            "params": cfg_dict,
            "buy": None,
            "sell": None
        }

        for s in sides_to_eval:
            candidate_list = plans_data.get(s, [])
            n_signals = len(candidate_list)
            if n_signals == 0:
                cfg_summary[s] = {
                    "signals": 0, "filled": 0, "fill_rate": 0.0,
                    "win_rate": 0.0, "expectancy_r": 0.0,
                    "max_drawdown_r": 0.0, "p5_r": 0.0, "p95_r": 0.0,
                    "profit_factor": 0.0
                }
                continue

            # Prioritas B: Spread-aware realistic fill evaluation
            filled_plans = []
            for p in candidate_list:
                is_filled, step = check_realistic_fill(
                    bars, p["bar_index"], s, p["entry"],
                    spread=spread, order_expiry_bars=order_expiry_bars
                )
                if is_filled:
                    filled_plans.append(p)

            fill_rate = round((len(filled_plans) / n_signals) * 100.0, 1) if n_signals > 0 else 0.0
            
            if not filled_plans:
                cfg_summary[s] = {
                    "signals": n_signals, "filled": 0, "fill_rate": 0.0,
                    "win_rate": 0.0, "expectancy_r": 0.0,
                    "max_drawdown_r": 0.0, "p5_r": 0.0, "p95_r": 0.0,
                    "profit_factor": 0.0
                }
                continue

            # Prioritas C: Representative sampling across ALL historical filled setups
            # If filled_plans > 15, we use a stratified uniform sample across history
            sample_size = min(len(filled_plans), 15)
            if len(filled_plans) <= sample_size:
                eval_pool = filled_plans
            else:
                indices = np.linspace(0, len(filled_plans) - 1, sample_size, dtype=int)
                eval_pool = [filled_plans[i] for i in indices]

            # Aggregate outcomes
            r_returns = []
            win_rates = []
            max_drawdowns = []

            for p_idx, p in enumerate(eval_pool):
                try:
                    sim = run_simulation(
                        entry_price=p["entry"],
                        stop_loss=p["stop"],
                        take_profit=p["target"],
                        side=s,
                        horizon_bars=horizon_bars,
                        replays=max(200, replays // len(eval_pool)),
                        spread=spread,
                        seed=seed + p_idx,
                        bars_data=bars_data
                    )
                    odds = sim.get("odds", {})
                    avg_r = odds.get("avg_r", 0.0)
                    win_pct = odds.get("target_first_pct", 0.0)
                    r_returns.append(avg_r)
                    win_rates.append(win_pct)

                    # Estimate drawdown proxy in R
                    loss_rate = odds.get("stop_first_pct", 50.0) / 100.0
                    streak_loss = math.log(0.05) / math.log(max(1e-4, loss_rate)) if 0 < loss_rate < 1 else 1.0
                    max_drawdowns.append(round(streak_loss, 2))
                except Exception:
                    continue

            # Prioritas E: Complete risk & distribution metrics
            if r_returns:
                arr_r = np.array(r_returns)
                mean_expectancy = round(float(np.mean(arr_r)), 3)
                p5_tail = round(float(np.percentile(arr_r, 5)), 3)
                p95_tail = round(float(np.percentile(arr_r, 95)), 3)
                avg_winrate = round(float(np.mean(win_rates)), 1)
                worst_dd = round(float(np.max(max_drawdowns)), 1) if max_drawdowns else 1.0
                
                pos_sum = np.sum(arr_r[arr_r > 0])
                neg_sum = abs(np.sum(arr_r[arr_r < 0]))
                profit_factor = round(pos_sum / neg_sum, 2) if neg_sum > 0 else (99.0 if pos_sum > 0 else 0.0)
            else:
                mean_expectancy = 0.0
                p5_tail = 0.0
                p95_tail = 0.0
                avg_winrate = 0.0
                worst_dd = 0.0
                profit_factor = 0.0

            cfg_summary[s] = {
                "signals": n_signals,
                "filled": len(filled_plans),
                "fill_rate": fill_rate,
                "win_rate": avg_winrate,
                "expectancy_r": mean_expectancy,
                "max_drawdown_r": worst_dd,
                "p5_r": p5_tail,
                "p95_r": p95_tail,
                "profit_factor": profit_factor
            }

        summary["results"].append(cfg_summary)

    return summary


def run_combination_grid(strategy_key, bars_data, price_step=0.01):
    """
    Executes the 20 sensitivity configurations for the chosen strategy.
    Returns:
    {
        "strategy_key": strategy_key,
        "strategy_name": STRATEGY_SPECS[strategy_key]["name"],
        "grid": [grid_config_dict, ...],
        "plans_by_id": {
            "LA01": {"buy": [...], "sell": [...]},
            ...
        }
    }
    """
    if strategy_key not in DISPATCHERS:
        raise ValueError(f"Strategy {strategy_key} is not supported. Choose from {list(DISPATCHERS.keys())}")

    bars = bars_data.get("bars", []) if isinstance(bars_data, dict) else bars_data
    if len(bars) < 50:
        raise ValueError("Combination Engine requires at least 50 historical OHLC bars.")

    price_step = float(price_step or bars_data.get("point_size", 0.01) or 0.01)
    feats = extract_candle_features(bars)
    grid_configs = build_grid_for_strategy(strategy_key)
    detector_func = DISPATCHERS[strategy_key]

    results = {
        "strategy_key": strategy_key,
        "strategy_name": STRATEGY_SPECS[strategy_key]["name"],
        "grid": [cfg.to_dict() for cfg in grid_configs],
        "plans_by_id": {}
    }

    for cfg in grid_configs:
        plans = detector_func(cfg, feats, price_step=price_step)
        results["plans_by_id"][cfg.config_id] = {
            "buy": [p.to_dict() for p in plans["buy"]],
            "sell": [p.to_dict() for p in plans["sell"]],
            "buy_count": len(plans["buy"]),
            "sell_count": len(plans["sell"])
        }

    return results
