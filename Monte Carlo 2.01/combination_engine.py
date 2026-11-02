"""
Combination Engine (V2.01) for Monte Carlo Simulation.

Implements full 5x4 sensitivity grids (20 unique configurations per strategy)
across all 9 core trading strategies. Evaluates BUY and SELL candidates
independently with standardized structural stop-loss and 2R baseline targets.
"""

import math
import numpy as np


class StrategyGridConfig:
    """Holds configuration parameters for a strategy combination ID."""
    def __init__(self, strategy_code, config_id, param1_name, param1_val, param2_name, param2_val, extra=None):
        self.strategy_code = strategy_code  # e.g. "LA", "SS", "FV"
        self.config_id = config_id          # e.g. "LA01", "SS15"
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
    p1_vals = spec["param1_vals"]  # 5 items
    p2_vals = spec["param2_vals"]  # 4 items

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
# FEATURE EXTRACTION ENGINE (Vectorized helper)
# ---------------------------------------------------------------------------

def extract_candle_features(bars, baseline_period=20):
    """
    Extracts vectorized features across all bars:
    RVOL, wicks, bodies, close positions, ATR.
    """
    n = len(bars)
    if n < 5:
        return {}

    opens = np.array([float(b["open"]) for b in bars], dtype=np.float64)
    highs = np.array([float(b["high"]) for b in bars], dtype=np.float64)
    lows = np.array([float(b["low"]) for b in bars], dtype=np.float64)
    closes = np.array([float(b["close"]) for b in bars], dtype=np.float64)
    vols = np.array([float(b.get("volume", b.get("tick_volume", 1.0)) or 1.0) for b in bars], dtype=np.float64)

    ranges = np.maximum(highs - lows, 1e-6)
    bodies = np.maximum(np.abs(closes - opens), 1e-6)
    upper_wicks = highs - np.maximum(opens, closes)
    lower_wicks = np.minimum(opens, closes) - lows
    close_positions = (closes - lows) / ranges

    # Rolling baseline volume using previous bars (avoid look-ahead)
    vol_baseline = np.zeros(n, dtype=np.float64)
    for i in range(n):
        start_idx = max(0, i - baseline_period)
        if i > start_idx:
            vol_baseline[i] = np.mean(vols[start_idx:i])
        else:
            vol_baseline[i] = vols[i]
    vol_baseline = np.maximum(vol_baseline, 1e-6)
    rvol = vols / vol_baseline

    # ATR (14)
    tr = np.zeros(n, dtype=np.float64)
    tr[0] = ranges[0]
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))

    atr = np.zeros(n, dtype=np.float64)
    atr_period = 14
    for i in range(n):
        s = max(0, i - atr_period + 1)
        atr[i] = np.mean(tr[s:i + 1])

    return {
        "n": n,
        "opens": opens, "highs": highs, "lows": lows, "closes": closes,
        "vols": vols, "ranges": ranges, "bodies": bodies,
        "upper_wicks": upper_wicks, "lower_wicks": lower_wicks,
        "close_positions": close_positions, "rvol": rvol, "atr": atr
    }


# ---------------------------------------------------------------------------
# CANDIDATE PLAN GENERATOR PER CONFIGURATION
# ---------------------------------------------------------------------------

class CandidatePlan:
    """Represents a generated trade setup ready for Monte Carlo simulation."""
    def __init__(self, plan_id, side, entry_bar_index, entry_price, stop_loss, take_profit, tag=""):
        self.plan_id = plan_id
        self.side = side.lower()
        self.entry_bar_index = entry_bar_index
        self.entry_price = round(float(entry_price), 2)
        self.stop_loss = round(float(stop_loss), 2)
        self.take_profit = round(float(take_profit), 2)
        self.risk = abs(self.entry_price - self.stop_loss)
        self.reward = abs(self.take_profit - self.entry_price)
        self.target_r = round(self.reward / self.risk, 2) if self.risk > 0 else 2.0
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
# STRATEGY DETECTORS
# ---------------------------------------------------------------------------

def generate_absorption_plans(grid_config, feats, price_step=0.01):
    """
    Generates CandidatePlans for Liquidity Absorption + Volume (LA01 - LA20).
    Grid params: min_rvol (1.2 - 2.0), min_wick_ratio (1.0 - 2.0).
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

    for i in range(25, n - 1):
        c_atr = atr[i]
        if ranges[i] < 0.20 * c_atr:
            continue

        # Bullish Absorption (BUY LIMIT at midpoint lower wick)
        if (rvol[i] >= min_rvol and
            lower_wicks[i] >= min_wick_ratio * bodies[i] and
            close_positions[i] >= 0.65):
            
            entry = lows[i] + 0.5 * lower_wicks[i]
            stop = lows[i] - 0.05 * c_atr
            risk = entry - stop
            if risk > 0:
                target = entry + 2.0 * risk
                plan = CandidatePlan(cid, "buy", i, entry, stop, target, tag=f"{cid} Bullish Absorption")
                if plan.is_valid():
                    plans["buy"].append(plan)

        # Bearish Absorption (SELL LIMIT at midpoint upper wick)
        if (rvol[i] >= min_rvol and
            upper_wicks[i] >= min_wick_ratio * bodies[i] and
            close_positions[i] <= 0.35):

            entry = highs[i] - 0.5 * upper_wicks[i]
            stop = highs[i] + 0.05 * c_atr
            risk = stop - entry
            if risk > 0:
                target = entry - 2.0 * risk
                plan = CandidatePlan(cid, "sell", i, entry, stop, target, tag=f"{cid} Bearish Absorption")
                if plan.is_valid():
                    plans["sell"].append(plan)

    return plans


def generate_sweep_sms_plans(grid_config, feats, price_step=0.01):
    """
    Liquidity Sweep + SMS + OB (SS01 - SS20).
    Grid params: sweep_depth_atr (0.05 - 0.40), sms_body_atr (0.50 - 1.50).
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
        prior_low = np.min(lows[i - 10:i])
        prior_high = np.max(highs[i - 10:i])

        # Bullish: Low penetrates prior_low by required sweep_depth, then SMS occurs
        if lows[i] <= prior_low - (sweep_depth * c_atr):
            # Check for SMS displacement in next 1-2 bars
            for k in [i + 1, min(i + 2, n - 1)]:
                if closes[k] > opens[k] and (closes[k] - opens[k]) >= (sms_body * c_atr) and closes[k] > prior_low:
                    ob_entry = lows[i] + 0.618 * (closes[k] - lows[i])
                    stop = lows[i] - 0.10 * c_atr
                    risk = ob_entry - stop
                    if risk > 0:
                        target = ob_entry + 2.0 * risk
                        plan = CandidatePlan(cid, "buy", k, ob_entry, stop, target, tag=f"{cid} Sweep+SMS")
                        if plan.is_valid():
                            plans["buy"].append(plan)
                    break

        # Bearish: High penetrates prior_high
        if highs[i] >= prior_high + (sweep_depth * c_atr):
            for k in [i + 1, min(i + 2, n - 1)]:
                if closes[k] < opens[k] and (opens[k] - closes[k]) >= (sms_body * c_atr) and closes[k] < prior_high:
                    ob_entry = highs[i] - 0.618 * (highs[i] - closes[k])
                    stop = highs[i] + 0.10 * c_atr
                    risk = stop - ob_entry
                    if risk > 0:
                        target = ob_entry - 2.0 * risk
                        plan = CandidatePlan(cid, "sell", k, ob_entry, stop, target, tag=f"{cid} Sweep+SMS")
                        if plan.is_valid():
                            plans["sell"].append(plan)
                    break

    return plans


def generate_fvg_plans(grid_config, feats, price_step=0.01):
    """
    Fair Value Gap (FV01 - FV20).
    Grid params: min_gap_atr (0.10 - 0.50), retrace_depth_pct (0.00 - 0.75).
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
        # Bullish FVG: Low of candle i > High of candle i-2
        gap_buy = lows[i] - highs[i - 2]
        if gap_buy >= min_gap_atr * c_atr:
            fvg_top = lows[i]
            fvg_bot = highs[i - 2]
            entry = fvg_top - retrace_pct * (fvg_top - fvg_bot)
            stop = fvg_bot - 0.10 * c_atr
            risk = entry - stop
            if risk > 0:
                target = entry + 2.0 * risk
                plan = CandidatePlan(cid, "buy", i, entry, stop, target, tag=f"{cid} FVG Reversal")
                if plan.is_valid():
                    plans["buy"].append(plan)

        # Bearish FVG: High of candle i < Low of candle i-2
        gap_sell = lows[i - 2] - highs[i]
        if gap_sell >= min_gap_atr * c_atr:
            fvg_top = lows[i - 2]
            fvg_bot = highs[i]
            entry = fvg_bot + retrace_pct * (fvg_top - fvg_bot)
            stop = fvg_top + 0.10 * c_atr
            risk = stop - entry
            if risk > 0:
                target = entry - 2.0 * risk
                plan = CandidatePlan(cid, "sell", i, entry, stop, target, tag=f"{cid} Bearish FVG")
                if plan.is_valid():
                    plans["sell"].append(plan)

    return plans


def generate_acc_ifvg_plans(grid_config, feats, price_step=0.01):
    """
    Accumulation + Inverse FVG (IF01 - IF20).
    Grid params: compression_atr (0.75 - 2.50), retest_tolerance_pct (0.25 - 0.618).
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
        # Range of preceding 10 bars
        cons_high = np.max(highs[i - 10:i])
        cons_low = np.min(lows[i - 10:i])
        if (cons_high - cons_low) <= comp_width * c_atr:
            # Bullish IFVG breakout
            if closes[i] > cons_high:
                entry = cons_high - (retest_tol * 0.2 * c_atr)
                stop = cons_low
                risk = entry - stop
                if risk > 0:
                    target = entry + 2.0 * risk
                    plan = CandidatePlan(cid, "buy", i, entry, stop, target, tag=f"{cid} IFVG Reclaim")
                    if plan.is_valid():
                        plans["buy"].append(plan)
            # Bearish IFVG breakdown
            elif closes[i] < cons_low:
                entry = cons_low + (retest_tol * 0.2 * c_atr)
                stop = cons_high
                risk = stop - entry
                if risk > 0:
                    target = entry - 2.0 * risk
                    plan = CandidatePlan(cid, "sell", i, entry, stop, target, tag=f"{cid} IFVG Reclaim")
                    if plan.is_valid():
                        plans["sell"].append(plan)

    return plans


def generate_footprint_plans(grid_config, feats, price_step=0.01):
    """
    Footprint Proxy (FP01 - FP20).
    Grid params: imbalance_ratio (1.5 - 4.0), exhaustion_div_pct (0.15 - 0.50).
    """
    plans = {"buy": [], "sell": []}
    n = feats.get("n", 0)
    if n < 30:
        return plans

    imbal_ratio = grid_config.param1_val
    div_pct = grid_config.param2_val
    cid = grid_config.config_id

    rvol = feats["rvol"]
    closes, opens = feats["closes"], feats["opens"]
    highs, lows = feats["highs"], feats["lows"]
    atr = feats["atr"]

    for i in range(10, n - 1):
        c_atr = atr[i]
        # Simulated Delta Proxy from candle shape & rvol
        delta_proxy = (closes[i] - opens[i]) * rvol[i]
        
        # Bullish footprint: Price down but high volume absorption (delta divergence)
        if closes[i] < opens[i] and rvol[i] >= imbal_ratio and (opens[i] - closes[i]) < div_pct * c_atr:
            poc_node = lows[i] + 0.382 * (highs[i] - lows[i])
            stop = lows[i] - 0.10 * c_atr
            risk = poc_node - stop
            if risk > 0:
                target = poc_node + 2.0 * risk
                plan = CandidatePlan(cid, "buy", i, poc_node, stop, target, tag=f"{cid} Footprint Bid Delta")
                if plan.is_valid():
                    plans["buy"].append(plan)

        # Bearish footprint: Price up but high volume absorption
        elif closes[i] > opens[i] and rvol[i] >= imbal_ratio and (closes[i] - opens[i]) < div_pct * c_atr:
            poc_node = highs[i] - 0.382 * (highs[i] - lows[i])
            stop = highs[i] + 0.10 * c_atr
            risk = stop - poc_node
            if risk > 0:
                target = poc_node - 2.0 * risk
                plan = CandidatePlan(cid, "sell", i, poc_node, stop, target, tag=f"{cid} Footprint Ask Delta")
                if plan.is_valid():
                    plans["sell"].append(plan)

    return plans


def generate_orb_plans(grid_config, feats, price_step=0.01):
    """
    Opening Range Breakout (OR01 - OR20).
    Grid params: breakout_buffer_atr (0.05 - 0.30), pullback_depth_pct (0.00 - 0.50).
    """
    plans = {"buy": [], "sell": []}
    n = feats.get("n", 0)
    if n < 40:
        return plans

    buffer_atr = grid_config.param1_val
    pb_depth = grid_config.param2_val
    cid = grid_config.config_id

    highs, lows, closes = feats["highs"], feats["lows"], feats["closes"]
    atr = feats["atr"]

    # Use rolling 12 bars as proxy session opening range
    for i in range(24, n - 2, 12):
        c_atr = atr[i]
        orb_high = np.max(highs[i - 12:i])
        orb_low = np.min(lows[i - 12:i])
        orb_range = max(orb_high - orb_low, 0.1 * c_atr)

        # Test subsequent 6 bars for breakout & retest
        for k in range(i, min(i + 6, n - 1)):
            if closes[k] > orb_high + buffer_atr * c_atr:
                entry = orb_high - pb_depth * orb_range
                stop = orb_high - 0.5 * orb_range
                risk = entry - stop
                if risk > 0:
                    target = entry + 2.0 * risk
                    plan = CandidatePlan(cid, "buy", k, entry, stop, target, tag=f"{cid} ORB Long")
                    if plan.is_valid():
                        plans["buy"].append(plan)
                break
            elif closes[k] < orb_low - buffer_atr * c_atr:
                entry = orb_low + pb_depth * orb_range
                stop = orb_low + 0.5 * orb_range
                risk = stop - entry
                if risk > 0:
                    target = entry - 2.0 * risk
                    plan = CandidatePlan(cid, "sell", k, entry, stop, target, tag=f"{cid} ORB Short")
                    if plan.is_valid():
                        plans["sell"].append(plan)
                break

    return plans


def generate_poc_plans(grid_config, feats, price_step=0.01):
    """
    Point of Control (PC01 - PC20).
    Grid params: dist_to_poc_atr (0.10 - 0.50), va_width_pct (0.68 - 0.80).
    """
    plans = {"buy": [], "sell": []}
    n = feats.get("n", 0)
    if n < 30:
        return plans

    dist_atr = grid_config.param1_val
    va_width = grid_config.param2_val
    cid = grid_config.config_id

    highs, lows, closes = feats["highs"], feats["lows"], feats["closes"]
    atr = feats["atr"]

    for i in range(20, n - 1):
        c_atr = atr[i]
        # Approximated POC from rolling median price
        poc_approx = np.median(closes[i - 20:i])
        val = poc_approx - (va_width * 0.5 * c_atr)
        vah = poc_approx + (va_width * 0.5 * c_atr)

        # BUY candidate near VAL or bounce towards POC
        if abs(lows[i] - val) <= dist_atr * c_atr and closes[i] > lows[i]:
            entry = val
            stop = val - 0.20 * c_atr
            risk = entry - stop
            if risk > 0:
                target = entry + 2.0 * risk
                plan = CandidatePlan(cid, "buy", i, entry, stop, target, tag=f"{cid} VAL Bounce")
                if plan.is_valid():
                    plans["buy"].append(plan)

        # SELL candidate near VAH
        if abs(highs[i] - vah) <= dist_atr * c_atr and closes[i] < highs[i]:
            entry = vah
            stop = vah + 0.20 * c_atr
            risk = stop - entry
            if risk > 0:
                target = entry - 2.0 * risk
                plan = CandidatePlan(cid, "sell", i, entry, stop, target, tag=f"{cid} VAH Rejection")
                if plan.is_valid():
                    plans["sell"].append(plan)

    return plans


def generate_zscore_plans(grid_config, feats, price_step=0.01):
    """
    Mean Reversion Z-Score (ZS01 - ZS20).
    Grid params: z_threshold (1.8 - 3.0), rejection_wick_pct (0.30 - 0.60).
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

    # Rolling Z-Score on Close
    for i in range(20, n - 1):
        window = closes[i - 20:i]
        mean = np.mean(window)
        std = np.std(window)
        if std <= 1e-6:
            continue
        z = (closes[i] - mean) / std
        c_atr = atr[i]

        # Oversold Buy
        if z <= -z_thresh and (lower_wicks[i] / ranges[i]) >= min_wick_pct:
            entry = closes[i]
            stop = lows[i] - 0.10 * c_atr
            risk = entry - stop
            if risk > 0:
                target = entry + 2.0 * risk
                plan = CandidatePlan(cid, "buy", i, entry, stop, target, tag=f"{cid} Z-Score Oversold")
                if plan.is_valid():
                    plans["buy"].append(plan)

        # Overbought Sell
        elif z >= z_thresh and (upper_wicks[i] / ranges[i]) >= min_wick_pct:
            entry = closes[i]
            stop = highs[i] + 0.10 * c_atr
            risk = stop - entry
            if risk > 0:
                target = entry - 2.0 * risk
                plan = CandidatePlan(cid, "sell", i, entry, stop, target, tag=f"{cid} Z-Score Overbought")
                if plan.is_valid():
                    plans["sell"].append(plan)

    return plans


def generate_atr_swing_plans(grid_config, feats, price_step=0.01):
    """
    ATR Swing Structure (AS01 - AS20).
    Grid params: trend_velocity_atr (0.5 - 2.5), pullback_atr (1.0 - 2.5).
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
        # Trend slope proxy over 10 bars
        slope = (closes[i] - closes[i - 10]) / (c_atr * 10)

        # Uptrend with healthy pullback
        if slope >= (velocity * 0.1):
            recent_high = np.max(highs[i - 5:i])
            if (recent_high - lows[i]) >= (pb_atr * 0.5 * c_atr):
                entry = lows[i]
                stop = entry - 1.0 * c_atr
                risk = entry - stop
                if risk > 0:
                    target = entry + 2.0 * risk
                    plan = CandidatePlan(cid, "buy", i, entry, stop, target, tag=f"{cid} ATR Swing Pullback")
                    if plan.is_valid():
                        plans["buy"].append(plan)

        # Downtrend with healthy pullback
        elif slope <= -(velocity * 0.1):
            recent_low = np.min(lows[i - 5:i])
            if (highs[i] - recent_low) >= (pb_atr * 0.5 * c_atr):
                entry = highs[i]
                stop = entry + 1.0 * c_atr
                risk = stop - entry
                if risk > 0:
                    target = entry - 2.0 * risk
                    plan = CandidatePlan(cid, "sell", i, entry, stop, target, tag=f"{cid} ATR Swing Pullback")
                    if plan.is_valid():
                        plans["sell"].append(plan)

    return plans


# Dispatcher dictionary mapping strategy key to detector function
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
# HIGH-LEVEL RUNNER FOR COMBINATION ENGINE
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# HIGH-LEVEL RUNNER FOR COMBINATION ENGINE & MONTE CARLO INTEGRATION
# ---------------------------------------------------------------------------

def evaluate_combination_monte_carlo(strategy_key, bars_data, side="both", replays=1000, horizon_bars=48, spread=0.25):
    """
    Simulates Monte Carlo outcomes across all 20 configurations of the selected strategy.
    
    Evaluates:
    - Sample size (N)
    - Fill rate (%)
    - Win rate (%)
    - Expectancy (Avg R)
    - Max Drawdown (Worst R run / 5th percentile)
    """
    from engine_v2 import run_simulation

    grid_results = run_combination_grid(strategy_key, bars_data)
    bars = bars_data.get("bars", []) if isinstance(bars_data, dict) else bars_data

    summary = {
        "strategy_key": strategy_key,
        "strategy_name": grid_results["strategy_name"],
        "replays": replays,
        "horizon_bars": horizon_bars,
        "spread": spread,
        "results": []
    }

    sides_to_eval = ["buy", "sell"] if side == "both" else [side.lower()]

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
                    "signals": 0,
                    "filled": 0,
                    "fill_rate": 0.0,
                    "win_rate": 0.0,
                    "expectancy_r": 0.0,
                    "p5_r": 0.0,
                    "p95_r": 0.0
                }
                continue

            # Evaluate fill & simulate trade for candidates
            filled_plans = []
            for p in candidate_list:
                bar_idx = p["bar_index"]
                entry_target = p["entry"]
                # Check if next 3 bars touched entry
                filled = False
                for step in range(1, 4):
                    if bar_idx + step < len(bars):
                        b = bars[bar_idx + step]
                        low_b = float(b["low"])
                        high_b = float(b["high"])
                        if s == "buy" and low_b <= entry_target:
                            filled = True
                            break
                        elif s == "sell" and high_b >= entry_target:
                            filled = True
                            break
                if filled:
                    filled_plans.append(p)

            fill_rate = round((len(filled_plans) / n_signals) * 100.0, 1) if n_signals > 0 else 0.0
            
            # Select representative sample to simulate (or most recent filled setups)
            sample_plans = filled_plans[-min(5, len(filled_plans)):] if filled_plans else []
            r_returns = []
            win_rates = []

            for p in sample_plans:
                try:
                    sim = run_simulation(
                        entry_price=p["entry"],
                        stop_loss=p["stop"],
                        take_profit=p["target"],
                        side=s,
                        horizon_bars=horizon_bars,
                        replays=replays,
                        spread=spread,
                        bars_data=bars_data
                    )
                    odds = sim.get("odds", {})
                    r_returns.append(odds.get("avg_r", 0.0))
                    win_rates.append(odds.get("target_first_pct", 0.0))
                except Exception:
                    continue

            avg_expectancy = round(float(np.mean(r_returns)), 3) if r_returns else 0.0
            avg_winrate = round(float(np.mean(win_rates)), 1) if win_rates else 0.0

            cfg_summary[s] = {
                "signals": n_signals,
                "filled": len(filled_plans),
                "fill_rate": fill_rate,
                "win_rate": avg_winrate,
                "expectancy_r": avg_expectancy,
            }

        summary["results"].append(cfg_summary)

    return summary


def run_combination_grid(strategy_key, bars_data, price_step=0.01):
    """
    Executes the 20 sensitivity configurations for the chosen strategy.
    Returns:
    {
        "strategy": strategy_key,
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
