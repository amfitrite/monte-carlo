import unittest
from unittest.mock import patch
import tkinter as tk
import gui
import analyzer
import timemachine
import tests.test_dual_auto_analyzer as t
import os

class GuiZoomAndGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
            cls.root.withdraw()
        except Exception as e:
            raise unittest.SkipTest(f"Skipping GUI tests in headless environment without display: {e}")
        cls.bars = t.make_bars(260)
        cls.dual_res = analyzer.find_dual_recommendations(
            cls.bars, horizon_bars=12, replays=50, engine_mode="legacy"
        )

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        # Create a lightweight headless GUI instance for testing chart methods
        self.app = gui.TimeMachineProGUI.__new__(gui.TimeMachineProGUI)
        self.app.root = self.root
        self.app.active_mode = "auto"
        self.app.current_timeframe = "M5"
        self.app.grid_lines_var = tk.StringVar(value="Dynamic Adaptive (Default)")

        self.app.zoom_y = 1.0
        self.app.zoom_x = 1.0
        self.app.pan_y = 0.0
        self.app.pan_x = 0.0
        self.app._pan_start_x = 0
        self.app._pan_start_y = 0
        self.app._is_panning = False
        self.app._cached_base_range = 80.0
        self.app._cached_orig_mid = 3875.0
        self.app._cached_total_steps = 72
        self.app._cached_plot_w = 400
        self.app._cached_plot_h = 300
        self.app._cached_vis_price_range = 80.0
        self.app._cached_vis_steps = 72

        self.app.buy_canvas = tk.Canvas(self.root, width=500, height=350, bg="#0f141d")
        self.app.sell_canvas = tk.Canvas(self.root, width=500, height=350, bg="#0f141d")
        self.app.manual_canvas = tk.Canvas(self.root, width=500, height=350, bg="#0f141d")
        self.app.dual_results = self.dual_res
        self.app._dragging_line = None
        self.app._hover_line = None

    def tearDown(self):
        try:
            self.app.buy_canvas.destroy()
            self.app.sell_canvas.destroy()
            self.app.manual_canvas.destroy()
        except Exception:
            pass

    def test_nice_grid_step_produces_clean_round_numbers(self):
        expected_mappings = [
            (0.08, 0.1),
            (0.14, 0.1),
            (0.25, 0.2),
            (0.65, 0.5),
            (1.2, 1.0),
            (2.8, 2.0),
            (6.5, 5.0),
            (9.0, 10.0),
            (18.0, 20.0),
            (45.0, 50.0),
            (85.0, 100.0),
        ]
        for raw, expected in expected_mappings:
            nice = self.app._nice_grid_step(raw)
            self.assertAlmostEqual(nice, expected, places=5, msg=f"raw={raw} expected={expected} got={nice}")

    def test_mousewheel_ctrl_zooms_price_only(self):
        class MockWheelEvent:
            delta = 120
            state = 0x0004  # Ctrl key
            x = 250
            y = 175
            widget = self.app.buy_canvas

        self.app._on_chart_mousewheel(MockWheelEvent())
        self.assertGreater(self.app.zoom_y, 1.0)
        self.assertEqual(self.app.zoom_x, 1.0)

    def test_mousewheel_shift_zooms_time_only(self):
        class MockWheelEvent:
            delta = 120
            state = 0x0001  # Shift key
            x = 250
            y = 175
            widget = self.app.buy_canvas

        self.app._on_chart_mousewheel(MockWheelEvent())
        self.assertEqual(self.app.zoom_y, 1.0)
        self.assertGreater(self.app.zoom_x, 1.0)

    def test_mousewheel_regular_zooms_both_proportionally(self):
        class MockWheelEvent:
            delta = 120
            state = 0  # No modifier
            x = 250
            y = 175
            widget = self.app.buy_canvas

        self.app._on_chart_mousewheel(MockWheelEvent())
        self.assertGreater(self.app.zoom_y, 1.0)
        self.assertGreater(self.app.zoom_x, 1.0)

    def test_pan_drag_updates_pan_offsets(self):
        class MockPressEvent:
            x = 100
            y = 100
            widget = self.app.buy_canvas

        class MockMotionEvent:
            x = 130
            y = 120
            widget = self.app.buy_canvas

        self.app._on_chart_pan_start(MockPressEvent())
        self.assertTrue(self.app._is_panning)
        self.app._on_chart_pan_motion(MockMotionEvent())
        self.assertLess(self.app.pan_x, 0.0)  # dragged right -> negative pan_x
        self.assertGreater(self.app.pan_y, 0.0)  # dragged down -> positive pan_y
        self.app._on_chart_pan_end(MockMotionEvent())
        self.assertFalse(self.app._is_panning)

    def test_reset_chart_zoom_restores_defaults(self):
        self.app.zoom_y = 3.5
        self.app.zoom_x = 2.0
        self.app.pan_y = 15.0
        self.app.pan_x = -8.0

        self.app._reset_chart_zoom()
        self.assertEqual(self.app.zoom_y, 1.0)
        self.assertEqual(self.app.zoom_x, 1.0)
        self.assertEqual(self.app.pan_y, 0.0)
        self.assertEqual(self.app.pan_x, 0.0)

    def test_render_cone_executes_cleanly_at_multiple_zoom_levels(self):
        for z in [0.5, 1.0, 2.5, 5.0]:
            self.app.zoom_y = z
            self.app.zoom_x = z
            self.app._render_cone(self.app.buy_canvas, self.dual_res["buy"], is_buy=True)
            items = self.app.buy_canvas.find_all()
            self.assertGreater(len(items), 20, f"Expected rendered canvas items at zoom {z}")

    def test_dual_charts_synchronize_shared_price_bounds(self):
        bounds = self.app._extract_chart_bounds(self.dual_res["buy"])
        self.assertGreater(len(bounds), 5)
        # Calling _draw_dual_charts renders both canvases synchronously without errors
        self.app._draw_dual_charts()
        buy_items = self.app.buy_canvas.find_all()
        sell_items = self.app.sell_canvas.find_all()
        self.assertGreater(len(buy_items), 20)
        self.assertGreater(len(sell_items), 20)

    def test_gui_candidate_grid_and_replay_options(self):
        top = tk.Toplevel(self.root)
        top.withdraw()
        try:
            with patch.object(gui.TimeMachineProGUI, "_initial_load_data"):
                app = gui.TimeMachineProGUI(top)
                self.assertTrue(hasattr(app, "candidate_grid_combo"))
                self.assertTrue(hasattr(app, "replays_combo"))

                expected_grids = [
                    "0 (Versi Asli / Baseline)",
                    "5 Variasi (Cepat)",
                    "10 Variasi (Seimbang)",
                    "20 Variasi (Optimal Brute-Force)"
                ]
                self.assertEqual(list(app.candidate_grid_combo["values"]), expected_grids)

                expected_replays = ["100", "250", "500", "1,000", "3,000", "5,000", "10,000"]
                self.assertEqual(list(app.replays_combo["values"]), expected_replays)

                app.candidate_grid_var.set("20 Variasi (Optimal Brute-Force)")
                self.assertEqual(int(app.candidate_grid_var.get().split()[0]), 20)

                # Verify dynamic quota and effective entries in GUI summary description
                res_quota = dict(self.dual_res)
                res_quota["search"] = {
                    "strategy": "ATR Pullback & Swing Structure",
                    "candidate_count_requested": 20,
                    "effective_entries_per_side": 10,
                    "entries_scanned": 10,
                    "buy_entries_scanned": 10,
                    "sell_entries_scanned": 10,
                    "entry_quota_adjusted": True,
                    "buy_candidates_scanned": 200,
                    "sell_candidates_scanned": 200,
                }
                app._apply_dual_results(res_quota)
                desc = app.dual_summary_desc.cget("text")
                self.assertIn("10/20 entri", desc)
                self.assertIn("kuota dinamis", desc)

                # Verify Auto mode with asymmetric buy/sell entries and no quota capping
                res_auto_asym = dict(self.dual_res)
                res_auto_asym["search"] = {
                    "strategy": "ATR Pullback & Swing Structure",
                    "candidate_count_requested": 20,
                    "effective_entries_per_side": {"buy": 16, "sell": 13},
                    "entries_scanned": {"buy": 16, "sell": 13},
                    "buy_entries_scanned": 16,
                    "sell_entries_scanned": 13,
                    "entry_quota_adjusted": False,
                    "buy_candidates_scanned": 64,
                    "sell_candidates_scanned": 52,
                }
                app._apply_dual_results(res_auto_asym)
                desc_asym = app.dual_summary_desc.cget("text")
                self.assertIn("BUY 16 / SELL 13 entri", desc_asym)
                self.assertNotIn("kuota dinamis", desc_asym)

                # Verify baseline candidate_count=0 summary displays cleanly
                res_baseline = dict(self.dual_res)
                res_baseline["search"] = {
                    "strategy": "ATR Pullback & Swing Structure",
                    "candidate_count_requested": 0,
                    "effective_entries_per_side": 5,
                    "entries_scanned": 5,
                    "entry_quota_adjusted": False,
                    "buy_candidates_scanned": 5,
                    "sell_candidates_scanned": 5,
                }
                app._apply_dual_results(res_baseline)
                desc_base = app.dual_summary_desc.cget("text")
                self.assertNotIn("Grid:", desc_base)
        finally:
            top.destroy()


    def test_manual_line_hover_and_drag_interactions(self):
        """Test hover detection and dragging for TP, SL, and Entry on manual canvas."""
        self.app.manual_entry_var = tk.StringVar(value="3875.00")
        self.app.manual_stop_var = tk.StringVar(value="3850.00")
        self.app.manual_target_var = tk.StringVar(value="3925.00")
        self.app.direction_var = tk.StringVar(value="BUY")
        self.app.point_size_var = tk.StringVar(value="0.01")
        self.app.manual_rr_lbl = tk.Label(self.root)

        # Set cached dimensions for coordinate mapping
        self.app._cached_pad_top = 25
        self.app._cached_plot_h = 300
        self.app._cached_min_p = 3800.0
        self.app._cached_max_p = 4000.0
        self.app._cached_pad_left = 60
        self.app._cached_pad_right = 20

        # Simulate line coordinates
        self.app._cached_y_tp = 100
        self.app._cached_y_en = 150
        self.app._cached_y_sl = 200

        class MockEvent:
            def __init__(self, x, y, widget, state=0):
                self.x = x
                self.y = y
                self.widget = widget
                self.state = state

        # 1. Hover near TP (y=100)
        self.app._on_chart_mouse_motion(MockEvent(100, 102, self.app.manual_canvas))
        self.assertEqual(self.app._hover_line, "tp")

        # 2. Hover near SL (y=200)
        self.app._on_chart_mouse_motion(MockEvent(100, 198, self.app.manual_canvas))
        self.assertEqual(self.app._hover_line, "sl")

        # 3. Hover near Entry (y=150)
        self.app._on_chart_mouse_motion(MockEvent(100, 151, self.app.manual_canvas))
        self.assertEqual(self.app._hover_line, "entry")

        # 4. Click to start drag Entry
        self.app._on_chart_pan_start(MockEvent(100, 150, self.app.manual_canvas))
        self.assertEqual(self.app._dragging_line, "entry")
        self.assertFalse(self.app._is_panning)

        # 5. Drag Entry upwards (y moves from 150 to 120 -> price increases)
        old_entry = float(self.app.manual_entry_var.get())
        old_sl = float(self.app.manual_stop_var.get())
        old_tp = float(self.app.manual_target_var.get())

        self.app._on_chart_pan_motion(MockEvent(100, 120, self.app.manual_canvas))
        new_entry = float(self.app.manual_entry_var.get())
        new_sl = float(self.app.manual_stop_var.get())
        new_tp = float(self.app.manual_target_var.get())

        self.assertGreater(new_entry, old_entry)
        self.assertAlmostEqual(new_sl - old_sl, new_entry - old_entry, places=1)
        self.assertAlmostEqual(new_tp - old_tp, new_entry - old_entry, places=1)

        # Release drag
        self.app._on_chart_pan_end(MockEvent(100, 120, self.app.manual_canvas))
        self.assertIsNone(self.app._dragging_line)

        # 6. Drag TP line independently
        self.app._hover_line = "tp"
        self.app._on_chart_pan_start(MockEvent(100, 100, self.app.manual_canvas))
        self.assertEqual(self.app._dragging_line, "tp")

        # Drag TP further up (y=80)
        self.app._on_chart_pan_motion(MockEvent(100, 80, self.app.manual_canvas))
        self.assertGreater(float(self.app.manual_target_var.get()), new_entry)

        # Drag TP below entry -> should be clamped above entry for BUY
        self.app._on_chart_pan_motion(MockEvent(100, 250, self.app.manual_canvas))
        self.assertGreater(float(self.app.manual_target_var.get()), float(self.app.manual_entry_var.get()))

        self.app._on_chart_pan_end(MockEvent(100, 250, self.app.manual_canvas))
        self.assertIsNone(self.app._dragging_line)

        # 7. Drag SL line independently
        self.app._hover_line = "sl"
        self.app._on_chart_pan_start(MockEvent(100, 200, self.app.manual_canvas))
        self.assertEqual(self.app._dragging_line, "sl")

        # Drag SL above entry -> should be clamped below entry for BUY
        self.app._on_chart_pan_motion(MockEvent(100, 50, self.app.manual_canvas))
        self.assertLess(float(self.app.manual_stop_var.get()), float(self.app.manual_entry_var.get()))

        self.app._on_chart_pan_end(MockEvent(100, 50, self.app.manual_canvas))
        self.assertIsNone(self.app._dragging_line)


    def test_apply_strategy_to_manual_populates_distinct_levels(self):
        """Verify that selecting different strategies in manual mode updates entry, SL, and TP distinctly."""
        self.app.direction_var = tk.StringVar(value="BUY")
        self.app.manual_entry_var = tk.StringVar(value="3875.00")
        self.app.manual_stop_var = tk.StringVar(value="3850.00")
        self.app.manual_target_var = tk.StringVar(value="3925.00")
        self.app.point_size_var = tk.StringVar(value="0.01")
        self.app.spread_var = tk.StringVar(value="0.24")
        self.app.replays_var = tk.StringVar(value="50")
        self.app.engine_mode_var = tk.StringVar(value="Legacy V1 (Default)")
        self.app.horizon_var = tk.StringVar(value="12 Bars (1 Jam)")
        self.app.manual_rr_lbl = tk.Label(self.root)
        self.app.btn_run_manual = tk.Button(self.root)
        self.app.m_verdict_lbl = tk.Label(self.root)
        self.app.m_card_win = tk.Label(self.root)
        self.app.m_card_loss = tk.Label(self.root)
        self.app.m_card_open = tk.Label(self.root)
        self.app.m_card_r = tk.Label(self.root)
        self.app.manual_canvas = tk.Canvas(self.root)
        self.app.bars_data = self.bars
        self.app.current_projection_mode = "free_drift"
        self.app.current_tie_break = "smart"
        self.app.current_seasonality = False

        self.app.strategy_var = tk.StringVar(value="Breakout + POC Retest")
        self.app._apply_strategy_to_manual()
        poc_entry = float(self.app.manual_entry_var.get())

        self.app.strategy_var.set("Bollinger Extremes (Z-Score)")
        self.app._apply_strategy_to_manual()
        boll_entry = float(self.app.manual_entry_var.get())

        self.app.strategy_var.set("Liquidity Sweep + FVG")
        self.app._apply_strategy_to_manual()
        fvg_entry = float(self.app.manual_entry_var.get())

        self.assertNotEqual(poc_entry, boll_entry)
        self.assertNotEqual(boll_entry, fvg_entry)

    def test_on_strategy_change_in_manual_mode_preserves_custom_levels(self):
        """Verify that changing strategy or direction in manual mode NEVER overwrites custom prices."""
        self.app.active_mode = "manual"
        self.app.direction_var = tk.StringVar(value="SELL")
        self.app.manual_entry_var = tk.StringVar(value="3900.13")
        self.app.manual_stop_var = tk.StringVar(value="3931.20")
        self.app.manual_target_var = tk.StringVar(value="3847.94")
        self.app.spread_var = tk.StringVar(value="0.25")
        self.app.replays_var = tk.StringVar(value="50")
        self.app.engine_mode_var = tk.StringVar(value="Legacy V1 (Default)")
        self.app.horizon_var = tk.StringVar(value="12 Bars (1 Jam)")
        self.app.current_projection_mode = "free_drift"
        self.app.current_tie_break = "smart"
        self.app.current_seasonality = False
        self.app.strategy_var = tk.StringVar(value="ATR Pullback & Swing (Default)")
        self.app.bars_data = self.bars
        self.app.manual_rr_lbl = tk.Label(self.root)
        self.app.btn_run_manual = tk.Button(self.root)
        self.app.m_verdict_lbl = tk.Label(self.root)
        self.app.m_card_win = tk.Label(self.root)
        self.app.m_card_loss = tk.Label(self.root)
        self.app.m_card_open = tk.Label(self.root)
        self.app.m_card_r = tk.Label(self.root)
        self.app.manual_canvas = tk.Canvas(self.root)
        self.app.buy_btn = tk.Button(self.root)
        self.app.sell_btn = tk.Button(self.root)

        # 1. Change strategy dropdown - prices must NOT change!
        self.app.strategy_var.set("Breakout + POC Retest")
        self.app._on_strategy_change()
        self.assertEqual(self.app.manual_entry_var.get(), "3900.13")
        self.assertEqual(self.app.manual_stop_var.get(), "3931.20")
        self.assertEqual(self.app.manual_target_var.get(), "3847.94")

        self.app.strategy_var.set("Bollinger Extremes (Z-Score)")
        self.app._on_strategy_change()
        self.assertEqual(self.app.manual_entry_var.get(), "3900.13")
        self.assertEqual(self.app.manual_stop_var.get(), "3931.20")
        self.assertEqual(self.app.manual_target_var.get(), "3847.94")

        # 2. Change direction - prices must NOT change!
        self.app._set_direction("BUY")
        self.assertEqual(self.app.manual_entry_var.get(), "3900.13")
        self.assertEqual(self.app.manual_stop_var.get(), "3931.20")
        self.assertEqual(self.app.manual_target_var.get(), "3847.94")

    def test_simulation_strategy_conditioning_with_fixed_levels(self):
        """Verify that timemachine simulation with fixed levels produces distinct odds per strategy."""
        c = self.bars["bars"][-1]["close"]
        entry, stop, target = c, c + 5.0, c - 5.0
        res_baseline = timemachine.run_simulation(
            entry, stop, target, side="sell", bars_data=self.bars, replays=1000, seed=19, strategy="atr_swing"
        )
        res_poc = timemachine.run_simulation(
            entry, stop, target, side="sell", bars_data=self.bars, replays=1000, seed=19, strategy="poc"
        )
        res_fvg = timemachine.run_simulation(
            entry, stop, target, side="sell", bars_data=self.bars, replays=1000, seed=19, strategy="fvg"
        )

        self.assertNotEqual(res_baseline["odds"]["target_first_pct"], res_poc["odds"]["target_first_pct"])
        self.assertNotEqual(res_poc["odds"]["target_first_pct"], res_fvg["odds"]["target_first_pct"])



if __name__ == "__main__":
    unittest.main()
