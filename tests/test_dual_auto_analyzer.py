import unittest
from unittest.mock import patch
import analyzer


def make_bars(count=260):
    bars = []
    price = 2000.0
    for i in range(count):
        # Deterministic, valid OHLC sequence with a mild oscillation.
        drift = 0.08 if (i // 12) % 2 == 0 else -0.05
        o = price
        c = price + drift
        h = max(o, c) + 0.7
        l = min(o, c) - 0.7
        bars.append({
            "timestamp": 1_700_000_000 + i * 300,
            "open": o, "high": h, "low": l, "close": c
        })
        price = c
    return {"symbol": "XAUUSD", "interval_minutes": 5, "bars": bars}


class DualAutoSearchTests(unittest.TestCase):
    def test_generates_multiple_limit_candidates_for_both_sides(self):
        data = make_bars()
        metrics = analyzer.calculate_market_metrics(data["bars"])
        buy = analyzer._candidate_entries("buy", metrics)
        sell = analyzer._candidate_entries("sell", metrics)
        self.assertGreaterEqual(len(buy), 2)
        self.assertGreaterEqual(len(sell), 2)
        self.assertTrue(all(x < metrics["current_price"] for x in buy))
        self.assertTrue(all(x > metrics["current_price"] for x in sell))

    def test_auto_analyzer_runs_end_to_end_with_legacy_engine(self):
        result = analyzer.find_dual_recommendations(
            make_bars(), horizon_bars=4, replays=100, engine_mode="legacy"
        )
        self.assertIn(result["best_direction"], ("BUY", "SELL", "EQUAL", "NO TRADE"))
        self.assertEqual(result["buy"]["plan"]["order_type"], "LIMIT")
        self.assertEqual(result["sell"]["plan"]["order_type"], "LIMIT")
        self.assertIn("target_r", result["buy"]["plan"])
        self.assertIn("entry_fill_probability", result["buy"]["plan"])
        self.assertIn("entry_touch_probability_pct", result["buy"]["plan"])
        self.assertIn("fill_adjusted_simulated_avg_r", result["buy"]["plan"])

    def test_fixed_points_keep_exact_user_distances_for_buy_and_sell(self):
        data = make_bars()
        metrics = analyzer.calculate_market_metrics(data["bars"])
        for side in ("buy", "sell"):
            entry = metrics["current_price"] - 0.5 if side == "buy" else metrics["current_price"] + 0.5
            plan = analyzer._build_point_plan(side, entry, 2000, 1000, 0.01, 5)
            if side == "buy":
                self.assertAlmostEqual(plan["take_profit"] - plan["entry_price"], 20.0, places=6)
                self.assertAlmostEqual(plan["entry_price"] - plan["stop_loss"], 10.0, places=6)
            else:
                self.assertAlmostEqual(plan["entry_price"] - plan["take_profit"], 20.0, places=6)
                self.assertAlmostEqual(plan["stop_loss"] - plan["entry_price"], 10.0, places=6)
            self.assertEqual(plan["target_rr"], 2.0)

    def test_fixed_mode_runs_and_marks_result(self):
        result = analyzer.find_dual_recommendations(
            make_bars(), horizon_bars=4, replays=100, engine_mode="legacy",
            tpsl_mode="fixed", point_size=0.01,
            fixed_tp_points=2000, fixed_sl_points=1000
        )
        self.assertEqual(result["tpsl_config"]["mode"], "fixed")
        for side in ("buy", "sell"):
            plan = result[side]["plan"]
            self.assertEqual(plan["tp_points"], 2000)
            self.assertEqual(plan["sl_points"], 1000)
            self.assertEqual(plan["point_size"], 0.01)
            self.assertEqual(plan["target_rr"], 2.0)

    def test_range_mode_searches_configured_grid(self):
        with patch.object(analyzer, "_run_one") as mocked, \
             patch.object(analyzer, "_estimate_entry_touch", return_value={
                 "touch_probability_pct": 80.0, "touches": 80, "samples": 100,
                 "median_bars_to_touch": 2.0, "distance_atr": 0.5
             }):
            def fake_run(plan, bars_data, horizon_bars, replays, spread, seed,
                         projection_mode, tie_break, seasonality, engine_mode):
                risk = abs(plan["entry_price"] - plan["stop_loss"])
                reward = abs(plan["take_profit"] - plan["entry_price"])
                target_r = reward / risk
                return {
                    "plan": {"side": plan["side"].upper(), "entry": plan["entry_price"],
                             "stop": plan["stop_loss"], "target": plan["take_profit"],
                             "target_r": target_r, "replays": replays},
                    "odds": {"avg_r": 0.25, "target_first_pct": 55.0,
                             "stop_first_pct": 25.0, "neither_pct": 20.0,
                             "breakeven_pct": 40.0},
                    "verdict": "test", "verdict_notes": [],
                    "fan_data": {"step_bars": [0, 1]}, "sample_paths": []
                }
            mocked.side_effect = fake_run
            result = analyzer.find_dual_recommendations(
                make_bars(), horizon_bars=12, replays=100,
                tpsl_mode="range", point_size=0.01,
                tp_min_points=1000, tp_max_points=2000, tp_step_points=1000,
                sl_min_points=500, sl_max_points=1000, sl_step_points=500
            )
        self.assertEqual(result["tpsl_config"]["mode"], "range")
        self.assertEqual(result["search"]["buy_candidates_scanned"], 20)
        self.assertEqual(result["search"]["sell_candidates_scanned"], 20)
        self.assertGreater(mocked.call_count, 20)
        self.assertIn(result["buy"]["plan"]["tp_points"], (1000, 2000))
        self.assertIn(result["buy"]["plan"]["sl_points"], (500, 1000))

    def test_range_grid_rejects_excessive_combinations(self):
        with self.assertRaisesRegex(ValueError, "maximum is 20"):
            analyzer.find_dual_recommendations(
                make_bars(), tpsl_mode="range", point_size=0.01,
                tp_min_points=100, tp_max_points=1000, tp_step_points=100,
                sl_min_points=100, sl_max_points=1000, sl_step_points=100
            )

    def test_fixed_mode_requires_valid_point_size(self):
        with self.assertRaisesRegex(ValueError, "point_size"):
            analyzer.find_dual_recommendations(
                make_bars(), tpsl_mode="fixed", point_size=0,
                fixed_tp_points=2000, fixed_sl_points=1000
            )

    def test_auto_analyzer_runs_end_to_end_with_v2_engine(self):
        result = analyzer.find_dual_recommendations(
            make_bars(), horizon_bars=4, replays=100, engine_mode="v2"
        )
        self.assertEqual(result["engine_mode"], "v2")
        self.assertIn("ambiguous_pct", result["buy"]["odds"])
        self.assertEqual(result["sell"]["plan"]["order_type"], "LIMIT")

    def test_auto_analyzer_ranks_candidates_and_returns_no_fill_claim(self):
        def fake_run(plan, bars_data, horizon_bars, replays, spread, seed,
                     projection_mode, tie_break, seasonality, engine_mode):
            is_buy = plan["side"] == "buy"
            avg_r = 0.35 if is_buy else 0.15
            risk = abs(plan["entry_price"] - plan["stop_loss"])
            reward = abs(plan["take_profit"] - plan["entry_price"])
            return {
                "plan": {
                    "side": plan["side"].upper(),
                    "entry": plan["entry_price"],
                    "stop": plan["stop_loss"],
                    "target": plan["take_profit"],
                    "target_r": reward / risk,
                    "replays": replays
                },
                "odds": {
                    "avg_r": avg_r,
                    "target_first_pct": 55.0,
                    "stop_first_pct": 25.0,
                    "neither_pct": 20.0,
                    "breakeven_pct": 40.0
                },
                "verdict": "test",
                "verdict_notes": [],
                "fan_data": {"step_bars": [0, 1]},
                "sample_paths": []
            }

        with patch.object(analyzer, "_run_one", side_effect=fake_run) as mocked, \
             patch.object(analyzer, "_estimate_entry_touch", return_value={
                 "touch_probability_pct": 75.0, "touches": 75, "samples": 100,
                 "median_bars_to_touch": 3.0, "distance_atr": 0.5
             }):
            result = analyzer.find_dual_recommendations(
                make_bars(), horizon_bars=12, replays=100,
                engine_mode="legacy"
            )
        self.assertEqual(result["best_direction"], "BUY")
        self.assertGreater(result["search"]["buy_candidates_scanned"], 1)
        self.assertGreater(result["search"]["sell_candidates_scanned"], 1)
        self.assertIsNone(result["buy"]["plan"]["entry_fill_probability"])
        self.assertEqual(result["buy"]["plan"]["entry_touch_probability_pct"], 75.0)
        self.assertIn("historical OHLC touch proxy", result["buy"]["plan"]["entry_fill_assumption"])
        self.assertGreater(mocked.call_count, 4)

    def test_risk_reward_mode_generates_exact_ratio_plans(self):
        result = analyzer.find_dual_recommendations(
            make_bars(), horizon_bars=4, replays=100, engine_mode="legacy",
            tpsl_mode="risk_reward", point_size=0.01,
            rr_ratio=3.0, rr_sl_points=500
        )
        self.assertEqual(result["tpsl_config"]["mode"], "risk_reward")
        self.assertEqual(result["tpsl_config"]["rr_ratio"], 3.0)
        self.assertEqual(result["tpsl_config"]["sl_points"], 500)
        self.assertEqual(result["tpsl_config"]["tp_points"], 1500)
        for side in ("buy", "sell"):
            plan = result[side]["plan"]
            self.assertEqual(plan["tp_points"], 1500)
            self.assertEqual(plan["sl_points"], 500)
            self.assertAlmostEqual(plan["target_rr"], 3.0, places=4)
            if side == "buy":
                self.assertAlmostEqual(plan["target"] - plan["entry"], 15.0, places=6)
                self.assertAlmostEqual(plan["entry"] - plan["stop"], 5.0, places=6)
            else:
                self.assertAlmostEqual(plan["entry"] - plan["target"], 15.0, places=6)
                self.assertAlmostEqual(plan["stop"] - plan["entry"], 5.0, places=6)

    def test_risk_reward_mode_validates_ratio_and_sl(self):
        with self.assertRaisesRegex(ValueError, "rr_ratio"):
            analyzer.find_dual_recommendations(
                make_bars(), tpsl_mode="risk_reward", point_size=0.01,
                rr_ratio=-1.0, rr_sl_points=1000
            )
        with self.assertRaisesRegex(ValueError, "rr_sl_points"):
            analyzer.find_dual_recommendations(
                make_bars(), tpsl_mode="risk_reward", point_size=0.01,
                rr_ratio=2.0, rr_sl_points=0
            )


if __name__ == "__main__":
    unittest.main()
