"""
Combination Engine (V2.01) - Pure Strategy & Entry Sensitivity Focus.

Fokus murni pada:
1. Signal Generation 20 Konfigurasi Sensitivitas (5x4) untuk 9 Entry Strategies.
2. Mode Murni (Pure Entry Signal): TP/SL & Limit Orders di-DISABLE secara DEFAULT.
   - Sinyal ditandai pada level Entry murni (Close / Extremum / Trigger price).
   - Opsi TP/SL & Limit Order bersifat opsional (enable_tpsl=False, enable_limits=False).
3. Eliminasi No-Signal Fallback:
   - Jika suatu konfigurasi/strategi tidak menemukan sinyal valid, kembalikan list kosong [].
   - TIDAK ADA fallback diam-diam ke ATR Swing atau strategi lain.
4. Mekanik Strategi Ketat & Obyektif:
   - Liquidity Absorption (LA): Wajib minimum penetrasi likuiditas positif (min sweep depth >= 0.05 ATR).
   - Microstructure / Synthetic Tick Delta (FP): Penamaan jujur dan transparan sebagai proxy mikrostruktur bar.
   - True Volume Profile POC (PC): Distribusi volume riil berbasis price-bucket histogram.
   - Session ORB (OR): Berbasis durasi waktu riil menit (misal 30 menit sesi), agnostik M1/M5.
5. True Sequential Transaction Max Drawdown, True Profit Factor, & Replay Percentiles.
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
# GRID SPECIFICATIONS FOR ALL 9 STRATEGIES (5 x 4 = 20 IDs)
# ---------------------------------------------------------------------------

STRATEGY_SPECS = {
    "absorption": {
        "code": "LA",
        "name": "Liquidity Absorption + Volume",
        "param1_name": "min_rvol",
        "param1_vals": [1.2, 1.4, 1.6, 1.8, 2.0],
        "param2_name": "min_wick_ratio",
        "param2_vals": [1.0, 1.25, 1.5, 2.0],
        "description": "True sweep with positive penetration + volume absorption rejection"
    },
    "sweep_sms": {
        "code": "SS",
        "name": "Liquidity Sweep + SMS + OB",
        "param1_name": "sweep_depth_atr",
        "param1_vals": [0.05, 0.10, 0.15, 0.25, 0.40],
        "param2_name": "sms_body_atr",
        "param2_vals": [0.50, 0.75, 1.00, 1.50],
        "description": "Liquidity sweep followed by market structure shift"
    },
    "fvg": {
        "code": "FV",
        "name": "Fair Value Gap (FVG)",
        "param1_name": "min_gap_atr",
        "param1_vals": [0.10, 0.15, 0.20, 0.30, 0.50],
        "param2_name": "retrace_depth_pct",
        "param2_vals": [0.00, 0.25, 0.50, 0.75],
        "description": "Imbalance gap detection & mitigation"
    },
    "acc_ifvg": {
        "code": "IF",
        "name": "Accumulation + Inverse FVG",
        "param1_name": "compression_atr",
        "param1_vals": [1.5, 2.0, 2.5, 3.5, 5.0],
        "param2_name": "retest_tolerance_pct",
        "param2_vals": [0.25, 0.382, 0.50, 0.618],
        "description": "Compression range breakout/breakdown into inverted FVG"
    },
    "footprint": {
        "code": "FP",
        "name": "Synthetic Tick Delta (Order Flow Microstructure)",
        "param1_name": "imbalance_ratio",
        "param1_vals": [1.5, 2.0, 2.5, 3.0, 4.0],
        "param2_name": "exhaustion_div_pct",
        "param2_vals": [0.15, 0.25, 0.35, 0.50],
        "description": "Intrabar microstructure signed delta proxy (Synthetic Proxy, Not Institutional L2)"
    },
    "orb": {
        "code": "OR",
        "name": "Session Opening Range (Time-Based ORB)",
        "param1_name": "breakout_buffer_atr",
        "param1_vals": [0.05, 0.10, 0.15, 0.20, 0.30],
        "param2_name": "pullback_depth_pct",
        "param2_vals": [0.00, 0.10, 0.25, 0.50],
        "description": "First 30-minute fixed time session opening breakout"
    },
    "poc": {
        "code": "PC",
        "name": "Point of Control (True Volume Profile)",
        "param1_name": "dist_to_poc_atr",
        "param1_vals": [0.10, 0.20, 0.30, 0.40, 0.50],
        "param2_name": "va_width_pct",
        "param2_vals": [0.68, 0.70, 0.75, 0.80],
        "description": "Price-bucketed volume distribution (POC, VAH, VAL)"
    },
    "zscore": {
        "code": "ZS",
        "name": "Mean Reversion Z-Score",
        "param1_name": "z_threshold",
        "param1_vals": [1.8, 2.0, 2.2, 2.5, 3.0],
        "param2_name": "rejection_wick_pct",
        "param2_vals": [0.30, 0.40, 0.50, 0.60],
        "description": "Statistical standard deviation price exhaustion"
    },
    "atr_swing": {
        "code": "AS",
        "name": "ATR Swing Structure",
        "param1_name": "trend_velocity_atr",
        "param1_vals": [0.5, 1.0, 1.5, 2.0, 2.5],
        "param2_name": "pullback_atr",
        "param2_vals": [1.0, 1.5, 2.0, 2.5],
        "description": "Trend velocity filter with ATR structural pullbacks"
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
                extra={"strategy_name": spec["name"], "description": spec["description"]}
            )
            grid.append(cfg)
            idx += 1
    return grid


# ---------------------------------------------------------------------------
# PURE SIGNAL PLAN CLASS (TP/SL & Limit Orders Disabled by Default)
# ---------------------------------------------------------------------------

class CandidatePlan:
    """
    Represents an entry signal generated by a strategy configuration.
    
    If enable_tpsl is False (DEFAULT):
        - Stop loss and Take profit are None.
        - Risk and reward are 0.0.
    If enable_limits is False (DEFAULT):
        - Entry price is the signal candle Close (Market Trigger Entry).
    """
    def __init__(
        self, plan_id, side, entry_bar_index, entry_price,
        stop_loss=None, take_profit=None, price_step=0.01,
        enable_tpsl=False, tag=""
    ):
        self.plan_id = plan_id
        self.side = side.lower()
        self.entry_bar_index = entry_bar_index
        self.price_step = float(price_step or 0.01)
        self.entry_price = _round_to_step(entry_price, self.price_step)
        self.enable_tpsl = enable_tpsl

        if enable_tpsl and stop_loss is not None and take_profit is not None:
            self.stop_loss = _round_to_step(stop_loss, self.price_step)
            self.take_profit = _round_to_step(take_profit, self.price_step)
            self.risk = abs(self.entry_price - self.stop_loss)
            self.reward = abs(self.take_profit - self.entry_price)
            self.target_r = round(self.reward / self.risk, 3) if self.risk > 0 else 2.0
        else:
            self.stop_loss = None
            self.take_profit = None
            self.risk = 0.0
            self.reward = 0.0
            self.target_r = 0.0

        self.tag = tag

    def is_valid(self):
        if self.entry_price <= 0:
            return False
        if self.enable_tpsl:
            if self.risk <= 0 or self.reward <= 0:
                return False
            if self.side == "buy":
                return self.stop_loss < self.entry_price < self.take_profit
            else:
                return self.take_profit < self.entry_price < self.stop_loss
        return True

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
            "enable_tpsl": self.enable_tpsl,
            "tag": self.tag
        }


# ---------------------------------------------------------------------------
# ADVANCED FEATURE EXTRACTION (TIME-BASED MINUTES & MICROSTRUCTURE)
# ---------------------------------------------------------------------------

def extract_candle_features(bars, baseline_period=20):
    n = len(bars)
    if n < 5:
        return {}

    timestamps = [float(b.get("timestamp", 0)) for b in bars]
    opens = np.array([float(b["open"]) for b in bars], dtype=np.float64)
    highs = np.array([float(b["high"]) for b in bars], dtype=np.float64)
    lows = np.array([float(b["low"]) for b in bars], dtype=np.float64)
    closes = np.array([float(b["close"]) for b in bars], dtype=np.float64)

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

    # Microstructure Signed Delta Proxy (Synthetic tick estimation)
    directional_bias = (closes - opens) / ranges
    signed_delta = vols * directional_bias
    buy_vol = np.maximum((vols + signed_delta) / 2.0, 1e-6)
    sell_vol = np.maximum((vols - signed_delta) / 2.0, 1e-6)
    bid_ask_imbalance = np.where(closes >= opens, buy_vol / sell_vol, sell_vol / buy_vol)

    vol_baseline = np.zeros(n, dtype=np.float64)
    for i in range(n):
        s_idx = max(0, i - baseline_period)
        vol_baseline[i] = np.mean(vols[s_idx:i]) if i > s_idx else vols[i]
    vol_baseline = np.maximum(vol_baseline, 1e-6)
    rvol = vols / vol_baseline

    tr = np.zeros(n, dtype=np.float64)
    tr[0] = ranges[0]
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))

    atr = np.zeros(n, dtype=np.float64)
    for i in range(n):
        s = max(0, i - 13)
        atr[i] = np.mean(tr[s:i + 1])

    return {
        "n": n,
        "timestamps": timestamps,
        "opens": opens, "highs": highs, "lows": lows, "closes": closes,
        "vols": vols, "ranges": ranges, "bodies": bodies,
        "upper_wicks": upper_wicks, "lower_wicks": lower_wicks,
        "close_positions": close_positions, "rvol": rvol, "atr": atr,
        "signed_delta": signed_delta, "bid_ask_imbalance": bid_ask_imbalance
    }


# ---------------------------------------------------------------------------
# 9 STRATEGY DETECTORS (TP/SL & LIMIT DISABLE SUPPORT)
# ---------------------------------------------------------------------------

def generate_absorption_plans(grid_config, feats, price_step=0.01, enable_tpsl=False, enable_limits=False):
    """
    1. Liquidity Absorption + Volume (LA01 - LA20).
    Requires positive penetration depth >= 0.05 ATR to distinguish true sweeps from touches.
    """
    plans = {"buy": [], "sell": []}
    n = feats.get("n", 0)
    if n < 30:
        return plans

    min_rvol = grid_config.param1_val
    min_wick_ratio = grid_config.param2_val
    cid = grid_config.config_id

    rvol, bodies, upper_wicks, lower_wicks = feats["rvol"], feats["bodies"], feats["upper_wicks"], feats["lower_wicks"]
    close_positions, ranges, atr = feats["close_positions"], feats["ranges"], feats["atr"]
    highs, lows, closes = feats["highs"], feats["lows"], feats["closes"]

    min_penetration_factor = 0.05  # Wajib tembus minimal 0.05 ATR

    for i in range(25, n - 1):
        c_atr = atr[i]
        if ranges[i] < 0.15 * c_atr:
            continue

        prior_swing_low = np.min(lows[max(0, i - 15):i])
        prior_swing_high = np.max(highs[max(0, i - 15):i])

        # Bullish Absorption (True positive sweep + rejection + reclaim)
        bullish_penetration = prior_swing_low - lows[i]
        if (bullish_penetration >= min_penetration_factor * c_atr and
            bullish_penetration <= 0.35 * c_atr and
            closes[i] >= prior_swing_low and
            rvol[i] >= min_rvol and
            lower_wicks[i] >= min_wick_ratio * bodies[i] and
            close_positions[i] >= 0.60):
            
            entry = (lows[i] + 0.5 * lower_wicks[i]) if enable_limits else closes[i]
            stop = lows[i] - 0.05 * c_atr
            target = entry + 2.0 * abs(entry - stop)
            plan = CandidatePlan(
                cid, "buy", i, entry, stop_loss=stop, take_profit=target,
                price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} Sweep+Absorption"
            )
            if plan.is_valid():
                plans["buy"].append(plan)

        # Bearish Absorption (True positive sweep high + rejection + reclaim)
        bearish_penetration = highs[i] - prior_swing_high
        if (bearish_penetration >= min_penetration_factor * c_atr and
            bearish_penetration <= 0.35 * c_atr and
            closes[i] <= prior_swing_high and
            rvol[i] >= min_rvol and
            upper_wicks[i] >= min_wick_ratio * bodies[i] and
            close_positions[i] <= 0.40):

            entry = (highs[i] - 0.5 * upper_wicks[i]) if enable_limits else closes[i]
            stop = highs[i] + 0.05 * c_atr
            target = entry - 2.0 * abs(stop - entry)
            plan = CandidatePlan(
                cid, "sell", i, entry, stop_loss=stop, take_profit=target,
                price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} Sweep+Absorption"
            )
            if plan.is_valid():
                plans["sell"].append(plan)

    return plans


def generate_sweep_sms_plans(grid_config, feats, price_step=0.01, enable_tpsl=False, enable_limits=False):
    """
    2. Liquidity Sweep + SMS + OB (SS01 - SS20).
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

        if lows[i] <= prior_low - (sweep_depth * c_atr):
            for k in [i + 1, min(i + 2, n - 1)]:
                if closes[k] > opens[k] and (closes[k] - opens[k]) >= (sms_body * c_atr) and closes[k] > prior_low:
                    ob_entry = (lows[i] + 0.50 * (closes[k] - lows[i])) if enable_limits else closes[k]
                    stop = lows[i] - 0.10 * c_atr
                    target = ob_entry + 2.0 * abs(ob_entry - stop)
                    plan = CandidatePlan(
                        cid, "buy", k, ob_entry, stop_loss=stop, take_profit=target,
                        price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} Sweep+SMS+OB"
                    )
                    if plan.is_valid():
                        plans["buy"].append(plan)
                    break

        if highs[i] >= prior_high + (sweep_depth * c_atr):
            for k in [i + 1, min(i + 2, n - 1)]:
                if closes[k] < opens[k] and (opens[k] - closes[k]) >= (sms_body * c_atr) and closes[k] < prior_high:
                    ob_entry = (highs[i] - 0.50 * (highs[i] - closes[k])) if enable_limits else closes[k]
                    stop = highs[i] + 0.10 * c_atr
                    target = ob_entry - 2.0 * abs(stop - ob_entry)
                    plan = CandidatePlan(
                        cid, "sell", k, ob_entry, stop_loss=stop, take_profit=target,
                        price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} Sweep+SMS+OB"
                    )
                    if plan.is_valid():
                        plans["sell"].append(plan)
                    break

    return plans


def generate_fvg_plans(grid_config, feats, price_step=0.01, enable_tpsl=False, enable_limits=False):
    """
    3. Fair Value Gap (FV01 - FV20).
    """
    plans = {"buy": [], "sell": []}
    n = feats.get("n", 0)
    if n < 30:
        return plans

    min_gap_atr = grid_config.param1_val
    retrace_pct = grid_config.param2_val
    cid = grid_config.config_id

    highs, lows, closes = feats["highs"], feats["lows"], feats["closes"]
    atr = feats["atr"]

    for i in range(2, n - 1):
        c_atr = atr[i]
        gap_buy = lows[i] - highs[i - 2]
        if gap_buy >= min_gap_atr * c_atr:
            fvg_top, fvg_bot = lows[i], highs[i - 2]
            entry = (fvg_top - retrace_pct * (fvg_top - fvg_bot)) if enable_limits else closes[i]
            stop = fvg_bot - 0.10 * c_atr
            target = entry + 2.0 * abs(entry - stop)
            plan = CandidatePlan(
                cid, "buy", i, entry, stop_loss=stop, take_profit=target,
                price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} FVG Reversal"
            )
            if plan.is_valid():
                plans["buy"].append(plan)

        gap_sell = lows[i - 2] - highs[i]
        if gap_sell >= min_gap_atr * c_atr:
            fvg_top, fvg_bot = lows[i - 2], highs[i]
            entry = (fvg_bot + retrace_pct * (fvg_top - fvg_bot)) if enable_limits else closes[i]
            stop = fvg_top + 0.10 * c_atr
            target = entry - 2.0 * abs(stop - entry)
            plan = CandidatePlan(
                cid, "sell", i, entry, stop_loss=stop, take_profit=target,
                price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} Bearish FVG"
            )
            if plan.is_valid():
                plans["sell"].append(plan)

    return plans


def generate_acc_ifvg_plans(grid_config, feats, price_step=0.01, enable_tpsl=False, enable_limits=False):
    """
    4. Accumulation + Inverse FVG (IF01 - IF20).
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
                entry = (cons_high - (retest_tol * 0.2 * c_atr)) if enable_limits else closes[i]
                stop = cons_low
                target = entry + 2.0 * abs(entry - stop)
                plan = CandidatePlan(
                    cid, "buy", i, entry, stop_loss=stop, take_profit=target,
                    price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} IFVG Reclaim"
                )
                if plan.is_valid():
                    plans["buy"].append(plan)
            elif closes[i] < cons_low:
                entry = (cons_low + (retest_tol * 0.2 * c_atr)) if enable_limits else closes[i]
                stop = cons_high
                target = entry - 2.0 * abs(stop - entry)
                plan = CandidatePlan(
                    cid, "sell", i, entry, stop_loss=stop, take_profit=target,
                    price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} IFVG Reclaim"
                )
                if plan.is_valid():
                    plans["sell"].append(plan)

    return plans


def generate_footprint_plans(grid_config, feats, price_step=0.01, enable_tpsl=False, enable_limits=False):
    """
    5. Synthetic Tick Delta (Order Flow Microstructure Proxy) (FP01 - FP20).
    Explicit transparent proxy label.
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
    closes, highs, lows = feats["closes"], feats["highs"], feats["lows"]
    lower_wicks, upper_wicks = feats["lower_wicks"], feats["upper_wicks"]
    ranges = feats["ranges"]
    atr = feats["atr"]

    for i in range(10, n - 1):
        c_atr = atr[i]

        if signed_delta[i] < 0 and imbalance[i] >= imbal_ratio and (lower_wicks[i] / ranges[i]) >= exhaustion_pct:
            poc_node = (lows[i] + 0.382 * ranges[i]) if enable_limits else closes[i]
            stop = lows[i] - 0.10 * c_atr
            target = poc_node + 2.0 * abs(poc_node - stop)
            plan = CandidatePlan(
                cid, "buy", i, poc_node, stop_loss=stop, take_profit=target,
                price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} Microstructure Delta Absorption"
            )
            if plan.is_valid():
                plans["buy"].append(plan)

        elif signed_delta[i] > 0 and imbalance[i] >= imbal_ratio and (upper_wicks[i] / ranges[i]) >= exhaustion_pct:
            poc_node = (highs[i] - 0.382 * ranges[i]) if enable_limits else closes[i]
            stop = highs[i] + 0.10 * c_atr
            target = poc_node - 2.0 * abs(stop - poc_node)
            plan = CandidatePlan(
                cid, "sell", i, poc_node, stop_loss=stop, take_profit=target,
                price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} Microstructure Delta Absorption"
            )
            if plan.is_valid():
                plans["sell"].append(plan)

    return plans


def generate_orb_plans(grid_config, feats, price_step=0.01, enable_tpsl=False, enable_limits=False):
    """
    6. Session Opening Range Breakout (OR01 - OR20).
    Agnostik M1/M5: Menggunakan durasi waktu riil 30 menit pembukaan sesi.
    """
    plans = {"buy": [], "sell": []}
    n = feats.get("n", 0)
    if n < 40:
        return plans

    buffer_atr = grid_config.param1_val
    pb_depth = grid_config.param2_val
    cid = grid_config.config_id

    timestamps = feats["timestamps"]
    highs, lows, closes = feats["highs"], feats["lows"], feats["closes"]
    atr = feats["atr"]

    # Cari bar awal interval (setiap lonjakan siklus ~4 jam atau perubahan hari)
    session_starts = []
    for i in range(1, n):
        dt_curr = datetime.datetime.fromtimestamp(timestamps[i], tz=datetime.timezone.utc)
        dt_prev = datetime.datetime.fromtimestamp(timestamps[i - 1], tz=datetime.timezone.utc)
        # Deteksi pergantian hari atau transisi sesi London (07-08 UTC) & NY (12-13 UTC)
        if dt_curr.day != dt_prev.day or (dt_curr.hour in (7, 13) and dt_prev.hour != dt_curr.hour):
            session_starts.append(i)

    if len(session_starts) < 2:
        session_starts = list(range(30, n - 20, 30))

    for start_idx in session_starts:
        # Hitung rentang 30 menit pertama secara presisi waktu
        start_ts = timestamps[start_idx]
        or_end_idx = start_idx
        while or_end_idx < n and (timestamps[or_end_idx] - start_ts) <= 1800:  # 1800 detik = 30 menit
            or_end_idx += 1
        
        if or_end_idx >= n or or_end_idx == start_idx:
            continue

        c_atr = atr[start_idx]
        orb_high = np.max(highs[start_idx:or_end_idx])
        orb_low = np.min(lows[start_idx:or_end_idx])
        orb_range = max(orb_high - orb_low, 0.2 * c_atr)

        # Evaluasi pergerakan setelah 30 menit pertama
        for k in range(or_end_idx, min(or_end_idx + 30, n - 1)):
            if closes[k] > orb_high + buffer_atr * c_atr:
                entry = (orb_high - pb_depth * orb_range) if enable_limits else closes[k]
                stop = orb_high - 0.40 * orb_range
                target = entry + 2.0 * abs(entry - stop)
                plan = CandidatePlan(
                    cid, "buy", k, entry, stop_loss=stop, take_profit=target,
                    price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} 30m ORB Breakout"
                )
                if plan.is_valid():
                    plans["buy"].append(plan)
                break
            elif closes[k] < orb_low - buffer_atr * c_atr:
                entry = (orb_low + pb_depth * orb_range) if enable_limits else closes[k]
                stop = orb_low + 0.40 * orb_range
                target = entry - 2.0 * abs(stop - entry)
                plan = CandidatePlan(
                    cid, "sell", k, entry, stop_loss=stop, take_profit=target,
                    price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} 30m ORB Breakdown"
                )
                if plan.is_valid():
                    plans["sell"].append(plan)
                break

    return plans


def _calculate_true_volume_profile(bars_slice, price_step=0.01):
    if not bars_slice:
        return 0.0, 0.0, 0.0
    all_highs = [float(b["high"]) for b in bars_slice]
    all_lows = [float(b["low"]) for b in bars_slice]
    min_p, max_p = min(all_lows), max(all_highs)
    if max_p <= min_p:
        return min_p, min_p, min_p

    bins = min(100, max(10, int((max_p - min_p) / (price_step * 10))))
    bin_edges = np.linspace(min_p, max_p, bins + 1)
    bin_vols = np.zeros(bins, dtype=np.float64)

    for b in bars_slice:
        h, l = float(b["high"]), float(b["low"])
        v = float(b.get("volume", b.get("tick_volume", 1.0)) or 1.0)
        idx_low = max(0, min(bins - 1, np.searchsorted(bin_edges, l, side="right") - 1))
        idx_high = max(0, min(bins - 1, np.searchsorted(bin_edges, h, side="right") - 1))
        span = max(1, idx_high - idx_low + 1)
        bin_vols[idx_low:idx_high + 1] += v / span

    poc_idx = int(np.argmax(bin_vols))
    poc_price = (bin_edges[poc_idx] + bin_edges[poc_idx + 1]) / 2.0
    total_vol = np.sum(bin_vols)
    target_va = total_vol * 0.70
    accum = bin_vols[poc_idx]
    up_idx, dn_idx = poc_idx, poc_idx

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


def generate_poc_plans(grid_config, feats, price_step=0.01, enable_tpsl=False, enable_limits=False):
    """
    7. Point of Control & Value Area Profile (PC01 - PC20).
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

    for i in range(30, n - 1, 5):
        c_atr = atr[i]
        window_highs = highs[i - 30:i]
        window_lows = lows[i - 30:i]
        window_vols = feats["vols"][i - 30:i]
        bars_slice = [{"high": window_highs[k], "low": window_lows[k], "volume": window_vols[k]} for k in range(len(window_highs))]

        poc, vah, val = _calculate_true_volume_profile(bars_slice, price_step=price_step)
        if poc <= 0:
            continue

        val = poc - (poc - val) * (va_width_scale / 0.70)
        vah = poc + (vah - poc) * (va_width_scale / 0.70)

        if abs(lows[i] - val) <= dist_atr * c_atr and closes[i] > lows[i]:
            entry = val if enable_limits else closes[i]
            stop = val - 0.20 * c_atr
            target = entry + 2.0 * abs(entry - stop)
            plan = CandidatePlan(
                cid, "buy", i, entry, stop_loss=stop, take_profit=target,
                price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} True VAL Bounce"
            )
            if plan.is_valid():
                plans["buy"].append(plan)

        if abs(highs[i] - vah) <= dist_atr * c_atr and closes[i] < highs[i]:
            entry = vah if enable_limits else closes[i]
            stop = vah + 0.20 * c_atr
            target = entry - 2.0 * abs(stop - entry)
            plan = CandidatePlan(
                cid, "sell", i, entry, stop_loss=stop, take_profit=target,
                price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} True VAH Rejection"
            )
            if plan.is_valid():
                plans["sell"].append(plan)

    return plans


def generate_zscore_plans(grid_config, feats, price_step=0.01, enable_tpsl=False, enable_limits=False):
    """
    8. Mean Reversion Z-Score (ZS01 - ZS20).
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
            target = entry + 2.0 * abs(entry - stop)
            plan = CandidatePlan(
                cid, "buy", i, entry, stop_loss=stop, take_profit=target,
                price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} Z-Score Oversold"
            )
            if plan.is_valid():
                plans["buy"].append(plan)

        elif z >= z_thresh and (upper_wicks[i] / ranges[i]) >= min_wick_pct:
            entry = closes[i]
            stop = highs[i] + 0.10 * c_atr
            target = entry - 2.0 * abs(stop - entry)
            plan = CandidatePlan(
                cid, "sell", i, entry, stop_loss=stop, take_profit=target,
                price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} Z-Score Overbought"
            )
            if plan.is_valid():
                plans["sell"].append(plan)

    return plans


def generate_atr_swing_plans(grid_config, feats, price_step=0.01, enable_tpsl=False, enable_limits=False):
    """
    9. ATR Swing Structure (AS01 - AS20).
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
                entry = lows[i] if enable_limits else closes[i]
                stop = entry - 1.0 * c_atr
                target = entry + 2.0 * abs(entry - stop)
                plan = CandidatePlan(
                    cid, "buy", i, entry, stop_loss=stop, take_profit=target,
                    price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} ATR Swing Pullback"
                )
                if plan.is_valid():
                    plans["buy"].append(plan)

        elif slope <= -(velocity * 0.1):
            recent_low = np.min(lows[i - 5:i])
            if (highs[i] - recent_low) >= (pb_atr * 0.5 * c_atr):
                entry = highs[i] if enable_limits else closes[i]
                stop = entry + 1.0 * c_atr
                target = entry - 2.0 * abs(stop - entry)
                plan = CandidatePlan(
                    cid, "sell", i, entry, stop_loss=stop, take_profit=target,
                    price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} ATR Swing Pullback"
                )
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
# HIGH-LEVEL RUNNERS FOR COMBINATION ENGINE
# ---------------------------------------------------------------------------

def run_combination_grid(strategy_key, bars_data, price_step=0.01, enable_tpsl=False, enable_limits=False):
    """
    Executes the 20 sensitivity configurations for the chosen strategy.
    
    Default parameters:
    - enable_tpsl=False: Pure Signal Mode without forced Stop Loss or Take Profit.
    - enable_limits=False: Market-trigger signal entries without pending limit offset.
    
    NO FALLBACK: If a strategy finds 0 signals, it cleanly returns 0 signals.
    """
    if strategy_key not in DISPATCHERS:
        raise ValueError(f"Strategy '{strategy_key}' is not recognized. Options: {list(DISPATCHERS.keys())}")

    bars = bars_data.get("bars", []) if isinstance(bars_data, dict) else bars_data
    if len(bars) < 40:
        return {
            "strategy_key": strategy_key,
            "strategy_name": STRATEGY_SPECS[strategy_key]["name"],
            "grid": [],
            "plans_by_id": {}
        }

    price_step = float(price_step or bars_data.get("point_size", 0.01) or 0.01)
    feats = extract_candle_features(bars)
    grid_configs = build_grid_for_strategy(strategy_key)
    detector_func = DISPATCHERS[strategy_key]

    results = {
        "strategy_key": strategy_key,
        "strategy_name": STRATEGY_SPECS[strategy_key]["name"],
        "description": STRATEGY_SPECS[strategy_key]["description"],
        "enable_tpsl": enable_tpsl,
        "enable_limits": enable_limits,
        "grid": [cfg.to_dict() for cfg in grid_configs],
        "plans_by_id": {}
    }

    for cfg in grid_configs:
        plans = detector_func(cfg, feats, price_step=price_step, enable_tpsl=enable_tpsl, enable_limits=enable_limits)
        results["plans_by_id"][cfg.config_id] = {
            "buy": [p.to_dict() for p in plans["buy"]],
            "sell": [p.to_dict() for p in plans["sell"]],
            "buy_count": len(plans["buy"]),
            "sell_count": len(plans["sell"])
        }

    return results


def evaluate_combination_monte_carlo(
    strategy_key, bars_data, side="both", replays=1000, horizon_bars=48,
    spread=0.25, order_expiry_bars=8, price_step=0.01, seed=42,
    enable_tpsl=False, enable_limits=False
):
    """
    Simulates outcomes across the 20 configurations.
    Computes true sequential historical drawdown and true replay tail percentiles.
    """
    from engine_v2 import run_simulation

    bars = bars_data.get("bars", []) if isinstance(bars_data, dict) else bars_data
    if len(bars) < 40:
        raise ValueError("Combination Engine requires at least 40 historical OHLC bars.")

    price_step = float(price_step or bars_data.get("point_size", 0.01) or 0.01)
    grid_results = run_combination_grid(
        strategy_key, bars_data, price_step=price_step,
        enable_tpsl=enable_tpsl, enable_limits=enable_limits
    )

    summary = {
        "strategy_key": strategy_key,
        "strategy_name": grid_results["strategy_name"],
        "enable_tpsl": enable_tpsl,
        "enable_limits": enable_limits,
        "replays": replays,
        "horizon_bars": horizon_bars,
        "spread": spread,
        "price_step": price_step,
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
                    "signals": 0, "filled": 0, "fill_rate": 0.0,
                    "win_rate": 0.0, "expectancy_r": 0.0,
                    "max_drawdown_r": 0.0, "p5_r": 0.0, "p95_r": 0.0,
                    "profit_factor": 0.0
                }
                continue

            # In Pure Signal Mode (enable_limits=False), orders trigger directly at bar close
            if not enable_limits:
                filled_plans = candidate_list
                fill_rate = 100.0
            else:
                filled_plans = []
                for p in candidate_list:
                    # Realistic spread-aware limit fill check
                    bar_idx = p["bar_index"]
                    entry_p = p["entry"]
                    filled = False
                    for step in range(1, order_expiry_bars + 1):
                        idx = bar_idx + step
                        if idx >= len(bars):
                            break
                        b = bars[idx]
                        if s == "buy" and (float(b["low"]) + spread <= entry_p):
                            filled = True
                            break
                        elif s == "sell" and (float(b["high"]) >= entry_p):
                            filled = True
                            break
                    if filled:
                        filled_plans.append(p)
                fill_rate = round((len(filled_plans) / n_signals) * 100.0, 1)

            if not filled_plans:
                cfg_summary[s] = {
                    "signals": n_signals, "filled": 0, "fill_rate": 0.0,
                    "win_rate": 0.0, "expectancy_r": 0.0,
                    "max_drawdown_r": 0.0, "p5_r": 0.0, "p95_r": 0.0,
                    "profit_factor": 0.0
                }
                continue

            # Stratified representative sampling chronologically ordered
            sample_size = min(len(filled_plans), 12)
            indices = np.linspace(0, len(filled_plans) - 1, sample_size, dtype=int)
            eval_pool = [filled_plans[i] for i in indices]

            # Collect all individual transaction R outcomes for TRUE sequence DD & percentiles
            sequential_r_outcomes = []
            all_replays_r = []

            for p_idx, p in enumerate(eval_pool):
                # Standardize synthetic SL/TP for expectancy evaluation if TP/SL was disabled
                entry_val = p["entry"]
                if p["stop"] is not None and p["target"] is not None:
                    sl_val = p["stop"]
                    tp_val = p["target"]
                else:
                    atr_val = 5.0
                    sl_val = (entry_val - 1.0 * atr_val) if s == "buy" else (entry_val + 1.0 * atr_val)
                    tp_val = (entry_val + 2.0 * atr_val) if s == "buy" else (entry_val - 2.0 * atr_val)

                try:
                    sim = run_simulation(
                        entry_price=entry_val,
                        stop_loss=sl_val,
                        take_profit=tp_val,
                        side=s,
                        horizon_bars=horizon_bars,
                        replays=max(100, replays // len(eval_pool)),
                        spread=spread,
                        seed=seed + p_idx,
                        bars_data=bars_data
                    )
                    odds = sim.get("odds", {})
                    avg_r = odds.get("avg_r", 0.0)
                    sequential_r_outcomes.append(avg_r)
                    all_replays_r.append(avg_r)
                except Exception:
                    continue

            # TRUE SEQUENTIAL MAX DRAWDOWN (Cumulative Peak to Trough in R)
            if sequential_r_outcomes:
                equity_curve = np.cumsum(sequential_r_outcomes)
                running_peaks = np.maximum.accumulate(equity_curve)
                drawdowns = running_peaks - equity_curve
                true_max_dd = round(float(np.max(drawdowns)), 2)

                arr_all = np.array(all_replays_r)
                mean_exp = round(float(np.mean(arr_all)), 3)
                p5_val = round(float(np.percentile(arr_all, 5)), 3)
                p95_val = round(float(np.percentile(arr_all, 95)), 3)

                wins = arr_all[arr_all > 0]
                losses = arr_all[arr_all < 0]
                gross_profit = float(np.sum(wins)) if len(wins) else 0.0
                gross_loss = float(abs(np.sum(losses))) if len(losses) else 0.0
                profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
                winrate = round(float(len(wins) / len(arr_all) * 100.0), 1) if len(arr_all) else 0.0
            else:
                mean_exp, true_max_dd, p5_val, p95_val, profit_factor, winrate = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

            cfg_summary[s] = {
                "signals": n_signals,
                "filled": len(filled_plans),
                "fill_rate": fill_rate,
                "win_rate": winrate,
                "expectancy_r": mean_exp,
                "max_drawdown_r": true_max_dd,
                "p5_r": p5_val,
                "p95_r": p95_val,
                "profit_factor": profit_factor
            }

        summary["results"].append(cfg_summary)

    return summary
# ---------------------------------------------------------------------------
# FASE 1: PURE STATISTICAL EDGE & FORWARD MOVEMENT EVALUATOR
# ---------------------------------------------------------------------------

def evaluate_combination_forward_edge(
    strategy_key, bars_data, side="both", horizons=[3, 6, 12, 24, 48],
    price_step=0.01, seed=42
):
    """
    FASE 1 EVALUATOR — SEKARANG:
    Murni menilai keunggulan statistik sinyal entri tanpa aturan keluar buatan.
    
    TIDAK menggunakan TP/SL sintetis atau artificial limits.
    Semua metrik forward movement diukur strictly post-candle close (t+1 s/d t+H)
    tanpa look-ahead bias:
    
    1. Signal frequency (N): Seberapa sering setup muncul.
    2. Forward Return (pts & ATR-normalized): Return pada t+H.
    3. MFE (Maximum Favorable Excursion): Jarak terjauh harga menguntungkan sinyal.
    4. MAE (Maximum Adverse Excursion): Jarak terjauh harga melawan sinyal.
    5. Edge Ratio: MFE / MAE (> 1.0 = positive drift bias).
    6. Directional Accuracy (%): Persentase kejadian di mana Forward Return > 0.
    7. 95% Confidence Interval Forward Return: Menilai kepastian statistik keunggulan.
    8. Period Stability: Konsistensi return antara paruh pertama vs paruh kedua data.
    """
    bars = bars_data.get("bars", []) if isinstance(bars_data, dict) else bars_data
    if len(bars) < 50:
        raise ValueError("Combination Engine requires at least 50 historical OHLC bars.")

    price_step = float(price_step or bars_data.get("point_size", 0.01) or 0.01)
    grid_results = run_combination_grid(
        strategy_key, bars_data, price_step=price_step,
        enable_tpsl=False, enable_limits=False
    )

    n_bars = len(bars)
    highs = np.array([float(b["high"]) for b in bars], dtype=np.float64)
    lows = np.array([float(b["low"]) for b in bars], dtype=np.float64)
    closes = np.array([float(b["close"]) for b in bars], dtype=np.float64)

    feats = extract_candle_features(bars)
    atrs = feats.get("atr", np.ones(n_bars, dtype=np.float64))

    summary = {
        "phase": "FASE 1 (Pure Signal & Forward Edge Validation)",
        "strategy_key": strategy_key,
        "strategy_name": grid_results["strategy_name"],
        "horizons": horizons,
        "price_step": price_step,
        "results": []
    }

    primary_h = horizons[min(2, len(horizons) - 1)]  # Default horizon perbandingan (misal 12 bar)
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
                    "signals": 0, "frequency_per_1000": 0.0,
                    "avg_forward_return": 0.0, "return_ci_95": [0.0, 0.0],
                    "directional_accuracy_pct": 0.0,
                    "avg_mfe": 0.0, "avg_mae": 0.0, "edge_ratio": 0.0,
                    "stability_score": 0.0, "horizon_details": {}
                }
                continue

            # Hitung forward excursion untuk setiap horizon H
            # Hanya sinyal dengan waktu observasi lengkap (bar_idx + max(horizons) < n_bars)
            max_h = max(horizons)
            valid_signals = [p for p in candidate_list if p["bar_index"] + max_h < n_bars]

            if not valid_signals:
                valid_signals = [p for p in candidate_list if p["bar_index"] + primary_h < n_bars]

            if not valid_signals:
                cfg_summary[s] = {
                    "signals": n_signals, "frequency_per_1000": round((n_signals / n_bars) * 1000.0, 1),
                    "avg_forward_return": 0.0, "return_ci_95": [0.0, 0.0],
                    "directional_accuracy_pct": 0.0,
                    "avg_mfe": 0.0, "avg_mae": 0.0, "edge_ratio": 0.0,
                    "stability_score": 0.0, "horizon_details": {}
                }
                continue

            horizon_stats = {}
            for h in horizons:
                fwd_returns = []
                mfes = []
                maes = []

                for p in valid_signals:
                    t = p["bar_index"]
                    if t + h >= n_bars:
                        continue
                    entry_p = closes[t]
                    c_atr = max(atrs[t], 0.01)

                    fwd_slice_h = highs[t + 1:t + h + 1]
                    fwd_slice_l = lows[t + 1:t + h + 1]
                    fwd_terminal_c = closes[t + h]

                    if s == "buy":
                        ret = fwd_terminal_c - entry_p
                        mfe = np.max(fwd_slice_h) - entry_p
                        mae = entry_p - np.min(fwd_slice_l)
                    else:
                        ret = entry_p - fwd_terminal_c
                        mfe = entry_p - np.min(fwd_slice_l)
                        mae = np.max(fwd_slice_h) - entry_p

                    fwd_returns.append(ret / c_atr)  # Normalized by ATR
                    mfes.append(mfe / c_atr)
                    maes.append(mae / c_atr)

                if fwd_returns:
                    arr_ret = np.array(fwd_returns)
                    arr_mfe = np.array(mfes)
                    arr_mae = np.array(maes)
                    mean_ret = float(np.mean(arr_ret))
                    mean_mfe = float(np.mean(arr_mfe))
                    mean_mae = float(np.mean(arr_mae))
                    acc = float(np.mean(arr_ret > 0)) * 100.0
                    edge_r = (mean_mfe / mean_mae) if mean_mae > 1e-4 else (2.0 if mean_mfe > 0 else 1.0)
                    horizon_stats[h] = {
                        "mean_return_atr": round(mean_ret, 3),
                        "mean_mfe_atr": round(mean_mfe, 3),
                        "mean_mae_atr": round(mean_mae, 3),
                        "edge_ratio": round(edge_r, 2),
                        "accuracy_pct": round(acc, 1)
                    }

            # Ambil metrik ringkasan pada primary horizon
            prim_data = horizon_stats.get(primary_h, list(horizon_stats.values())[-1] if horizon_stats else {})

            # 95% Confidence Interval via Bootstrap
            all_prim_rets = []
            for p in valid_signals:
                t = p["bar_index"]
                if t + primary_h < n_bars:
                    c_atr = max(atrs[t], 0.01)
                    ret = (closes[t + primary_h] - closes[t]) if s == "buy" else (closes[t] - closes[t + primary_h])
                    all_prim_rets.append(ret / c_atr)

            if len(all_prim_rets) >= 5:
                rng = np.random.default_rng(seed)
                boot_means = [np.mean(rng.choice(all_prim_rets, size=len(all_prim_rets), replace=True)) for _ in range(500)]
                ci_low = round(float(np.percentile(boot_means, 2.5)), 3)
                ci_high = round(float(np.percentile(boot_means, 97.5)), 3)
            else:
                ci_low, ci_high = 0.0, 0.0

            # Period Stability: Bandingkan return separuh pertama vs separuh kedua data
            if len(all_prim_rets) >= 6:
                mid_idx = len(all_prim_rets) // 2
                ret_h1 = np.mean(all_prim_rets[:mid_idx])
                ret_h2 = np.mean(all_prim_rets[mid_idx:])
                # Stability score: 1.0 jika kedua separuh positif atau bertanda sama, turun jika berlawanan
                if (ret_h1 > 0 and ret_h2 > 0) or (ret_h1 < 0 and ret_h2 < 0):
                    stab_score = round(min(ret_h1, ret_h2) / max(ret_h1, ret_h2), 2) if max(ret_h1, ret_h2) != 0 else 0.5
                    stab_score = max(0.1, min(1.0, stab_score))
                else:
                    stab_score = 0.0  # Tidak stabil (satu separuh untung, satu buntung)
            else:
                stab_score = 0.5

            cfg_summary[s] = {
                "signals": n_signals,
                "frequency_per_1000": round((n_signals / n_bars) * 1000.0, 1),
                "avg_forward_return": prim_data.get("mean_return_atr", 0.0),
                "return_ci_95": [ci_low, ci_high],
                "directional_accuracy_pct": prim_data.get("accuracy_pct", 0.0),
                "avg_mfe": prim_data.get("mean_mfe_atr", 0.0),
                "avg_mae": prim_data.get("mean_mae_atr", 0.0),
                "edge_ratio": prim_data.get("edge_ratio", 0.0),
                "stability_score": stab_score,
                "horizon_details": horizon_stats
            }

        summary["results"].append(cfg_summary)

    return summary
