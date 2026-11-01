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

    def test_all_nine_strategies_generate_valid_dual_plans(self):
        bars = make_bars()
        strategies = [
            "atr_swing", "poc", "fvg", "orb", "zscore",
            "acc_ifvg", "sweep_sms", "absorption", "footprint"
        ]
        expected_labels = {
            "atr_swing": "ATR Pullback & Swing Structure",
            "poc": "Breakout + Retest Point of Control (POC)",
            "fvg": "Liquidity Sweep + Fair Value Gap (FVG)",
            "orb": "Session Open Range Breakout (ORB)",
            "zscore": "Bollinger Bands Extremes (Z-Score)",
            "acc_ifvg": "Accumulation + Inverse FVG (IFVG)",
            "sweep_sms": "Liquidity Sweep + Market Structure Shift (SMS)",
            "absorption": "Liquidity Absorption + Volume Bubbles",
            "footprint": "Footprint (Order Flow) Bid/Ask Absorption Proxy"
        }
        for strat in strategies:
            res = analyzer.find_dual_recommendations(
                bars, horizon_bars=4, replays=100, engine_mode="legacy",
                strategy=strat
            )
            self.assertEqual(res["strategy"], strat)
            self.assertEqual(res["strategy_label"], expected_labels[strat])
            for side in ("buy", "sell"):
                plan = res[side]["plan"]
                self.assertEqual(plan["order_type"], "LIMIT")
                self.assertGreater(plan["entry"], 0.0)
                self.assertGreater(plan["stop"], 0.0)
                self.assertGreater(plan["target"], 0.0)
                if side == "buy":
                    self.assertLess(plan["entry"], res["metrics"]["current_price"])
                    self.assertLess(plan["stop"], plan["entry"])
                    self.assertGreater(plan["target"], plan["entry"])
                else:
                    self.assertGreater(plan["entry"], res["metrics"]["current_price"])
                    self.assertGreater(plan["stop"], plan["entry"])
                    self.assertLess(plan["target"], plan["entry"])

    def test_strategy_combines_with_risk_reward_mode(self):
        bars = make_bars()
        res = analyzer.find_dual_recommendations(
            bars, horizon_bars=4, replays=100, engine_mode="legacy",
            strategy="poc", tpsl_mode="risk_reward", point_size=0.01,
            rr_ratio=4.0, rr_sl_points=800
        )
        self.assertEqual(res["strategy"], "poc")
        self.assertEqual(res["tpsl_config"]["mode"], "risk_reward")
        self.assertEqual(res["tpsl_config"]["rr_ratio"], 4.0)
        self.assertEqual(res["buy"]["plan"]["tp_points"], 3200)
        self.assertEqual(res["buy"]["plan"]["sl_points"], 800)
        self.assertEqual(res["sell"]["plan"]["tp_points"], 3200)
        self.assertEqual(res["sell"]["plan"]["sl_points"], 800)

    def test_strategies_produce_distinct_entries_and_tags(self):
        bars = make_bars()
        res_atr = analyzer.find_dual_recommendations(bars, horizon_bars=4, replays=100, strategy="atr_swing")
        res_poc = analyzer.find_dual_recommendations(bars, horizon_bars=4, replays=100, strategy="poc")
        res_zscore = analyzer.find_dual_recommendations(bars, horizon_bars=4, replays=100, strategy="zscore")
        
        self.assertTrue(bool(res_atr["buy"]["plan"].get("setup_tag")))
        self.assertTrue(bool(res_poc["buy"]["plan"].get("setup_tag")))
        self.assertTrue(bool(res_zscore["buy"]["plan"].get("setup_tag")))
        
        tags = {res_atr["buy"]["plan"]["setup_tag"], res_poc["buy"]["plan"]["setup_tag"], res_zscore["buy"]["plan"]["setup_tag"]}
        self.assertGreater(len(tags), 1)

    def test_candidate_count_zero_preserves_exact_baseline(self):
        # Test across multiple bar sizes to ensure formula invariance (not just one fragile synthetic snapshot)
        for bar_count in (220, 260):
            bars = make_bars(bar_count)
            metrics = analyzer.calculate_market_metrics(bars["bars"])
            
            cur, atr = metrics["current_price"], metrics["atr"]
            lo, hi = metrics["swing_low"], metrics["swing_high"]
            span = max(hi - lo, atr)
            price_step = float(metrics.get("price_step", 0.01) or 0.01)

            # Test 1: Dynamic formula invariance for BUY baseline
            expected_buy = [
                analyzer._round_to_step(cur - atr * 0.35, price_step),
                analyzer._round_to_step(cur - atr * 0.60, price_step),
                analyzer._round_to_step(cur - atr * 0.85, price_step),
                analyzer._round_to_step(lo + span * 0.15, price_step),
                analyzer._round_to_step(lo + span * 0.30, price_step)
            ]
            buy_baseline = analyzer._candidate_entries_atr_swing("buy", metrics, candidate_count=0)
            self.assertEqual(len(buy_baseline), 5)
            self.assertEqual([float(x) for x in buy_baseline], expected_buy)
            self.assertEqual(
                [x.tag for x in buy_baseline],
                ['ATR Pullback 0.35', 'ATR Pullback 0.60', 'ATR Pullback 0.85', 'Swing Low Support', 'Swing Structure Mid']
            )

            # Test 2: Dynamic formula invariance for SELL baseline
            expected_sell = [
                analyzer._round_to_step(cur + atr * 0.35, price_step),
                analyzer._round_to_step(cur + atr * 0.60, price_step),
                analyzer._round_to_step(cur + atr * 0.85, price_step),
                analyzer._round_to_step(hi - span * 0.15, price_step),
                analyzer._round_to_step(hi - span * 0.30, price_step)
            ]
            sell_baseline = analyzer._candidate_entries_atr_swing("sell", metrics, candidate_count=0)
            self.assertEqual(len(sell_baseline), 5)
            self.assertEqual([float(x) for x in sell_baseline], expected_sell)
            self.assertEqual(
                [x.tag for x in sell_baseline],
                ['ATR Premium 0.35', 'ATR Premium 0.60', 'ATR Premium 0.85', 'Swing High Resistance', 'Swing Structure Mid']
            )

        # Test 3: Full pipeline end-to-end equivalence: default call vs explicit candidate_count=0
        bars = make_bars(260)
        res_default = analyzer.find_dual_recommendations(bars, horizon_bars=4, replays=100, seed=42)
        res_zero = analyzer.find_dual_recommendations(bars, horizon_bars=4, replays=100, seed=42, candidate_count=0)

        self.assertEqual(res_zero["search"]["candidate_count_requested"], 0)
        self.assertEqual(res_zero["search"]["entries_scanned"], 5)
        self.assertEqual(res_zero["search"]["effective_entries_per_side"], 5)
        self.assertEqual(res_zero["best_direction"], res_default["best_direction"])
        
        # BUY plan exact equivalence
        self.assertEqual(res_zero["buy"]["plan"]["entry"], res_default["buy"]["plan"]["entry"])
        self.assertEqual(res_zero["buy"]["plan"]["stop"], res_default["buy"]["plan"]["stop"])
        self.assertEqual(res_zero["buy"]["plan"]["target"], res_default["buy"]["plan"]["target"])
        self.assertEqual(res_zero["buy"]["odds"]["avg_r"], res_default["buy"]["odds"]["avg_r"])
        self.assertEqual(res_zero["buy"]["odds"]["target_first_pct"], res_default["buy"]["odds"]["target_first_pct"])

        # SELL plan exact equivalence
        self.assertEqual(res_zero["sell"]["plan"]["entry"], res_default["sell"]["plan"]["entry"])
        self.assertEqual(res_zero["sell"]["plan"]["stop"], res_default["sell"]["plan"]["stop"])
        self.assertEqual(res_zero["sell"]["plan"]["target"], res_default["sell"]["plan"]["target"])
        self.assertEqual(res_zero["sell"]["odds"]["avg_r"], res_default["sell"]["odds"]["avg_r"])
        self.assertEqual(res_zero["sell"]["odds"]["target_first_pct"], res_default["sell"]["odds"]["target_first_pct"])

    def test_candidate_count_grid_sweep_generates_up_to_20_variations(self):
        bars = make_bars()
        metrics = analyzer.calculate_market_metrics(bars["bars"])
        for strat in ("atr_swing", "poc", "zscore", "fvg"):
            # 1. Candidate price entries must never exceed the requested 20 variations
            entries = analyzer._candidate_entries("buy", metrics, bars=bars["bars"], strategy=strat, candidate_count=20)
            self.assertGreaterEqual(len(entries), 1)
            self.assertLessEqual(len(entries), 20)

            # 2. Total plans scanned in dual recommendations must never exceed MAX_CANDIDATES_PER_SIDE
            res = analyzer.find_dual_recommendations(
                bars, horizon_bars=4, replays=100, strategy=strat, candidate_count=20
            )
            self.assertEqual(res["search"]["candidate_count_requested"], 20)
            self.assertGreaterEqual(res["search"]["buy_candidates_scanned"], 1)
            self.assertLessEqual(res["search"]["buy_candidates_scanned"], analyzer.MAX_CANDIDATES_PER_SIDE)
            self.assertGreaterEqual(res["search"]["sell_candidates_scanned"], 1)
            self.assertLessEqual(res["search"]["sell_candidates_scanned"], analyzer.MAX_CANDIDATES_PER_SIDE)
            self.assertGreater(res["buy"]["plan"]["entry"], 0)
            self.assertGreater(res["sell"]["plan"]["entry"], 0)

    def test_candidate_count_20_with_tpsl_range_mode_does_not_crash(self):
        bars = make_bars()
        # Test full 20 TP/SL combinations with 20 candidate variations (would previously create 320 plans and crash)
        res = analyzer.find_dual_recommendations(
            bars, horizon_bars=4, replays=100,
            strategy="atr_swing", candidate_count=20,
            tpsl_mode="range", point_size=0.01,
            tp_min_points=1000, tp_max_points=5000, tp_step_points=1000,  # 5 tp
            sl_min_points=500, sl_max_points=2000, sl_step_points=500     # 4 sl -> 5*4 = 20 combinations
        )
        self.assertEqual(res["tpsl_config"]["mode"], "range")
        self.assertEqual(res["search"]["candidate_count_requested"], 20)
        self.assertEqual(res["search"]["entries_scanned"], 10)
        self.assertEqual(res["search"]["effective_entries_per_side"], 10)
        self.assertTrue(res["search"]["entry_quota_adjusted"])
        self.assertEqual(res["search"]["buy_candidates_scanned"], 200)
        self.assertEqual(res["search"]["sell_candidates_scanned"], 200)
        self.assertLessEqual(res["search"]["buy_candidates_scanned"], analyzer.MAX_CANDIDATES_PER_SIDE)
        self.assertLessEqual(res["search"]["sell_candidates_scanned"], analyzer.MAX_CANDIDATES_PER_SIDE)
        self.assertEqual(res["buy"]["plan"]["order_type"], "LIMIT")
        self.assertEqual(res["sell"]["plan"]["order_type"], "LIMIT")

    def test_candidate_count_with_rr_1_to_5_and_100_replays(self):
        bars = make_bars()
        res = analyzer.find_dual_recommendations(
            bars, horizon_bars=4, replays=100, strategy="atr_swing",
            tpsl_mode="risk_reward", point_size=0.01,
            rr_ratio=5.0, rr_sl_points=1000,
            candidate_count=20
        )
        self.assertEqual(res["tpsl_config"]["mode"], "risk_reward")
        self.assertEqual(res["tpsl_config"]["rr_ratio"], 5.0)
        self.assertEqual(res["search"]["candidate_count_requested"], 20)
        self.assertEqual(res["search"]["final_replays"], 100)
        for side in ("buy", "sell"):
            plan = res[side]["plan"]
            self.assertEqual(plan["order_type"], "LIMIT")
            self.assertEqual(plan["target_rr"], 5.0)
            self.assertEqual(plan["tp_points"], 5000)
            self.assertEqual(plan["sl_points"], 1000)
            if side == "buy":
                self.assertAlmostEqual(plan["target"] - plan["entry"], 50.0, places=4)
                self.assertAlmostEqual(plan["entry"] - plan["stop"], 10.0, places=4)
            else:
                self.assertAlmostEqual(plan["entry"] - plan["target"], 50.0, places=4)
                self.assertAlmostEqual(plan["stop"] - plan["entry"], 10.0, places=4)


if __name__ == "__main__":
    unittest.main()
