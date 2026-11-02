"""
XAUUSD Time Machine PRO - Frameless Modern Desktop GUI
Features:
- Frameless Pro Window with Custom Title Bar (Draggable, Minimize, Maximize, Close)
- Dual Data Source: COMEX Gold (Yahoo) and MetaTrader 5 (Exness Direct IPC)
- Dual Engine Auto-Analyzer (BUY LIMIT and SELL LIMIT) with Side-by-Side Dual Fan Charts
- Manual Mode for Custom Trade Setup Simulation
- Multi-Timeframe support (Scalping, Day Trade, Multi-Day Swing)
"""

import os
import sys
import re
import math
import ctypes
import threading
import json
import tkinter as tk
from tkinter import ttk, messagebox

# Set Windows High-DPI awareness
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

import timemachine
import engine_v2
import mt5_connector
import analyzer
import combination_engine

DARK_BG = "#0b0f17"
PANEL_BG = "#131822"
CARD_BG = "#1a2230"
INPUT_BG = "#222c3d"
BORDER_COL = "#2a364a"
TEXT_PRIMARY = "#f1f5f9"
TEXT_MUTED = "#94a3b8"

GOLD = "#f59e0b"
GOLD_HOVER = "#d97706"
GREEN = "#10b981"
RED = "#ef4444"
BLUE = "#38bdf8"
CYAN = "#06b6d4"

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_settings.json")

HORIZON_PRESETS_M5 = [
    ("30 Menit (6 bars M5)", 6),
    ("1 Jam (12 bars M5)", 12),
    ("2 Jam (24 bars M5)", 24),
    ("4 Jam (48 bars M5)", 48),
    ("8 Jam (96 bars M5)", 96),
    ("24 Jam / 1 Hari (288 bars M5)", 288),
    ("2 Hari Swing (576 bars M5)", 576),
    ("3 Hari Swing (864 bars M5)", 864),
    ("5 Hari / 1 Minggu Swing (1440 bars M5)", 1440),
    ("10 Hari / 2 Minggu Swing (2880 bars M5)", 2880),
]

HORIZON_PRESETS_M1 = [
    ("15 Menit (15 bars M1)", 15),
    ("30 Menit (30 bars M1)", 30),
    ("1 Jam (60 bars M1)", 60),
    ("2 Jam (120 bars M1)", 120),
    ("4 Jam (240 bars M1)", 240),
    ("8 Jam (480 bars M1)", 480),
    ("24 Jam / 1 Hari (1440 bars M1)", 1440),
]

PROJECTION_MODES = {
    "Two-Stream Free Drift (Recommended)": "free_drift",
    "Frozen at Exit Level (Asli)": "frozen",
    "Survival / Active Only (Kaplan-Meier)": "survival",
}

TIE_BREAK_MODES = {
    "Smart Candle Anatomy (Recommended)": "smart",
    "Conservative SL First (Asli)": "conservative",
    "50:50 Balanced Coin Flip": "random",
}

SEASONALITY_MODES = {
    "Off (Default/Asli)": False,
    "On (Day-of-Week Aware)": True,
}

class TimeMachineProGUI:
    def __init__(self, root):
        self.root = root
        self.root.overrideredirect(True)
        self.root.geometry("1280x820+80+50")
        self.root.minsize(1080, 720)
        self.root.configure(bg=DARK_BG)

        # Window state
        self.is_maximized = False
        self.prev_geometry = "1280x820+80+50"
        self._drag_data = {"x": 0, "y": 0}

        # Data & Methodology states
        self.current_source = "mt5"
        self.current_timeframe = "M5"  # default to M5, with M1 option available
        self.current_projection_mode = "free_drift"  # default recommended two-stream unconstrained
        self.current_tie_break = "smart"  # default recommended candle anatomy
        self.current_seasonality = False  # default off
        self.active_mode = "auto"  # "auto" or "manual"
        self.bars_data = None
        self.current_market_price = 3875.0
        self.current_spread = 0.24
        self._point_size_custom = False
        self.manual_result = None
        self.dual_results = None
        self.mt5_positions = []
        self._auto_scan_debounce_timer = None
        self._auto_refresh_job = None
        self._is_scanning = False

        # Chart Interactive Zoom & Pan states
        self.zoom_y = 1.0
        self.zoom_x = 1.0
        self.pan_y = 0.0
        self.pan_x = 0.0
        self._pan_start_x = 0
        self._pan_start_y = 0
        self._is_panning = False
        self._cached_base_range = 80.0
        self._cached_orig_mid = 3875.0
        self._cached_total_steps = 72

        # Interactive Manual Line Dragging states
        self._dragging_line = None  # None, "entry", "sl", or "tp"
        self._hover_line = None  # None, "entry", "sl", or "tp"
        self._drag_start_y = 0
        self._drag_orig_entry = 0.0
        self._drag_orig_stop = 0.0
        self._drag_orig_target = 0.0
        self._cached_y_tp = None
        self._cached_y_sl = None
        self._cached_y_en = None
        self._cached_pad_top = 25
        self._cached_pad_bottom = 35
        self._cached_pad_left = 60
        self._cached_pad_right = 20
        self._cached_min_p = 0.0
        self._cached_max_p = 1.0
        self._cached_base_min_p = 0.0
        self._cached_base_max_p = 1.0
        self._cached_drag_min_p = None
        self._cached_drag_max_p = None
        self._cached_plot_w = 400
        self._cached_plot_h = 300
        self._cached_vis_price_range = 80.0
        self._cached_vis_steps = 72

        # Quant Profile & Capital Growth Simulation Variables
        self.opt_profile_var = tk.StringVar(value="WR Oriented")
        self.risk_pct_var = tk.StringVar(value="1.0")
        self.initial_capital_var = tk.StringVar(value="10000")
        self.max_dd_limit_var = tk.StringVar(value="20.0")
        self.ruin_threshold_var = tk.StringVar(value="50.0")
        self.rr_candidates_var = tk.StringVar(value="1:1, 1:1.5, 1:2, 1:3, 1:4, 1:5, 1:7, 1:10")

        # Configure taskbar integration for frameless window
        self._setup_taskbar()

        # Build UI - Header, Bottom Dock, and Center Canvas Body
        self._build_chrome_toolbar()
        self._build_bottom_dock()
        self._build_main_body()

        # Load saved settings if any
        self._load_settings()

        # Root window hotkeys for chart zoom
        self.root.bind("<Control-Key-0>", lambda e: self._reset_chart_zoom())
        self.root.bind("<Control-KP_0>", lambda e: self._reset_chart_zoom())
        self.root.bind("<Control-plus>", lambda e: self._zoom_step(1.2))
        self.root.bind("<Control-equal>", lambda e: self._zoom_step(1.2))
        self.root.bind("<Control-minus>", lambda e: self._zoom_step(1.0 / 1.2))
        self.root.bind("<Control-KP_Add>", lambda e: self._zoom_step(1.2))
        self.root.bind("<Control-KP_Subtract>", lambda e: self._zoom_step(1.0 / 1.2))

        # Bind close protocol on root window as well
        self.root.protocol("WM_DELETE_WINDOW", self._close_window)

        # Initial background data fetch
        threading.Thread(target=self._initial_load_data, daemon=True).start()

    def _setup_taskbar(self):
        """Set WS_EX_APPWINDOW so the frameless window appears in the Windows taskbar."""
        self.root.update_idletasks()
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            style = (style & ~0x00000080) | 0x00040000  # Remove TOOLWINDOW, Add APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)
            self.root.wm_withdraw()
            self.root.after(10, lambda: self.root.wm_deiconify())
        except Exception:
            pass

    # ========================== BOTTOM CONTROL & ACTION DOCK ==========================
    def _build_bottom_dock(self):
        """Bottom Dock: relocates action buttons and hosts Quant Profile and Capital Growth controls."""
        self.bottom_dock = tk.Frame(self.root, bg="#0d1117", height=46, highlightbackground=BORDER_COL, highlightthickness=1)
        self.bottom_dock.pack(side=tk.BOTTOM, fill=tk.X)
        self.bottom_dock.pack_propagate(False)

        # Left Zone: Quant Profile & Quick Capital Risk
        left_dock = tk.Frame(self.bottom_dock, bg="#0d1117")
        left_dock.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 6), pady=4)

        tk.Label(left_dock, text="🎯 Profile:", font=("Segoe UI", 8, "bold"), fg=GOLD, bg="#0d1117").pack(side=tk.LEFT, padx=(0, 4))
        self.opt_profile_combo = ttk.Combobox(
            left_dock, textvariable=self.opt_profile_var,
            values=["WR Oriented", "RR Oriented"],
            state="readonly", font=("Segoe UI", 8, "bold"), width=12
        )
        self.opt_profile_combo.pack(side=tk.LEFT, padx=(0, 8), fill=tk.Y)
        self.opt_profile_combo.bind("<<ComboboxSelected>>", lambda e: self.execute_auto_scan() if self.active_mode == "auto" else None)

        tk.Label(left_dock, text="Risk %:", font=("Segoe UI", 8), fg=TEXT_MUTED, bg="#0d1117").pack(side=tk.LEFT, padx=(0, 2))
        self.risk_pct_entry = tk.Entry(left_dock, textvariable=self.risk_pct_var, width=4, font=("Segoe UI", 8), bg=INPUT_BG, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief=tk.FLAT)
        self.risk_pct_entry.pack(side=tk.LEFT, padx=(0, 6), ipady=2)

        tk.Label(left_dock, text="Capital ($):", font=("Segoe UI", 8), fg=TEXT_MUTED, bg="#0d1117").pack(side=tk.LEFT, padx=(0, 2))
        self.initial_capital_entry = tk.Entry(left_dock, textvariable=self.initial_capital_var, width=7, font=("Segoe UI", 8), bg=INPUT_BG, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief=tk.FLAT)
        self.initial_capital_entry.pack(side=tk.LEFT, padx=(0, 10), ipady=2)

        # Center Zone: Real-Time Live Capital HUD
        center_dock = tk.Frame(self.bottom_dock, bg="#0d1117")
        center_dock.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.lbl_dock_hud = tk.Label(
            center_dock,
            text="Monte Carlo 3.01 Quant Engine Ready | Sequential Compounding & TP/SL Optimizer Active",
            font=("Segoe UI", 8), fg=TEXT_MUTED, bg="#0d1117"
        )
        self.lbl_dock_hud.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Right Zone: Action Buttons
        right_dock = tk.Frame(self.bottom_dock, bg="#0d1117")
        right_dock.pack(side=tk.RIGHT, fill=tk.Y, padx=(6, 10), pady=4)

        self.btn_bottom_zoom_reset = tk.Button(
            right_dock, text="🔍 Reset Zoom", font=("Segoe UI", 8),
            bg=INPUT_BG, fg=TEXT_MUTED, activebackground=CARD_BG, activeforeground=TEXT_PRIMARY,
            relief=tk.FLAT, cursor="hand2", padx=6, pady=2, bd=0,
            command=self._reset_chart_zoom
        )
        self.btn_bottom_zoom_reset.pack(side=tk.LEFT, padx=(0, 4), fill=tk.Y)

        self.btn_bottom_quant_tiers = tk.Button(
            right_dock, text="📊 Quant Tiers", font=("Segoe UI", 8, "bold"),
            bg=INPUT_BG, fg=GOLD, activebackground=CARD_BG, activeforeground="#ffffff",
            relief=tk.FLAT, cursor="hand2", padx=8, pady=2, bd=0,
            command=self._open_quant_ranking_tiers_modal
        )
        self.btn_bottom_quant_tiers.pack(side=tk.LEFT, padx=(0, 4), fill=tk.Y)

        self.btn_bottom_settings = tk.Button(
            right_dock, text="⚙ Settings", font=("Segoe UI", 8),
            bg=INPUT_BG, fg=TEXT_PRIMARY, activebackground=CARD_BG, activeforeground="#ffffff",
            relief=tk.FLAT, cursor="hand2", padx=8, pady=2, bd=0,
            command=self._open_settings_modal
        )
        self.btn_bottom_settings.pack(side=tk.LEFT, padx=(0, 6), fill=tk.Y)

        self.btn_bottom_scan = tk.Button(
            right_dock, text="⚡ SCAN DUAL SETUPS", font=("Segoe UI", 9, "bold"),
            bg=GOLD, fg="#0b0f17", activebackground=GOLD_HOVER, activeforeground="#ffffff",
            relief=tk.FLAT, cursor="hand2", padx=12, pady=2, bd=0,
            command=self.execute_auto_scan
        )
        self.btn_bottom_scan.pack(side=tk.LEFT, fill=tk.Y)


    # ========================== CHROME-STYLE INTEGRATED TOOLBAR ==========================
    def _build_chrome_toolbar(self):
        # Master single-row bar: height 44px, seamlessly merges window controls, tabs, parameter selectors, and actions
        self.top_bar = tk.Frame(self.root, bg="#0d1117", height=44, highlightbackground=BORDER_COL, highlightthickness=1)
        self.top_bar.pack(fill=tk.X, side=tk.TOP)
        self.top_bar.pack_propagate(False)

        # Brand / App Icon & Chrome-style Tabs on Left
        left_box = tk.Frame(self.top_bar, bg="#0d1117")
        left_box.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 4))

        tk.Label(left_box, text="⚡", font=("Segoe UI", 12), fg=GOLD, bg="#0d1117").pack(side=tk.LEFT, padx=(2, 6))

        # Tabs container (styled like browser active/inactive tabs)
        tabs_box = tk.Frame(left_box, bg="#0d1117")
        tabs_box.pack(side=tk.LEFT, fill=tk.Y, pady=5)

        self.btn_mode_auto = tk.Button(
            tabs_box, text="⧉ Dual Auto", font=("Segoe UI", 9, "bold"),
            bg=GOLD, fg="#0b0f17", relief=tk.FLAT, cursor="hand2", padx=10, pady=2,
            highlightthickness=0, bd=0,
            command=lambda: self._set_app_mode("auto")
        )
        self.btn_mode_auto.pack(side=tk.LEFT, padx=(0, 2), fill=tk.Y)

        self.btn_mode_manual = tk.Button(
            tabs_box, text="📊 Manual", font=("Segoe UI", 9, "bold"),
            bg=INPUT_BG, fg=TEXT_MUTED, relief=tk.FLAT, cursor="hand2", padx=10, pady=2,
            highlightthickness=0, bd=0,
            command=lambda: self._set_app_mode("manual")
        )
        self.btn_mode_manual.pack(side=tk.LEFT, padx=(2, 6), fill=tk.Y)

        # Center Parameter Quick Controls (In-line toolbar)
        center_box = tk.Frame(self.top_bar, bg="#0d1117")
        center_box.pack(side=tk.LEFT, fill=tk.Y, padx=4)

        # Timeframe toggle (M1 / M5)
        tf_box = tk.Frame(center_box, bg=CARD_BG, padx=2, pady=2, highlightbackground=BORDER_COL, highlightthickness=1)
        tf_box.pack(side=tk.LEFT, pady=6, padx=(0, 6))

        self.btn_tf_m5 = tk.Button(
            tf_box, text="M5", font=("Segoe UI", 8, "bold"),
            bg=GOLD, fg="#0b0f17", relief=tk.FLAT, cursor="hand2", padx=7, pady=1,
            highlightthickness=0, bd=0,
            command=lambda: self._set_timeframe("M5")
        )
        self.btn_tf_m5.pack(side=tk.LEFT)

        self.btn_tf_m1 = tk.Button(
            tf_box, text="M1", font=("Segoe UI", 8, "bold"),
            bg=INPUT_BG, fg=TEXT_MUTED, relief=tk.FLAT, cursor="hand2", padx=7, pady=1,
            highlightthickness=0, bd=0,
            command=lambda: self._set_timeframe("M1")
        )
        self.btn_tf_m1.pack(side=tk.LEFT)

        # Strategy Combobox
        self.strategy_var = tk.StringVar(value="ATR Pullback & Swing (Default)")
        self.strategy_combo = ttk.Combobox(
            center_box, textvariable=self.strategy_var,
            values=[
                "ATR Pullback & Swing (Default)",
                "Breakout + POC Retest",
                "Liquidity Sweep + FVG",
                "Session ORB (Asia/London/NY)",
                "Bollinger Extremes (Z-Score)",
                "Accumulation + Inverse FVG (IFVG)",
                "Liquidity Sweep + Shift Structure (SMS)",
                "Liquidity Absorption + Volume Bubbles",
                "Order Flow Footprint Proxy"
            ],
            state="readonly", font=("Segoe UI", 8), width=23
        )
        self.strategy_combo.pack(side=tk.LEFT, pady=8, padx=(0, 6))
        self.strategy_combo.bind("<<ComboboxSelected>>", lambda e: self._on_strategy_change())

        # Candidate Grid Combobox
        self.candidate_grid_var = tk.StringVar(value="0 (Versi Asli / Baseline)")
        self.candidate_grid_combo = ttk.Combobox(
            center_box, textvariable=self.candidate_grid_var,
            values=[
                "0 (Versi Asli / Baseline)",
                "5 Variasi (Cepat)",
                "10 Variasi (Seimbang)",
                "20 Variasi (Optimal Brute-Force)"
            ],
            state="readonly", font=("Segoe UI", 8), width=16
        )
        self.candidate_grid_combo.pack(side=tk.LEFT, pady=8, padx=(0, 6))
        self.candidate_grid_combo.bind("<<ComboboxSelected>>", lambda e: self.execute_auto_scan() if self.active_mode == "auto" else None)

        # Replays Combobox
        self.replays_var = tk.StringVar(value="5,000")
        self.replays_combo = ttk.Combobox(
            center_box, textvariable=self.replays_var,
            values=["100", "250", "500", "1,000", "3,000", "5,000", "10,000"],
            state="readonly", font=("Segoe UI", 8), width=7
        )
        self.replays_combo.pack(side=tk.LEFT, pady=8, padx=(0, 8))

        # Main Scan / Run Action Button in Toolbar
        self.btn_run_auto = tk.Button(
            center_box, text="⚡ SCAN DUAL", font=("Segoe UI", 9, "bold"),
            bg=GOLD, fg="#0b0f17", activebackground=GOLD_HOVER, activeforeground="#ffffff",
            relief=tk.FLAT, cursor="hand2", padx=10, pady=2,
            highlightthickness=0, bd=0,
            command=self.execute_auto_scan
        )
        self.btn_run_auto.pack(side=tk.LEFT, pady=6, padx=(0, 2))

        self.btn_run_manual = tk.Button(
            center_box, text="🚀 RUN SIM", font=("Segoe UI", 9, "bold"),
            bg=GOLD, fg="#0b0f17", activebackground=GOLD_HOVER, activeforeground="#ffffff",
            relief=tk.FLAT, cursor="hand2", padx=10, pady=2,
            highlightthickness=0, bd=0,
            command=self.execute_manual_simulation
        )

        # Aligned Tools / Actions Icons (In-line with menus):
        # ⚙ Settings modal, 📋 Copy setups to clipboard, 📥 MT5 active positions
        tools_box = tk.Frame(self.top_bar, bg="#0d1117")
        tools_box.pack(side=tk.LEFT, fill=tk.Y, padx=(4, 6))

        def make_tool_icon(text, tooltip_text, cmd, col=GOLD):
            b = tk.Label(tools_box, text=text, font=("Segoe UI", 11), fg=col, bg="#0d1117", width=3, cursor="hand2")
            b.pack(side=tk.LEFT, fill=tk.Y, pady=2)
            b.bind("<Button-1>", lambda e: cmd())
            b.bind("<Enter>", lambda e: b.configure(bg=CARD_BG))
            b.bind("<Leave>", lambda e: b.configure(bg="#0d1117"))
            return b

        self.btn_gear_settings = make_tool_icon("⚙", "Global Settings", self._open_settings_modal)
        self.btn_matrix_modal = make_tool_icon("🧮", "20-Combination Matrix", self._open_combination_matrix_modal, col=GREEN)
        self.btn_copy_signals = make_tool_icon("📋", "Copy Setup Signals", self._copy_signals_to_clipboard)
        self.import_mt5_btn = make_tool_icon("📥", "Impor Posisi MT5", self._open_positions_selector, col=CYAN)

        # Auto Refresh Interval Dropdown (Off, 5s, 10s, 15s (Default), 30s, 60s)
        self.auto_refresh_var = tk.StringVar(value="15s")
        self.auto_refresh_combo = ttk.Combobox(
            tools_box, textvariable=self.auto_refresh_var,
            values=["Off", "5s", "10s", "15s", "30s", "60s"],
            state="readonly", font=("Segoe UI", 8), width=5
        )
        self.auto_refresh_combo.pack(side=tk.LEFT, padx=(4, 2), pady=8)
        self.auto_refresh_combo.bind("<<ComboboxSelected>>", lambda e: self._on_auto_refresh_change())

        # Right Area: Window controls (—, ▢, ✕) & Price Pill
        right_box = tk.Frame(self.top_bar, bg="#0d1117")
        right_box.pack(side=tk.RIGHT, fill=tk.Y)

        # Window Action Buttons (Frameless window controllers)
        btn_box = tk.Frame(right_box, bg="#0d1117")
        btn_box.pack(side=tk.RIGHT, fill=tk.Y)

        def make_wbtn(text, cmd, hover_bg=CARD_BG, hover_fg=TEXT_PRIMARY):
            b = tk.Label(btn_box, text=text, font=("Segoe UI", 9), fg=TEXT_MUTED, bg="#0d1117", width=4, cursor="hand2")
            b.pack(side=tk.LEFT, fill=tk.Y)
            b.bind("<Button-1>", lambda e: cmd())
            b.bind("<Enter>", lambda e: b.configure(bg=hover_bg, fg=hover_fg))
            b.bind("<Leave>", lambda e: b.configure(bg="#0d1117", fg=TEXT_MUTED))
            return b

        make_wbtn("—", self._minimize_window)
        make_wbtn("▢", self._toggle_maximize)
        make_wbtn("✕", self._close_window, hover_bg="#dc2626", hover_fg="#ffffff")

        # Market Price Badge & Quick Sync Pill
        market_pill = tk.Frame(right_box, bg=CARD_BG, padx=8, pady=2, highlightbackground=BORDER_COL, highlightthickness=1)
        market_pill.pack(side=tk.RIGHT, pady=6, padx=(4, 8))

        self.price_badge = tk.Label(
            market_pill, text="Syncing Market...", font=("Segoe UI", 8, "bold"),
            fg=TEXT_PRIMARY, bg=CARD_BG
        )
        self.price_badge.pack(side=tk.LEFT, padx=(0, 4))

        tk.Button(
            market_pill, text="🔄", font=("Segoe UI", 8, "bold"),
            bg=INPUT_BG, fg=GOLD, relief=tk.FLAT, cursor="hand2", padx=4, pady=1,
            highlightthickness=0, bd=0,
            command=self.refresh_data
        ).pack(side=tk.LEFT)

        # Middle Draggable Spacer Frame: fills any gap between toolbar items and right controls
        drag_spacer = tk.Frame(self.top_bar, bg="#0d1117", cursor="fleur")
        drag_spacer.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Bind window dragging to top bar, spacer, and labels
        for w in (self.top_bar, left_box, tabs_box, drag_spacer):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._do_drag)

    def _start_drag(self, event):
        self._drag_data["x"] = event.x_root - self.root.winfo_x()
        self._drag_data["y"] = event.y_root - self.root.winfo_y()

    def _do_drag(self, event):
        if not self.is_maximized:
            x = event.x_root - self._drag_data["x"]
            y = event.y_root - self._drag_data["y"]
            self.root.geometry(f"+{x}+{y}")

    def _minimize_window(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
        except Exception:
            self.root.iconify()

    def _toggle_maximize(self):
        if not self.is_maximized:
            self.prev_geometry = self.root.geometry()
            # Maximized without overlapping taskbar
            w = self.root.winfo_screenwidth()
            h = self.root.winfo_screenheight() - 40
            self.root.geometry(f"{w}x{h}+0+0")
            self.is_maximized = True
        else:
            self.root.geometry(self.prev_geometry)
            self.is_maximized = False

    def _close_window(self):
        if getattr(self, "_auto_refresh_job", None):
            try:
                self.root.after_cancel(self._auto_refresh_job)
            except Exception:
                pass
            self._auto_refresh_job = None
        self._save_settings()
        self.root.destroy()

    # ========================== MAIN BODY ==========================
    def _build_main_body(self):
        # Full-window body frame without bulky 340px sidebar
        self.body_frame = tk.Frame(self.root, bg=DARK_BG, padx=8, pady=8)
        self.body_frame.pack(fill=tk.BOTH, expand=True)

        self.right_panel = tk.Frame(self.body_frame, bg=DARK_BG)
        self.right_panel.pack(fill=tk.BOTH, expand=True)

        # Initialize internal variables required by settings & models
        self.horizon_var = tk.StringVar(value="4 Jam (48 bars M5)")
        self.opt_profile_var = tk.StringVar(value="WR Oriented")
        self.risk_pct_var = tk.StringVar(value="1.0")
        self.initial_capital_var = tk.StringVar(value="10000")
        self.max_dd_limit_var = tk.StringVar(value="20.0")
        self.ruin_threshold_var = tk.StringVar(value="50.0")
        self.rr_candidates_var = tk.StringVar(value="1:1, 1:1.5, 1:2, 1:3, 1:4, 1:5, 1:7, 1:10")
        self.spread_var = tk.StringVar(value="0.24")
        self.engine_mode_var = tk.StringVar(value="Legacy V1 (Default)")
        self.proj_mode_var = tk.StringVar(value="Two-Stream Free Drift (Recommended)")
        self.tie_break_var = tk.StringVar(value="Smart Candle Anatomy (Recommended)")
        self.seasonality_var = tk.StringVar(value="Off (Default/Asli)")
        self.grid_lines_var = tk.StringVar(value="Dynamic Adaptive (Default)")

        # TP/SL Variables (Opsi Disable TP/SL dan Limit Orders - Default Disabled)
        self.enable_tpsl_var = tk.BooleanVar(value=False)
        self.enable_limits_var = tk.BooleanVar(value=False)
        self.tpsl_mode_var = tk.StringVar(value="Disabled (Murni Sinyal)")
        self.point_size_var = tk.StringVar(value="0.01")
        self.fixed_tp_points_var = tk.StringVar(value="2000")
        self.fixed_sl_points_var = tk.StringVar(value="1000")
        self.tp_min_points_var = tk.StringVar(value="1000")
        self.tp_max_points_var = tk.StringVar(value="5000")
        self.tp_step_points_var = tk.StringVar(value="500")
        self.sl_min_points_var = tk.StringVar(value="500")
        self.sl_max_points_var = tk.StringVar(value="2000")
        self.sl_step_points_var = tk.StringVar(value="250")
        self.rr_ratio_var = tk.StringVar(value="1:2.0")
        self.rr_sl_points_var = tk.StringVar(value="1000")

        # Trace TP/SL variable edits for auto-recalculation
        for var in (
            self.point_size_var, self.fixed_tp_points_var, self.fixed_sl_points_var,
            self.tp_min_points_var, self.tp_max_points_var, self.tp_step_points_var,
            self.sl_min_points_var, self.sl_max_points_var, self.sl_step_points_var,
            self.rr_ratio_var, self.rr_sl_points_var
        ):
            var.trace_add("write", lambda *args: self._on_tpsl_points_modified())

        # Initialize combobox references for compatibility with tests & settings persistence
        self.horizon_combo = ttk.Combobox(self.right_panel, textvariable=self.horizon_var, values=[h[0] for h in HORIZON_PRESETS_M5], state="readonly")
        self.engine_mode_combo = ttk.Combobox(self.right_panel, textvariable=self.engine_mode_var, values=["Legacy V1 (Default)", "Enhanced OHLC V2", "Compare V1 vs V2"], state="readonly")
        self.proj_combo = ttk.Combobox(self.right_panel, textvariable=self.proj_mode_var, values=list(PROJECTION_MODES.keys()), state="readonly")
        self.tb_combo = ttk.Combobox(self.right_panel, textvariable=self.tie_break_var, values=list(TIE_BREAK_MODES.keys()), state="readonly")
        self.seasonality_combo = ttk.Combobox(self.right_panel, textvariable=self.seasonality_var, values=list(SEASONALITY_MODES.keys()), state="readonly")
        self.grid_lines_combo = ttk.Combobox(self.right_panel, textvariable=self.grid_lines_var, values=["Dynamic Adaptive (Default)", "25 Lines", "50 Lines"], state="readonly")
        self.tpsl_mode_combo = ttk.Combobox(self.right_panel, textvariable=self.tpsl_mode_var, values=["Auto Structure & Native", "ATR Adaptive", "RR Sweep (1:1 s/d 1:10)", "Fixed TP/SL", "TP/SL Range Sweep", "Risk Reward (Custom)"], state="readonly")

        # Dummy button bindings for data sources (re-used in modal)
        self.btn_src_mt5 = tk.Button(self.right_panel, text="MT5")
        self.btn_src_comex = tk.Button(self.right_panel, text="COMEX")

        # Container for TP/SL fields in settings modal
        self.tpsl_fields_frame = tk.Frame(self.right_panel)

        # Build Dual Auto View & Manual View
        self._build_auto_view()
        self._build_manual_view()

        # Show initial mode
        self._update_view_visibility()

    # ========================== AUTO DUAL FAN CHART VIEW ==========================
    def _build_auto_view(self):
        self.auto_view_frame = tk.Frame(self.right_panel, bg=DARK_BG)

        # Top Summary Verdict Banner
        self.dual_summary_card = tk.Frame(self.auto_view_frame, bg=PANEL_BG, padx=12, pady=8, highlightbackground=BORDER_COL, highlightthickness=1)
        self.dual_summary_card.pack(fill=tk.X, pady=(0, 8))

        self.dual_summary_title = tk.Label(
            self.dual_summary_card, text="⚖️ DUAL QUANT SCANNER READY", font=("Segoe UI", 11, "bold"),
            fg=GOLD, bg=PANEL_BG, anchor="w"
        )
        self.dual_summary_title.pack(fill=tk.X)

        self.dual_summary_desc = tk.Label(
            self.dual_summary_card, text="Klik 'SCAN DUAL SETUPS' untuk menghitung probabilitas BUY LIMIT dan SELL LIMIT secara bersamaan.",
            font=("Segoe UI", 9), fg=TEXT_MUTED, bg=PANEL_BG, anchor="w"
        )
        self.dual_summary_desc.pack(fill=tk.X)

        # Dual Fan Charts Container (Side-by-Side Split)
        charts_split = tk.Frame(self.auto_view_frame, bg=DARK_BG)
        charts_split.pack(fill=tk.BOTH, expand=True)
        charts_split.rowconfigure(0, weight=1)
        charts_split.grid_columnconfigure(0, weight=1, uniform="group1")
        charts_split.grid_columnconfigure(1, weight=1, uniform="group1")

        # LEFT: BUY FAN CHART
        self.buy_chart_frame = tk.Frame(charts_split, bg=PANEL_BG, highlightbackground=GREEN, highlightthickness=1)
        self.buy_chart_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        buy_header = tk.Frame(self.buy_chart_frame, bg=PANEL_BG, padx=10, pady=6)
        buy_header.pack(fill=tk.X)
        tk.Label(buy_header, text="🟢 BUY LIMIT PROBABILITY CONE", font=("Segoe UI", 10, "bold"), fg=GREEN, bg=PANEL_BG).pack(side=tk.LEFT)
        self.buy_odds_lbl = tk.Label(buy_header, text="Target: --% | Expected: -- R", font=("Segoe UI", 9, "bold"), fg=TEXT_PRIMARY, bg=PANEL_BG)
        self.buy_odds_lbl.pack(side=tk.RIGHT)
        btn_reset_buy = tk.Button(
            buy_header, text="⟲ Reset Zoom", font=("Segoe UI", 8),
            bg=INPUT_BG, fg=TEXT_MUTED, activebackground=PANEL_BG, activeforeground=GOLD,
            relief="flat", padx=6, pady=1, cursor="hand2", command=self._reset_chart_zoom
        )
        btn_reset_buy.pack(side=tk.RIGHT, padx=(0, 8))

        self.buy_canvas = tk.Canvas(self.buy_chart_frame, bg="#0f141d", highlightthickness=0)
        self.buy_canvas.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        self.buy_canvas.bind("<Configure>", lambda e: self._draw_dual_charts())
        self._bind_chart_canvas_events(self.buy_canvas)

        # RIGHT: SELL FAN CHART
        self.sell_chart_frame = tk.Frame(charts_split, bg=PANEL_BG, highlightbackground=RED, highlightthickness=1)
        self.sell_chart_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        sell_header = tk.Frame(self.sell_chart_frame, bg=PANEL_BG, padx=10, pady=6)
        sell_header.pack(fill=tk.X)
        tk.Label(sell_header, text="🔴 SELL LIMIT PROBABILITY CONE", font=("Segoe UI", 10, "bold"), fg=RED, bg=PANEL_BG).pack(side=tk.LEFT)
        self.sell_odds_lbl = tk.Label(sell_header, text="Target: --% | Expected: -- R", font=("Segoe UI", 9, "bold"), fg=TEXT_PRIMARY, bg=PANEL_BG)
        self.sell_odds_lbl.pack(side=tk.RIGHT)
        btn_reset_sell = tk.Button(
            sell_header, text="⟲ Reset Zoom", font=("Segoe UI", 8),
            bg=INPUT_BG, fg=TEXT_MUTED, activebackground=PANEL_BG, activeforeground=GOLD,
            relief="flat", padx=6, pady=1, cursor="hand2", command=self._reset_chart_zoom
        )
        btn_reset_sell.pack(side=tk.RIGHT, padx=(0, 8))

        self.sell_canvas = tk.Canvas(self.sell_chart_frame, bg="#0f141d", highlightthickness=0)
        self.sell_canvas.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        self.sell_canvas.bind("<Configure>", lambda e: self._draw_dual_charts())
        self._bind_chart_canvas_events(self.sell_canvas)

    # ========================== MANUAL SINGLE FAN CHART VIEW ==========================
    def _build_manual_view(self):
        self.manual_view_frame = tk.Frame(self.right_panel, bg=DARK_BG)

        # Top Control Ribbon for Manual Setup (Entry, SL, TP, Direction, Run)
        m_ribbon = tk.Frame(self.manual_view_frame, bg=PANEL_BG, padx=12, pady=6, highlightbackground=BORDER_COL, highlightthickness=1)
        m_ribbon.pack(fill=tk.X, pady=(0, 6))

        # Direction buttons
        self.direction_var = tk.StringVar(value="BUY")
        dir_box = tk.Frame(m_ribbon, bg=PANEL_BG)
        dir_box.pack(side=tk.LEFT, padx=(0, 10))

        self.buy_btn = tk.Button(
            dir_box, text="▲ BUY", font=("Segoe UI", 8, "bold"),
            bg=GREEN, fg="#ffffff", relief=tk.FLAT, cursor="hand2", padx=8, pady=2,
            command=lambda: self._set_direction("BUY")
        )
        self.buy_btn.pack(side=tk.LEFT, padx=(0, 2))

        self.sell_btn = tk.Button(
            dir_box, text="▼ SELL", font=("Segoe UI", 8, "bold"),
            bg=INPUT_BG, fg=TEXT_MUTED, relief=tk.FLAT, cursor="hand2", padx=8, pady=2,
            command=lambda: self._set_direction("SELL")
        )
        self.sell_btn.pack(side=tk.LEFT)

        def make_m_input(parent, label, var, fg_col=TEXT_PRIMARY):
            f = tk.Frame(parent, bg=PANEL_BG)
            f.pack(side=tk.LEFT, padx=6)
            tk.Label(f, text=label, font=("Segoe UI", 7, "bold"), fg=TEXT_MUTED, bg=PANEL_BG).pack(anchor="w")
            e = tk.Entry(
                f, textvariable=var, font=("Segoe UI", 9, "bold"), width=9,
                bg=INPUT_BG, fg=fg_col, relief=tk.FLAT, highlightthickness=1, highlightbackground=BORDER_COL, highlightcolor=GOLD
            )
            e.pack(ipady=1)
            return e

        self.manual_entry_var = tk.StringVar(value="3875.00")
        self.manual_entry_var.trace_add("write", self._on_manual_price_change)
        make_m_input(m_ribbon, "Entry Price ($)", self.manual_entry_var)

        self.manual_stop_var = tk.StringVar(value="3850.00")
        self.manual_stop_var.trace_add("write", self._on_manual_price_change)
        make_m_input(m_ribbon, "Stop Loss ($)", self.manual_stop_var, fg_col=RED)

        self.manual_target_var = tk.StringVar(value="3925.00")
        self.manual_target_var.trace_add("write", self._on_manual_price_change)
        make_m_input(m_ribbon, "Take Profit ($)", self.manual_target_var, fg_col=GREEN)

        self.manual_rr_lbl = tk.Label(
            m_ribbon, text="Risk: $25.00 | Reward: $50.00 | 2.00 R",
            font=("Segoe UI", 8, "bold"), fg=GOLD, bg=CARD_BG, padx=8, pady=4,
            highlightbackground=BORDER_COL, highlightthickness=1
        )
        self.manual_rr_lbl.pack(side=tk.LEFT, padx=8)

        tk.Button(
            m_ribbon, text="🚀 SIMULASI", font=("Segoe UI", 8, "bold"),
            bg=GOLD, fg="#0b0f17", relief=tk.FLAT, cursor="hand2", padx=10, pady=2,
            command=self.execute_manual_simulation
        ).pack(side=tk.LEFT, padx=6)

        # 4 Stat Cards in Row
        m_score_row = tk.Frame(self.manual_view_frame, bg=DARK_BG)
        m_score_row.pack(fill=tk.X, pady=(0, 6))

        self.m_card_win = self._create_card(m_score_row, "TARGET FIRST", "-- %", GREEN)
        self.m_card_loss = self._create_card(m_score_row, "STOP FIRST", "-- %", RED)
        self.m_card_open = self._create_card(m_score_row, "NEITHER / OPEN", "-- %", BLUE)
        self.m_card_r = self._create_card(m_score_row, "EXPECTED RETURN", "-- R", GOLD)

        # Verdict
        self.m_verdict_card = tk.Frame(self.manual_view_frame, bg=PANEL_BG, padx=12, pady=6, highlightbackground=BORDER_COL, highlightthickness=1)
        self.m_verdict_card.pack(fill=tk.X, pady=(0, 6))
        self.m_verdict_lbl = tk.Label(self.m_verdict_card, text="Click 'RUN SIMULATION' to test custom setup.", font=("Segoe UI", 10, "bold"), fg=TEXT_PRIMARY, bg=PANEL_BG, anchor="w")
        self.m_verdict_lbl.pack(fill=tk.X)

        # Single Manual Canvas
        m_chart_box = tk.Frame(self.manual_view_frame, bg=PANEL_BG, highlightbackground=BORDER_COL, highlightthickness=1)
        m_chart_box.pack(fill=tk.BOTH, expand=True)

        m_chart_header = tk.Frame(m_chart_box, bg=PANEL_BG, padx=10, pady=4)
        m_chart_header.pack(fill=tk.X)
        tk.Label(m_chart_header, text="📊 PROBABILITY PATH SIMULATION", font=("Segoe UI", 9, "bold"), fg=GOLD, bg=PANEL_BG).pack(side=tk.LEFT)
        btn_reset_manual = tk.Button(
            m_chart_header, text="⟲ Reset Zoom", font=("Segoe UI", 8),
            bg=INPUT_BG, fg=TEXT_MUTED, activebackground=PANEL_BG, activeforeground=GOLD,
            relief="flat", padx=6, pady=1, cursor="hand2", command=self._reset_chart_zoom
        )
        btn_reset_manual.pack(side=tk.RIGHT)

        self.manual_canvas = tk.Canvas(m_chart_box, bg="#0f141d", highlightthickness=0)
        self.manual_canvas.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        self.manual_canvas.bind("<Configure>", lambda e: self._draw_manual_chart())
        self._bind_chart_canvas_events(self.manual_canvas)

    def _create_card(self, parent, title, val, col):
        f = tk.Frame(parent, bg=PANEL_BG, padx=10, pady=8, highlightbackground=BORDER_COL, highlightthickness=1)
        f.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=3)
        tk.Label(f, text=title, font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=PANEL_BG).pack(anchor="w")
        lbl = tk.Label(f, text=val, font=("Segoe UI", 16, "bold"), fg=col, bg=PANEL_BG)
        lbl.pack(anchor="w")
        return lbl

    # ========================== MODE SWITCHING ==========================
    def _set_app_mode(self, mode):
        self.active_mode = mode
        if mode == "auto":
            self.btn_mode_auto.configure(bg=GOLD, fg="#0b0f17")
            self.btn_mode_manual.configure(bg=INPUT_BG, fg=TEXT_MUTED)
        else:
            self.btn_mode_manual.configure(bg=GOLD, fg="#0b0f17")
            self.btn_mode_auto.configure(bg=INPUT_BG, fg=TEXT_MUTED)
            if not self.manual_result and self.bars_data:
                self.execute_manual_simulation()
        self._update_view_visibility()

    def _update_view_visibility(self):
        if self.active_mode == "auto":
            if hasattr(self, "manual_view_frame"):
                self.manual_view_frame.pack_forget()
            if hasattr(self, "auto_view_frame"):
                self.auto_view_frame.pack(fill=tk.BOTH, expand=True)
            if hasattr(self, "btn_run_manual") and hasattr(self, "btn_run_auto"):
                self.btn_run_manual.pack_forget()
                self.btn_run_auto.pack(side=tk.LEFT, pady=6, padx=(0, 2))
        else:
            if hasattr(self, "auto_view_frame"):
                self.auto_view_frame.pack_forget()
            if hasattr(self, "manual_view_frame"):
                self.manual_view_frame.pack(fill=tk.BOTH, expand=True)
            if hasattr(self, "btn_run_manual") and hasattr(self, "btn_run_auto"):
                self.btn_run_auto.pack_forget()
                self.btn_run_manual.pack(side=tk.LEFT, pady=6, padx=(0, 2))

    def _switch_data_source(self, source):
        self.current_source = source
        if source == "mt5":
            self.btn_src_mt5.configure(bg=GOLD, fg="#0b0f17")
            self.btn_src_comex.configure(bg=INPUT_BG, fg=TEXT_MUTED)
        else:
            self.btn_src_comex.configure(bg=GOLD, fg="#0b0f17")
            self.btn_src_mt5.configure(bg=INPUT_BG, fg=TEXT_MUTED)
        self.refresh_data()

    def _set_timeframe(self, tf):
        self.current_timeframe = tf
        if tf == "M5":
            self.btn_tf_m5.configure(bg=GOLD, fg="#0b0f17")
            self.btn_tf_m1.configure(bg=INPUT_BG, fg=TEXT_MUTED)
            self.horizon_combo.configure(values=[h[0] for h in HORIZON_PRESETS_M5])
            self.horizon_var.set("4 Jam (48 bars M5)")
        else:
            self.btn_tf_m1.configure(bg=GOLD, fg="#0b0f17")
            self.btn_tf_m5.configure(bg=INPUT_BG, fg=TEXT_MUTED)
            self.horizon_combo.configure(values=[h[0] for h in HORIZON_PRESETS_M1])
            self.horizon_var.set("4 Jam (240 bars M1)")
        self.refresh_data()

    def _parse_rr_ratio(self, text):
        s = str(text or "").strip()
        if ":" in s:
            parts = s.split(":")
            if len(parts) == 2:
                num = float(parts[0].strip())
                denom = float(parts[1].strip())
                if num > 0 and denom > 0:
                    return denom / num
        val = float(s)
        if not math.isfinite(val) or val <= 0:
            raise ValueError("R:R ratio must be greater than 0.")
        return val

    def _update_rr_info_label(self):
        if not hasattr(self, "rr_info_label") or not self.rr_info_label.winfo_exists():
            return
        try:
            ratio = self._parse_rr_ratio(self.rr_ratio_var.get())
            sl_pts = int(self.rr_sl_points_var.get().strip())
            p_size = float(self.point_size_var.get().strip())
            if ratio <= 0 or sl_pts <= 0 or p_size <= 0:
                self.rr_info_label.configure(text="", fg=TEXT_MUTED)
                return
            tp_pts = max(1, int(round(sl_pts * ratio)))
            tp_val = tp_pts * p_size
            sl_val = sl_pts * p_size
            tp_str = f"${tp_val:,.2f}" if abs(tp_val) >= 1.0 else f"${tp_val:g}"
            sl_str = f"${sl_val:,.2f}" if abs(sl_val) >= 1.0 else f"${sl_val:g}"
            self.rr_info_label.configure(
                text=f"🎯 Target TP: {tp_pts:,} pts ({tp_str}) | SL: {sl_pts:,} pts ({sl_str})",
                fg=GOLD
            )
        except Exception:
            self.rr_info_label.configure(
                text="ℹ️ Masukkan R:R (mis. 1:2) dan SL points yang valid",
                fg=TEXT_MUTED
            )

    def _render_tpsl_fields(self):
        for child in self.tpsl_fields_frame.winfo_children():
            child.destroy()

        mode = self.tpsl_mode_var.get()
        if mode == "Auto Optimize":
            tk.Label(
                self.tpsl_fields_frame,
                text="TP/SL dicari otomatis dari ATR dan struktur harga.",
                font=("Segoe UI", 7), fg=TEXT_MUTED, bg=CARD_BG,
                wraplength=280, justify=tk.LEFT
            ).pack(anchor="w")
            if hasattr(self, "bind_sidebar_mousewheel"):
                self.bind_sidebar_mousewheel(self.tpsl_fields_frame)
            return

        def add_field(parent, label, variable, row, col, width=9):
            cell = tk.Frame(parent, bg=CARD_BG)
            cell.grid(row=row, column=col, sticky="ew", padx=(0 if col == 0 else 6, 0), pady=2)
            tk.Label(cell, text=label, font=("Segoe UI", 7, "bold"), fg=TEXT_MUTED, bg=CARD_BG).pack(anchor="w")
            tk.Entry(
                cell, textvariable=variable, width=width, font=("Segoe UI", 8),
                bg=INPUT_BG, fg=TEXT_PRIMARY, relief=tk.FLAT,
                highlightthickness=1, highlightbackground=BORDER_COL, highlightcolor=GOLD
            ).pack(fill=tk.X, ipady=2)
            parent.grid_columnconfigure(col, weight=1)

        add_field(self.tpsl_fields_frame, "Point Size ($/point)", self.point_size_var, 0, 0, 12)
        note = "Satu point dalam nilai harga broker. MT5 mengisi dari symbol_info.point bila tersedia; verifikasi untuk data COMEX/cache."
        tk.Label(
            self.tpsl_fields_frame, text=note, font=("Segoe UI", 6),
            fg=TEXT_MUTED, bg=CARD_BG, wraplength=280, justify=tk.LEFT
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(1, 4))

        if mode == "Fixed TP/SL":
            add_field(self.tpsl_fields_frame, "Take Profit (points)", self.fixed_tp_points_var, 2, 0)
            add_field(self.tpsl_fields_frame, "Stop Loss (points)", self.fixed_sl_points_var, 2, 1)
        elif mode == "Risk Reward":
            cell_rr = tk.Frame(self.tpsl_fields_frame, bg=CARD_BG)
            cell_rr.grid(row=2, column=0, sticky="ew", padx=(0, 0), pady=2)
            tk.Label(cell_rr, text="Target R:R", font=("Segoe UI", 7, "bold"), fg=TEXT_MUTED, bg=CARD_BG).pack(anchor="w")
            self.rr_combo = ttk.Combobox(
                cell_rr, textvariable=self.rr_ratio_var,
                values=["1:1.5", "1:2.0", "1:3.0", "1:4.0", "1:5.0", "1:10.0"],
                font=("Segoe UI", 8), width=9
            )
            self.rr_combo.pack(fill=tk.X, ipady=1)
            self.rr_combo.bind("<<ComboboxSelected>>", lambda e: self._on_tpsl_points_modified())
            self.tpsl_fields_frame.grid_columnconfigure(0, weight=1)

            add_field(self.tpsl_fields_frame, "Stop Loss (points)", self.rr_sl_points_var, 2, 1)

            self.rr_info_label = tk.Label(
                self.tpsl_fields_frame,
                text="",
                font=("Segoe UI", 7, "bold"),
                fg=GOLD, bg=CARD_BG, justify=tk.LEFT
            )
            self.rr_info_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 2))
            self._update_rr_info_label()
        else:
            tk.Label(self.tpsl_fields_frame, text="Take Profit range (points)", font=("Segoe UI", 7, "bold"), fg=GOLD, bg=CARD_BG).grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))
            add_field(self.tpsl_fields_frame, "TP Min", self.tp_min_points_var, 3, 0)
            add_field(self.tpsl_fields_frame, "TP Max", self.tp_max_points_var, 3, 1)
            add_field(self.tpsl_fields_frame, "TP Step", self.tp_step_points_var, 4, 0)
            tk.Label(self.tpsl_fields_frame, text="Stop Loss range (points)", font=("Segoe UI", 7, "bold"), fg=GOLD, bg=CARD_BG).grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 0))
            add_field(self.tpsl_fields_frame, "SL Min", self.sl_min_points_var, 6, 0)
            add_field(self.tpsl_fields_frame, "SL Max", self.sl_max_points_var, 6, 1)
            add_field(self.tpsl_fields_frame, "SL Step", self.sl_step_points_var, 7, 0)

        if hasattr(self, "bind_sidebar_mousewheel"):
            self.bind_sidebar_mousewheel(self.tpsl_fields_frame)

    def _on_strategy_change(self):
        desc_map = {
            "ATR Pullback & Swing (Default)": "Pencarian level limit dari pullback ATR bertingkat dan swing structure 24 bar.",
            "Breakout + POC Retest": "Mendeteksi Point of Control (POC) dan Value Area dari Volume Profile untuk entri retest.",
            "Liquidity Sweep + FVG": "Mendeteksi pembersihan likuiditas (sweep) dan Fair Value Gap (FVG) imbalance.",
            "Session ORB (Asia/London/NY)": "Mengidentifikasi batas Open Range Breakout (ORB) dan entri retest batas pembukaan sesi.",
            "Bollinger Extremes (Z-Score)": "Menempatkan limit order di deviasi ekstrem Bollinger Bands (mean reversion +/-2.0 sigma).",
            "Accumulation + Inverse FVG (IFVG)": "Mendeteksi range akumulasi, sweep likuiditas, dan entri retest pada Inverse Fair Value Gap (IFVG).",
            "Liquidity Sweep + Shift Structure (SMS)": "Mendeteksi sweep swing high/low, konfirmasi Market Structure Shift (SMS), dan entri retest Order Block.",
            "Liquidity Absorption + Volume Bubbles": "Mendeteksi penyerapan likuiditas di level ekstrem saat terjadi lonjakan volume bar (volume bubble proxy).",
            "Order Flow Footprint Proxy": "Mendeteksi bid/ask absorption melalui lonjakan volume dan penolakan sumbu panjang (rejection wick > 1.5x body)."
        }
        text = desc_map.get(self.strategy_var.get(), "")
        if hasattr(self, "strategy_desc_label"):
            self.strategy_desc_label.configure(text=text)
        if self.active_mode == "auto":
            self.execute_auto_scan()

    def _on_tpsl_mode_change(self):
        self._render_tpsl_fields()
        if self.active_mode == "auto":
            self._on_tpsl_points_modified()

    def _on_tpsl_points_modified(self):
        """Debounced auto-calculation triggered when research TP/SL points are edited."""
        if self.active_mode != "auto":
            return
        mode = self.tpsl_mode_var.get()
        if mode == "Auto Optimize":
            return

        if mode == "Risk Reward":
            self._update_rr_info_label()

        # Quick validation without popping modal dialogs
        try:
            p_size = float(self.point_size_var.get().strip())
            if p_size <= 0:
                return
            if mode == "Fixed TP/SL":
                tp = int(self.fixed_tp_points_var.get().strip())
                sl = int(self.fixed_sl_points_var.get().strip())
                if tp <= 0 or sl <= 0:
                    return
            elif mode == "Risk Reward":
                ratio = self._parse_rr_ratio(self.rr_ratio_var.get())
                sl = int(self.rr_sl_points_var.get().strip())
                if ratio <= 0 or sl <= 0:
                    return
            elif mode == "TP/SL Range":
                tp_min = int(self.tp_min_points_var.get().strip())
                tp_max = int(self.tp_max_points_var.get().strip())
                tp_step = int(self.tp_step_points_var.get().strip())
                sl_min = int(self.sl_min_points_var.get().strip())
                sl_max = int(self.sl_max_points_var.get().strip())
                sl_step = int(self.sl_step_points_var.get().strip())
                if tp_min <= 0 or tp_max < tp_min or tp_step <= 0:
                    return
                if sl_min <= 0 or sl_max < sl_min or sl_step <= 0:
                    return
        except Exception:
            return  # User might still be typing or backspacing

        if self._auto_scan_debounce_timer:
            self.root.after_cancel(self._auto_scan_debounce_timer)
        self._auto_scan_debounce_timer = self.root.after(450, self.execute_auto_scan)

    def _get_tpsl_scan_params(self):
        mode_str = self.tpsl_mode_var.get()
        mode_map = {
            "Auto Optimize": "auto",
            "Auto Structure & Native": "auto",
            "ATR Adaptive": "atr",
            "Fixed TP/SL": "fixed",
            "TP/SL Range": "range",
            "TP/SL Range Sweep": "range",
            "Risk Reward": "risk_reward",
            "RR Sweep (1:1 s/d 1:10)": "rr_sweep"
        }
        mode = mode_map.get(mode_str, "auto")
        
        # Profile & Capital Risk Configuration
        opt_profile = "wr_oriented" if "wr" in self.opt_profile_var.get().lower() else "rr_oriented"
        try:
            risk_pct = float(str(self.risk_pct_var.get()).replace("%", "").strip()) / 100.0
        except Exception:
            risk_pct = 0.01

        try:
            init_cap = float(str(self.initial_capital_var.get()).replace("$", "").replace(",", "").strip())
        except Exception:
            init_cap = 10000.0

        try:
            max_dd = float(str(self.max_dd_limit_var.get()).replace("%", "").strip()) / 100.0
        except Exception:
            max_dd = 0.20

        try:
            ruin_th = float(str(self.ruin_threshold_var.get()).replace("%", "").strip()) / 100.0
        except Exception:
            ruin_th = 0.50

        params = {
            "tpsl_mode": mode,
            "optimization_profile": opt_profile,
            "initial_capital": init_cap,
            "risk_pct": risk_pct,
            "max_drawdown_limit": max_dd,
            "ruin_threshold": ruin_th,
            "compounding": True,
            "costs_r": 0.02
        }

        if mode != "auto":
            try:
                params["point_size"] = float(self.point_size_var.get().strip())
                self._point_size_custom = True
            except Exception:
                params["point_size"] = 0.01

        if mode == "fixed":
            params["fixed_tp_points"] = int(self.fixed_tp_points_var.get().strip())
            params["fixed_sl_points"] = int(self.fixed_sl_points_var.get().strip())
        elif mode == "risk_reward":
            params["rr_ratio"] = self._parse_rr_ratio(self.rr_ratio_var.get())
            params["rr_sl_points"] = int(self.rr_sl_points_var.get().strip())
        elif mode == "rr_sweep":
            params["rr_sl_points"] = int(self.rr_sl_points_var.get().strip())
            params["rr_candidates"] = [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0]
        elif mode == "range":
            params.update({
                "tp_min_points": int(self.tp_min_points_var.get().strip()),
                "tp_max_points": int(self.tp_max_points_var.get().strip()),
                "tp_step_points": int(self.tp_step_points_var.get().strip()),
                "sl_min_points": int(self.sl_min_points_var.get().strip()),
                "sl_max_points": int(self.sl_max_points_var.get().strip()),
                "sl_step_points": int(self.sl_step_points_var.get().strip())
            })
        return params

    def _on_methodology_change(self):
        self.current_projection_mode = PROJECTION_MODES.get(self.proj_mode_var.get(), "free_drift")
        self.current_tie_break = TIE_BREAK_MODES.get(self.tie_break_var.get(), "smart")
        self.current_seasonality = SEASONALITY_MODES.get(self.seasonality_var.get(), False)
        if self.active_mode == "auto":
            self.execute_auto_scan()
        elif self.active_mode == "manual" and self.manual_result:
            self.execute_manual_simulation()

    def _on_display_setting_change(self):
        if self.active_mode == "auto":
            self._draw_dual_charts()
        elif self.active_mode == "manual":
            self._draw_manual_chart()

    # ========================== DATA & EXECUTION ==========================
    def _initial_load_data(self):
        self._fetch_data()
        # Automatically run dual auto-scan on startup
        self.root.after(300, self.execute_auto_scan)
        # Start scheduled auto-refresh loop (default 15s)
        self.root.after(1000, self._schedule_next_auto_refresh)

    def _fetch_data(self):
        try:
            if self.current_source == "mt5":
                status = mt5_connector.get_mt5_connection()
                if status.get("connected"):
                    self.bars_data = mt5_connector.get_mt5_gold_bars(timeframe=self.current_timeframe)
                    self._sync_point_size_from_data()
                    self.current_market_price = self.bars_data.get("current_price", 3875.0)
                    self.current_spread = self.bars_data.get("spread", 0.24)
                    self.mt5_positions = mt5_connector.get_open_gold_positions()
                    self.root.after(0, lambda: self._update_mt5_header(status))
                else:
                    self.root.after(0, lambda: self.price_badge.configure(text="⚠️ MT5 Disconnected"))
            else:
                self.bars_data = timemachine.get_gold_bars(source="comex")
                self._sync_point_size_from_data()
                self.current_market_price = self.bars_data.get("current_price", 3898.0)
                self.current_spread = 0.25
                self.root.after(0, self._update_comex_header)
        except Exception as e:
            self.root.after(0, lambda: self.price_badge.configure(text=f"Sync: {e}"))

    def _sync_point_size_from_data(self):
        if not isinstance(self.bars_data, dict):
            return
        value = self.bars_data.get("point_size")
        try:
            point_size = float(value)
            if point_size > 0:
                # If custom point size produces an invalid/extreme price jump (> 50% of market price),
                # or if point_size is not custom, auto-reset to broker's valid point size.
                current_p = self.current_market_price or 3875.0
                try:
                    cur_val = float(self.point_size_var.get().strip())
                except Exception:
                    cur_val = 0.0

                if not self._point_size_custom or cur_val <= 0 or (cur_val * 1000 > current_p):
                    self._point_size_custom = False
                    val_str = format(point_size, ".10g")
                    self.point_size_var.set(val_str)
                    self.root.after(0, lambda v=val_str: self.point_size_var.set(v))
        except (TypeError, ValueError):
            pass

    def _update_mt5_header(self, status):
        sym = self.bars_data.get("symbol", "XAUUSD")
        cur = self.current_market_price
        broker = status.get("broker", "MT5")
        self.price_badge.configure(text=f"🟢 {sym} [{self.current_timeframe}]: ${cur:.2f} (Spread: ${self.current_spread:.2f})")
        self.spread_var.set(f"{self.current_spread:.2f}")

    def _update_comex_header(self):
        cur = self.current_market_price
        self.price_badge.configure(text=f"🌐 COMEX: ${cur:.2f}")
        self.spread_var.set("0.25")

    def refresh_data(self):
        self.price_badge.configure(text="Refreshing...")
        threading.Thread(target=lambda: [self._fetch_data(), self.execute_auto_scan() if self.active_mode == "auto" else None], daemon=True).start()

    def _on_auto_refresh_change(self):
        """Handle user changing auto-refresh interval (Off, 5s, 10s, 15s, 30s, 60s)."""
        if self._auto_refresh_job:
            try:
                self.root.after_cancel(self._auto_refresh_job)
            except Exception:
                pass
            self._auto_refresh_job = None
        self._schedule_next_auto_refresh()

    def _schedule_next_auto_refresh(self):
        """Schedule periodic auto-refresh cycle if interval is enabled."""
        val = getattr(self, "auto_refresh_var", None)
        if not val:
            return
        choice = val.get().strip().lower()
        sec_map = {"5s": 5, "10s": 10, "15s": 15, "30s": 30, "60s": 60}
        seconds = sec_map.get(choice)
        if not seconds:
            return

        self._auto_refresh_job = self.root.after(seconds * 1000, self._auto_refresh_tick)

    def _auto_refresh_tick(self):
        """Triggered periodically to fetch fresh market data and re-calculate setup odds."""
        self._auto_refresh_job = None
        def bg_sync():
            try:
                self._fetch_data()
                if self.active_mode == "auto" and not getattr(self, "_is_scanning", False):
                    self.root.after(0, self.execute_auto_scan)
            except Exception:
                pass
            finally:
                self.root.after(0, self._schedule_next_auto_refresh)

        threading.Thread(target=bg_sync, daemon=True).start()

    def _get_selected_horizon_bars(self):
        h_text = self.horizon_var.get()
        interval = 1 if self.current_timeframe == "M1" else 5
        return timemachine.normalize_horizon_bars(h_text, interval_minutes=interval)

    def _on_horizon_change(self):
        if self.active_mode == "auto":
            self.execute_auto_scan()

    # ========================== EXECUTE AUTO SCAN ==========================
    def execute_auto_scan(self):
        bars_count = self._get_selected_horizon_bars()
        replays = int(self.replays_var.get().replace(",", "").replace(".", "").strip())
        spread = float(self.spread_var.get() or 0.24)
        proj_mode = self.current_projection_mode
        tb_mode = self.current_tie_break
        season_mode = self.current_seasonality
        engine_mode = {"Legacy V1 (Default)": "legacy", "Enhanced OHLC V2": "v2", "Compare V1 vs V2": "compare"}.get(self.engine_mode_var.get(), "legacy")
        strategy_code = {
            "ATR Pullback & Swing (Default)": "atr_swing",
            "Breakout + POC Retest": "poc",
            "Liquidity Sweep + FVG": "fvg",
            "Session ORB (Asia/London/NY)": "orb",
            "Bollinger Extremes (Z-Score)": "zscore",
            "Accumulation + Inverse FVG (IFVG)": "acc_ifvg",
            "Liquidity Sweep + Shift Structure (SMS)": "sweep_sms",
            "Liquidity Absorption + Volume Bubbles": "absorption",
            "Order Flow Footprint Proxy": "footprint"
        }.get(self.strategy_var.get(), "atr_swing")
        candidate_count = 0
        if hasattr(self, "candidate_grid_var"):
            try:
                candidate_count = int(self.candidate_grid_var.get().split()[0])
            except (ValueError, IndexError):
                candidate_count = 0
        try:
            tpsl_params = self._get_tpsl_scan_params()
        except (TypeError, ValueError) as exc:
            messagebox.showerror("TP/SL Configuration", f"Periksa konfigurasi TP/SL: {exc}")
            return

        self.btn_run_auto.configure(state=tk.DISABLED, text="⚡ SCANNING...")
        self.dual_summary_title.configure(text="⏳ Scanning BUY & SELL candidates...", fg=GOLD)
        self._is_scanning = True

        def worker():
            try:
                res = analyzer.find_dual_recommendations(
                    bars_data=self.bars_data,
                    horizon_bars=bars_count,
                    replays=replays,
                    spread=spread,
                    projection_mode=proj_mode,
                    tie_break=tb_mode,
                    seasonality=season_mode,
                    engine_mode=engine_mode,
                    strategy=strategy_code,
                    candidate_count=candidate_count,
                    **tpsl_params
                )
                self.root.after(0, lambda r=res: self._apply_dual_results(r))
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda msg=err_msg: self._show_scan_error(msg))
            finally:
                self._is_scanning = False
                self.root.after(0, lambda: self.btn_run_auto.configure(state=tk.NORMAL, text="⚡ SCAN DUAL SETUPS"))

        threading.Thread(target=worker, daemon=True).start()

    def _show_scan_error(self, err_msg):
        self.dual_summary_title.configure(text="⚠️ Scan Error", fg=RED)
        self.dual_summary_desc.configure(text=f"Gagal melakukan simulasi: {err_msg}")


    def _apply_dual_results(self, res):
        self.dual_results = res
        best_dir = res["best_direction"]
        summary = res["summary"]

        # Update Bottom Dock Live Capital HUD
        try:
            rec = res.get(best_dir.lower(), res.get("buy", {}))
            cq = rec.get("capital_quality", {})
            tq = rec.get("trade_quality", {})
            wf = rec.get("walk_forward_validation", {})
            hud_txt = (
                f"[{res.get('strategy_label', 'Strategy')}] Best: {best_dir} | "
                f"Resolved WR: {tq.get('resolved_win_rate_pct', 0.0):.1f}% | "
                f"Target RR: 1:{tq.get('target_rr', 2.0):g} | "
                f"Geom Growth: {cq.get('geometric_growth_pct', 0.0):+.2f}%/tr | "
                f"MaxDD: {cq.get('max_drawdown_pct_median', 0.0):.1f}% | "
                f"Ruin: {cq.get('probability_of_ruin_pct', 0.0):.1f}% | "
                f"OOS: {wf.get('out_of_sample_status', 'N/A').upper()}"
            )
            if hasattr(self, "lbl_dock_hud"):
                self.lbl_dock_hud.configure(text=hud_txt, fg=GOLD if best_dir == "BUY" else (RED if best_dir == "SELL" else TEXT_MUTED))
        except Exception:
            pass

        # Update Summary Banner
        col = GREEN if best_dir == "BUY" else (RED if best_dir == "SELL" else GOLD)
        strat_lbl = res.get("strategy_label", "ATR & Swing")

        search_info = res.get("search", {})
        cand_req = search_info.get("candidate_count_requested", 0)
        buy_entries = search_info.get("buy_entries_scanned")
        sell_entries = search_info.get("sell_entries_scanned")
        if buy_entries is None or sell_entries is None:
            eff = search_info.get("effective_entries_per_side", search_info.get("entries_scanned", cand_req))
            if isinstance(eff, dict):
                buy_entries = eff.get("buy", cand_req)
                sell_entries = eff.get("sell", cand_req)
            else:
                buy_entries = sell_entries = eff

        buy_cand = search_info.get("buy_candidates_scanned", 0)
        sell_cand = search_info.get("sell_candidates_scanned", 0)
        quota_adj = search_info.get("entry_quota_adjusted", False)

        grid_note = ""
        if cand_req > 0:
            if buy_entries == sell_entries:
                entries_str = f"{buy_entries}"
            else:
                entries_str = f"BUY {buy_entries} / SELL {sell_entries}"

            if quota_adj:
                grid_note = f" • Grid: {entries_str}/{cand_req} entri ({buy_cand}+{sell_cand} plan, kuota dinamis)"
            else:
                grid_note = f" • Grid: {entries_str} entri ({buy_cand}+{sell_cand} plan)"

        self.dual_summary_title.configure(text=f"⭐ BEST QUANT EDGE: {best_dir} SETUP", fg=col)
        self.dual_summary_desc.configure(text=f"[{strat_lbl}{grid_note}] {summary}")

        # Update Headers
        bo = res["buy"]["odds"]
        so = res["sell"]["odds"]

        b_sign = "+" if bo["avg_r"] > 0 else ""
        s_sign = "+" if so["avg_r"] > 0 else ""
        bp = res["buy"]["plan"]
        sp = res["sell"]["plan"]
        buy_tpsl_label = f"{bp['tp_points']}/{bp['sl_points']} pts" if "tp_points" in bp and "sl_points" in bp else "Auto ATR/Structure"
        sell_tpsl_label = f"{sp['tp_points']}/{sp['sl_points']} pts" if "tp_points" in sp and "sl_points" in sp else "Auto ATR/Structure"
        bp_tag = f"[{bp['setup_tag']}] " if bp.get("setup_tag") else ""
        sp_tag = f"[{sp['setup_tag']}] " if sp.get("setup_tag") else ""
        self.buy_odds_lbl.configure(
            text=f"{bp_tag}TP: {bo['target_first_pct']:.1f}% | Touch: {bp['entry_touch_probability_pct']:.0f}% | RR: 1:{bp['target_r']:.2f} | Adj.Exp: {bp['fill_adjusted_simulated_avg_r']:+.2f}R | TP/SL: {buy_tpsl_label}",
            fg=GREEN if bp["fill_adjusted_simulated_avg_r"] > 0 else TEXT_MUTED
        )
        self.sell_odds_lbl.configure(
            text=f"{sp_tag}TP: {so['target_first_pct']:.1f}% | Touch: {sp['entry_touch_probability_pct']:.0f}% | RR: 1:{sp['target_r']:.2f} | Adj.Exp: {sp['fill_adjusted_simulated_avg_r']:+.2f}R | TP/SL: {sell_tpsl_label}",
            fg=RED if sp["fill_adjusted_simulated_avg_r"] > 0 else TEXT_MUTED
        )

        # Render Both Canvases
        self._draw_dual_charts()

    # ========================== DRAWING DUAL CHARTS & INTERACTIVE ZOOM ==========================
    def _nice_grid_step(self, raw_step):
        """Calculate clean round 'nice numbers' (1, 2, 5, 10, 20, 50, etc.) for dynamic grid lines."""
        if raw_step <= 0:
            return 1.0
        exponent = math.floor(math.log10(raw_step))
        fraction = raw_step / (10 ** exponent)
        if fraction <= 1.5:
            nice_fraction = 1.0
        elif fraction <= 3.0:
            nice_fraction = 2.0
        elif fraction <= 7.0:
            nice_fraction = 5.0
        else:
            nice_fraction = 10.0
        return nice_fraction * (10 ** exponent)

    def _bind_chart_canvas_events(self, canvas):
        """Bind mouse wheel, drag-to-pan, and double-click reset events to chart canvas."""
        canvas.bind("<Enter>", lambda e: canvas.focus_set())
        canvas.bind("<MouseWheel>", self._on_chart_mousewheel)
        canvas.bind("<Button-4>", lambda e: self._on_chart_mousewheel_linux(e, 1))
        canvas.bind("<Button-5>", lambda e: self._on_chart_mousewheel_linux(e, -1))
        canvas.bind("<ButtonPress-1>", self._on_chart_pan_start)
        canvas.bind("<B1-Motion>", self._on_chart_pan_motion)
        canvas.bind("<ButtonRelease-1>", self._on_chart_pan_end)
        canvas.bind("<Double-Button-1>", self._reset_chart_zoom)
        canvas.bind("<Motion>", self._on_chart_mouse_motion)
        canvas.bind("<Leave>", self._on_chart_mouse_leave)

    def _on_chart_mousewheel_linux(self, event, direction):
        event.delta = 120 * direction
        self._on_chart_mousewheel(event)

    def _on_chart_mousewheel(self, event):
        """Handle cursor-centered zoom for price (Ctrl+Wheel), time (Shift+Wheel), or proportional (Wheel)."""
        delta = getattr(event, "delta", 0)
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else (1.0 / 1.15)

        ctrl_pressed = bool(getattr(event, "state", 0) & 0x0004)
        shift_pressed = bool(getattr(event, "state", 0) & 0x0001)

        w = event.widget.winfo_width() if event.widget.winfo_width() >= 50 else 500
        h = event.widget.winfo_height() if event.widget.winfo_height() >= 50 else 350
        pad_left = 60
        pad_right = 20
        pad_top = 25
        pad_bottom = 35
        plot_w = max(10, w - pad_left - pad_right)
        plot_h = max(10, h - pad_top - pad_bottom)

        y_rel = min(1.0, max(0.0, (event.y - pad_top) / plot_h)) if plot_h > 0 else 0.5
        x_rel = min(1.0, max(0.0, (event.x - pad_left) / plot_w)) if plot_w > 0 else 0.5

        if ctrl_pressed and not shift_pressed:
            zoom_y_active = True
            zoom_x_active = False
        elif shift_pressed and not ctrl_pressed:
            zoom_y_active = False
            zoom_x_active = True
        else:
            zoom_y_active = True
            zoom_x_active = True

        if zoom_y_active:
            old_zoom_y = self.zoom_y
            new_zoom_y = min(10.0, max(0.5, old_zoom_y * factor))
            if new_zoom_y != old_zoom_y and getattr(self, "_cached_base_range", 0) > 0:
                base_range = self._cached_base_range
                orig_mid = self._cached_orig_mid
                old_range = base_range / old_zoom_y
                old_mid = orig_mid + self.pan_y
                price_at_cursor = (old_mid + 0.5 * old_range) - y_rel * old_range
                new_range = base_range / new_zoom_y
                self.pan_y = price_at_cursor - (0.5 - y_rel) * new_range - orig_mid
                self.zoom_y = new_zoom_y

        if zoom_x_active:
            old_zoom_x = self.zoom_x
            new_zoom_x = min(10.0, max(0.5, old_zoom_x * factor))
            if new_zoom_x != old_zoom_x and getattr(self, "_cached_total_steps", 0) > 0:
                total_steps = self._cached_total_steps
                old_vis_steps = total_steps / old_zoom_x
                step_at_cursor = self.pan_x + x_rel * old_vis_steps
                new_vis_steps = total_steps / new_zoom_x
                self.pan_x = step_at_cursor - x_rel * new_vis_steps
                self.zoom_x = new_zoom_x

        self._redraw_active_charts()

    def _on_chart_pan_start(self, event):
        if event.widget == getattr(self, "manual_canvas", None) and getattr(self, "_hover_line", None) is not None:
            self._dragging_line = self._hover_line
            self._is_panning = False
            self._drag_start_y = event.y
            try:
                self._drag_orig_entry = float(self.manual_entry_var.get())
                self._drag_orig_stop = float(self.manual_stop_var.get())
                self._drag_orig_target = float(self.manual_target_var.get())
            except Exception:
                pass
            self._cached_drag_min_p = getattr(self, "_cached_base_min_p", None)
            self._cached_drag_max_p = getattr(self, "_cached_base_max_p", None)
            try:
                event.widget.configure(cursor="sb_v_double_arrow")
            except Exception:
                pass
            return

        self._dragging_line = None
        self._pan_start_x = event.x
        self._pan_start_y = event.y
        self._is_panning = True
        try:
            event.widget.configure(cursor="fleur")
        except Exception:
            pass

    def _on_chart_pan_motion(self, event):
        if getattr(self, "_dragging_line", None) is not None:
            self._handle_manual_line_drag(event)
            return

        if not getattr(self, "_is_panning", False):
            return
        dx = event.x - self._pan_start_x
        dy = event.y - self._pan_start_y
        self._pan_start_x = event.x
        self._pan_start_y = event.y

        if getattr(self, "_cached_plot_h", 0) > 0 and getattr(self, "_cached_vis_price_range", 0) > 0:
            d_price = (dy / self._cached_plot_h) * self._cached_vis_price_range
            self.pan_y += d_price

        if getattr(self, "_cached_plot_w", 0) > 0 and getattr(self, "_cached_vis_steps", 0) > 0:
            d_steps = -(dx / self._cached_plot_w) * self._cached_vis_steps
            self.pan_x += d_steps

        self._redraw_active_charts()

    def _on_chart_pan_end(self, event):
        if getattr(self, "_dragging_line", None) is not None:
            self._dragging_line = None
            self._cached_drag_min_p = None
            self._cached_drag_max_p = None
            try:
                event.widget.configure(cursor="")
            except Exception:
                pass
            # Trigger real-time simulation on release
            if getattr(self, "bars_data", None) and getattr(self, "active_mode", None) == "manual":
                self.execute_manual_simulation()
            return

        self._is_panning = False
        try:
            event.widget.configure(cursor="")
        except Exception:
            pass

    def _on_chart_mouse_motion(self, event):
        """Track hover over draggable lines (TP, SL, Entry) in manual simulation canvas."""
        if event.widget != getattr(self, "manual_canvas", None):
            return
        if getattr(self, "_dragging_line", None) is not None:
            return  # currently dragging, maintain drag cursor

        pad_left = getattr(self, "_cached_pad_left", 60)
        pad_right = getattr(self, "_cached_pad_right", 20)
        w = event.widget.winfo_width() if event.widget.winfo_width() >= 50 else (getattr(self, "_cached_plot_w", 400) + pad_left + pad_right)

        # Only activate hover inside chart area
        if event.x < pad_left - 15 or event.x > w - pad_right + 15:
            if getattr(self, "_hover_line", None) is not None:
                self._hover_line = None
                self._draw_manual_chart()
                try:
                    event.widget.configure(cursor="")
                except Exception:
                    pass
            return

        y_tp = getattr(self, "_cached_y_tp", None)
        y_sl = getattr(self, "_cached_y_sl", None)
        y_en = getattr(self, "_cached_y_en", None)

        d_tp = abs(event.y - y_tp) if y_tp is not None else 999.0
        d_sl = abs(event.y - y_sl) if y_sl is not None else 999.0
        d_en = abs(event.y - y_en) if y_en is not None else 999.0

        min_d = min(d_tp, d_sl, d_en)
        if min_d <= 8:
            if min_d == d_tp:
                new_hover = "tp"
            elif min_d == d_sl:
                new_hover = "sl"
            else:
                new_hover = "entry"

            if getattr(self, "_hover_line", None) != new_hover:
                self._hover_line = new_hover
                self._draw_manual_chart()
            try:
                event.widget.configure(cursor="sb_v_double_arrow")
            except Exception:
                pass
        else:
            if getattr(self, "_hover_line", None) is not None:
                self._hover_line = None
                self._draw_manual_chart()
            try:
                event.widget.configure(cursor="")
            except Exception:
                pass

    def _on_chart_mouse_leave(self, event):
        if getattr(self, "_dragging_line", None) is None:
            if getattr(self, "_hover_line", None) is not None:
                self._hover_line = None
                if event.widget == getattr(self, "manual_canvas", None):
                    self._draw_manual_chart()
            try:
                event.widget.configure(cursor="")
            except Exception:
                pass

    def _handle_manual_line_drag(self, event):
        line_type = self._dragging_line
        if not line_type:
            return

        plot_h = getattr(self, "_cached_plot_h", 0)
        pad_top = getattr(self, "_cached_pad_top", 25)
        min_p = getattr(self, "_cached_min_p", 0.0)
        max_p = getattr(self, "_cached_max_p", 1.0)
        if plot_h <= 0 or max_p <= min_p:
            return

        y_clamped = max(pad_top + 2, min(pad_top + plot_h - 2, event.y))
        norm_y = 1.0 - (y_clamped - pad_top) / float(plot_h)
        raw_price = min_p + norm_y * (max_p - min_p)

        try:
            pt_sz = float(self.point_size_var.get().strip())
            if pt_sz <= 0:
                pt_sz = 0.01
        except Exception:
            pt_sz = 0.01

        decimals = 2
        if pt_sz < 0.001:
            decimals = 4
        elif pt_sz >= 1.0:
            decimals = 0

        new_price = round(round(raw_price / pt_sz) * pt_sz, decimals)

        is_buy = (self.direction_var.get() == "BUY")
        try:
            cur_entry = float(self.manual_entry_var.get())
            cur_stop = float(self.manual_stop_var.get())
            cur_target = float(self.manual_target_var.get())
        except Exception:
            cur_entry = self._drag_orig_entry
            cur_stop = self._drag_orig_stop
            cur_target = self._drag_orig_target

        min_buf = max(pt_sz * 5, 0.5)

        if line_type == "entry":
            shift_pressed = bool(getattr(event, "state", 0) & 0x0001)
            delta = new_price - cur_entry
            new_entry = new_price
            if shift_pressed:
                if is_buy:
                    new_entry = max(cur_stop + min_buf, min(cur_target - min_buf, new_entry))
                else:
                    new_entry = min(cur_stop - min_buf, max(cur_target + min_buf, new_entry))
                self.manual_entry_var.set(f"{new_entry:.{decimals}f}")
            else:
                new_stop = round(cur_stop + delta, decimals)
                new_target = round(cur_target + delta, decimals)
                self.manual_entry_var.set(f"{new_entry:.{decimals}f}")
                self.manual_stop_var.set(f"{new_stop:.{decimals}f}")
                self.manual_target_var.set(f"{new_target:.{decimals}f}")

        elif line_type == "tp":
            if is_buy:
                new_price = max(cur_entry + min_buf, new_price)
            else:
                new_price = min(cur_entry - min_buf, new_price)
            self.manual_target_var.set(f"{new_price:.{decimals}f}")

        elif line_type == "sl":
            if is_buy:
                new_price = min(cur_entry - min_buf, new_price)
            else:
                new_price = max(cur_entry + min_buf, new_price)
            self.manual_stop_var.set(f"{new_price:.{decimals}f}")

        if getattr(self, "manual_result", None) and "plan" in self.manual_result:
            p = self.manual_result["plan"]
            try:
                e_val = float(self.manual_entry_var.get())
                s_val = float(self.manual_stop_var.get())
                t_val = float(self.manual_target_var.get())
                p["entry"] = e_val
                p["stop"] = s_val
                p["target"] = t_val
                risk = abs(e_val - s_val)
                reward = abs(t_val - e_val)
                p["target_r"] = reward / risk if risk > 0 else 0.0
            except Exception:
                pass

        self._draw_manual_chart()

    def _reset_chart_zoom(self, event=None):
        """Reset chart zoom and pan to 100% auto-fit."""
        self.zoom_y = 1.0
        self.zoom_x = 1.0
        self.pan_y = 0.0
        self.pan_x = 0.0
        self._redraw_active_charts()

    def _zoom_step(self, factor):
        """Keyboard shortcut zoom step."""
        self.zoom_y = min(10.0, max(0.5, self.zoom_y * factor))
        self.zoom_x = min(10.0, max(0.5, self.zoom_x * factor))
        self._redraw_active_charts()

    def _redraw_active_charts(self):
        """Redraw active chart canvases according to current mode."""
        if self.active_mode == "auto":
            self._draw_dual_charts()
        else:
            self._draw_manual_chart()

    def _extract_chart_bounds(self, sim_res):
        try:
            fan = sim_res.get("fan_data", {})
            plan = sim_res.get("plan", {})
            p5 = fan.get("p5", [])
            p95 = fan.get("p95", [])
            entry = plan.get("entry")
            stop = plan.get("stop")
            target = plan.get("target")
            vals = list(p5) + list(p95)
            for v in (entry, stop, target):
                if v is not None:
                    vals.append(v)
            return vals
        except Exception:
            return []

    def _draw_dual_charts(self):
        if not self.dual_results:
            return

        buy_res = self.dual_results.get("buy")
        sell_res = self.dual_results.get("sell")

        shared_bounds = None
        if buy_res and sell_res:
            b_vals = self._extract_chart_bounds(buy_res)
            s_vals = self._extract_chart_bounds(sell_res)
            comb = b_vals + s_vals
            if comb:
                shared_bounds = (min(comb), max(comb))
        elif buy_res:
            b_vals = self._extract_chart_bounds(buy_res)
            if b_vals:
                shared_bounds = (min(b_vals), max(b_vals))
        elif sell_res:
            s_vals = self._extract_chart_bounds(sell_res)
            if s_vals:
                shared_bounds = (min(s_vals), max(s_vals))

        if buy_res:
            self._render_cone(self.buy_canvas, buy_res, is_buy=True, price_bounds=shared_bounds)
        if sell_res:
            self._render_cone(self.sell_canvas, sell_res, is_buy=False, price_bounds=shared_bounds)

    def _render_cone(self, canvas, sim_res, is_buy, price_bounds=None):
        canvas.delete("all")
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w < 50:
            w = canvas.winfo_reqwidth()
        if h < 50:
            h = canvas.winfo_reqheight()
        if w < 50 or h < 50:
            return

        pad_left = 60
        pad_right = 20
        pad_top = 25
        pad_bottom = 35

        plot_w = max(10, w - pad_left - pad_right)
        plot_h = max(10, h - pad_top - pad_bottom)

        fan = sim_res["fan_data"]
        plan = sim_res["plan"]
        sample_paths = sim_res.get("sample_paths", [])

        steps = fan["step_bars"]
        p5 = fan["p5"]
        p25 = fan["p25"]
        p50 = fan["p50"]
        p75 = fan["p75"]
        p95 = fan["p95"]

        entry = plan["entry"]
        stop = plan["stop"]
        target = plan["target"]

        is_manual = (canvas == getattr(self, "manual_canvas", None))
        if is_manual and getattr(self, "_dragging_line", None) is not None and getattr(self, "_cached_drag_min_p", None) is not None:
            base_min_p = self._cached_drag_min_p
            base_max_p = self._cached_drag_max_p
        elif price_bounds:
            base_min_p, base_max_p = price_bounds
        else:
            all_vals = p5 + p95 + [entry, stop, target]
            base_min_p = min(all_vals)
            base_max_p = max(all_vals)
            margin = max(1.0, (base_max_p - base_min_p) * 0.08)
            base_min_p -= margin
            base_max_p += margin

        base_range = max(0.01, base_max_p - base_min_p)
        orig_mid = 0.5 * (base_min_p + base_max_p)

        # Store cache for zoom/pan and drag calculations
        self._cached_base_range = base_range
        self._cached_orig_mid = orig_mid
        self._cached_base_min_p = base_min_p
        self._cached_base_max_p = base_max_p
        self._cached_pad_top = pad_top
        self._cached_pad_bottom = pad_bottom
        self._cached_pad_left = pad_left
        self._cached_pad_right = pad_right
        total_steps = float(steps[-1]) if steps[-1] > 0 else 1.0
        self._cached_total_steps = total_steps
        self._cached_plot_w = plot_w
        self._cached_plot_h = plot_h

        # Apply zoom_y and pan_y
        zoom_y = getattr(self, "zoom_y", 1.0)
        pan_y = getattr(self, "pan_y", 0.0)
        vis_price_range = base_range / max(0.2, zoom_y)
        self._cached_vis_price_range = vis_price_range
        cur_mid = orig_mid + pan_y
        min_p = cur_mid - 0.5 * vis_price_range
        max_p = cur_mid + 0.5 * vis_price_range
        self._cached_min_p = min_p
        self._cached_max_p = max_p

        # Apply zoom_x and pan_x
        zoom_x = getattr(self, "zoom_x", 1.0)
        pan_x = getattr(self, "pan_x", 0.0)
        vis_steps = total_steps / max(0.2, zoom_x)
        self._cached_vis_steps = vis_steps
        min_step = pan_x
        max_step = pan_x + vis_steps

        def to_x(s_val):
            return pad_left + ((s_val - min_step) / vis_steps) * plot_w

        def to_y(pr):
            return pad_top + (1.0 - (pr - min_p) / (max_p - min_p)) * plot_h

        # 1. 90% Ribbon
        poly_90 = []
        for s, v in zip(steps, p95):
            poly_90.extend([to_x(s), to_y(v)])
        for s, v in reversed(list(zip(steps, p5))):
            poly_90.extend([to_x(s), to_y(v)])
        if len(poly_90) >= 6:
            canvas.create_polygon(poly_90, fill="#182232", outline="")

        # 2. 50% Ribbon
        poly_50 = []
        for s, v in zip(steps, p75):
            poly_50.extend([to_x(s), to_y(v)])
        for s, v in reversed(list(zip(steps, p25))):
            poly_50.extend([to_x(s), to_y(v)])
        if len(poly_50) >= 6:
            canvas.create_polygon(poly_50, fill="#233147", outline="")

        # 3. Sample Paths
        for path in sample_paths[:12]:
            pts = []
            for step_idx, pr in enumerate(path):
                if step_idx < len(steps):
                    pts.extend([to_x(steps[step_idx]), to_y(pr)])
            if len(pts) >= 4:
                canvas.create_line(pts, fill="#324563", width=1)

        # 4. Median
        med_pts = []
        for s, v in zip(steps, p50):
            med_pts.extend([to_x(s), to_y(v)])
        if len(med_pts) >= 4:
            canvas.create_line(med_pts, fill=GOLD, width=2)

        # 5. Mask outer margins cleanly so no ribbons or paths bleed outside the plot area
        canvas.create_rectangle(0, 0, pad_left, h, fill="#0f141d", outline="")
        canvas.create_rectangle(w - pad_right, 0, w, h, fill="#0f141d", outline="")
        canvas.create_rectangle(0, 0, w, pad_top, fill="#0f141d", outline="")
        canvas.create_rectangle(0, h - pad_bottom, w, h, fill="#0f141d", outline="")

        # Plot outer boundary box
        canvas.create_rectangle(pad_left, pad_top, w - pad_right, h - pad_bottom, outline="#1e293b", width=1)

        # 6. Dynamic Price Grid Lines & Labels
        grid_pref = getattr(self, "grid_lines_var", None)
        grid_mode = grid_pref.get() if grid_pref else "Dynamic Adaptive (Default)"

        if "50" in grid_mode:
            raw_step = (max_p - min_p) / 50.0
            step = self._nice_grid_step(raw_step)
        elif "25" in grid_mode:
            raw_step = (max_p - min_p) / 25.0
            step = self._nice_grid_step(raw_step)
        else:
            # Dynamic Adaptive: density automatically increases with zoom
            spacing = max(24.0, 42.0 / (zoom_y ** 0.35))
            target_count = max(4, int(round(plot_h / spacing)))
            raw_step = (max_p - min_p) / target_count
            step = self._nice_grid_step(raw_step)

        start_k = math.floor(min_p / step)
        end_k = math.ceil(max_p / step)
        for k in range(start_k, end_k + 1):
            y_val = round(k * step, 6)
            y_px = to_y(y_val)
            if pad_top <= y_px <= h - pad_bottom:
                canvas.create_line(pad_left, y_px, w - pad_right, y_px, fill="#1c2536", dash=(2, 4))
                if step < 0.05:
                    lbl_txt = f"${y_val:.2f}"
                elif step < 1.0:
                    lbl_txt = f"${y_val:.1f}" if abs(y_val * 10 - round(y_val * 10)) < 1e-4 else f"${y_val:.2f}"
                else:
                    lbl_txt = f"${int(round(y_val))}" if abs(y_val - round(y_val)) < 1e-4 else f"${y_val:.1f}"
                canvas.create_text(pad_left - 6, y_px, text=lbl_txt, fill=TEXT_MUTED, font=("Segoe UI", 8), anchor="e")

        # 7. Dynamic Time Ticks & Grid Lines
        meta = sim_res.get("meta", {}) or sim_res.get("plan", {})
        int_m = meta.get("interval_minutes", 1 if self.current_timeframe == "M1" else 5)
        total_hours = steps[-1] * int_m / 60
        is_multiday = total_hours >= 24.0

        target_x_count = max(3, int(round(plot_w / 80.0)))
        raw_x_step = vis_steps / target_x_count
        x_step = max(1.0, self._nice_grid_step(raw_x_step))

        start_step_k = math.floor(min_step / x_step)
        end_step_k = math.ceil(max_step / x_step)
        for k in range(start_step_k, end_step_k + 1):
            bar_val = round(k * x_step, 4)
            if bar_val < 0 or bar_val > steps[-1]:
                continue
            x_px = to_x(bar_val)
            if pad_left <= x_px <= w - pad_right:
                canvas.create_line(x_px, pad_top, x_px, h - pad_bottom, fill="#1c2536", dash=(2, 4))
                bar_minutes = bar_val * int_m
                if is_multiday and bar_minutes >= 1440:
                    t_lbl = f"+{bar_minutes / 1440:.1f}d"
                elif bar_minutes >= 60:
                    t_lbl = f"+{bar_minutes / 60:.1f}h"
                else:
                    t_lbl = f"+{int(round(bar_minutes))}m"
                canvas.create_text(x_px, h - pad_bottom + 12, text=t_lbl, fill=TEXT_MUTED, font=("Segoe UI", 8))

        # 8. Target, Stop, Entry lines & off-screen markers
        # Manual mode always displays draggable lines; auto mode follows enable_tpsl_var
        has_tpsl = getattr(self, "enable_tpsl_var", None) and self.enable_tpsl_var.get()
        if is_manual:
            self._cached_y_tp = None
            self._cached_y_sl = None
            self._cached_y_en = None

        if target is not None and stop is not None and (has_tpsl or is_manual):
            y_tp = to_y(target)
            if is_manual and (pad_top - 10 <= y_tp <= h - pad_bottom + 10):
                self._cached_y_tp = y_tp
            is_tp_hover = is_manual and (getattr(self, "_hover_line", None) == "tp" or getattr(self, "_dragging_line", None) == "tp")
            tp_width = 3 if is_tp_hover else 2
            tp_color = "#34d399" if is_tp_hover else GREEN

            if pad_top <= y_tp <= h - pad_bottom:
                canvas.create_line(pad_left, y_tp, w - pad_right, y_tp, fill=tp_color, width=tp_width, dash=(6, 4))
                if is_manual:
                    badge_text = f" ⇅ TP ${target:.2f} (+{plan.get('target_r', 0.0):.2f}R) "
                    tw = len(badge_text) * 7.2
                    bx2 = w - pad_right - 6
                    bx1 = bx2 - tw
                    by1 = y_tp - 18
                    by2 = y_tp + 2
                    bg_col = "#047857" if is_tp_hover else "#064e3b"
                    canvas.create_rectangle(bx1, by1, bx2, by2, fill=bg_col, outline=tp_color, width=1)
                    canvas.create_text((bx1 + bx2) / 2, (by1 + by2) / 2, text=badge_text, fill=tp_color, font=("Segoe UI", 8, "bold"))
                else:
                    canvas.create_text(w - pad_right - 6, y_tp - 10, text=f"TP ${target:.2f} (+{plan.get('target_r', 0.0):.2f}R)", fill=GREEN, font=("Segoe UI", 9, "bold"), anchor="e")
            elif y_tp < pad_top:
                canvas.create_text(w - pad_right - 6, pad_top + 12, text=f"▲ TP ${target:.2f} (+{plan.get('target_r', 0.0):.1f}R)", fill=GREEN, font=("Segoe UI", 8, "bold"), anchor="e")
            elif y_tp > h - pad_bottom:
                canvas.create_text(w - pad_right - 6, h - pad_bottom - 12, text=f"▼ TP ${target:.2f} (+{plan.get('target_r', 0.0):.1f}R)", fill=GREEN, font=("Segoe UI", 8, "bold"), anchor="e")

            y_sl = to_y(stop)
            if is_manual and (pad_top - 10 <= y_sl <= h - pad_bottom + 10):
                self._cached_y_sl = y_sl
            is_sl_hover = is_manual and (getattr(self, "_hover_line", None) == "sl" or getattr(self, "_dragging_line", None) == "sl")
            sl_width = 3 if is_sl_hover else 2
            sl_color = "#f87171" if is_sl_hover else RED

            if pad_top <= y_sl <= h - pad_bottom:
                canvas.create_line(pad_left, y_sl, w - pad_right, y_sl, fill=sl_color, width=sl_width, dash=(6, 4))
                if is_manual:
                    badge_text = f" ⇅ SL ${stop:.2f} (-1.0R) "
                    tw = len(badge_text) * 7.2
                    bx2 = w - pad_right - 6
                    bx1 = bx2 - tw
                    by1 = y_sl - 2
                    by2 = y_sl + 18
                    bg_col = "#7f1d1d" if is_sl_hover else "#450a0a"
                    canvas.create_rectangle(bx1, by1, bx2, by2, fill=bg_col, outline=sl_color, width=1)
                    canvas.create_text((bx1 + bx2) / 2, (by1 + by2) / 2, text=badge_text, fill=sl_color, font=("Segoe UI", 8, "bold"))
                else:
                    canvas.create_text(w - pad_right - 6, y_sl + 10, text=f"SL ${stop:.2f} (-1.0R)", fill=RED, font=("Segoe UI", 9, "bold"), anchor="e")
            elif y_sl < pad_top:
                canvas.create_text(w - pad_right - 6, pad_top + 24, text=f"▲ SL ${stop:.2f} (-1.0R)", fill=RED, font=("Segoe UI", 8, "bold"), anchor="e")
            elif y_sl > h - pad_bottom:
                canvas.create_text(w - pad_right - 6, h - pad_bottom - 24, text=f"▼ SL ${stop:.2f} (-1.0R)", fill=RED, font=("Segoe UI", 8, "bold"), anchor="e")

        y_en = to_y(entry)
        if is_manual and (pad_top - 10 <= y_en <= h - pad_bottom + 10):
            self._cached_y_en = y_en
        is_en_hover = is_manual and (getattr(self, "_hover_line", None) == "entry" or getattr(self, "_dragging_line", None) == "entry")
        en_width = 3 if is_en_hover else 1
        en_color = "#facc15" if is_en_hover else "#ffffff"

        has_limits = getattr(self, "enable_limits_var", None) and self.enable_limits_var.get()
        limit_lbl = ("Buy Limit" if is_buy else "Sell Limit") if (has_limits or is_manual) else ("BUY SIGNAL" if is_buy else "SELL SIGNAL")
        tag_str = f" [{plan['setup_tag']}]" if plan.get("setup_tag") else ""
        if pad_top <= y_en <= h - pad_bottom:
            canvas.create_line(pad_left, y_en, w - pad_right, y_en, fill=en_color, width=en_width, dash=(3, 3))
            if is_manual:
                badge_text = f" ⇅ {limit_lbl} ${entry:.2f} "
                tw = len(badge_text) * 7.2
                bx1 = pad_left + 8
                bx2 = bx1 + tw
                by1 = y_en - 18
                by2 = y_en + 2
                bg_col = "#334155" if is_en_hover else "#1e293b"
                canvas.create_rectangle(bx1, by1, bx2, by2, fill=bg_col, outline=en_color, width=1)
                canvas.create_text((bx1 + bx2) / 2, (by1 + by2) / 2, text=badge_text, fill=en_color, font=("Segoe UI", 8, "bold"))
            else:
                canvas.create_text(pad_left + 8, y_en - 8, text=f"{limit_lbl}{tag_str} ${entry:.2f}", fill="#ffffff", font=("Segoe UI", 8, "bold"), anchor="w")

        if is_manual:
            canvas.create_text(
                w - pad_right - 8, pad_top + 10,
                text="💡 Geser garis Entry, SL, atau TP untuk simulasi instan (Shift: Entry saja)",
                fill="#64748b", font=("Segoe UI", 8), anchor="e"
            )

        # 9. Methodology Badge
        proj_mode = meta.get("projection_mode", "free_drift")
        tb_mode = meta.get("tie_break", "smart")
        pm_tag = ("Block Bootstrap V2" if proj_mode == "block_bootstrap" else
                  ("Two-Stream" if proj_mode == "free_drift" else ("Frozen (Asli)" if proj_mode == "frozen" else "Survival")))
        tb_tag = ("Ambiguous=SL" if tb_mode == "conservative_ambiguous" else
                  ("Smart" if tb_mode == "smart" else ("SL First (Asli)" if tb_mode == "conservative" else "50:50")))

        canvas.create_text(
            pad_left + 8, pad_top + 10,
            text=f"⚙️ {pm_tag} | {tb_tag} | M{int_m}",
            fill="#64748b", font=("Segoe UI", 8), anchor="w"
        )

        # 10. Zoom Status Badge
        is_zoomed_or_panned = (abs(zoom_y - 1.0) > 0.02 or abs(zoom_x - 1.0) > 0.02 or
                               abs(pan_y) > 0.1 or abs(pan_x) > 0.1)
        if is_zoomed_or_panned:
            canvas.create_text(
                w - pad_right - 8, pad_top - 10,
                text=f"🔍 Zoom: {int(round(zoom_y * 100))}% Y | {int(round(zoom_x * 100))}% X  (Double-Click to Reset)",
                fill=GOLD, font=("Segoe UI", 8, "bold"), anchor="e"
            )

    # ========================== MANUAL SINGLE SIMULATION ==========================
    def _set_direction(self, direction):
        self.direction_var.set(direction)
        if direction == "BUY":
            self.buy_btn.configure(bg=GREEN, fg="#ffffff")
            self.sell_btn.configure(bg=INPUT_BG, fg=TEXT_MUTED)
        else:
            self.sell_btn.configure(bg=RED, fg="#ffffff")
            self.buy_btn.configure(bg=INPUT_BG, fg=TEXT_MUTED)
        self._on_manual_price_change()
        if getattr(self, "manual_result", None) and getattr(self, "bars_data", None):
            self.execute_manual_simulation()

    def _on_manual_price_change(self, *args):
        try:
            entry = float(self.manual_entry_var.get())
            stop = float(self.manual_stop_var.get())
            target = float(self.manual_target_var.get())
            risk = abs(entry - stop)
            reward = abs(target - entry)
            r_ratio = reward / risk if risk > 0 else 0
            self.manual_rr_lbl.configure(text=f"Risk: ${risk:.2f} | Reward: ${reward:.2f} | {r_ratio:.2f} R")
        except Exception:
            self.manual_rr_lbl.configure(text="Invalid numbers")

    def execute_manual_simulation(self):
        try:
            entry = float(self.manual_entry_var.get())
            stop = float(self.manual_stop_var.get())
            target = float(self.manual_target_var.get())
            spread = float(self.spread_var.get())
            side = self.direction_var.get().lower()
            bars_count = self._get_selected_horizon_bars()
            replays = int(self.replays_var.get().replace(",", "").replace(".", "").strip())
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid numeric values.")
            return

        self.btn_run_manual.configure(state=tk.DISABLED, text="⚡ SIMULATING...")
        self.m_verdict_lbl.configure(text="Computing Monte Carlo replays...", fg=GOLD)

        def worker():
            try:
                params = dict(
                    entry_price=entry,
                    stop_loss=stop,
                    take_profit=target,
                    side=side,
                    horizon_bars=bars_count,
                    replays=replays,
                    spread=spread,
                    bars_data=self.bars_data,
                    projection_mode=self.current_projection_mode,
                    tie_break=self.current_tie_break,
                    seasonality=self.current_seasonality
                )
                mode = {"Legacy V1 (Default)": "legacy", "Enhanced OHLC V2": "v2", "Compare V1 vs V2": "compare"}.get(self.engine_mode_var.get(), "legacy")
                if mode == "v2":
                    res = engine_v2.run_simulation(**{k: v for k, v in params.items() if k not in ("projection_mode", "tie_break", "seasonality")})
                else:
                    res = timemachine.run_simulation(**params)
                    if mode == "compare":
                        v2 = engine_v2.run_simulation(**{k: v for k, v in params.items() if k not in ("projection_mode", "tie_break", "seasonality")})
                        res["comparison"] = {"engine": "Enhanced V2", "target_first_pct": v2["odds"]["target_first_pct"], "avg_r": v2["odds"]["avg_r"], "ambiguous_pct": v2["odds"].get("ambiguous_pct", 0.0), "optimistic_target_first_pct": v2["odds"].get("optimistic_target_first_pct", 0.0)}
                self.root.after(0, lambda: self._apply_manual_results(res))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Simulation Error", str(e)))
            finally:
                self.root.after(0, lambda: self.btn_run_manual.configure(state=tk.NORMAL, text="🚀 RUN SIMULATION"))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_manual_results(self, res):
        self.manual_result = res
        o = res["odds"]
        self.m_card_win.configure(text=f"{o['target_first_pct']:.1f} %")
        self.m_card_loss.configure(text=f"{o['stop_first_pct']:.1f} %")
        self.m_card_open.configure(text=f"{o['neither_pct']:.1f} %")
        
        avg_r = o['avg_r']
        r_sign = "+" if avg_r > 0 else ""
        self.m_card_r.configure(text=f"{r_sign}{avg_r:.2f} R", fg=GREEN if avg_r > 0 else (RED if avg_r < 0 else GOLD))

        v = res["verdict"]
        comparison = res.get("comparison")
        if comparison:
            v += f" | V2: TP {comparison['target_first_pct']:.1f}% / Avg {comparison['avg_r']:+.2f}R / Ambiguous {comparison['ambiguous_pct']:.1f}%"
        col = GREEN if "Positive simulated expectancy" in v or ("Target" in v and "Stop Loss" not in v) else (RED if "Stop Loss" in v else GOLD)
        self.m_verdict_lbl.configure(text=f"⚖️ {v}", fg=col)
        self._draw_manual_chart()

    def _draw_manual_chart(self):
        c = self.manual_canvas
        c.delete("all")
        if not getattr(self, "manual_result", None):
            w = c.winfo_width()
            h = c.winfo_height()
            c.create_text(w / 2, h / 2, text="Run simulation to visualize probability paths", fill=TEXT_MUTED, font=("Segoe UI", 11))
            return
        self._render_cone(c, self.manual_result, is_buy=(self.direction_var.get() == "BUY"))

    # ========================== SETTINGS MODAL & SIGNAL ACTIONS ==========================
    def _open_settings_modal(self):
        """Open floating Chrome-style Settings modal dialog for global and engine configurations."""
        modal = tk.Toplevel(self.root)
        modal.title("⚙️ Global Settings & Engine Configuration")
        modal.geometry("540x520")
        modal.configure(bg=PANEL_BG)
        modal.transient(self.root)
        modal.grab_set()

        # Modal Header
        m_head = tk.Frame(modal, bg="#0d1117", padx=16, pady=12, highlightbackground=BORDER_COL, highlightthickness=1)
        m_head.pack(fill=tk.X)
        tk.Label(m_head, text="⚙️ PENGATURAN GLOBAL & ENGINE", font=("Segoe UI", 11, "bold"), fg=GOLD, bg="#0d1117").pack(side=tk.LEFT)
        close_lbl = tk.Label(m_head, text="✕", font=("Segoe UI", 11, "bold"), fg=TEXT_MUTED, bg="#0d1117", cursor="hand2")
        close_lbl.pack(side=tk.RIGHT)
        close_lbl.bind("<Button-1>", lambda e: modal.destroy())

        # Modal Notebook / Tabs
        style = ttk.Style()
        notebook = ttk.Notebook(modal)
        notebook.pack(fill=tk.BOTH, expand=True, padx=14, pady=12)

        # Tab 1: Data Source & Time Horizon
        tab_data = tk.Frame(notebook, bg=PANEL_BG, padx=14, pady=12)
        notebook.add(tab_data, text=" 🔌 Data Source ")

        tk.Label(tab_data, text="SUMBER KONEKSI DATA HARGA", font=("Segoe UI", 8, "bold"), fg=GOLD, bg=PANEL_BG).pack(anchor="w", pady=(0, 4))
        ds_box = tk.Frame(tab_data, bg=CARD_BG, padx=8, pady=6, highlightbackground=BORDER_COL, highlightthickness=1)
        ds_box.pack(fill=tk.X, pady=(0, 12))

        btn_mt5 = tk.Button(
            ds_box, text="🔗 MetaTrader 5 (Live)", font=("Segoe UI", 9, "bold"),
            bg=GOLD if self.current_source == "mt5" else INPUT_BG,
            fg="#0b0f17" if self.current_source == "mt5" else TEXT_MUTED,
            relief=tk.FLAT, cursor="hand2", padx=10, pady=4,
            command=lambda: [self._switch_data_source("mt5"), update_ds_btns()]
        )
        btn_mt5.pack(side=tk.LEFT, padx=(0, 4))

        btn_comex = tk.Button(
            ds_box, text="🌐 COMEX Gold (Historical)", font=("Segoe UI", 9, "bold"),
            bg=GOLD if self.current_source == "comex" else INPUT_BG,
            fg="#0b0f17" if self.current_source == "comex" else TEXT_MUTED,
            relief=tk.FLAT, cursor="hand2", padx=10, pady=4,
            command=lambda: [self._switch_data_source("comex"), update_ds_btns()]
        )
        btn_comex.pack(side=tk.LEFT)

        def update_ds_btns():
            if self.current_source == "mt5":
                btn_mt5.configure(bg=GOLD, fg="#0b0f17")
                btn_comex.configure(bg=INPUT_BG, fg=TEXT_MUTED)
            else:
                btn_comex.configure(bg=GOLD, fg="#0b0f17")
                btn_mt5.configure(bg=INPUT_BG, fg=TEXT_MUTED)

        tk.Label(tab_data, text="SCAN TIME HORIZON", font=("Segoe UI", 8, "bold"), fg=GOLD, bg=PANEL_BG).pack(anchor="w", pady=(0, 4))
        self.horizon_combo = ttk.Combobox(
            tab_data, textvariable=self.horizon_var,
            values=[h[0] for h in (HORIZON_PRESETS_M1 if self.current_timeframe == "M1" else HORIZON_PRESETS_M5)],
            state="readonly", font=("Segoe UI", 9)
        )
        self.horizon_combo.pack(fill=tk.X, pady=(0, 12))
        self.horizon_combo.bind("<<ComboboxSelected>>", lambda e: self._on_horizon_change())

        tk.Label(tab_data, text="SPREAD BID/ASK SIMULASI ($)", font=("Segoe UI", 8, "bold"), fg=GOLD, bg=PANEL_BG).pack(anchor="w", pady=(0, 4))
        tk.Entry(
            tab_data, textvariable=self.spread_var, font=("Segoe UI", 9),
            bg=INPUT_BG, fg=TEXT_PRIMARY, relief=tk.FLAT, highlightthickness=1, highlightbackground=BORDER_COL, highlightcolor=GOLD
        ).pack(fill=tk.X, ipady=3, pady=(0, 12))

        # Tab 2: Monte Carlo Engine Configuration
        tab_engine = tk.Frame(notebook, bg=PANEL_BG, padx=14, pady=12)
        notebook.add(tab_engine, text=" 🎲 Monte Carlo Engine ")

        tk.Label(tab_engine, text="ENGINE SELECTION", font=("Segoe UI", 8, "bold"), fg=GOLD, bg=PANEL_BG).pack(anchor="w", pady=(0, 2))
        self.engine_mode_combo = ttk.Combobox(
            tab_engine, textvariable=self.engine_mode_var,
            values=["Legacy V1 (Default)", "Enhanced OHLC V2", "Compare V1 vs V2"],
            state="readonly", font=("Segoe UI", 8)
        )
        self.engine_mode_combo.pack(fill=tk.X, pady=(0, 10))

        tk.Label(tab_engine, text="FAN CHART PROJECTION MODE", font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=PANEL_BG).pack(anchor="w", pady=(0, 2))
        self.proj_combo = ttk.Combobox(
            tab_engine, textvariable=self.proj_mode_var,
            values=list(PROJECTION_MODES.keys()), state="readonly", font=("Segoe UI", 8)
        )
        self.proj_combo.pack(fill=tk.X, pady=(0, 10))
        self.proj_combo.bind("<<ComboboxSelected>>", lambda e: self._on_methodology_change())

        tk.Label(tab_engine, text="COLLISION TIE-BREAK RESOLUTION", font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=PANEL_BG).pack(anchor="w", pady=(0, 2))
        self.tb_combo = ttk.Combobox(
            tab_engine, textvariable=self.tie_break_var,
            values=list(TIE_BREAK_MODES.keys()), state="readonly", font=("Segoe UI", 8)
        )
        self.tb_combo.pack(fill=tk.X, pady=(0, 10))
        self.tb_combo.bind("<<ComboboxSelected>>", lambda e: self._on_methodology_change())

        tk.Label(tab_engine, text="SEASONALITY FILTER", font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=PANEL_BG).pack(anchor="w", pady=(0, 2))
        self.seasonality_combo = ttk.Combobox(
            tab_engine, textvariable=self.seasonality_var,
            values=list(SEASONALITY_MODES.keys()), state="readonly", font=("Segoe UI", 8)
        )
        self.seasonality_combo.pack(fill=tk.X, pady=(0, 10))
        self.seasonality_combo.bind("<<ComboboxSelected>>", lambda e: self._on_methodology_change())

        # Tab 3: Dual Auto TP/SL Configuration
        tab_tpsl = tk.Frame(notebook, bg=PANEL_BG, padx=14, pady=12)
        notebook.add(tab_tpsl, text=" 🎯 TP / SL Search ")

        chk_tpsl = tk.Checkbutton(
            tab_tpsl, text="Aktifkan Proyeksi TP / SL (Default: Dinonaktifkan)",
            variable=self.enable_tpsl_var, font=("Segoe UI", 9, "bold"),
            fg=GOLD, bg=PANEL_BG, selectcolor=CARD_BG, activebackground=PANEL_BG, activeforeground=GOLD,
            command=lambda: [self._draw_dual_charts(), self.execute_auto_scan() if self.active_mode == "auto" else None]
        )
        chk_tpsl.pack(anchor="w", pady=(0, 6))

        chk_limits = tk.Checkbutton(
            tab_tpsl, text="Gunakan Pending Limit Offset (Uncheck: Sinyal Market Close)",
            variable=self.enable_limits_var, font=("Segoe UI", 8),
            fg=TEXT_MUTED, bg=PANEL_BG, selectcolor=CARD_BG, activebackground=PANEL_BG, activeforeground=TEXT_PRIMARY,
            command=lambda: [self._draw_dual_charts(), self.execute_auto_scan() if self.active_mode == "auto" else None]
        )
        chk_limits.pack(anchor="w", pady=(0, 10))

        tk.Label(tab_tpsl, text="DUAL AUTO TP / SL METHOD", font=("Segoe UI", 8, "bold"), fg=GOLD, bg=PANEL_BG).pack(anchor="w", pady=(0, 4))
        self.tpsl_mode_combo = ttk.Combobox(
            tab_tpsl, textvariable=self.tpsl_mode_var,
            values=["Disabled (Murni Sinyal)", "Auto Optimize", "Fixed TP/SL", "TP/SL Range", "Risk Reward"],
            state="readonly", font=("Segoe UI", 8)
        )
        self.tpsl_mode_combo.pack(fill=tk.X, pady=(0, 10))
        self.tpsl_mode_combo.bind("<<ComboboxSelected>>", lambda e: self._on_tpsl_mode_change())

        self.tpsl_fields_frame = tk.Frame(tab_tpsl, bg=CARD_BG, padx=8, pady=8, highlightbackground=BORDER_COL, highlightthickness=1)
        self.tpsl_fields_frame.pack(fill=tk.X, pady=(0, 8))
        self._render_tpsl_fields()

        # Tab 4: Display & Visual Settings
        tab_disp = tk.Frame(notebook, bg=PANEL_BG, padx=14, pady=12)
        notebook.add(tab_disp, text=" 🎨 Display ")

        tk.Label(tab_disp, text="PRICE GRID LINES", font=("Segoe UI", 8, "bold"), fg=GOLD, bg=PANEL_BG).pack(anchor="w", pady=(0, 4))
        self.grid_lines_combo = ttk.Combobox(
            tab_disp, textvariable=self.grid_lines_var,
            values=["Dynamic Adaptive (Default)", "25 Lines", "50 Lines"], state="readonly", font=("Segoe UI", 8)
        )
        self.grid_lines_combo.pack(fill=tk.X, pady=(0, 12))
        self.grid_lines_combo.bind("<<ComboboxSelected>>", lambda e: self._on_display_setting_change())

        tk.Label(tab_disp, text="AUTO REFRESH INTERVAL", font=("Segoe UI", 8, "bold"), fg=GOLD, bg=PANEL_BG).pack(anchor="w", pady=(0, 4))
        ar_combo_modal = ttk.Combobox(
            tab_disp, textvariable=self.auto_refresh_var,
            values=["Off", "5s", "10s", "15s", "30s", "60s"], state="readonly", font=("Segoe UI", 8)
        )
        ar_combo_modal.pack(fill=tk.X, pady=(0, 12))
        ar_combo_modal.bind("<<ComboboxSelected>>", lambda e: self._on_auto_refresh_change())

        # Bottom modal action footer
        m_foot = tk.Frame(modal, bg=PANEL_BG, padx=14, pady=10)
        m_foot.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Button(
            m_foot, text="Tutup & Simpan", font=("Segoe UI", 9, "bold"),
            bg=GOLD, fg="#0b0f17", relief=tk.FLAT, cursor="hand2", padx=12, pady=4,
            command=lambda: [self._save_settings(), modal.destroy()]
        ).pack(side=tk.RIGHT)

    # ========================== THREE-TIER QUANT RANKING MODAL ==========================
    def _open_quant_ranking_tiers_modal(self):
        """Displays the 3 Tiers of Quant Output: Candidate Ranking, Equity Growth Ranking, and Best Recommendation."""
        if not self.dual_results or "candidate_rankings" not in self.dual_results:
            messagebox.showinfo("Quant Ranking Tiers", "Silakan klik 'SCAN DUAL SETUPS' terlebih dahulu untuk menghasilkan evaluasi ranking kuantitatif.")
            return

        modal = tk.Toplevel(self.root)
        modal.title("📊 Quant Ranking Tiers: Candidate Ranking, Equity Growth & Best Recommendation")
        modal.geometry("1120x680")
        modal.configure(bg=DARK_BG)
        modal.transient(self.root)

        header = tk.Frame(modal, bg=PANEL_BG, padx=14, pady=10)
        header.pack(fill=tk.X)
        tk.Label(
            header, text="📊 TIGA TINGKAT OUTPUT QUANT (MONTE CARLO 3.01)",
            font=("Segoe UI", 11, "bold"), fg=GOLD, bg=PANEL_BG
        ).pack(side=tk.LEFT)

        opt_prof = self.dual_results.get("tpsl_config", {}).get("optimization_profile", self.opt_profile_var.get() if hasattr(self, "opt_profile_var") else "wr_oriented")
        best_dir = self.dual_results.get("best_direction", "N/A")
        tk.Label(
            header, text=f"Profile: {opt_prof.upper()} | Best Direction: {best_dir}",
            font=("Segoe UI", 9, "bold"), fg=GREEN if best_dir == "BUY" else (RED if best_dir == "SELL" else TEXT_MUTED), bg=PANEL_BG
        ).pack(side=tk.RIGHT)

        notebook = ttk.Notebook(modal)
        notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

        cols = ("Rank", "Side", "Entry", "SL", "TP", "RR", "Tag", "Touch%", "Resolved WR%", "Geom Growth%/tr", "Net Exp (R)", "Max DD%", "Ruin%", "Viable")

        # Tab 1: Candidate Ranking (Profile-Sorted)
        tab_cand = tk.Frame(notebook, bg=DARK_BG, padx=8, pady=8)
        notebook.add(tab_cand, text=" 1. Candidate Ranking (Profile-Sorted) ")

        tree1 = ttk.Treeview(tab_cand, columns=cols, show="headings", height=20)
        for c in cols:
            tree1.heading(c, text=c)
            w = 50 if c in ("Rank", "Side", "RR", "Viable") else (80 if "Tag" in c or "Geom" in c else 65)
            tree1.column(c, width=w, anchor=tk.CENTER)
        sc1 = ttk.Scrollbar(tab_cand, orient=tk.VERTICAL, command=tree1.yview)
        tree1.configure(yscroll=sc1.set)
        tree1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc1.pack(side=tk.RIGHT, fill=tk.Y)

        for item in self.dual_results.get("candidate_rankings", []):
            tree1.insert("", tk.END, values=(
                item["rank"], item["side"], f"{item['entry_price']:.2f}",
                f"{item['stop_loss']:.2f}", f"{item['take_profit']:.2f}",
                f"1:{item['target_rr']:g}", item["setup_tag"] or "N/A",
                f"{item['touch_probability_pct']:.1f}%", f"{item['resolved_win_rate_pct']:.1f}%",
                f"{item['geometric_growth_pct']:+.2f}%", f"{item['net_expectancy_r']:+.3f}R",
                f"{item['max_drawdown_pct']:.1f}%", f"{item['probability_of_ruin_pct']:.1f}%",
                "YES" if item["is_viable"] else "NO"
            ))

        # Tab 2: Equity Growth Ranking (Strictly Sorted by Compound Growth)
        tab_growth = tk.Frame(notebook, bg=DARK_BG, padx=8, pady=8)
        notebook.add(tab_growth, text=" 2. Equity Growth Ranking (Pure Compound Growth) ")

        tree2 = ttk.Treeview(tab_growth, columns=cols, show="headings", height=20)
        for c in cols:
            tree2.heading(c, text=c)
            w = 50 if c in ("Rank", "Side", "RR", "Viable") else (80 if "Tag" in c or "Geom" in c else 65)
            tree2.column(c, width=w, anchor=tk.CENTER)
        sc2 = ttk.Scrollbar(tab_growth, orient=tk.VERTICAL, command=tree2.yview)
        tree2.configure(yscroll=sc2.set)
        tree2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc2.pack(side=tk.RIGHT, fill=tk.Y)

        for item in self.dual_results.get("equity_growth_rankings", []):
            tree2.insert("", tk.END, values=(
                item.get("growth_rank", 1), item["side"], f"{item['entry_price']:.2f}",
                f"{item['stop_loss']:.2f}", f"{item['take_profit']:.2f}",
                f"1:{item['target_rr']:g}", item["setup_tag"] or "N/A",
                f"{item['touch_probability_pct']:.1f}%", f"{item['resolved_win_rate_pct']:.1f}%",
                f"{item['geometric_growth_pct']:+.2f}%", f"{item['net_expectancy_r']:+.3f}R",
                f"{item['max_drawdown_pct']:.1f}%", f"{item['probability_of_ruin_pct']:.1f}%",
                "YES" if item["is_viable"] else "NO"
            ))

        # Tab 3: Best Recommendation Details
        tab_best = tk.Frame(notebook, bg=DARK_BG, padx=14, pady=14)
        notebook.add(tab_best, text=" 3. Best Recommendation Details ")

        best_rec = self.dual_results.get("best_recommendation", {})
        dir_val = best_rec.get("direction", "NO TRADE")
        summary_txt = self.dual_results.get("summary", "")

        tk.Label(tab_best, text=f"ARAH REKOMENDASI UTAMA: {dir_val}", font=("Segoe UI", 13, "bold"),
                 fg=GREEN if dir_val == "BUY" else (RED if dir_val == "SELL" else GOLD), bg=DARK_BG).pack(anchor="w", pady=(0, 6))

        tk.Label(tab_best, text=summary_txt, font=("Segoe UI", 9), fg=TEXT_PRIMARY, bg=DARK_BG, wraplength=980, justify=tk.LEFT).pack(anchor="w", pady=(0, 14))

        rec_target = self.dual_results.get(dir_val.lower(), self.dual_results.get("buy", {}))
        if rec_target and "capital_quality" in rec_target:
            eq = rec_target.get("entry_quality", {})
            tq = rec_target.get("trade_quality", {})
            cq = rec_target.get("capital_quality", {})
            wf = rec_target.get("walk_forward_validation", {})

            cards_box = tk.Frame(tab_best, bg=DARK_BG)
            cards_box.pack(fill=tk.BOTH, expand=True)

            def make_card(parent, title, lines_dict):
                card = tk.Frame(parent, bg=CARD_BG, padx=12, pady=10, highlightbackground=BORDER_COL, highlightthickness=1)
                card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
                tk.Label(card, text=title, font=("Segoe UI", 9, "bold"), fg=GOLD, bg=CARD_BG).pack(anchor="w", pady=(0, 8))
                for k, v in lines_dict.items():
                    row = tk.Frame(card, bg=CARD_BG)
                    row.pack(fill=tk.X, pady=2)
                    tk.Label(row, text=k, font=("Segoe UI", 8), fg=TEXT_MUTED, bg=CARD_BG).pack(side=tk.LEFT)
                    tk.Label(row, text=str(v), font=("Segoe UI", 8, "bold"), fg=TEXT_PRIMARY, bg=CARD_BG).pack(side=tk.RIGHT)

            make_card(cards_box, "🎯 ENTRY QUALITY", {
                "Order Type": eq.get("order_type", "LIMIT"),
                "Entry Price": f"{eq.get('entry_price', 0.0):.2f}",
                "Touch Prob": f"{eq.get('historical_touch_probability_pct', 0.0):.1f}%",
                "Touch Samples": eq.get("historical_touch_samples", 0),
                "Median Bars": eq.get("median_bars_to_touch", 0),
                "Distance ATR": f"{eq.get('distance_atr', 0.0)} ATR"
            })

            make_card(cards_box, "🎲 TRADE QUALITY", {
                "Target RR": f"1:{tq.get('target_rr', 2.0):g}",
                "Resolved WR": f"{tq.get('resolved_win_rate_pct', 0.0):.1f}%",
                "Total WR": f"{tq.get('total_win_rate_pct', 0.0):.1f}%",
                "TP-first Prob": f"{tq.get('target_first_pct', 0.0):.1f}%",
                "SL-first Prob": f"{tq.get('stop_first_pct', 0.0):.1f}%",
                "Timeout Prob": f"{tq.get('timeout_pct', 0.0):.1f}%",
                "Net Exp (R)": f"{tq.get('net_expectancy_r', 0.0):+.3f}R"
            })

            make_card(cards_box, "💰 CAPITAL QUALITY", {
                "Geom Growth": f"{cq.get('geometric_growth_pct', 0.0):+.2f}%/trade",
                "Final Equity Med": f"${cq.get('final_equity_median', 0.0):,.2f}",
                "Median Max DD": f"{cq.get('max_drawdown_pct_median', 0.0):.1f}%",
                "Worst Max DD": f"{cq.get('max_drawdown_pct_worst', 0.0):.1f}%",
                "Ruin Prob": f"{cq.get('probability_of_ruin_pct', 0.0):.1f}%",
                "Max Consec Loss": cq.get("max_consecutive_losses", 0),
                "Recovery Trades": f"{cq.get('avg_recovery_trades', 0.0):.1f} tr"
            })

            make_card(cards_box, "🛡 WALK-FORWARD OOS", {
                "In-Sample Bars": wf.get("in_sample_bars", 0),
                "Out-of-Sample Bars": wf.get("out_of_sample_bars", 0),
                "In-Sample Touch": f"{wf.get('in_sample_touch_pct', 0.0):.1f}%",
                "OOS Touch": f"{wf.get('out_of_sample_touch_pct', 0.0):.1f}%",
                "OOS Robustness": str(wf.get("out_of_sample_status", "N/A")).upper()
            })

    def _open_combination_matrix_modal(self):
        """Displays FASE 1: Pure Statistical Alpha & Forward Edge Profiler (MFE, MAE, Edge Ratio, Directional Accuracy)."""
        modal = tk.Toplevel(self.root)
        modal.title("FASE 1: Combination Engine - Pure Forward Edge & Alpha Profiler")
        modal.geometry("1060x640")
        modal.configure(bg=DARK_BG)
        modal.transient(self.root)

        header = tk.Frame(modal, bg=PANEL_BG, padx=14, pady=10)
        header.pack(fill=tk.X)
        tk.Label(
            header, text="🔬 FASE 1: PURE ENTRY ALPHA & FORWARD EDGE PROFILER (NO TP/SL BIAS)",
            font=("Segoe UI", 11, "bold"), fg=GOLD, bg=PANEL_BG
        ).pack(side=tk.LEFT)

        strat_val = self.strategy_var.get()
        tk.Label(
            header, text=f"Strategy: {strat_val} | Evaluation: Strictly Post-Close Forward Movement",
            font=("Segoe UI", 9), fg=TEXT_MUTED, bg=PANEL_BG
        ).pack(side=tk.RIGHT)

        body = tk.Frame(modal, bg=DARK_BG, padx=12, pady=10)
        body.pack(fill=tk.BOTH, expand=True)

        cols = (
            "ID", "Param 1", "Param 2",
            "BUY N", "BUY Fwd(ATR)", "BUY MFE", "BUY MAE", "BUY EdgeRatio", "BUY Acc%",
            "SELL N", "SELL Fwd(ATR)", "SELL MFE", "SELL MAE", "SELL EdgeRatio", "SELL Acc%", "Stability"
        )
        tree = ttk.Treeview(body, columns=cols, show="headings", height=18)
        for c in cols:
            tree.heading(c, text=c)
            width = 55 if "ID" in c or "Param" in c or "N" in c else 68
            tree.column(c, width=width, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(body, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscroll=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        status_lbl = tk.Label(modal, text="⏳ Menghitung forward edge murni (MFE, MAE, Forward Return)...", font=("Segoe UI", 9), fg=CYAN, bg=DARK_BG)
        status_lbl.pack(side=tk.BOTTOM, pady=6)

        def worker():
            strategy_code = {
                "ATR Pullback & Swing (Default)": "atr_swing",
                "Breakout + POC Retest": "poc",
                "Liquidity Sweep + FVG": "fvg",
                "Session ORB (Asia/London/NY)": "orb",
                "Bollinger Extremes (Z-Score)": "zscore",
                "Accumulation + Inverse FVG (IFVG)": "acc_ifvg",
                "Liquidity Sweep + Shift Structure (SMS)": "sweep_sms",
                "Liquidity Absorption + Volume Bubbles": "absorption",
                "Order Flow Footprint Proxy": "footprint"
            }.get(strat_val, "absorption")

            try:
                res = combination_engine.evaluate_combination_forward_edge(
                    strategy_code, self.bars_data, side="both", horizons=[3, 6, 12, 24, 48]
                )
                
                def update_ui():
                    for item in tree.get_children():
                        tree.delete(item)
                    for r in res.get("results", []):
                        cid = r["config_id"]
                        p = r["params"]
                        p1_val = list(p.values())[2] if len(p) > 2 else "-"
                        p2_val = list(p.values())[3] if len(p) > 3 else "-"
                        b = r.get("buy") or {}
                        s = r.get("sell") or {}

                        b_edge = b.get("edge_ratio", 0.0)
                        s_edge = s.get("edge_ratio", 0.0)
                        stab = (b.get("stability_score", 0.0) + s.get("stability_score", 0.0)) / 2.0

                        row = (
                            cid, str(p1_val), str(p2_val),
                            b.get("signals", 0), f"{b.get('avg_forward_return', 0.0):+.2f}", f"{b.get('avg_mfe', 0.0):.2f}", f"{b.get('avg_mae', 0.0):.2f}", f"{b_edge:.2f}x", f"{b.get('directional_accuracy_pct', 0.0):.1f}%",
                            s.get("signals", 0), f"{s.get('avg_forward_return', 0.0):+.2f}", f"{s.get('avg_mfe', 0.0):.2f}", f"{s.get('avg_mae', 0.0):.2f}", f"{s_edge:.2f}x", f"{s.get('directional_accuracy_pct', 0.0):.1f}%",
                            f"{stab:.2f}"
                        )
                        tree.insert("", tk.END, values=row)
                    status_lbl.configure(text=f"✅ Selesai mengevaluasi FASE 1: 20 konfigurasi {strategy_code.upper()} murni forward edge tanpa TP/SL.", fg=GREEN)

                self.root.after(0, update_ui)
            except Exception as e:
                self.root.after(0, lambda err=e: status_lbl.configure(text=f"❌ Error evaluasi Fase 1: {err}", fg=RED))

        threading.Thread(target=worker, daemon=True).start()

    def _copy_signals_to_clipboard(self):
        """Format the active dual auto scan setups and odds into clipboard."""
        if not self.dual_results or "buy" not in self.dual_results or "sell" not in self.dual_results:
            messagebox.showinfo("Clipboard", "Belum ada hasil kalkulasi untuk disalin. Jalankan SCAN terlebih dahulu.")
            return

        b = self.dual_results["buy"]
        s = self.dual_results["sell"]
        bp = b["plan"]
        sp = s["plan"]
        bo = b["odds"]
        so = s["odds"]
        cur = self.current_market_price

        lines = [
            "========================================",
            "⚡ XAUUSD TIME MACHINE PRO SIGNAL REPORT",
            f"Harga Saat Ini: ${cur:.2f} [{self.current_timeframe}]",
            f"Strategi: {self.strategy_var.get()}",
            "========================================",
            "🟢 BUY LIMIT SETUP:",
            f"  • Entry : ${bp['entry']:.2f}",
            f"  • SL    : ${bp['stop']:.2f}",
            f"  • TP    : ${bp['target']:.2f} (+{bp.get('target_r', 0.0):.2f} R)",
            f"  • Touch Prob: {bp.get('entry_touch_probability_pct', 0.0):.1f}%",
            f"  • Win Odds  : {bo.get('target_first_pct', 0.0):.1f}%",
            f"  • Expectancy: {bp.get('fill_adjusted_simulated_avg_r', 0.0):+.2f} R",
            "----------------------------------------",
            "🔴 SELL LIMIT SETUP:",
            f"  • Entry : ${sp['entry']:.2f}",
            f"  • SL    : ${sp['stop']:.2f}",
            f"  • TP    : ${sp['target']:.2f} (+{sp.get('target_r', 0.0):.2f} R)",
            f"  • Touch Prob: {sp.get('entry_touch_probability_pct', 0.0):.1f}%",
            f"  • Win Odds  : {so.get('target_first_pct', 0.0):.1f}%",
            f"  • Expectancy: {sp.get('fill_adjusted_simulated_avg_r', 0.0):+.2f} R",
            "========================================"
        ]
        text_to_copy = "\n".join(lines)

        copied = False
        try:
            p = subprocess.Popen(["clip"], stdin=subprocess.PIPE, shell=True)
            p.communicate(text_to_copy.encode("utf-8"))
            copied = True
        except Exception:
            pass

        if not copied:
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(text_to_copy)
                self.root.update()
                copied = True
            except Exception:
                pass

        messagebox.showinfo("Clipboard", "Sinyal BUY dan SELL berhasil disalin ke clipboard!")

    # ========================== MT5 POSITION IMPORT MODAL ==========================
    def _open_positions_selector(self):
        positions = mt5_connector.get_open_gold_positions()
        if not positions:
            messagebox.showinfo("Info", "Tidak ada posisi XAUUSD yang sedang terbuka di MT5 saat ini.")
            return

        win = tk.Toplevel(self.root)
        win.title("Pilih Posisi Aktif MT5")
        win.geometry("540x300")
        win.configure(bg=PANEL_BG)
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text="POSISI TRADING AKTIF DI MT5:", font=("Segoe UI", 10, "bold"), fg=GOLD, bg=PANEL_BG).pack(anchor="w", padx=14, pady=(12, 6))

        for pos in positions:
            pf = tk.Frame(win, bg=CARD_BG, padx=8, pady=6, highlightbackground=BORDER_COL, highlightthickness=1)
            pf.pack(fill=tk.X, padx=14, pady=3)

            p_text = f"#{pos['ticket']} | {pos['type']} {pos['volume']} Lot @ ${pos['entry']:.2f}\nSL: ${pos['sl']:.2f} | TP: ${pos['tp']:.2f} | Floating: ${pos['profit']:+.2f}"
            tk.Label(pf, text=p_text, font=("Segoe UI", 8), fg=TEXT_PRIMARY, bg=CARD_BG, justify=tk.LEFT).pack(side=tk.LEFT)

            def pick(p=pos):
                self._set_app_mode("manual")
                self._set_direction(p["type"])
                self.manual_entry_var.set(f"{p['entry']:.2f}")
                self.manual_stop_var.set(f"{p['sl']:.2f}")
                self.manual_target_var.set(f"{p['tp']:.2f}")
                self.execute_manual_simulation()
                win.destroy()

            tk.Button(pf, text="Uji Odds ⚡", font=("Segoe UI", 8, "bold"), bg=GOLD, fg="#000", relief=tk.FLAT, highlightthickness=1, highlightbackground=BORDER_COL, highlightcolor=GOLD, cursor="hand2", command=pick).pack(side=tk.RIGHT)

    # ========================== SETTINGS PERSISTENCE ==========================
    def _save_settings(self):
        """Save user preferences and settings to JSON file on exit."""
        settings = {
            "source": self.current_source,
            "timeframe": self.current_timeframe,
            "mode": self.active_mode,
            "horizon": self.horizon_var.get(),
            "replays": self.replays_var.get(),
            "spread": self.spread_var.get(),
            "projection_mode": self.proj_mode_var.get(),
            "tie_break": self.tie_break_var.get(),
            "seasonality": self.seasonality_var.get(),
            "engine_mode": self.engine_mode_var.get(),
            "grid_lines": self.grid_lines_var.get(),
            "strategy": self.strategy_var.get(),
            "candidate_grid": self.candidate_grid_var.get() if hasattr(self, "candidate_grid_var") else "0 (Versi Asli / Baseline)",
            "tpsl_mode": self.tpsl_mode_var.get(),
            "point_size": self.point_size_var.get(),
            "point_size_custom": self._point_size_custom,
            "fixed_tp_points": self.fixed_tp_points_var.get(),
            "fixed_sl_points": self.fixed_sl_points_var.get(),
            "tp_min_points": self.tp_min_points_var.get(),
            "tp_max_points": self.tp_max_points_var.get(),
            "tp_step_points": self.tp_step_points_var.get(),
            "sl_min_points": self.sl_min_points_var.get(),
            "sl_max_points": self.sl_max_points_var.get(),
            "sl_step_points": self.sl_step_points_var.get(),
            "rr_ratio": self.rr_ratio_var.get(),
            "rr_sl_points": self.rr_sl_points_var.get(),
            "manual_direction": self.direction_var.get(),
            "manual_entry": self.manual_entry_var.get(),
            "manual_stop": self.manual_stop_var.get(),
            "manual_target": self.manual_target_var.get(),
            "auto_refresh": self.auto_refresh_var.get() if hasattr(self, "auto_refresh_var") else "15s",
        }
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2)
        except Exception:
            pass

    def _load_settings(self):
        """Load and restore saved user preferences from JSON file on launch."""
        if not os.path.exists(SETTINGS_FILE):
            return
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
            
            # Restore Data Source
            saved_src = settings.get("source", "mt5")
            if saved_src in ("mt5", "comex") and saved_src != self.current_source:
                self._switch_data_source(saved_src)

            # Restore Timeframe
            saved_tf = settings.get("timeframe", "M5")
            if saved_tf in ("M5", "M1") and saved_tf != self.current_timeframe:
                self._set_timeframe(saved_tf)

            # Restore Horizon
            saved_h = settings.get("horizon")
            if saved_h and saved_h in self.horizon_combo["values"]:
                self.horizon_var.set(saved_h)

            # Restore Replays & Spread
            saved_replays = settings.get("replays")
            if saved_replays:
                self.replays_var.set(saved_replays)
            saved_spread = settings.get("spread")
            if saved_spread:
                self.spread_var.set(saved_spread)

            # Restore engine selection; old settings remain Legacy V1 by default.
            saved_engine = settings.get("engine_mode", "Legacy V1 (Default)")
            if saved_engine in self.engine_mode_combo["values"]:
                self.engine_mode_var.set(saved_engine)

            saved_grid_lines = settings.get("grid_lines", "Dynamic Adaptive (Default)")
            if saved_grid_lines == "25 Lines (Default)":
                saved_grid_lines = "Dynamic Adaptive (Default)"
            if saved_grid_lines in self.grid_lines_combo["values"]:
                self.grid_lines_var.set(saved_grid_lines)

            # Restore Strategy selection
            saved_strat = settings.get("strategy", "ATR Pullback & Swing (Default)")
            if saved_strat in self.strategy_combo["values"]:
                self.strategy_var.set(saved_strat)
                self._on_strategy_change()

            # Restore Candidate Grid selection
            saved_grid = settings.get("candidate_grid")
            if saved_grid and hasattr(self, "candidate_grid_combo") and saved_grid in self.candidate_grid_combo["values"]:
                self.candidate_grid_var.set(saved_grid)

            # Restore TP/SL search mode and broker point conversion.
            saved_tpsl_mode = settings.get("tpsl_mode", "Auto Optimize")
            if saved_tpsl_mode in self.tpsl_mode_combo["values"]:
                self.tpsl_mode_var.set(saved_tpsl_mode)
            for key, variable in (
                ("point_size", self.point_size_var),
                ("fixed_tp_points", self.fixed_tp_points_var),
                ("fixed_sl_points", self.fixed_sl_points_var),
                ("tp_min_points", self.tp_min_points_var),
                ("tp_max_points", self.tp_max_points_var),
                ("tp_step_points", self.tp_step_points_var),
                ("sl_min_points", self.sl_min_points_var),
                ("sl_max_points", self.sl_max_points_var),
                ("sl_step_points", self.sl_step_points_var),
                ("rr_ratio", self.rr_ratio_var),
                ("rr_sl_points", self.rr_sl_points_var)
            ):
                if key in settings:
                    variable.set(str(settings[key]))
            self._point_size_custom = bool(settings.get("point_size_custom", False))
            self._render_tpsl_fields()

            # Restore Statistical Methodology
            saved_pm = settings.get("projection_mode")
            if saved_pm and saved_pm in PROJECTION_MODES:
                self.proj_mode_var.set(saved_pm)
                self.current_projection_mode = PROJECTION_MODES[saved_pm]

            saved_tb = settings.get("tie_break")
            if saved_tb and saved_tb in TIE_BREAK_MODES:
                self.tie_break_var.set(saved_tb)
                self.current_tie_break = TIE_BREAK_MODES[saved_tb]

            saved_season = settings.get("seasonality")
            if saved_season and saved_season in SEASONALITY_MODES:
                self.seasonality_var.set(saved_season)
                self.current_seasonality = SEASONALITY_MODES[saved_season]

            # Restore Manual Trade Setup Inputs
            saved_dir = settings.get("manual_direction", "BUY")
            if saved_dir in ("BUY", "SELL"):
                self._set_direction(saved_dir)
            if "manual_entry" in settings:
                self.manual_entry_var.set(settings["manual_entry"])
            if "manual_stop" in settings:
                self.manual_stop_var.set(settings["manual_stop"])
            if "manual_target" in settings:
                self.manual_target_var.set(settings["manual_target"])

            # Restore Active Mode
            saved_mode = settings.get("mode", "auto")
            if saved_mode in ("auto", "manual"):
                self._set_app_mode(saved_mode)

            # Restore Auto-Refresh Interval
            saved_ar = settings.get("auto_refresh")
            if saved_ar and hasattr(self, "auto_refresh_var") and saved_ar in ("Off", "5s", "10s", "15s", "30s", "60s"):
                self.auto_refresh_var.set(saved_ar)
                self._on_auto_refresh_change()

        except Exception:
            pass

def main():
    root = tk.Tk()
    app = TimeMachineProGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
