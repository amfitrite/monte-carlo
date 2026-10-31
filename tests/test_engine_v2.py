"""Unit tests for the isolated Enhanced OHLC V2 engine."""
import unittest
import engine_v2


def collision_dataset(count=260):
    bars = []
    for i in range(count):
        bars.append({
            "timestamp": 1_700_000_000 + i * 300,
            "open": 100.0, "high": 103.0, "low": 98.0, "close": 100.0
        })
    return {"symbol": "TEST", "interval_minutes": 5, "bars": bars}


class EnhancedEngineTests(unittest.TestCase):
    def test_same_bar_collision_is_conservative_and_exposes_upper_bound(self):
        result = engine_v2.run_simulation(
            entry_price=100, stop_loss=99, take_profit=102, side="buy",
            horizon_bars=5, replays=200, seed=7, spread=0,
            bars_data=collision_dataset(), block_length=5
        )
        odds = result["odds"]
        self.assertEqual(odds["ambiguous_pct"], 100.0)
        self.assertEqual(odds["target_first_pct"], 0.0)
        self.assertEqual(odds["stop_first_pct"], 100.0)
        self.assertEqual(odds["optimistic_target_first_pct"], 100.0)

    def test_seed_reproducibility_and_output_shape(self):
        data = collision_dataset()
        kwargs = dict(entry_price=100, stop_loss=95, take_profit=110, side="buy",
                      horizon_bars=20, replays=300, seed=19, spread=0,
                      bars_data=data, block_length=8)
        first = engine_v2.run_simulation(**kwargs)
        second = engine_v2.run_simulation(**kwargs)
        self.assertEqual(first["odds"], second["odds"])
        self.assertEqual(first["fan_data"]["step_bars"], second["fan_data"]["step_bars"])
        self.assertEqual(len(first["sample_paths"][0]), len(first["fan_data"]["step_bars"]))
        total = (first["odds"]["target_first_pct"] +
                 first["odds"]["stop_first_pct"] +
                 first["odds"]["neither_pct"])
        self.assertAlmostEqual(total, 100.0, places=1)


if __name__ == "__main__":
    unittest.main()
