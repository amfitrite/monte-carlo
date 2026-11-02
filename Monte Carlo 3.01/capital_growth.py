"""
capital_growth.py - Sequential Capital Growth Simulator for Monte Carlo Analysis

Calculates path-dependent equity curves, geometric growth, maximum drawdown,
consecutive loss streaks, recovery times, and probability of ruin from
sequential trade outcome probabilities.
"""

import numpy as np


def simulate_capital_growth(
    initial_capital=10000.0,
    risk_pct=0.01,
    p_tp=0.50,
    p_sl=0.40,
    p_timeout=0.10,
    target_r=2.0,
    timeout_r=0.0,
    costs_r=0.02,
    replays=500,
    horizon_trades=50,
    compounding=True,
    max_drawdown_limit=0.20,
    ruin_threshold=0.50,
    seed=42
):
    """
    Simulates sequential capital growth over a specified trade horizon.

    Parameters:
    -----------
    initial_capital : float
        Starting balance (e.g. 10000.0).
    risk_pct : float
        Fraction of equity risked per trade (e.g. 0.01 = 1%).
    p_tp : float
        Probability of hitting Take Profit first (0.0 to 1.0).
    p_sl : float
        Probability of hitting Stop Loss first (0.0 to 1.0).
    p_timeout : float
        Probability of trade timeout / unresolved at horizon (0.0 to 1.0).
    target_r : float
        Reward-to-risk ratio on Take Profit (e.g. 2.0).
    timeout_r : float
        Average R outcome for trades reaching timeout (mark-to-market).
    costs_r : float
        Execution friction (spread, commission, slippage) expressed in R units (e.g. 0.02 R).
    replays : int
        Number of independent sequential capital trajectories to simulate.
    horizon_trades : int
        Number of sequential trades per trajectory.
    compounding : bool
        If True, position size scales with current equity; if False, fixed risk dollar based on initial capital.
    max_drawdown_limit : float
        Maximum acceptable peak-to-trough drawdown fraction (e.g. 0.20 = 20%).
    ruin_threshold : float
        Fraction of initial capital below which an account is considered ruined (e.g. 0.50 = 50% loss).
        If ruin_threshold < 1.0, threshold dollar = initial_capital * ruin_threshold.
        If ruin_threshold >= 1.0, threshold dollar = ruin_threshold.
    seed : int
        Deterministic random seed for reproducibility.

    Returns:
    --------
    dict containing:
        - final_equity_median, final_equity_p5, final_equity_p95
        - net_profit_median, total_return_pct_median
        - geometric_growth_rate (per trade)
        - max_drawdown_pct_median, max_drawdown_pct_worst
        - max_consecutive_losses_median, max_consecutive_losses_worst
        - avg_recovery_trades
        - probability_of_ruin_pct
        - passes_drawdown_constraint (bool)
        - passes_ruin_constraint (bool)
        - net_expectancy_r
        - resolved_win_rate_pct
        - total_win_rate_pct
        - equity_curve_median (list of float of length horizon_trades + 1)
        - distribution_final_equity: dict(p5, p25, p50, p75, p95)
    """
    initial_capital = float(max(1.0, initial_capital))
    risk_pct = float(max(0.0001, min(0.50, risk_pct)))
    replays = int(max(10, min(5000, replays)))
    horizon_trades = int(max(5, min(500, horizon_trades)))

    # Normalize outcome probabilities
    probs = np.array([max(0.0, float(p_tp)), max(0.0, float(p_sl)), max(0.0, float(p_timeout))], dtype=np.float64)
    total_p = np.sum(probs)
    if total_p <= 0:
        probs = np.array([0.5, 0.5, 0.0], dtype=np.float64)
    else:
        probs /= total_p

    p_tp_norm, p_sl_norm, p_timeout_norm = probs

    # Net R outcomes after execution friction
    net_tp_r = float(target_r) - float(costs_r)
    net_sl_r = -1.0 - float(costs_r)
    net_timeout_r = float(timeout_r) - float(costs_r)

    # Calculate theoretical expectancy per trade in R
    net_expectancy_r = (
        p_tp_norm * net_tp_r +
        p_sl_norm * net_sl_r +
        p_timeout_norm * net_timeout_r
    )

    resolved_sum = p_tp_norm + p_sl_norm
    resolved_wr = (p_tp_norm / resolved_sum * 100.0) if resolved_sum > 0 else 0.0
    total_wr = p_tp_norm * 100.0

    # Determine ruin dollar threshold
    if ruin_threshold < 1.0:
        dollar_ruin = initial_capital * float(ruin_threshold)
    else:
        dollar_ruin = float(ruin_threshold)
    dollar_ruin = max(0.0, min(initial_capital, dollar_ruin))

    rng = np.random.default_rng(seed)

    # Vectorized simulation of trade sequences
    # Outcome values: 0 -> TP, 1 -> SL, 2 -> Timeout
    r_map = np.array([net_tp_r, net_sl_r, net_timeout_r], dtype=np.float64)
    outcomes = rng.choice(3, size=(replays, horizon_trades), p=probs)
    trade_r_matrix = r_map[outcomes]  # shape: (replays, horizon_trades)

    # Initialize equity trajectories
    # Shape: (replays, horizon_trades + 1)
    equity_paths = np.empty((replays, horizon_trades + 1), dtype=np.float64)
    equity_paths[:, 0] = initial_capital

    if compounding:
        for t in range(horizon_trades):
            cur_eq = equity_paths[:, t]
            deltas = cur_eq * risk_pct * trade_r_matrix[:, t]
            equity_paths[:, t + 1] = np.maximum(0.0, cur_eq + deltas)
    else:
        risk_dollar = initial_capital * risk_pct
        cum_r = np.cumsum(trade_r_matrix, axis=1)
        equity_paths[:, 1:] = np.maximum(0.0, initial_capital + (cum_r * risk_dollar))

    # Calculate Maximum Drawdown for each path
    running_peaks = np.maximum.accumulate(equity_paths, axis=1)
    drawdowns = (running_peaks - equity_paths) / np.maximum(1e-9, running_peaks)
    max_dds = np.max(drawdowns, axis=1)  # shape: (replays,)

    # Probability of Ruin
    min_equity_per_path = np.min(equity_paths, axis=1)
    ruined_paths = min_equity_per_path <= dollar_ruin
    prob_ruin_pct = float(np.mean(ruined_paths) * 100.0)

    # Consecutive loss streaks vectorized across steps
    is_loss = trade_r_matrix < 0
    # Fast streak check across 50 sample paths
    max_streaks = []
    for r in range(min(50, replays)):
        cur = 0
        mx = 0
        for l in is_loss[r]:
            if l:
                cur += 1
                if cur > mx:
                    mx = cur
            else:
                cur = 0
        max_streaks.append(mx)
    consec_loss_median = int(np.median(max_streaks)) if max_streaks else 0
    consec_loss_worst = int(np.max(max_streaks)) if max_streaks else 0

    # Median Equity Curve for display
    curve_median = np.quantile(equity_paths, 0.50, axis=0)

    # Recovery Time on median curve
    rec_times = []
    peak_val = curve_median[0]
    peak_idx = 0
    for t in range(1, len(curve_median)):
        if curve_median[t] >= peak_val:
            if t - peak_idx > 1:
                rec_times.append(t - peak_idx)
            peak_val = curve_median[t]
            peak_idx = t
    avg_recovery_trades = float(np.mean(rec_times)) if rec_times else 0.0

    # Final Equity & Distributions
    final_equities = equity_paths[:, -1]
    fe_p5, fe_p25, fe_p50, fe_p75, fe_p95 = np.quantile(
        final_equities, [0.05, 0.25, 0.50, 0.75, 0.95]
    )

    net_profit_median = float(fe_p50 - initial_capital)
    total_return_pct_median = float((fe_p50 - initial_capital) / initial_capital * 100.0)

    # Geometric Growth Rate per trade
    if fe_p50 > 0:
        geometric_growth_rate = float((fe_p50 / initial_capital) ** (1.0 / horizon_trades) - 1.0)
    else:
        geometric_growth_rate = -1.0

    max_dd_median = float(np.median(max_dds) * 100.0)
    max_dd_worst = float(np.quantile(max_dds, 0.95) * 100.0)

    passes_dd = (max_dd_median / 100.0) <= float(max_drawdown_limit)
    passes_ruin = (prob_ruin_pct / 100.0) <= 0.05

    return {
        "final_equity_median": round(float(fe_p50), 2),
        "final_equity_p5": round(float(fe_p5), 2),
        "final_equity_p95": round(float(fe_p95), 2),
        "net_profit_median": round(net_profit_median, 2),
        "total_return_pct_median": round(total_return_pct_median, 2),
        "geometric_growth_rate": round(geometric_growth_rate, 5),
        "geometric_growth_pct": round(geometric_growth_rate * 100.0, 3),
        "max_drawdown_pct_median": round(max_dd_median, 2),
        "max_drawdown_pct_worst": round(max_dd_worst, 2),
        "max_consecutive_losses_median": consec_loss_median,
        "max_consecutive_losses_worst": consec_loss_worst,
        "avg_recovery_trades": round(avg_recovery_trades, 1),
        "probability_of_ruin_pct": round(prob_ruin_pct, 2),
        "passes_drawdown_constraint": bool(passes_dd),
        "passes_ruin_constraint": bool(passes_ruin),
        "net_expectancy_r": round(float(net_expectancy_r), 4),
        "resolved_win_rate_pct": round(float(resolved_wr), 2),
        "total_win_rate_pct": round(float(total_wr), 2),
        "equity_curve_median": [round(float(x), 2) for x in curve_median.tolist()],
        "distribution_final_equity": {
            "p5": round(float(fe_p5), 2),
            "p25": round(float(fe_p25), 2),
            "p50": round(float(fe_p50), 2),
            "p75": round(float(fe_p75), 2),
            "p95": round(float(fe_p95), 2)
        }
    }
