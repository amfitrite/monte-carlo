"""
Unit tests for Phase 2: TP/SL Optimization and WR/RR Oriented Capital Growth.
"""

import unittest
import numpy as np
import analyzer
import capital_growth


class TestCapitalGrowthAndTPSLOptimization(unittest.TestCase):
    def setUp(self):
        # Generate 200 synthetic M5 bars for deterministic testing
        base_price = 2700.0
        self.bars = []
        rng = np.random.default_rng(12345)
        cur = base_price
        for i in range(250):
            step = float(rng.normal(0.0, 1.5))
            o = cur
            h = o + abs(float(rng.normal(1.0, 0.5)))
            l = o - abs(float(rng.normal(1.0, 0.5)))
            c = o + step
            h = max(h, o, c)
            l = min(l, o, c)
            cur = c
            self.bars.append({
                "timestamp": 1700000000 + i * 300,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 100.0
            })
        self.bars_data = {
            "bars": self.bars,
            "point_size": 0.01,
            "interval_minutes": 5
        }

    def test_capital_growth_compounding_math(self):
        """Test sequential compounding vs linear math."""
        # 100% win rate test with target_r = 1.0, risk 1%, 10 trades
        res = capital_growth.simulate_capital_growth(
            initial_capital=10000.0,
            risk_pct=0.01,
            p_tp=1.0,
            p_sl=0.0,
            p_timeout=0.0,
            target_r=1.0,
            costs_r=0.0,
            replays=10,
            horizon_trades=10,
            compounding=True,
            seed=42
        )
        # (1 + 0.01)^10 * 10000 = ~11046.22
        expected_compound = 10000.0 * (1.01 ** 10)
        self.assertAlmostEqual(res["final_equity_median"], expected_compound, places=1)
        self.assertGreater(res["geometric_growth_pct"], 0.99)
        self.assertEqual(res["probability_of_ruin_pct"], 0.0)
        self.assertEqual(res["max_consecutive_losses_median"], 0)

    def test_capital_growth_linear_math(self):
        """Test fixed dollar non-compounding capital growth."""
        res = capital_growth.simulate_capital_growth(
            initial_capital=10000.0,
            risk_pct=0.01,
            p_tp=1.0,
            p_sl=0.0,
            p_timeout=0.0,
            target_r=1.0,
            costs_r=0.0,
            replays=10,
            horizon_trades=10,
            compounding=False,
            seed=42
        )
        # 10000 + 10 * (10000 * 0.01) = 11000
        self.assertEqual(res["final_equity_median"], 11000.0)

    def test_ruin_probability_detection(self):
        """Ensure ruin threshold detects severe losing streaks."""
        # High loss probability: 90% SL
        res = capital_growth.simulate_capital_growth(
            initial_capital=10000.0,
            risk_pct=0.05,
            p_tp=0.10,
            p_sl=0.90,
            p_timeout=0.0,
            target_r=1.0,
            costs_r=0.0,
            replays=500,
            horizon_trades=50,
            ruin_threshold=0.50, # 50% loss threshold
            seed=42
        )
        self.assertGreater(res["probability_of_ruin_pct"], 50.0)
        self.assertFalse(res["passes_ruin_constraint"])
        self.assertLess(res["geometric_growth_rate"], 0.0)

    def test_timeout_trades_not_discarded(self):
        """Confirm unresolved / timeout trades contribute to statistics with mark-to-market."""
        # 50% timeout with negative mark-to-market (-0.2 R)
        res = capital_growth.simulate_capital_growth(
            initial_capital=10000.0,
            risk_pct=0.01,
            p_tp=0.40,
            p_sl=0.10,
            p_timeout=0.50,
            target_r=2.0,
            timeout_r=-0.2,
            costs_r=0.02,
            replays=200,
            horizon_trades=50,
            seed=42
        )
        self.assertEqual(res["resolved_win_rate_pct"], 80.0)  # 40 / (40 + 10) = 80%
        self.assertEqual(res["total_win_rate_pct"], 40.0)     # 40% of all trades
        # Expectancy: 0.4*(2 - 0.02) + 0.1*(-1 - 0.02) + 0.5*(-0.2 - 0.02) = 0.792 - 0.102 - 0.11 = 0.58
        self.assertAlmostEqual(res["net_expectancy_r"], 0.58, places=2)

    def test_geometry_validation_buy_and_sell(self):
        """Test strict geometry validation for BUY (stop < entry < target) and SELL (target < entry < stop)."""
        self.assertTrue(analyzer._validate_geometry("buy", 2700.0, 2690.0, 2720.0))
        self.assertFalse(analyzer._validate_geometry("buy", 2700.0, 2710.0, 2720.0)) # stop > entry
        self.assertFalse(analyzer._validate_geometry("buy", 2700.0, 2690.0, 2695.0)) # target < entry

        self.assertTrue(analyzer._validate_geometry("sell", 2700.0, 2710.0, 2680.0))
        self.assertFalse(analyzer._validate_geometry("sell", 2700.0, 2690.0, 2680.0)) # stop < entry
        self.assertFalse(analyzer._validate_geometry("sell", 2700.0, 2710.0, 2720.0)) # target > entry

    def test_rr_sweep_candidates_generation(self):
        """Verify that rr_candidates sweep generates 1:1, 1:1.5, 1:2, 1:3, 1:4, 1:5, 1:7, 1:10 plans."""
        cfg = analyzer._normalize_tpsl_config(
            mode="rr_sweep",
            bars_data=self.bars_data,
            point_size=0.01,
            rr_sl_points=1000
        )
        self.assertEqual(cfg["mode"], "risk_reward")
        self.assertEqual(cfg["rr_candidates"], [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0])

        metrics = analyzer.calculate_market_metrics(self.bars, period=48)
        entries = [2700.0]
        plans, count, capped = analyzer._build_candidate_plans("buy", entries, metrics, 5, cfg)
        self.assertEqual(len(plans), 8)
        self.assertEqual(plans[0]["target_rr"], 1.0)
        self.assertEqual(plans[-1]["target_rr"], 10.0)

    def test_three_quality_dimensions_separated(self):
        """Check that entry_quality, trade_quality, and capital_quality are distinctly reported."""
        res = analyzer.find_dual_recommendations(
            self.bars_data,
            horizon_bars=12,
            replays=100,
            engine_mode="legacy",
            strategy="atr_swing"
        )
        self.assertIn("entry_quality", res["buy"])
        self.assertIn("trade_quality", res["buy"])
        self.assertIn("capital_quality", res["buy"])
        self.assertIn("walk_forward_validation", res["buy"])

        # Check entry quality fields
        eq = res["buy"]["entry_quality"]
        self.assertIn("historical_touch_probability_pct", eq)
        self.assertIn("median_bars_to_touch", eq)

        # Check trade quality fields
        tq = res["buy"]["trade_quality"]
        self.assertIn("resolved_win_rate_pct", tq)
        self.assertIn("target_rr", tq)
        self.assertIn("net_expectancy_r", tq)

        # Check capital quality fields
        cq = res["buy"]["capital_quality"]
        self.assertIn("geometric_growth_pct", cq)
        self.assertIn("final_equity_median", cq)
        self.assertIn("max_drawdown_pct_median", cq)
        self.assertIn("probability_of_ruin_pct", cq)
        self.assertIn("equity_curve", cq)

    def test_wr_oriented_vs_rr_oriented_profiling(self):
        """Verify that WR Oriented and RR Oriented apply distinct ranking priorities."""
        # Run WR oriented
        res_wr = analyzer.find_dual_recommendations(
            self.bars_data,
            horizon_bars=12,
            replays=100,
            optimization_profile="wr_oriented",
            candidate_count=5
        )
        # Run RR oriented
        res_rr = analyzer.find_dual_recommendations(
            self.bars_data,
            horizon_bars=12,
            replays=100,
            optimization_profile="rr_oriented",
            candidate_count=5
        )
        self.assertEqual(res_wr["buy"]["recommendation"]["optimization_profile"], "wr_oriented")
        self.assertEqual(res_rr["buy"]["recommendation"]["optimization_profile"], "rr_oriented")
        self.assertEqual(res_wr["buy"]["recommendation"]["ranking_metric"], "wr_expectancy_growth")
        self.assertEqual(res_rr["buy"]["recommendation"]["ranking_metric"], "geometric_capital_growth")

    def test_negative_expectancy_never_recommended(self):
        """Verify that a setup with negative expectancy is never marked as a recommended viable candidate."""
        # Craft a dummy result with 99% WR but negative expectancy due to huge loss on SL
        dummy_result = {
            "odds": {"target_first_pct": 99.0, "stop_first_pct": 1.0, "neither_pct": 0.0, "avg_r": -0.5, "breakeven_pct": 0.0},
            "plan": {"entry": 2700.0, "stop": 2600.0, "target": 2701.0, "side": "buy", "target_r": 0.01, "risk_dollar": 100.0}
        }
        touch = {"touch_probability_pct": 100.0, "samples": 50, "median_bars_to_touch": 1}
        cfg = {"optimization_profile": "wr_oriented", "costs_r": 0.05}
        score = analyzer._rank_score(dummy_result, touch, cfg)
        # Gate constraint flag must be 0 (rejected) because net expectancy <= 0
        gate = score[0]
        self.assertEqual(gate, 0)



    def test_quant_three_tiers_presence(self):
        """Verify presence and structure of Three Tiers of Quant Output."""
        res = analyzer.find_dual_recommendations(
            self.bars_data,
            horizon_bars=12,
            replays=50,
            candidate_count=5,
            optimization_profile="rr_oriented",
        )
        self.assertIn("candidate_rankings", res)
        self.assertIn("equity_growth_rankings", res)
        self.assertIn("best_recommendation", res)
        self.assertIn("quant_tiers", res)

        cand_ranks = res["candidate_rankings"]
        eq_ranks = res["equity_growth_rankings"]
        best_rec = res["best_recommendation"]

        self.assertIsInstance(cand_ranks, list)
        self.assertGreater(len(cand_ranks), 0)
        self.assertIsInstance(eq_ranks, list)
        self.assertGreater(len(eq_ranks), 0)

        # Check sorting of equity growth rankings for viable slice
        viable_growths = [c.get("geometric_growth_pct", 0.0) for c in eq_ranks if c.get("net_expectancy_r", 0.0) > 0]
        for i in range(len(viable_growths) - 1):
            self.assertGreaterEqual(viable_growths[i], viable_growths[i+1] - 1e-6)

        # Check best recommendation direction matches best_direction
        self.assertIn(best_rec["direction"], ["BUY", "SELL", "NO TRADE", "EQUAL"])
        self.assertEqual(res["best_direction"], best_rec["direction"])

    def test_rr_oriented_best_direction_consistent_with_growth(self):
        """Verify that in RR-oriented mode, best_direction selects the candidate with higher geometric growth."""
        res = analyzer.find_dual_recommendations(
            self.bars_data,
            horizon_bars=12,
            replays=50,
            candidate_count=5,
            optimization_profile="rr_oriented",
        )
        best_dir = res["best_direction"]
        best_rec = res["best_recommendation"]
        self.assertEqual(best_dir, best_rec["direction"])
        self.assertEqual(best_rec["optimization_profile"], "rr_oriented")

        if best_dir in ("BUY", "SELL"):
            side_key = best_dir.lower()
            side_data = res[side_key]
            self.assertEqual(side_data["recommendation"]["optimization_profile"], "rr_oriented")
            self.assertIsNotNone(best_rec["selected_plan"])
            self.assertEqual(best_rec["selected_plan"]["side"].lower(), side_key.lower())

    def test_wr_oriented_best_direction_consistent_with_winrate(self):
        """Verify that in WR-oriented mode, best_direction and best_recommendation align with win rate."""
        res = analyzer.find_dual_recommendations(
            self.bars_data,
            horizon_bars=12,
            replays=50,
            candidate_count=5,
            optimization_profile="wr_oriented",
        )
        best_dir = res["best_direction"]
        best_rec = res["best_recommendation"]
        self.assertEqual(best_dir, best_rec["direction"])
        self.assertEqual(best_rec["optimization_profile"], "wr_oriented")

        if best_dir in ("BUY", "SELL"):
            side_key = best_dir.lower()
            side_data = res[side_key]
            self.assertEqual(side_data["recommendation"]["optimization_profile"], "wr_oriented")
            self.assertIsNotNone(best_rec["selected_plan"])
            self.assertEqual(best_rec["selected_plan"]["side"].lower(), side_key.lower())


if __name__ == "__main__":
    unittest.main()
