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

        with patch.object(analyzer, "_run_one", side_effect=fake_run) as mocked:
            result = analyzer.find_dual_recommendations(
                make_bars(), horizon_bars=12, replays=100,
                engine_mode="legacy"
            )
        self.assertEqual(result["best_direction"], "BUY")
        self.assertGreater(result["search"]["buy_candidates_scanned"], 1)
        self.assertGreater(result["search"]["sell_candidates_scanned"], 1)
        self.assertIsNone(result["buy"]["plan"]["entry_fill_probability"])
        self.assertIn("Conditional", result["buy"]["plan"]["entry_fill_assumption"])
        self.assertGreater(mocked.call_count, 4)


if __name__ == "__main__":
    unittest.main()
