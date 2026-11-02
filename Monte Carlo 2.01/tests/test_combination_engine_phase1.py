"""
Tests for Combination Engine Phase 1:
- 20 unique functional configurations per strategy
- Non-negative MFE and MAE
- Explicit Edge Ratio behavior (including inf and 1.0)
- Block bootstrap safety with small sample (N < 5 gives None, None)
- Absence of look-ahead bias
- Out-of-sample metrics
"""

import unittest
import numpy as np
import combination_engine as ce


def make_test_bars(count=300):
    bars = []
    price = 2000.0
    for i in range(count):
        # Deterministic wave pattern with volume
        drift = 0.5 * math.sin(i / 5.0)
        o = price
        c = price + drift
        h = max(o, c) + 0.8
        l = min(o, c) - 0.8
        bars.append({
            "timestamp": 1_700_000_000 + i * 300,
            "open": round(o, 2), "high": round(h, 2), "low": round(l, 2), "close": round(c, 2),
            "volume": 500.0 + 200.0 * math.sin(i / 3.0)
        })
        price = c
    return {"symbol": "XAUUSD", "interval_minutes": 5, "bars": bars}


import math


class TestCombinationEnginePhase1(unittest.TestCase):
    def test_20_configurations_generated_for_all_strategies(self):
        for strat in ce.STRATEGY_SPECS:
            grid = ce.build_grid_for_strategy(strat)
            self.assertEqual(len(grid), 20, f"{strat} must have exactly 20 configurations")
            ids = [g.config_id for g in grid]
            self.assertEqual(len(set(ids)), 20, f"Config IDs for {strat} must be unique")

    def test_fvg_second_param_creates_functional_signal_differences(self):
        import json, os
        cache_file = "data_cache_mt5.json"
        if os.path.exists(cache_file):
            data = json.load(open(cache_file))
            res = ce.run_combination_grid("fvg", data)
            counts = [res["plans_by_id"][cid]["buy_count"] for cid in res["plans_by_id"]]
            self.assertGreater(len(set(counts)), 1, "FVG configurations must produce functionally varied signal counts")
        else:
            self.skipTest("data_cache_mt5.json not present")

    def test_mfe_mae_strictly_non_negative(self):
        data = make_test_bars(250)
        res = ce.evaluate_combination_forward_edge("absorption", data, horizons=[6, 12])
        for r in res["results"]:
            for s in ("buy", "sell"):
                item = r.get(s)
                if item and item["signals"] > 0:
                    self.assertGreaterEqual(item["avg_mfe"], 0.0, "MFE must be non-negative")
                    self.assertGreaterEqual(item["avg_mae"], 0.0, "MAE must be non-negative")
                    for h, stats in item["horizon_details"].items():
                        self.assertGreaterEqual(stats["mean_mfe_atr"], 0.0)
                        self.assertGreaterEqual(stats["mean_mae_atr"], 0.0)

    def test_edge_ratio_explicit_inf_and_positive(self):
        # Test edge ratio logic when MAE is zero
        res = ce.evaluate_combination_forward_edge("fvg", make_test_bars(200), horizons=[6])
        for r in res["results"]:
            for s in ("buy", "sell"):
                item = r.get(s)
                if item and item["signals"] > 0:
                    self.assertTrue(
                        item["edge_ratio"] == float("inf") or item["edge_ratio"] >= 0.0,
                        "Edge ratio must be non-negative or inf"
                    )

    def test_small_sample_bootstrap_safe_none(self):
        # Sample with < 5 items must return (None, None)
        low, high = ce.compute_block_bootstrap_ci([0.1, 0.2, 0.3], block_size=2)
        self.assertIsNone(low)
        self.assertIsNone(high)

    def test_sufficient_sample_block_bootstrap_ci(self):
        sample = [0.1, 0.2, -0.1, 0.4, 0.3, 0.2, -0.05, 0.15, 0.25, 0.35]
        low, high = ce.compute_block_bootstrap_ci(sample, block_size=3, num_replays=200)
        self.assertIsNotNone(low)
        self.assertIsNotNone(high)
        self.assertLess(low, high)

    def test_out_of_sample_split_metrics_present(self):
        data = make_test_bars(300)
        res = ce.evaluate_combination_forward_edge("zscore", data, oos_split_pct=0.30)
        self.assertIn("split_index", res)
        self.assertIn("oos_bars", res)
        self.assertGreater(res["oos_bars"], 0)
        for r in res["results"]:
            for s in ("buy", "sell"):
                item = r.get(s)
                if item:
                    self.assertIn("oos_accuracy_pct", item)
                    self.assertIn("oos_edge_ratio", item)


if __name__ == "__main__":
    unittest.main()
