"""
Combination Engine (V2.01) - Quantitative Alpha & Entry Strategy Engine.

FASE 1: PURE ENTRY ALPHA & FORWARD EDGE VALIDATION
- Evaluasi strictly post-candle close (t+1 s/d t+H) tanpa look-ahead bias
- 9 Strategi x 20 Konfigurasi Sensitivitas (180 Variasi) dievaluasi independen (BUY & SELL terpisah)
- Parameter kedua berfungsi sebagai FILTER SINYAL RIIL (bukan sekadar pending limit offset)
- Non-negative MFE & MAE dengan penanganan Edge Ratio eksplit:
    MFE = max(0.0, max(High) - Close_t)
    MAE = max(0.0, Close_t - min(Low))
    Edge Ratio = MFE / MAE (inf jika MAE == 0 dan MFE > 0; 1.0 jika keduanya 0)
- True IFVG: Compression -> FVG Formation -> Displacement Inversion -> Retest Zone Confirmation
- Stationary / Block Bootstrap untuk menangani overlapping autocorrelation forward return
- Penanganan sampel kecil aman: jika N < 5, CI mengeluarkan [None, None]
- Walk-Forward / Out-of-Sample (OOS) data split untuk mengeliminasi selection bias
- Label jujur dan transparan untuk Synthetic Volume & Microstructure Proxies
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
        "description": "True sweep with positive penetration (>=0.05 ATR) + volume absorption rejection"
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
        "param2_name": "min_retrace_confirm_pct",
        "param2_vals": [0.10, 0.25, 0.50, 0.75],
        "description": "Imbalance gap with mandatory retracement confirmation depth"
    },
    "acc_ifvg": {
        "code": "IF",
        "name": "Accumulation + Inverse FVG",
        "param1_name": "compression_atr",
        "param1_vals": [1.5, 2.0, 2.5, 3.5, 5.0],
        "param2_name": "retest_depth_pct",
        "param2_vals": [0.20, 0.382, 0.50, 0.618],
        "description": "Compression range into FVG inversion with confirmed retest bounce"
    },
    "footprint": {
        "code": "FP",
        "name": "Synthetic Intrabar Tick-Delta Proxy",
        "param1_name": "imbalance_ratio",
        "param1_vals": [1.5, 2.0, 2.5, 3.0, 4.0],
        "param2_name": "exhaustion_div_pct",
        "param2_vals": [0.15, 0.25, 0.35, 0.50],
        "description": "Synthetic tick delta proxy from OHLC close/open ratio (Not institutional L2/L3 order book)"
    },
    "orb": {
        "code": "OR",
        "name": "Session Opening Range (Time-Based ORB)",
        "param1_name": "breakout_buffer_atr",
        "param1_vals": [0.05, 0.10, 0.15, 0.20, 0.30],
        "param2_name": "pullback_retest_pct",
        "param2_vals": [0.10, 0.25, 0.50, 0.75],
        "description": "First 30-minute fixed time session opening breakout with confirmed pullback retest"
    },
    "poc": {
        "code": "PC",
        "name": "Point of Control (OHLC Volume Distribution Proxy)",
        "param1_name": "dist_to_poc_atr",
        "param1_vals": [0.10, 0.20, 0.30, 0.40, 0.50],
        "param2_name": "va_width_pct",
        "param2_vals": [0.68, 0.70, 0.75, 0.80],
        "description": "Price-bucketed volume distribution proxy from OHLC bars"
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
# CANDIDATE PLAN CLASS
# ---------------------------------------------------------------------------

class CandidatePlan:
    """Represents an entry signal generated strictly at candle close."""
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
# ADVANCED FEATURE EXTRACTION
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
# 9 STRATEGY DETECTORS (FUNCTIONALLY UNIQUE 20 SENSITIVITIES)
# ---------------------------------------------------------------------------

def generate_absorption_plans(grid_config, feats, price_step=0.01, enable_tpsl=False, enable_limits=False):
    """
    1. Liquidity Absorption + Volume (LA01 - LA20).
    Requires positive penetration depth >= 0.05 ATR.
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
    min_penetration_factor = 0.05

    for i in range(25, n - 1):
        c_atr = atr[i]
        if ranges[i] < 0.15 * c_atr:
            continue

        prior_swing_low = np.min(lows[max(0, i - 15):i])
        prior_swing_high = np.max(highs[max(0, i - 15):i])

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
    Parameter 2 is now a FUNCTIONAL SIGNAL FILTER: min_retrace_confirm_pct.
    Signal only triggers when subsequent bar confirms retracement into the gap by >= min_retrace_confirm_pct.
    """
    plans = {"buy": [], "sell": []}
    n = feats.get("n", 0)
    if n < 30:
        return plans

    min_gap_atr = grid_config.param1_val
    min_retrace_pct = grid_config.param2_val
    cid = grid_config.config_id

    highs, lows, closes = feats["highs"], feats["lows"], feats["closes"]
    atr = feats["atr"]

    for i in range(2, n - 2):
        c_atr = atr[i]
        # Bullish FVG
        gap_buy = lows[i] - highs[i - 2]
        if gap_buy >= min_gap_atr * c_atr:
            fvg_top, fvg_bot = lows[i], highs[i - 2]
            retrace_threshold = fvg_top - (min_retrace_pct * gap_buy)
            # Check if next 1-3 bars confirmed retracement to retrace_threshold
            for k in range(i + 1, min(i + 4, n)):
                if lows[k] <= retrace_threshold and closes[k] >= fvg_bot:
                    entry = retrace_threshold if enable_limits else closes[k]
                    stop = fvg_bot - 0.10 * c_atr
                    target = entry + 2.0 * abs(entry - stop)
                    plan = CandidatePlan(
                        cid, "buy", k, entry, stop_loss=stop, take_profit=target,
                        price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} FVG Confirmed Retrace {int(min_retrace_pct*100)}%"
                    )
                    if plan.is_valid():
                        plans["buy"].append(plan)
                    break

        # Bearish FVG
        gap_sell = lows[i - 2] - highs[i]
        if gap_sell >= min_gap_atr * c_atr:
            fvg_top, fvg_bot = lows[i - 2], highs[i]
            retrace_threshold = fvg_bot + (min_retrace_pct * gap_sell)
            for k in range(i + 1, min(i + 4, n)):
                if highs[k] >= retrace_threshold and closes[k] <= fvg_top:
                    entry = retrace_threshold if enable_limits else closes[k]
                    stop = fvg_top + 0.10 * c_atr
                    target = entry - 2.0 * abs(stop - entry)
                    plan = CandidatePlan(
                        cid, "sell", k, entry, stop_loss=stop, take_profit=target,
                        price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} FVG Confirmed Retrace {int(min_retrace_pct*100)}%"
                    )
                    if plan.is_valid():
                        plans["sell"].append(plan)
                    break

    return plans


def generate_acc_ifvg_plans(grid_config, feats, price_step=0.01, enable_tpsl=False, enable_limits=False):
    """
    4. Accumulation + Inverse FVG (IF01 - IF20).
    TRUE MECHANIC:
    - Step 1: Accumulation / Compression of preceding bars within compression_atr.
    - Step 2: FVG forms and then gets violated/inverted (Inverse FVG).
    - Step 3: Retest penetrates IFVG zone by >= retest_depth_pct and closes back out (Trigger Signal).
    """
    plans = {"buy": [], "sell": []}
    n = feats.get("n", 0)
    if n < 35:
        return plans

    comp_width = grid_config.param1_val
    retest_depth_pct = grid_config.param2_val
    cid = grid_config.config_id

    highs, lows, closes = feats["highs"], feats["lows"], feats["closes"]
    atr = feats["atr"]

    for i in range(12, n - 4):
        c_atr = atr[i]
        cons_high = np.max(highs[i - 10:i])
        cons_low = np.min(lows[i - 10:i])
        if (cons_high - cons_low) > comp_width * c_atr:
            continue

        # Check for prior Bearish FVG inverted into Bullish IFVG
        # Bearish FVG: Low[i-2] > High[i]
        gap = lows[i - 2] - highs[i]
        if gap >= 0.10 * c_atr:
            ifvg_top, ifvg_bot = lows[i - 2], highs[i]
            # Inversion: Bar i+1 closes above ifvg_top
            if closes[i + 1] > ifvg_top:
                # Retest: Subsequent bars retest inside IFVG zone
                for k in range(i + 2, min(i + 5, n)):
                    penetration_target = ifvg_top - retest_depth_pct * (ifvg_top - ifvg_bot)
                    if lows[k] <= penetration_target and closes[k] >= ifvg_bot:
                        entry = penetration_target if enable_limits else closes[k]
                        stop = ifvg_bot - 0.10 * c_atr
                        target = entry + 2.0 * abs(entry - stop)
                        plan = CandidatePlan(
                            cid, "buy", k, entry, stop_loss=stop, take_profit=target,
                            price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} True IFVG Retest {int(retest_depth_pct*100)}%"
                        )
                        if plan.is_valid():
                            plans["buy"].append(plan)
                        break

        # Check for prior Bullish FVG inverted into Bearish IFVG
        gap_bull = lows[i] - highs[i - 2]
        if gap_bull >= 0.10 * c_atr:
            ifvg_top, ifvg_bot = lows[i], highs[i - 2]
            if closes[i + 1] < ifvg_bot:
                for k in range(i + 2, min(i + 5, n)):
                    penetration_target = ifvg_bot + retest_depth_pct * (ifvg_top - ifvg_bot)
                    if highs[k] >= penetration_target and closes[k] <= ifvg_top:
                        entry = penetration_target if enable_limits else closes[k]
                        stop = ifvg_top + 0.10 * c_atr
                        target = entry - 2.0 * abs(stop - entry)
                        plan = CandidatePlan(
                            cid, "sell", k, entry, stop_loss=stop, take_profit=target,
                            price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} True IFVG Retest {int(retest_depth_pct*100)}%"
                        )
                        if plan.is_valid():
                            plans["sell"].append(plan)
                        break

    return plans


def generate_footprint_plans(grid_config, feats, price_step=0.01, enable_tpsl=False, enable_limits=False):
    """
    5. Synthetic Intrabar Tick-Delta Proxy (FP01 - FP20).
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
                price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} Synthetic Delta Absorption"
            )
            if plan.is_valid():
                plans["buy"].append(plan)

        elif signed_delta[i] > 0 and imbalance[i] >= imbal_ratio and (upper_wicks[i] / ranges[i]) >= exhaustion_pct:
            poc_node = (highs[i] - 0.382 * ranges[i]) if enable_limits else closes[i]
            stop = highs[i] + 0.10 * c_atr
            target = poc_node - 2.0 * abs(stop - poc_node)
            plan = CandidatePlan(
                cid, "sell", i, poc_node, stop_loss=stop, take_profit=target,
                price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} Synthetic Delta Absorption"
            )
            if plan.is_valid():
                plans["sell"].append(plan)

    return plans


def generate_orb_plans(grid_config, feats, price_step=0.01, enable_tpsl=False, enable_limits=False):
    """
    6. Session Opening Range Breakout (OR01 - OR20).
    Parameter 2 is now a FUNCTIONAL SIGNAL FILTER: pullback_retest_pct.
    Signal only triggers when subsequent bar confirms pullback retest onto ORB boundary.
    """
    plans = {"buy": [], "sell": []}
    n = feats.get("n", 0)
    if n < 40:
        return plans

    buffer_atr = grid_config.param1_val
    retest_pct = grid_config.param2_val
    cid = grid_config.config_id

    timestamps = feats["timestamps"]
    highs, lows, closes = feats["highs"], feats["lows"], feats["closes"]
    atr = feats["atr"]

    session_starts = []
    for i in range(1, n):
        dt_curr = datetime.datetime.fromtimestamp(timestamps[i], tz=datetime.timezone.utc)
        dt_prev = datetime.datetime.fromtimestamp(timestamps[i - 1], tz=datetime.timezone.utc)
        if dt_curr.day != dt_prev.day or (dt_curr.hour in (7, 13) and dt_prev.hour != dt_curr.hour):
            session_starts.append(i)

    if len(session_starts) < 2:
        session_starts = list(range(30, n - 20, 30))

    for start_idx in session_starts:
        start_ts = timestamps[start_idx]
        or_end_idx = start_idx
        while or_end_idx < n and (timestamps[or_end_idx] - start_ts) <= 1800:
            or_end_idx += 1
        
        if or_end_idx >= n or or_end_idx == start_idx:
            continue

        c_atr = atr[start_idx]
        orb_high = np.max(highs[start_idx:or_end_idx])
        orb_low = np.min(lows[start_idx:or_end_idx])
        orb_range = max(orb_high - orb_low, 0.2 * c_atr)

        # Look for breakout, then require pullback retest confirmation
        for k in range(or_end_idx, min(or_end_idx + 25, n - 2)):
            # Bullish ORB Breakout
            if closes[k] > orb_high + buffer_atr * c_atr:
                retest_level = orb_high - (retest_pct * 0.5 * orb_range)
                for m in range(k + 1, min(k + 5, n)):
                    if lows[m] <= retest_level and closes[m] >= orb_high - 0.40 * orb_range:
                        entry = retest_level if enable_limits else closes[m]
                        stop = orb_high - 0.40 * orb_range
                        target = entry + 2.0 * abs(entry - stop)
                        plan = CandidatePlan(
                            cid, "buy", m, entry, stop_loss=stop, take_profit=target,
                            price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} 30m ORB Retest {int(retest_pct*100)}%"
                        )
                        if plan.is_valid():
                            plans["buy"].append(plan)
                        break
                break

            # Bearish ORB Breakdown
            elif closes[k] < orb_low - buffer_atr * c_atr:
                retest_level = orb_low + (retest_pct * 0.5 * orb_range)
                for m in range(k + 1, min(k + 5, n)):
                    if highs[m] >= retest_level and closes[m] <= orb_low + 0.40 * orb_range:
                        entry = retest_level if enable_limits else closes[m]
                        stop = orb_low + 0.40 * orb_range
                        target = entry - 2.0 * abs(stop - entry)
                        plan = CandidatePlan(
                            cid, "sell", m, entry, stop_loss=stop, take_profit=target,
                            price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} 30m ORB Retest {int(retest_pct*100)}%"
                        )
                        if plan.is_valid():
                            plans["sell"].append(plan)
                        break
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
                price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} VAL Rebound Proxy"
            )
            if plan.is_valid():
                plans["buy"].append(plan)

        if abs(highs[i] - vah) <= dist_atr * c_atr and closes[i] < highs[i]:
            entry = vah if enable_limits else closes[i]
            stop = vah + 0.20 * c_atr
            target = entry - 2.0 * abs(stop - entry)
            plan = CandidatePlan(
                cid, "sell", i, entry, stop_loss=stop, take_profit=target,
                price_step=price_step, enable_tpsl=enable_tpsl, tag=f"{cid} VAH Rejection Proxy"
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


# ---------------------------------------------------------------------------
# FASE 1: PURE STATISTICAL EDGE & FORWARD MOVEMENT EVALUATOR
# ---------------------------------------------------------------------------

def compute_block_bootstrap_ci(data_series, block_size=5, num_replays=500, rng=None):
    """
    Stationary Block Bootstrap to safely calculate 95% Confidence Interval
    for autocorrelated forward return series without breaking time structure.
    If sample size < 5, returns (None, None) to avoid false certainty of [0, 0].
    """
    n = len(data_series)
    if n < 5:
        return None, None

    if rng is None:
        rng = np.random.default_rng(42)

    arr = np.asarray(data_series, dtype=np.float64)
    num_blocks = int(math.ceil(n / block_size))
    bootstrap_means = np.empty(num_replays, dtype=np.float64)

    for r in range(num_replays):
        sample = []
        for _ in range(num_blocks):
            start = rng.integers(0, max(1, n - block_size + 1))
            sample.extend(arr[start:start + block_size])
        bootstrap_means[r] = np.mean(sample[:n])

    ci_low = round(float(np.percentile(bootstrap_means, 2.5)), 3)
    ci_high = round(float(np.percentile(bootstrap_means, 97.5)), 3)
    return ci_low, ci_high


def evaluate_combination_forward_edge(
    strategy_key, bars_data, side="both", horizons=[3, 6, 12, 24, 48],
    price_step=0.01, seed=42, oos_split_pct=0.30
):
    """
    FASE 1 EVALUATOR:
    - Pure Entry Alpha Validation (Zero TP/SL Bias)
    - Strictly Post-Close Forward Excursion (t+1 s/d t+H)
    - Non-negative MFE/MAE: max(0.0, ...)
    - Explicit Edge Ratio (inf if MAE==0 and MFE>0)
    - Block Bootstrap for Overlapping Autocorrelated Returns
    - Safe CI: (None, None) when N < 5
    - Walk-Forward Out-of-Sample (OOS) validation metrics
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

    # In-Sample vs Out-of-Sample Split Index
    split_idx = int(n_bars * (1.0 - max(0.10, min(0.50, float(oos_split_pct)))))

    summary = {
        "phase": "FASE 1 (Pure Signal & Forward Edge Validation)",
        "strategy_key": strategy_key,
        "strategy_name": grid_results["strategy_name"],
        "horizons": horizons,
        "split_index": split_idx,
        "oos_bars": n_bars - split_idx,
        "price_step": price_step,
        "results": []
    }

    primary_h = horizons[min(2, len(horizons) - 1)]  # 12 bar default
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
                    "signals": 0, "frequency_per_1000": 0.0,
                    "avg_forward_return": 0.0, "return_ci_95": [None, None],
                    "directional_accuracy_pct": 0.0,
                    "avg_mfe": 0.0, "avg_mae": 0.0, "edge_ratio": 0.0,
                    "stability_score": 0.0, "oos_accuracy_pct": 0.0, "oos_edge_ratio": 0.0,
                    "horizon_details": {}
                }
                continue

            max_h = max(horizons)
            valid_signals = [p for p in candidate_list if p["bar_index"] + max_h < n_bars]
            if not valid_signals:
                valid_signals = [p for p in candidate_list if p["bar_index"] + primary_h < n_bars]

            if not valid_signals:
                cfg_summary[s] = {
                    "signals": n_signals, "frequency_per_1000": round((n_signals / n_bars) * 1000.0, 1),
                    "avg_forward_return": 0.0, "return_ci_95": [None, None],
                    "directional_accuracy_pct": 0.0,
                    "avg_mfe": 0.0, "avg_mae": 0.0, "edge_ratio": 0.0,
                    "stability_score": 0.0, "oos_accuracy_pct": 0.0, "oos_edge_ratio": 0.0,
                    "horizon_details": {}
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

                    # Non-Negative MFE & MAE definition
                    if s == "buy":
                        ret = fwd_terminal_c - entry_p
                        mfe = max(0.0, float(np.max(fwd_slice_h) - entry_p))
                        mae = max(0.0, float(entry_p - np.min(fwd_slice_l)))
                    else:
                        ret = entry_p - fwd_terminal_c
                        mfe = max(0.0, float(entry_p - np.min(fwd_slice_l)))
                        mae = max(0.0, float(np.max(fwd_slice_h) - entry_p))

                    fwd_returns.append(ret / c_atr)
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

                    # Explicit Edge Ratio logic
                    if mean_mae > 1e-4:
                        edge_r = round(mean_mfe / mean_mae, 2)
                    elif mean_mfe > 0:
                        edge_r = float("inf")
                    else:
                        edge_r = 1.0

                    horizon_stats[h] = {
                        "mean_return_atr": round(mean_ret, 3),
                        "mean_mfe_atr": round(mean_mfe, 3),
                        "mean_mae_atr": round(mean_mae, 3),
                        "edge_ratio": edge_r,
                        "accuracy_pct": round(acc, 1)
                    }

            prim_data = horizon_stats.get(primary_h, list(horizon_stats.values())[-1] if horizon_stats else {})

            # Primary returns for Block Bootstrap & Stability
            all_prim_rets = []
            is_returns = []
            oos_returns = []
            oos_mfes = []
            oos_maes = []

            for p in valid_signals:
                t = p["bar_index"]
                if t + primary_h < n_bars:
                    c_atr = max(atrs[t], 0.01)
                    ret = (closes[t + primary_h] - closes[t]) if s == "buy" else (closes[t] - closes[t + primary_h])
                    norm_ret = ret / c_atr
                    all_prim_rets.append(norm_ret)
                    if t < split_idx:
                        is_returns.append(norm_ret)
                    else:
                        oos_returns.append(norm_ret)
                        fwd_h = highs[t + 1:t + primary_h + 1]
                        fwd_l = lows[t + 1:t + primary_h + 1]
                        if s == "buy":
                            oos_mfes.append(max(0.0, float(np.max(fwd_h) - closes[t])) / c_atr)
                            oos_maes.append(max(0.0, float(closes[t] - np.min(fwd_l))) / c_atr)
                        else:
                            oos_mfes.append(max(0.0, float(closes[t] - np.min(fwd_l))) / c_atr)
                            oos_maes.append(max(0.0, float(np.max(fwd_h) - closes[t])) / c_atr)

            # Block Bootstrap Confidence Interval
            ci_low, ci_high = compute_block_bootstrap_ci(all_prim_rets, block_size=5, num_replays=500, rng=rng)

            # Period Stability Score (In-Sample vs Out-of-Sample consistency)
            if is_returns and oos_returns:
                is_mean = float(np.mean(is_returns))
                oos_mean = float(np.mean(oos_returns))
                if (is_mean > 0 and oos_mean > 0) or (is_mean < 0 and oos_mean < 0):
                    stab_score = round(min(is_mean, oos_mean) / max(is_mean, oos_mean), 2) if max(is_mean, oos_mean) != 0 else 0.5
                    stab_score = max(0.1, min(1.0, stab_score))
                else:
                    stab_score = 0.0
                oos_acc = round(float(np.mean(np.array(oos_returns) > 0)) * 100.0, 1)
                m_mfe = float(np.mean(oos_mfes)) if oos_mfes else 0.0
                m_mae = float(np.mean(oos_maes)) if oos_maes else 0.0
                oos_edge = round(m_mfe / m_mae, 2) if m_mae > 1e-4 else (float("inf") if m_mfe > 0 else 1.0)
            else:
                stab_score = 0.5
                oos_acc = prim_data.get("accuracy_pct", 0.0)
                oos_edge = prim_data.get("edge_ratio", 0.0)

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
                "oos_accuracy_pct": oos_acc,
                "oos_edge_ratio": oos_edge,
                "horizon_details": horizon_stats
            }

        summary["results"].append(cfg_summary)

    return summary
