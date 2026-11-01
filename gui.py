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

        # Configure taskbar integration for frameless window
        self._setup_taskbar()

        # Build UI
        self._build_title_bar()
        self._build_header_toolbar()
        self._build_main_body()

        # Load saved settings if any
        self._load_settings()

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

    # ========================== CUSTOM TITLE BAR ==========================
    def _build_title_bar(self):
        self.title_bar = tk.Frame(self.root, bg="#0d1117", height=34, highlightbackground=BORDER_COL, highlightthickness=1)
        self.title_bar.pack(fill=tk.X, side=tk.TOP)
        self.title_bar.pack_propagate(False)

        # App Brand & Icon
        brand_frame = tk.Frame(self.title_bar, bg="#0d1117")
        brand_frame.pack(side=tk.LEFT, padx=10)

        tk.Label(brand_frame, text="⚡", font=("Segoe UI", 11), fg=GOLD, bg="#0d1117").pack(side=tk.LEFT, padx=(0, 4))
        title_lbl = tk.Label(
            brand_frame, text="XAUUSD TIME MACHINE PRO", font=("Segoe UI", 9, "bold"),
            fg=TEXT_PRIMARY, bg="#0d1117"
        )
        title_lbl.pack(side=tk.LEFT)

        sub_lbl = tk.Label(
            brand_frame, text="— Monte Carlo Quant Odds Engine", font=("Segoe UI", 8),
            fg=TEXT_MUTED, bg="#0d1117"
        )
        sub_lbl.pack(side=tk.LEFT, padx=6)

        # Window Action Buttons on Right
        btn_box = tk.Frame(self.title_bar, bg="#0d1117")
        btn_box.pack(side=tk.RIGHT)

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

        # Bind dragging to title bar and brand label
        for w in (self.title_bar, brand_frame, title_lbl, sub_lbl):
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
        self._save_settings()
        self.root.destroy()

    # ========================== HEADER TOOLBAR ==========================
    def _build_header_toolbar(self):
        toolbar = tk.Frame(self.root, bg=PANEL_BG, height=52, padx=16, pady=8)
        toolbar.pack(fill=tk.X, side=tk.TOP)

        # Left: App Mode Switcher (Auto Analyzer vs Manual Setup)
        mode_box = tk.Frame(toolbar, bg=CARD_BG, padx=3, pady=3, highlightbackground=BORDER_COL, highlightthickness=1)
        mode_box.pack(side=tk.LEFT)

        self.btn_mode_auto = tk.Button(
            mode_box, text="🤖 DUAL AUTO-ANALYZER", font=("Segoe UI", 9, "bold"),
            bg=GOLD, fg="#0b0f17", relief=tk.FLAT, cursor="hand2", padx=12, pady=4,
            command=lambda: self._set_app_mode("auto")
        )
        self.btn_mode_auto.pack(side=tk.LEFT, padx=(0, 2))

        self.btn_mode_manual = tk.Button(
            mode_box, text="🛠️ MANUAL SETUP", font=("Segoe UI", 9, "bold"),
            bg=INPUT_BG, fg=TEXT_MUTED, relief=tk.FLAT, cursor="hand2", padx=12, pady=4,
            command=lambda: self._set_app_mode("manual")
        )
        self.btn_mode_manual.pack(side=tk.LEFT, padx=(2, 0))

        # Center-Right: Data Source Switcher (MT5 vs COMEX)
        src_box = tk.Frame(toolbar, bg=CARD_BG, padx=3, pady=3, highlightbackground=BORDER_COL, highlightthickness=1)
        src_box.pack(side=tk.LEFT, padx=(20, 0))

        self.btn_src_mt5 = tk.Button(
            src_box, text="🔗 MetaTrader 5", font=("Segoe UI", 8, "bold"),
            bg=GOLD, fg="#0b0f17", relief=tk.FLAT, cursor="hand2", padx=8, pady=3,
            command=lambda: self._switch_data_source("mt5")
        )
        self.btn_src_mt5.pack(side=tk.LEFT, padx=(0, 2))

        self.btn_src_comex = tk.Button(
            src_box, text="🌐 COMEX Gold", font=("Segoe UI", 8, "bold"),
            bg=INPUT_BG, fg=TEXT_MUTED, relief=tk.FLAT, cursor="hand2", padx=8, pady=3,
            command=lambda: self._switch_data_source("comex")
        )
        self.btn_src_comex.pack(side=tk.LEFT, padx=(2, 0))

        # Right: Live Price & Sync Status
        market_pill = tk.Frame(toolbar, bg=CARD_BG, padx=10, pady=4, highlightbackground=BORDER_COL, highlightthickness=1)
        market_pill.pack(side=tk.RIGHT)

        self.price_badge = tk.Label(
            market_pill, text="Syncing Market...", font=("Segoe UI", 9, "bold"),
            fg=TEXT_PRIMARY, bg=CARD_BG
        )
        self.price_badge.pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(
            market_pill, text="🔄 Sync", font=("Segoe UI", 8, "bold"),
            bg=INPUT_BG, fg=GOLD, relief=tk.FLAT, cursor="hand2", padx=6, pady=2,
            command=self.refresh_data
        ).pack(side=tk.LEFT)

    # ========================== MAIN BODY ==========================
    def _build_main_body(self):
        self.body_frame = tk.Frame(self.root, bg=DARK_BG, padx=14, pady=12)
        self.body_frame.pack(fill=tk.BOTH, expand=True)

        # Left Control Sidebar (Width ~340px)
        self.left_panel = tk.Frame(self.body_frame, bg=PANEL_BG, width=340, padx=16, pady=12, highlightbackground=BORDER_COL, highlightthickness=1)
        self.left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        self.left_panel.pack_propagate(False)

        # Right Display Area (Holds either Dual Fan Charts or Single Fan Chart)
        self.right_panel = tk.Frame(self.body_frame, bg=DARK_BG)
        self.right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Build Sidebar Content
        self._build_sidebar_controls()

        # Build Right Views
        self._build_auto_view()
        self._build_manual_view()

        # Show initial mode
        self._update_view_visibility()

    def _build_sidebar_controls(self):
        # Section 1: Time Horizon Selector (Common to both modes)
        tk.Label(self.left_panel, text="SCAN TIME HORIZON", font=("Segoe UI", 9, "bold"), fg=GOLD, bg=PANEL_BG).pack(anchor="w", pady=(0, 4))
        self.horizon_var = tk.StringVar(value="4 Jam (48 bars M5)")
        horizon_options = [h[0] for h in HORIZON_PRESETS_M5]
        self.horizon_combo = ttk.Combobox(
            self.left_panel, textvariable=self.horizon_var, values=horizon_options, state="readonly", font=("Segoe UI", 9)
        )
        self.horizon_combo.pack(fill=tk.X, pady=(0, 8))
        self.horizon_combo.bind("<<ComboboxSelected>>", lambda e: self._on_horizon_change())

        # Section 1B: Candle Timeframe Base (M5 Default vs M1 Scalper)
        tk.Label(self.left_panel, text="CANDLE TIMEFRAME BASE", font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=PANEL_BG).pack(anchor="w", pady=(0, 2))
        tf_frame = tk.Frame(self.left_panel, bg=PANEL_BG)
        tf_frame.pack(fill=tk.X, pady=(0, 10))

        self.btn_tf_m5 = tk.Button(
            tf_frame, text="M5 (Default)", font=("Segoe UI", 8, "bold"),
            bg=GOLD, fg="#0b0f17", relief=tk.FLAT, cursor="hand2",
            command=lambda: self._set_timeframe("M5")
        )
        self.btn_tf_m5.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))

        self.btn_tf_m1 = tk.Button(
            tf_frame, text="M1 (Scalper)", font=("Segoe UI", 8, "bold"),
            bg=INPUT_BG, fg=TEXT_MUTED, relief=tk.FLAT, cursor="hand2",
            command=lambda: self._set_timeframe("M1")
        )
        self.btn_tf_m1.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        # Section 2: Replays & Spread
        sub_row = tk.Frame(self.left_panel, bg=PANEL_BG)
        sub_row.pack(fill=tk.X, pady=(0, 8))

        f_rep = tk.Frame(sub_row, bg=PANEL_BG)
        f_rep.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        tk.Label(f_rep, text="Replays", font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=PANEL_BG).pack(anchor="w")
        self.replays_var = tk.StringVar(value="5,000")
        ttk.Combobox(f_rep, textvariable=self.replays_var, values=["3,000", "5,000", "10,000"], state="readonly", font=("Segoe UI", 9)).pack(fill=tk.X)

        f_spr = tk.Frame(sub_row, bg=PANEL_BG)
        f_spr.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(4, 0))
        tk.Label(f_spr, text="Spread ($)", font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=PANEL_BG).pack(anchor="w")
        self.spread_var = tk.StringVar(value="0.24")
        self.spread_entry = tk.Entry(
            f_spr, textvariable=self.spread_var, font=("Segoe UI", 9),
            bg=INPUT_BG, fg=TEXT_PRIMARY, relief=tk.FLAT,
            highlightthickness=1, highlightbackground=PANEL_BG, highlightcolor=GOLD
        )
        self.spread_entry.pack(fill=tk.X, ipady=2)

        # Section 2B: Statistical Methodology Options (User Selectable)
        method_card = tk.Frame(self.left_panel, bg=CARD_BG, padx=10, pady=8, highlightbackground=BORDER_COL, highlightthickness=1)
        method_card.pack(fill=tk.X, pady=(0, 10))

        tk.Label(method_card, text="⚙️ ENGINE SELECTION", font=("Segoe UI", 8, "bold"), fg=GOLD, bg=CARD_BG).pack(anchor="w")
        self.engine_mode_var = tk.StringVar(value="Legacy V1 (Default)")
        self.engine_mode_combo = ttk.Combobox(
            method_card, textvariable=self.engine_mode_var,
            values=["Legacy V1 (Default)", "Enhanced OHLC V2", "Compare V1 vs V2"],
            state="readonly", font=("Segoe UI", 8)
        )
        self.engine_mode_combo.pack(fill=tk.X, pady=(4, 6))
        tk.Label(method_card, text="V2 uses block bootstrap + conservative same-bar collision handling. Compare mode keeps V1 as the displayed baseline.", font=("Segoe UI", 7), fg=TEXT_MUTED, bg=CARD_BG, wraplength=280, justify=tk.LEFT).pack(anchor="w", pady=(0, 5))

        tk.Label(method_card, text="⚙️ LEGACY V1 METHODOLOGY OPTIONS", font=("Segoe UI", 8, "bold"), fg=GOLD, bg=CARD_BG).pack(anchor="w")

        tk.Label(method_card, text="Fan Chart Projection", font=("Segoe UI", 7, "bold"), fg=TEXT_MUTED, bg=CARD_BG).pack(anchor="w", pady=(4, 1))
        self.proj_mode_var = tk.StringVar(value="Two-Stream Free Drift (Recommended)")
        self.proj_combo = ttk.Combobox(
            method_card, textvariable=self.proj_mode_var,
            values=list(PROJECTION_MODES.keys()), state="readonly", font=("Segoe UI", 8)
        )
        self.proj_combo.pack(fill=tk.X)
        self.proj_combo.bind("<<ComboboxSelected>>", lambda e: self._on_methodology_change())

        tk.Label(method_card, text="Collision Tie-Break", font=("Segoe UI", 7, "bold"), fg=TEXT_MUTED, bg=CARD_BG).pack(anchor="w", pady=(4, 1))
        self.tie_break_var = tk.StringVar(value="Smart Candle Anatomy (Recommended)")
        self.tb_combo = ttk.Combobox(
            method_card, textvariable=self.tie_break_var,
            values=list(TIE_BREAK_MODES.keys()), state="readonly", font=("Segoe UI", 8)
        )
        self.tb_combo.pack(fill=tk.X)
        self.tb_combo.bind("<<ComboboxSelected>>", lambda e: self._on_methodology_change())

        tk.Label(method_card, text="Seasonality Filter", font=("Segoe UI", 7, "bold"), fg=TEXT_MUTED, bg=CARD_BG).pack(anchor="w", pady=(4, 1))
        self.seasonality_var = tk.StringVar(value="Off (Default/Asli)")
        self.seasonality_combo = ttk.Combobox(
            method_card, textvariable=self.seasonality_var,
            values=list(SEASONALITY_MODES.keys()), state="readonly", font=("Segoe UI", 8), cursor="hand2"
        )
        self.seasonality_combo.pack(fill=tk.X)
        self.seasonality_combo.bind("<<ComboboxSelected>>", lambda e: self._on_methodology_change())

        # Section 2C: Dual Auto TP/SL Search Configuration
        tpsl_card = tk.Frame(self.left_panel, bg=CARD_BG, padx=10, pady=8, highlightbackground=BORDER_COL, highlightthickness=1)
        tpsl_card.pack(fill=tk.X, pady=(0, 10))
        tk.Label(tpsl_card, text="🎯 DUAL AUTO TP / SL", font=("Segoe UI", 8, "bold"), fg=GOLD, bg=CARD_BG).pack(anchor="w")
        self.tpsl_mode_var = tk.StringVar(value="Auto Optimize")
        self.tpsl_mode_combo = ttk.Combobox(
            tpsl_card, textvariable=self.tpsl_mode_var,
            values=["Auto Optimize", "Fixed TP/SL", "TP/SL Range"],
            state="readonly", font=("Segoe UI", 8)
        )
        self.tpsl_mode_combo.pack(fill=tk.X, pady=(4, 5))
        self.tpsl_mode_combo.bind("<<ComboboxSelected>>", lambda e: self._on_tpsl_mode_change())
        self.tpsl_fields_frame = tk.Frame(tpsl_card, bg=CARD_BG)
        self.tpsl_fields_frame.pack(fill=tk.X)
        self.point_size_var = tk.StringVar(value="0.01")
        self.fixed_tp_points_var = tk.StringVar(value="2000")
        self.fixed_sl_points_var = tk.StringVar(value="1000")
        self.tp_min_points_var = tk.StringVar(value="1000")
        self.tp_max_points_var = tk.StringVar(value="5000")
        self.tp_step_points_var = tk.StringVar(value="500")
        self.sl_min_points_var = tk.StringVar(value="500")
        self.sl_max_points_var = tk.StringVar(value="2000")
        self.sl_step_points_var = tk.StringVar(value="250")
        self._render_tpsl_fields()

        # Section 3A: AUTO MODE SPECIFIC CONTROLS
        self.auto_sidebar_frame = tk.Frame(self.left_panel, bg=PANEL_BG)
        
        info_card = tk.Frame(self.auto_sidebar_frame, bg=CARD_BG, padx=10, pady=8, highlightbackground=BORDER_COL, highlightthickness=1)
        info_card.pack(fill=tk.X, pady=(0, 12))

        tk.Label(
            info_card, text="💡 DUAL QUANT SCANNER", font=("Segoe UI", 9, "bold"),
            fg=CYAN, bg=CARD_BG
        ).pack(anchor="w")
        tk.Label(
            info_card, text="Memindai titik pantulan (Buy Limit di Support & Sell Limit di Resistance) lalu menyimulasikan 2 skenario sekaligus.",
            font=("Segoe UI", 8), fg=TEXT_MUTED, bg=CARD_BG, wraplength=280, justify=tk.LEFT
        ).pack(anchor="w", pady=(3, 0))

        self.btn_run_auto = tk.Button(
            self.auto_sidebar_frame, text="⚡ SCAN DUAL SETUPS", font=("Segoe UI", 11, "bold"),
            bg=GOLD, fg="#0b0f17", activebackground=GOLD_HOVER, activeforeground="#ffffff",
            relief=tk.FLAT, cursor="hand2", pady=10,
            command=self.execute_auto_scan
        )
        self.btn_run_auto.pack(fill=tk.X, pady=(4, 10))

        # MT5 Quick Import Button in Auto
        self.import_mt5_btn = tk.Button(
            self.auto_sidebar_frame, text="📥 Impor Posisi Aktif MT5", font=("Segoe UI", 9, "bold"),
            bg=INPUT_BG, fg=CYAN, relief=tk.FLAT, cursor="hand2", pady=5,
            command=self._open_positions_selector
        )
        self.import_mt5_btn.pack(fill=tk.X)

        # Section 3B: MANUAL MODE SPECIFIC CONTROLS
        self.manual_sidebar_frame = tk.Frame(self.left_panel, bg=PANEL_BG)

        # Direction Toggle
        tk.Label(self.manual_sidebar_frame, text="Order Direction", font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=PANEL_BG).pack(anchor="w")
        dir_frame = tk.Frame(self.manual_sidebar_frame, bg=PANEL_BG)
        dir_frame.pack(fill=tk.X, pady=(2, 6))

        self.direction_var = tk.StringVar(value="BUY")
        self.buy_btn = tk.Button(
            dir_frame, text="▲ BUY", font=("Segoe UI", 9, "bold"),
            bg=GREEN, fg="#ffffff", relief=tk.FLAT, cursor="hand2",
            command=lambda: self._set_direction("BUY")
        )
        self.buy_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))

        self.sell_btn = tk.Button(
            dir_frame, text="▼ SELL", font=("Segoe UI", 9, "bold"),
            bg=INPUT_BG, fg=TEXT_MUTED, relief=tk.FLAT, cursor="hand2",
            command=lambda: self._set_direction("SELL")
        )
        self.sell_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        # Entry Price
        tk.Label(self.manual_sidebar_frame, text="Entry Price ($)", font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=PANEL_BG).pack(anchor="w")
        self.manual_entry_var = tk.StringVar(value="3875.00")
        self.manual_entry_var.trace_add("write", self._on_manual_price_change)
        tk.Entry(
            self.manual_sidebar_frame, textvariable=self.manual_entry_var, font=("Segoe UI", 10),
            bg=INPUT_BG, fg=TEXT_PRIMARY, relief=tk.FLAT,
            highlightthickness=1, highlightbackground=PANEL_BG, highlightcolor=GOLD
        ).pack(fill=tk.X, pady=(1, 5), ipady=2)

        # Stop Loss
        tk.Label(self.manual_sidebar_frame, text="Stop Loss ($)", font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=PANEL_BG).pack(anchor="w")
        self.manual_stop_var = tk.StringVar(value="3850.00")
        self.manual_stop_var.trace_add("write", self._on_manual_price_change)
        tk.Entry(
            self.manual_sidebar_frame, textvariable=self.manual_stop_var, font=("Segoe UI", 10),
            bg=INPUT_BG, fg=RED, relief=tk.FLAT,
            highlightthickness=1, highlightbackground=PANEL_BG, highlightcolor=GOLD
        ).pack(fill=tk.X, pady=(1, 5), ipady=2)

        # Take Profit
        tk.Label(self.manual_sidebar_frame, text="Take Profit ($)", font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=PANEL_BG).pack(anchor="w")
        self.manual_target_var = tk.StringVar(value="3925.00")
        self.manual_target_var.trace_add("write", self._on_manual_price_change)
        tk.Entry(
            self.manual_sidebar_frame, textvariable=self.manual_target_var, font=("Segoe UI", 10),
            bg=INPUT_BG, fg=GREEN, relief=tk.FLAT,
            highlightthickness=1, highlightbackground=PANEL_BG, highlightcolor=GOLD
        ).pack(fill=tk.X, pady=(1, 5), ipady=2)

        # Manual R:R badge
        self.manual_rr_lbl = tk.Label(
            self.manual_sidebar_frame, text="Risk: $25.00 | Reward: $50.00 | 2.00 R",
            font=("Segoe UI", 8, "bold"), fg=GOLD, bg=CARD_BG, pady=4
        )
        self.manual_rr_lbl.pack(fill=tk.X, pady=(2, 10))

        self.btn_run_manual = tk.Button(
            self.manual_sidebar_frame, text="🚀 RUN SIMULATION", font=("Segoe UI", 11, "bold"),
            bg=GOLD, fg="#0b0f17", activebackground=GOLD_HOVER, activeforeground="#ffffff",
            relief=tk.FLAT, cursor="hand2", pady=10,
            command=self.execute_manual_simulation
        )
        self.btn_run_manual.pack(fill=tk.X, pady=(4, 0))

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

        # LEFT: BUY FAN CHART
        self.buy_chart_frame = tk.Frame(charts_split, bg=PANEL_BG, highlightbackground=GREEN, highlightthickness=1)
        self.buy_chart_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        buy_header = tk.Frame(self.buy_chart_frame, bg=PANEL_BG, padx=10, pady=6)
        buy_header.pack(fill=tk.X)
        tk.Label(buy_header, text="🟢 BUY LIMIT PROBABILITY CONE", font=("Segoe UI", 10, "bold"), fg=GREEN, bg=PANEL_BG).pack(side=tk.LEFT)
        self.buy_odds_lbl = tk.Label(buy_header, text="Target: --% | Expected: -- R", font=("Segoe UI", 9, "bold"), fg=TEXT_PRIMARY, bg=PANEL_BG)
        self.buy_odds_lbl.pack(side=tk.RIGHT)

        self.buy_canvas = tk.Canvas(self.buy_chart_frame, bg="#0f141d", highlightthickness=0)
        self.buy_canvas.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        self.buy_canvas.bind("<Configure>", lambda e: self._draw_dual_charts())

        # RIGHT: SELL FAN CHART
        self.sell_chart_frame = tk.Frame(charts_split, bg=PANEL_BG, highlightbackground=RED, highlightthickness=1)
        self.sell_chart_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 0))

        sell_header = tk.Frame(self.sell_chart_frame, bg=PANEL_BG, padx=10, pady=6)
        sell_header.pack(fill=tk.X)
        tk.Label(sell_header, text="🔴 SELL LIMIT PROBABILITY CONE", font=("Segoe UI", 10, "bold"), fg=RED, bg=PANEL_BG).pack(side=tk.LEFT)
        self.sell_odds_lbl = tk.Label(sell_header, text="Target: --% | Expected: -- R", font=("Segoe UI", 9, "bold"), fg=TEXT_PRIMARY, bg=PANEL_BG)
        self.sell_odds_lbl.pack(side=tk.RIGHT)

        self.sell_canvas = tk.Canvas(self.sell_chart_frame, bg="#0f141d", highlightthickness=0)
        self.sell_canvas.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        self.sell_canvas.bind("<Configure>", lambda e: self._draw_dual_charts())

    # ========================== MANUAL SINGLE FAN CHART VIEW ==========================
    def _build_manual_view(self):
        self.manual_view_frame = tk.Frame(self.right_panel, bg=DARK_BG)

        # 4 Stat Cards in Row
        m_score_row = tk.Frame(self.manual_view_frame, bg=DARK_BG)
        m_score_row.pack(fill=tk.X, pady=(0, 8))

        self.m_card_win = self._create_card(m_score_row, "TARGET FIRST", "-- %", GREEN)
        self.m_card_loss = self._create_card(m_score_row, "STOP FIRST", "-- %", RED)
        self.m_card_open = self._create_card(m_score_row, "NEITHER / OPEN", "-- %", BLUE)
        self.m_card_r = self._create_card(m_score_row, "EXPECTED RETURN", "-- R", GOLD)

        # Verdict
        self.m_verdict_card = tk.Frame(self.manual_view_frame, bg=PANEL_BG, padx=12, pady=8, highlightbackground=BORDER_COL, highlightthickness=1)
        self.m_verdict_card.pack(fill=tk.X, pady=(0, 8))
        self.m_verdict_lbl = tk.Label(self.m_verdict_card, text="Click 'RUN SIMULATION' to test custom setup.", font=("Segoe UI", 11, "bold"), fg=TEXT_PRIMARY, bg=PANEL_BG, anchor="w")
        self.m_verdict_lbl.pack(fill=tk.X)

        # Single Manual Canvas
        m_chart_box = tk.Frame(self.manual_view_frame, bg=PANEL_BG, highlightbackground=BORDER_COL, highlightthickness=1)
        m_chart_box.pack(fill=tk.BOTH, expand=True)

        self.manual_canvas = tk.Canvas(m_chart_box, bg="#0f141d", highlightthickness=0)
        self.manual_canvas.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.manual_canvas.bind("<Configure>", lambda e: self._draw_manual_chart())

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
        self._update_view_visibility()

    def _update_view_visibility(self):
        if self.active_mode == "auto":
            self.manual_sidebar_frame.pack_forget()
            self.auto_sidebar_frame.pack(fill=tk.BOTH, expand=True)
            self.manual_view_frame.pack_forget()
            self.auto_view_frame.pack(fill=tk.BOTH, expand=True)
        else:
            self.auto_sidebar_frame.pack_forget()
            self.manual_sidebar_frame.pack(fill=tk.BOTH, expand=True)
            self.auto_view_frame.pack_forget()
            self.manual_view_frame.pack(fill=tk.BOTH, expand=True)

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
        else:
            tk.Label(self.tpsl_fields_frame, text="Take Profit range (points)", font=("Segoe UI", 7, "bold"), fg=GOLD, bg=CARD_BG).grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))
            add_field(self.tpsl_fields_frame, "TP Min", self.tp_min_points_var, 3, 0)
            add_field(self.tpsl_fields_frame, "TP Max", self.tp_max_points_var, 3, 1)
            add_field(self.tpsl_fields_frame, "TP Step", self.tp_step_points_var, 4, 0)
            tk.Label(self.tpsl_fields_frame, text="Stop Loss range (points)", font=("Segoe UI", 7, "bold"), fg=GOLD, bg=CARD_BG).grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 0))
            add_field(self.tpsl_fields_frame, "SL Min", self.sl_min_points_var, 6, 0)
            add_field(self.tpsl_fields_frame, "SL Max", self.sl_max_points_var, 6, 1)
            add_field(self.tpsl_fields_frame, "SL Step", self.sl_step_points_var, 7, 0)

    def _on_tpsl_mode_change(self):
        self._render_tpsl_fields()

    def _get_tpsl_scan_params(self):
        mode = {
            "Auto Optimize": "auto",
            "Fixed TP/SL": "fixed",
            "TP/SL Range": "range"
        }.get(self.tpsl_mode_var.get(), "auto")
        params = {"tpsl_mode": mode}
        if mode != "auto":
            params["point_size"] = float(self.point_size_var.get().strip())
            self._point_size_custom = True
        if mode == "fixed":
            params["fixed_tp_points"] = int(self.fixed_tp_points_var.get().strip())
            params["fixed_sl_points"] = int(self.fixed_sl_points_var.get().strip())
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

    # ========================== DATA & EXECUTION ==========================
    def _initial_load_data(self):
        self._fetch_data()
        # Automatically run dual auto-scan on startup
        self.root.after(300, self.execute_auto_scan)

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
        if self._point_size_custom or not isinstance(self.bars_data, dict):
            return
        value = self.bars_data.get("point_size")
        try:
            point_size = float(value)
            if point_size > 0:
                self.point_size_var.set(format(point_size, ".10g"))
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
        try:
            tpsl_params = self._get_tpsl_scan_params()
        except (TypeError, ValueError) as exc:
            messagebox.showerror("TP/SL Configuration", f"Periksa konfigurasi TP/SL: {exc}")
            return

        self.btn_run_auto.configure(state=tk.DISABLED, text="⚡ SCANNING...")
        self.dual_summary_title.configure(text="⏳ Scanning BUY & SELL candidates...", fg=GOLD)

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
                    engine_mode={"Legacy V1 (Default)": "legacy", "Enhanced OHLC V2": "v2", "Compare V1 vs V2": "compare"}.get(self.engine_mode_var.get(), "legacy"),
                    **tpsl_params
                )
                self.root.after(0, lambda: self._apply_dual_results(res))
            except Exception as e:
                self.root.after(0, lambda: self.dual_summary_title.configure(text=f"Scan Error: {e}", fg=RED))
            finally:
                self.root.after(0, lambda: self.btn_run_auto.configure(state=tk.NORMAL, text="⚡ SCAN DUAL SETUPS"))

        threading.Thread(target=worker, daemon=True).start()


    def _apply_dual_results(self, res):
        self.dual_results = res
        best_dir = res["best_direction"]
        summary = res["summary"]

        # Update Summary Banner
        col = GREEN if best_dir == "BUY" else (RED if best_dir == "SELL" else GOLD)
        self.dual_summary_title.configure(text=f"⭐ BEST QUANT EDGE: {best_dir} SETUP", fg=col)
        self.dual_summary_desc.configure(text=summary)

        # Update Headers
        bo = res["buy"]["odds"]
        so = res["sell"]["odds"]

        b_sign = "+" if bo["avg_r"] > 0 else ""
        s_sign = "+" if so["avg_r"] > 0 else ""
        bp = res["buy"]["plan"]
        sp = res["sell"]["plan"]
        buy_tpsl_label = f"{bp['tp_points']}/{bp['sl_points']} pts" if "tp_points" in bp and "sl_points" in bp else "Auto ATR/Structure"
        sell_tpsl_label = f"{sp['tp_points']}/{sp['sl_points']} pts" if "tp_points" in sp and "sl_points" in sp else "Auto ATR/Structure"
        self.buy_odds_lbl.configure(
            text=f"TP: {bo['target_first_pct']:.1f}% | Touch: {bp['entry_touch_probability_pct']:.0f}% | RR: 1:{bp['target_r']:.2f} | Adj.Exp: {bp['fill_adjusted_simulated_avg_r']:+.2f}R | TP/SL: {buy_tpsl_label}",
            fg=GREEN if bp["fill_adjusted_simulated_avg_r"] > 0 else TEXT_MUTED
        )
        self.sell_odds_lbl.configure(
            text=f"TP: {so['target_first_pct']:.1f}% | Touch: {sp['entry_touch_probability_pct']:.0f}% | RR: 1:{sp['target_r']:.2f} | Adj.Exp: {sp['fill_adjusted_simulated_avg_r']:+.2f}R | TP/SL: {sell_tpsl_label}",
            fg=RED if sp["fill_adjusted_simulated_avg_r"] > 0 else TEXT_MUTED
        )

        # Render Both Canvases
        self._draw_dual_charts()

    # ========================== DRAWING DUAL CHARTS ==========================
    def _draw_dual_charts(self):
        if not self.dual_results:
            return
        self._render_cone(self.buy_canvas, self.dual_results["buy"], is_buy=True)
        self._render_cone(self.sell_canvas, self.dual_results["sell"], is_buy=False)

    def _render_cone(self, canvas, sim_res, is_buy):
        canvas.delete("all")
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w < 50 or h < 50:
            return

        pad_left = 60
        pad_right = 20
        pad_top = 25
        pad_bottom = 35

        plot_w = w - pad_left - pad_right
        plot_h = h - pad_top - pad_bottom

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

        all_vals = p5 + p95 + [entry, stop, target]
        min_p = min(all_vals)
        max_p = max(all_vals)
        margin = max(1.0, (max_p - min_p) * 0.08)
        min_p -= margin
        max_p += margin

        def to_x(s_val):
            return pad_left + (s_val / steps[-1]) * plot_w

        def to_y(pr):
            return pad_top + (1.0 - (pr - min_p) / (max_p - min_p)) * plot_h

        # Grid lines
        for i in range(5):
            y_val = min_p + (max_p - min_p) * (i / 4.0)
            y_px = to_y(y_val)
            canvas.create_line(pad_left, y_px, w - pad_right, y_px, fill="#1c2536", dash=(2, 4))
            canvas.create_text(pad_left - 6, y_px, text=f"${y_val:.1f}", fill=TEXT_MUTED, font=("Segoe UI", 8), anchor="e")

        # Time ticks - dynamically scaled by interval
        meta = sim_res.get("meta", {}) or sim_res.get("plan", {})
        int_m = meta.get("interval_minutes", 1 if self.current_timeframe == "M1" else 5)
        total_hours = steps[-1] * int_m / 60
        is_multiday = total_hours >= 24.0
        for i in range(4):
            bar_val = steps[-1] * (i / 3.0)
            x_px = to_x(bar_val)
            canvas.create_line(x_px, pad_top, x_px, h - pad_bottom, fill="#1c2536", dash=(2, 4))
            if is_multiday:
                t_lbl = f"+{bar_val * int_m / 1440:.1f}d"
            elif total_hours < 1.0:
                t_lbl = f"+{int(round(bar_val * int_m))}m"
            else:
                t_lbl = f"+{bar_val * int_m / 60:.1f}h"
            canvas.create_text(x_px, h - pad_bottom + 12, text=t_lbl, fill=TEXT_MUTED, font=("Segoe UI", 8))

        # Methodology & Timeframe Tag Badge
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

        # 90% Ribbon
        poly_90 = []
        for s, v in zip(steps, p95): poly_90.extend([to_x(s), to_y(v)])
        for s, v in reversed(list(zip(steps, p5))): poly_90.extend([to_x(s), to_y(v)])
        if len(poly_90) >= 6:
            canvas.create_polygon(poly_90, fill="#182232", outline="")

        # 50% Ribbon
        poly_50 = []
        for s, v in zip(steps, p75): poly_50.extend([to_x(s), to_y(v)])
        for s, v in reversed(list(zip(steps, p25))): poly_50.extend([to_x(s), to_y(v)])
        if len(poly_50) >= 6:
            canvas.create_polygon(poly_50, fill="#233147", outline="")

        # Sample Paths
        for path in sample_paths[:12]:
            pts = []
            for step_idx, pr in enumerate(path):
                if step_idx < len(steps):
                    pts.extend([to_x(steps[step_idx]), to_y(pr)])
            if len(pts) >= 4:
                canvas.create_line(pts, fill="#324563", width=1)

        # Median
        med_pts = []
        for s, v in zip(steps, p50): med_pts.extend([to_x(s), to_y(v)])
        if len(med_pts) >= 4:
            canvas.create_line(med_pts, fill=GOLD, width=2)

        # Target & Stop lines
        y_tp = to_y(target)
        canvas.create_line(pad_left, y_tp, w - pad_right, y_tp, fill=GREEN, width=2, dash=(6, 4))
        canvas.create_text(w - pad_right, y_tp - 10, text=f"TP ${target:.2f} (+{plan.get('target_r', 0.0):.2f}R)", fill=GREEN, font=("Segoe UI", 9, "bold"), anchor="e")

        y_sl = to_y(stop)
        canvas.create_line(pad_left, y_sl, w - pad_right, y_sl, fill=RED, width=2, dash=(6, 4))
        canvas.create_text(w - pad_right, y_sl + 10, text=f"SL ${stop:.2f} (-1.0R)", fill=RED, font=("Segoe UI", 9, "bold"), anchor="e")

        y_en = to_y(entry)
        limit_lbl = "Buy Limit" if is_buy else "Sell Limit"
        canvas.create_line(pad_left, y_en, w - pad_right, y_en, fill="#ffffff", width=1, dash=(3, 3))
        canvas.create_text(pad_left + 8, y_en - 8, text=f"{limit_lbl} ${entry:.2f}", fill="#ffffff", font=("Segoe UI", 8, "bold"), anchor="w")

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
        if not self.manual_result:
            w = c.winfo_width()
            h = c.winfo_height()
            c.create_text(w / 2, h / 2, text="Run simulation to visualize probability paths", fill=TEXT_MUTED, font=("Segoe UI", 11))
            return
        self._render_cone(c, self.manual_result, is_buy=(self.direction_var.get() == "BUY"))

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

            tk.Button(pf, text="Uji Odds ⚡", font=("Segoe UI", 8, "bold"), bg=GOLD, fg="#000", relief=tk.FLAT, cursor="hand2", command=pick).pack(side=tk.RIGHT)

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
            "tpsl_mode": self.tpsl_mode_var.get(),
            "point_size": self.point_size_var.get(),
            "fixed_tp_points": self.fixed_tp_points_var.get(),
            "fixed_sl_points": self.fixed_sl_points_var.get(),
            "tp_min_points": self.tp_min_points_var.get(),
            "tp_max_points": self.tp_max_points_var.get(),
            "tp_step_points": self.tp_step_points_var.get(),
            "sl_min_points": self.sl_min_points_var.get(),
            "sl_max_points": self.sl_max_points_var.get(),
            "sl_step_points": self.sl_step_points_var.get(),
            "manual_direction": self.direction_var.get(),
            "manual_entry": self.manual_entry_var.get(),
            "manual_stop": self.manual_stop_var.get(),
            "manual_target": self.manual_target_var.get(),
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
                ("sl_step_points", self.sl_step_points_var)
            ):
                if key in settings:
                    variable.set(str(settings[key]))
            if "point_size" in settings:
                self._point_size_custom = True
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

        except Exception:
            pass

def main():
    root = tk.Tk()
    app = TimeMachineProGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
