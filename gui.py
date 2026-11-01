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
        self._cached_plot_w = 400
        self._cached_plot_h = 300
        self._cached_vis_price_range = 80.0
        self._cached_vis_steps = 72

        # Configure taskbar integration for frameless window
        self._setup_taskbar()

        # Build UI
        self._build_title_bar()
        self._build_header_toolbar()
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
            bg=GOLD, fg="#0b0f17", relief=tk.FLAT, highlightthickness=1, highlightbackground=BORDER_COL, highlightcolor=GOLD, cursor="hand2", padx=12, pady=4,
            command=lambda: self._set_app_mode("auto")
        )
        self.btn_mode_auto.pack(side=tk.LEFT, padx=(0, 2))

        self.btn_mode_manual = tk.Button(
            mode_box, text="🛠️ MANUAL SETUP", font=("Segoe UI", 9, "bold"),
            bg=INPUT_BG, fg=TEXT_MUTED, relief=tk.FLAT, highlightthickness=1, highlightbackground=BORDER_COL, highlightcolor=GOLD, cursor="hand2", padx=12, pady=4,
            command=lambda: self._set_app_mode("manual")
        )
        self.btn_mode_manual.pack(side=tk.LEFT, padx=(2, 0))

        # Center-Right: Data Source Switcher (MT5 vs COMEX)
        src_box = tk.Frame(toolbar, bg=CARD_BG, padx=3, pady=3, highlightbackground=BORDER_COL, highlightthickness=1)
        src_box.pack(side=tk.LEFT, padx=(20, 0))

        self.btn_src_mt5 = tk.Button(
            src_box, text="🔗 MetaTrader 5", font=("Segoe UI", 8, "bold"),
            bg=GOLD, fg="#0b0f17", relief=tk.FLAT, highlightthickness=1, highlightbackground=BORDER_COL, highlightcolor=GOLD, cursor="hand2", padx=8, pady=3,
            command=lambda: self._switch_data_source("mt5")
        )
        self.btn_src_mt5.pack(side=tk.LEFT, padx=(0, 2))

        self.btn_src_comex = tk.Button(
            src_box, text="🌐 COMEX Gold", font=("Segoe UI", 8, "bold"),
            bg=INPUT_BG, fg=TEXT_MUTED, relief=tk.FLAT, highlightthickness=1, highlightbackground=BORDER_COL, highlightcolor=GOLD, cursor="hand2", padx=8, pady=3,
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
            bg=INPUT_BG, fg=GOLD, relief=tk.FLAT, highlightthickness=1, highlightbackground=BORDER_COL, highlightcolor=GOLD, cursor="hand2", padx=6, pady=2,
            command=self.refresh_data
        ).pack(side=tk.LEFT)

    # ========================== MAIN BODY ==========================
    def _build_main_body(self):
        self.body_frame = tk.Frame(self.root, bg=DARK_BG, padx=14, pady=12)
        self.body_frame.pack(fill=tk.BOTH, expand=True)

        # Left Control Sidebar (Width ~340px) with smooth scrolling & docked action footer
        self.left_panel = tk.Frame(self.body_frame, bg=PANEL_BG, width=340, highlightbackground=BORDER_COL, highlightthickness=1)
        self.left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        self.left_panel.pack_propagate(False)

        # Docked Action Footer (Always visible regardless of sidebar scrolling)
        self.sidebar_footer = tk.Frame(self.left_panel, bg=PANEL_BG, padx=12, pady=10, highlightbackground=BORDER_COL, highlightthickness=1)
        self.sidebar_footer.pack(side=tk.BOTTOM, fill=tk.X)

        # Auto Mode Docked Action Bar
        self.auto_action_bar = tk.Frame(self.sidebar_footer, bg=PANEL_BG)
        self.btn_run_auto = tk.Button(
            self.auto_action_bar, text="⚡ SCAN DUAL SETUPS", font=("Segoe UI", 11, "bold"),
            bg=GOLD, fg="#0b0f17", activebackground=GOLD_HOVER, activeforeground="#ffffff",
            relief=tk.FLAT, highlightthickness=1, highlightbackground=BORDER_COL, highlightcolor=GOLD, cursor="hand2", pady=8,
            command=self.execute_auto_scan
        )
        self.btn_run_auto.pack(fill=tk.X, pady=(0, 6))

        self.import_mt5_btn = tk.Button(
            self.auto_action_bar, text="📥 Impor Posisi Aktif MT5", font=("Segoe UI", 9, "bold"),
            bg=INPUT_BG, fg=CYAN, relief=tk.FLAT, highlightthickness=1, highlightbackground=BORDER_COL, highlightcolor=GOLD, cursor="hand2", pady=4,
            command=self._open_positions_selector
        )
        self.import_mt5_btn.pack(fill=tk.X)
        self.auto_action_bar.pack(fill=tk.X)

        # Manual Mode Docked Action Bar
        self.manual_action_bar = tk.Frame(self.sidebar_footer, bg=PANEL_BG)
        self.btn_run_manual = tk.Button(
            self.manual_action_bar, text="🚀 RUN SIMULATION", font=("Segoe UI", 11, "bold"),
            bg=GOLD, fg="#0b0f17", activebackground=GOLD_HOVER, activeforeground="#ffffff",
            relief=tk.FLAT, highlightthickness=1, highlightbackground=BORDER_COL, highlightcolor=GOLD, cursor="hand2", pady=8,
            command=self.execute_manual_simulation
        )
        self.btn_run_manual.pack(fill=tk.X)

        # Scrollable container for control forms
        self._scroll_container = tk.Frame(self.left_panel, bg=PANEL_BG)
        self._scroll_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Scrollbar packed first on right to ensure visibility
        self._sidebar_scrollbar = ttk.Scrollbar(self._scroll_container, orient="vertical")
        self._sidebar_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._sidebar_canvas = tk.Canvas(self._scroll_container, bg=PANEL_BG, highlightthickness=0, bd=0, yscrollcommand=self._sidebar_scrollbar.set)
        self._sidebar_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._sidebar_scrollbar.configure(command=self._sidebar_canvas.yview)

        self._sidebar_content = tk.Frame(self._sidebar_canvas, bg=PANEL_BG, padx=12, pady=10)
        self._sidebar_window = self._sidebar_canvas.create_window((0, 0), window=self._sidebar_content, anchor="nw")

        def _on_sidebar_content_config(event):
            self._sidebar_canvas.configure(scrollregion=self._sidebar_canvas.bbox("all"))

        def _on_sidebar_canvas_config(event):
            self._sidebar_canvas.itemconfig(self._sidebar_window, width=event.width)

        self._sidebar_content.bind("<Configure>", _on_sidebar_content_config)
        self._sidebar_canvas.bind("<Configure>", _on_sidebar_canvas_config)

        # Mousewheel scrolling
        def _on_mousewheel(event):
            if self._sidebar_canvas.winfo_exists():
                delta = -1 * (event.delta // 120) if event.delta else 0
                self._sidebar_canvas.yview_scroll(delta, "units")

        def _bind_mousewheel(widget):
            widget.bind("<MouseWheel>", _on_mousewheel, add="+")
            for child in widget.winfo_children():
                _bind_mousewheel(child)

        self.bind_sidebar_mousewheel = _bind_mousewheel
        self._sidebar_canvas.bind("<MouseWheel>", _on_mousewheel)
        self._sidebar_content.bind("<MouseWheel>", _on_mousewheel)

        # Right Display Area (Holds either Dual Fan Charts or Single Fan Chart)
        self.right_panel = tk.Frame(self.body_frame, bg=DARK_BG)
        self.right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Build Sidebar Content
        self._build_sidebar_controls()
        self.bind_sidebar_mousewheel(self._sidebar_content)

        # Build Right Views
        self._build_auto_view()
        self._build_manual_view()

        # Show initial mode
        self._update_view_visibility()

    def _build_sidebar_controls(self):
        parent = self._sidebar_content

        # Section 1: Time Horizon Selector (Common to both modes)
        tk.Label(parent, text="SCAN TIME HORIZON", font=("Segoe UI", 9, "bold"), fg=GOLD, bg=PANEL_BG).pack(anchor="w", pady=(0, 4))
        self.horizon_var = tk.StringVar(value="4 Jam (48 bars M5)")
        horizon_options = [h[0] for h in HORIZON_PRESETS_M5]
        self.horizon_combo = ttk.Combobox(
            parent, textvariable=self.horizon_var, values=horizon_options, state="readonly", font=("Segoe UI", 9)
        )
        self.horizon_combo.pack(fill=tk.X, pady=(0, 8))
        self.horizon_combo.bind("<<ComboboxSelected>>", lambda e: self._on_horizon_change())

        # Section 1B: Candle Timeframe Base (M5 Default vs M1 Scalper)
        tk.Label(parent, text="CANDLE TIMEFRAME BASE", font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=PANEL_BG).pack(anchor="w", pady=(0, 2))
        tf_frame = tk.Frame(parent, bg=PANEL_BG)
        tf_frame.pack(fill=tk.X, pady=(0, 10))

        self.btn_tf_m5 = tk.Button(
            tf_frame, text="M5 (Default)", font=("Segoe UI", 8, "bold"),
            bg=GOLD, fg="#0b0f17", relief=tk.FLAT, highlightthickness=1, highlightbackground=BORDER_COL, highlightcolor=GOLD, cursor="hand2",
            command=lambda: self._set_timeframe("M5")
        )
        self.btn_tf_m5.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))

        self.btn_tf_m1 = tk.Button(
            tf_frame, text="M1 (Scalper)", font=("Segoe UI", 8, "bold"),
            bg=INPUT_BG, fg=TEXT_MUTED, relief=tk.FLAT, highlightthickness=1, highlightbackground=BORDER_COL, highlightcolor=GOLD, cursor="hand2",
            command=lambda: self._set_timeframe("M1")
        )
        self.btn_tf_m1.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        # Section 2: Replays & Spread
        sub_row = tk.Frame(parent, bg=PANEL_BG)
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
            bg=INPUT_BG, fg=TEXT_PRIMARY, relief=tk.FLAT, highlightthickness=1, highlightbackground=BORDER_COL, highlightcolor=GOLD
        )
        self.spread_entry.pack(fill=tk.X, ipady=2)

        # Section 2B: Statistical Methodology Options (User Selectable & Collapsible)
        method_card = tk.Frame(parent, bg=CARD_BG, padx=10, pady=8, highlightbackground=BORDER_COL, highlightthickness=1)
        method_card.pack(fill=tk.X, pady=(0, 10))

        # Collapsible header
        method_header = tk.Frame(method_card, bg=CARD_BG)
        method_header.pack(fill=tk.X)
        self.method_toggle_btn = tk.Label(
            method_header, text="⚙️ ADVANCED SETTINGS ▶", font=("Segoe UI", 8, "bold"),
            fg=GOLD, bg=CARD_BG, cursor="hand2"
        )
        self.method_toggle_btn.pack(side=tk.LEFT)

        self.method_body = tk.Frame(method_card, bg=CARD_BG)
        # Hidden by default so DUAL AUTO TP/SL card is immediately visible!

        def _toggle_method_card(event=None):
            if self.method_body.winfo_ismapped():
                self.method_body.pack_forget()
                self.method_toggle_btn.configure(text="⚙️ ADVANCED SETTINGS ▶")
            else:
                self.method_body.pack(fill=tk.X, pady=(6, 0))
                self.method_toggle_btn.configure(text="⚙️ ADVANCED SETTINGS ▼")
            if hasattr(self, "_sidebar_canvas"):
                self.root.after(10, lambda: self._sidebar_canvas.configure(scrollregion=self._sidebar_canvas.bbox("all")))

        self.method_toggle_btn.bind("<Button-1>", _toggle_method_card)
        method_header.bind("<Button-1>", _toggle_method_card)

        tk.Label(self.method_body, text="ENGINE SELECTION", font=("Segoe UI", 7, "bold"), fg=TEXT_MUTED, bg=CARD_BG).pack(anchor="w")
        self.engine_mode_var = tk.StringVar(value="Legacy V1 (Default)")
        self.engine_mode_combo = ttk.Combobox(
            self.method_body, textvariable=self.engine_mode_var,
            values=["Legacy V1 (Default)", "Enhanced OHLC V2", "Compare V1 vs V2"],
            state="readonly", font=("Segoe UI", 8)
        )
        self.engine_mode_combo.pack(fill=tk.X, pady=(2, 6))
        tk.Label(self.method_body, text="V2 uses block bootstrap + conservative collision handling.", font=("Segoe UI", 7), fg=TEXT_MUTED, bg=CARD_BG, wraplength=280, justify=tk.LEFT).pack(anchor="w", pady=(0, 5))

        tk.Label(self.method_body, text="LEGACY V1 METHODOLOGY", font=("Segoe UI", 7, "bold"), fg=TEXT_MUTED, bg=CARD_BG).pack(anchor="w")

        tk.Label(self.method_body, text="Fan Chart Projection", font=("Segoe UI", 7, "bold"), fg=TEXT_MUTED, bg=CARD_BG).pack(anchor="w", pady=(4, 1))
        self.proj_mode_var = tk.StringVar(value="Two-Stream Free Drift (Recommended)")
        self.proj_combo = ttk.Combobox(
            self.method_body, textvariable=self.proj_mode_var,
            values=list(PROJECTION_MODES.keys()), state="readonly", font=("Segoe UI", 8)
        )
        self.proj_combo.pack(fill=tk.X)
        self.proj_combo.bind("<<ComboboxSelected>>", lambda e: self._on_methodology_change())

        tk.Label(self.method_body, text="Collision Tie-Break", font=("Segoe UI", 7, "bold"), fg=TEXT_MUTED, bg=CARD_BG).pack(anchor="w", pady=(4, 1))
        self.tie_break_var = tk.StringVar(value="Smart Candle Anatomy (Recommended)")
        self.tb_combo = ttk.Combobox(
            self.method_body, textvariable=self.tie_break_var,
            values=list(TIE_BREAK_MODES.keys()), state="readonly", font=("Segoe UI", 8)
        )
        self.tb_combo.pack(fill=tk.X)
        self.tb_combo.bind("<<ComboboxSelected>>", lambda e: self._on_methodology_change())

        tk.Label(self.method_body, text="Seasonality Filter", font=("Segoe UI", 7, "bold"), fg=TEXT_MUTED, bg=CARD_BG).pack(anchor="w", pady=(4, 1))
        self.seasonality_var = tk.StringVar(value="Off (Default/Asli)")
        self.seasonality_combo = ttk.Combobox(
            self.method_body, textvariable=self.seasonality_var,
            values=list(SEASONALITY_MODES.keys()), state="readonly", font=("Segoe UI", 8), cursor="hand2"
        )
        self.seasonality_combo.pack(fill=tk.X)
        self.seasonality_combo.bind("<<ComboboxSelected>>", lambda e: self._on_methodology_change())

        tk.Label(self.method_body, text="Price Grid Lines", font=("Segoe UI", 7, "bold"), fg=TEXT_MUTED, bg=CARD_BG).pack(anchor="w", pady=(4, 1))
        self.grid_lines_var = tk.StringVar(value="Dynamic Adaptive (Default)")
        self.grid_lines_combo = ttk.Combobox(
            self.method_body, textvariable=self.grid_lines_var,
            values=["Dynamic Adaptive (Default)", "25 Lines", "50 Lines"], state="readonly", font=("Segoe UI", 8), cursor="hand2"
        )
        self.grid_lines_combo.pack(fill=tk.X)
        self.grid_lines_combo.bind("<<ComboboxSelected>>", lambda e: self._on_display_setting_change())

        # Section 3A: AUTO MODE SPECIFIC CONTROLS
        self.auto_sidebar_frame = tk.Frame(parent, bg=PANEL_BG)
        
        # Strategy Selector Card
        strat_card = tk.Frame(self.auto_sidebar_frame, bg=CARD_BG, padx=10, pady=8, highlightbackground=BORDER_COL, highlightthickness=1)
        strat_card.pack(fill=tk.X, pady=(0, 10))

        tk.Label(strat_card, text="🧠 ENTRY STRATEGY", font=("Segoe UI", 8, "bold"), fg=GOLD, bg=CARD_BG).pack(anchor="w")
        self.strategy_var = tk.StringVar(value="ATR Pullback & Swing (Default)")
        self.strategy_combo = ttk.Combobox(
            strat_card, textvariable=self.strategy_var,
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
            state="readonly", font=("Segoe UI", 8)
        )
        self.strategy_combo.pack(fill=tk.X, pady=(4, 4))
        self.strategy_combo.bind("<<ComboboxSelected>>", lambda e: self._on_strategy_change())
        
        self.strategy_desc_label = tk.Label(
            strat_card,
            text="Pencarian level limit dari pullback ATR bertingkat dan swing structure 24 bar.",
            font=("Segoe UI", 7), fg=TEXT_MUTED, bg=CARD_BG, wraplength=280, justify=tk.LEFT
        )
        self.strategy_desc_label.pack(anchor="w")

        # Dual Auto TP/SL search configuration (hidden in Manual mode).
        tpsl_card = tk.Frame(self.auto_sidebar_frame, bg=CARD_BG, padx=10, pady=8, highlightbackground=BORDER_COL, highlightthickness=1)
        tpsl_card.pack(fill=tk.X, pady=(0, 10))
        tk.Label(tpsl_card, text="🎯 DUAL AUTO TP / SL", font=("Segoe UI", 8, "bold"), fg=GOLD, bg=CARD_BG).pack(anchor="w")
        self.tpsl_mode_var = tk.StringVar(value="Auto Optimize")
        self.tpsl_mode_combo = ttk.Combobox(
            tpsl_card, textvariable=self.tpsl_mode_var,
            values=["Auto Optimize", "Fixed TP/SL", "TP/SL Range", "Risk Reward"],
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
        self.rr_ratio_var = tk.StringVar(value="1:2.0")
        self.rr_sl_points_var = tk.StringVar(value="1000")

        # Auto re-calculate / re-scan when research points are edited
        for var in (
            self.point_size_var, self.fixed_tp_points_var, self.fixed_sl_points_var,
            self.tp_min_points_var, self.tp_max_points_var, self.tp_step_points_var,
            self.sl_min_points_var, self.sl_max_points_var, self.sl_step_points_var,
            self.rr_ratio_var, self.rr_sl_points_var
        ):
            var.trace_add("write", lambda *args: self._on_tpsl_points_modified())

        self._render_tpsl_fields()

        # Section 3B: MANUAL MODE SPECIFIC CONTROLS
        self.manual_sidebar_frame = tk.Frame(parent, bg=PANEL_BG)

        # Direction Toggle
        tk.Label(self.manual_sidebar_frame, text="Order Direction", font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=PANEL_BG).pack(anchor="w")
        dir_frame = tk.Frame(self.manual_sidebar_frame, bg=PANEL_BG)
        dir_frame.pack(fill=tk.X, pady=(2, 6))

        self.direction_var = tk.StringVar(value="BUY")
        self.buy_btn = tk.Button(
            dir_frame, text="▲ BUY", font=("Segoe UI", 9, "bold"),
            bg=GREEN, fg="#ffffff", relief=tk.FLAT, highlightthickness=1, highlightbackground=BORDER_COL, highlightcolor=GOLD, cursor="hand2",
            command=lambda: self._set_direction("BUY")
        )
        self.buy_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))

        self.sell_btn = tk.Button(
            dir_frame, text="▼ SELL", font=("Segoe UI", 9, "bold"),
            bg=INPUT_BG, fg=TEXT_MUTED, relief=tk.FLAT, highlightthickness=1, highlightbackground=BORDER_COL, highlightcolor=GOLD, cursor="hand2",
            command=lambda: self._set_direction("SELL")
        )
        self.sell_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        # Entry Price
        tk.Label(self.manual_sidebar_frame, text="Entry Price ($)", font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=PANEL_BG).pack(anchor="w")
        self.manual_entry_var = tk.StringVar(value="3875.00")
        self.manual_entry_var.trace_add("write", self._on_manual_price_change)
        tk.Entry(
            self.manual_sidebar_frame, textvariable=self.manual_entry_var, font=("Segoe UI", 10),
            bg=INPUT_BG, fg=TEXT_PRIMARY, relief=tk.FLAT, highlightthickness=1, highlightbackground=BORDER_COL, highlightcolor=GOLD
        ).pack(fill=tk.X, pady=(1, 5), ipady=2)

        # Stop Loss
        tk.Label(self.manual_sidebar_frame, text="Stop Loss ($)", font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=PANEL_BG).pack(anchor="w")
        self.manual_stop_var = tk.StringVar(value="3850.00")
        self.manual_stop_var.trace_add("write", self._on_manual_price_change)
        tk.Entry(
            self.manual_sidebar_frame, textvariable=self.manual_stop_var, font=("Segoe UI", 10),
            bg=INPUT_BG, fg=RED, relief=tk.FLAT, highlightthickness=1, highlightbackground=BORDER_COL, highlightcolor=GOLD
        ).pack(fill=tk.X, pady=(1, 5), ipady=2)

        # Take Profit
        tk.Label(self.manual_sidebar_frame, text="Take Profit ($)", font=("Segoe UI", 8, "bold"), fg=TEXT_MUTED, bg=PANEL_BG).pack(anchor="w")
        self.manual_target_var = tk.StringVar(value="3925.00")
        self.manual_target_var.trace_add("write", self._on_manual_price_change)
        tk.Entry(
            self.manual_sidebar_frame, textvariable=self.manual_target_var, font=("Segoe UI", 10),
            bg=INPUT_BG, fg=GREEN, relief=tk.FLAT, highlightthickness=1, highlightbackground=BORDER_COL, highlightcolor=GOLD
        ).pack(fill=tk.X, pady=(1, 5), ipady=2)

        # Manual R:R badge
        self.manual_rr_lbl = tk.Label(
            self.manual_sidebar_frame, text="Risk: $25.00 | Reward: $50.00 | 2.00 R",
            font=("Segoe UI", 8, "bold"), fg=GOLD, bg=CARD_BG, pady=4
        )
        self.manual_rr_lbl.pack(fill=tk.X, pady=(2, 10))

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

        m_chart_header = tk.Frame(m_chart_box, bg=PANEL_BG, padx=10, pady=6)
        m_chart_header.pack(fill=tk.X)
        tk.Label(m_chart_header, text="📊 PROBABILITY PATH SIMULATION", font=("Segoe UI", 10, "bold"), fg=GOLD, bg=PANEL_BG).pack(side=tk.LEFT)
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
        self._update_view_visibility()

    def _update_view_visibility(self):
        if self.active_mode == "auto":
            self.manual_sidebar_frame.pack_forget()
            self.auto_sidebar_frame.pack(fill=tk.BOTH, expand=True)
            self.manual_view_frame.pack_forget()
            self.auto_view_frame.pack(fill=tk.BOTH, expand=True)
            if hasattr(self, "manual_action_bar") and hasattr(self, "auto_action_bar"):
                self.manual_action_bar.pack_forget()
                self.auto_action_bar.pack(fill=tk.X)
        else:
            self.auto_sidebar_frame.pack_forget()
            self.manual_sidebar_frame.pack(fill=tk.BOTH, expand=True)
            self.auto_view_frame.pack_forget()
            self.manual_view_frame.pack(fill=tk.BOTH, expand=True)
            if hasattr(self, "manual_action_bar") and hasattr(self, "auto_action_bar"):
                self.auto_action_bar.pack_forget()
                self.manual_action_bar.pack(fill=tk.X)

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
        mode = {
            "Auto Optimize": "auto",
            "Fixed TP/SL": "fixed",
            "TP/SL Range": "range",
            "Risk Reward": "risk_reward"
        }.get(self.tpsl_mode_var.get(), "auto")
        params = {"tpsl_mode": mode}
        if mode != "auto":
            params["point_size"] = float(self.point_size_var.get().strip())
            self._point_size_custom = True
        if mode == "fixed":
            params["fixed_tp_points"] = int(self.fixed_tp_points_var.get().strip())
            params["fixed_sl_points"] = int(self.fixed_sl_points_var.get().strip())
        elif mode == "risk_reward":
            params["rr_ratio"] = self._parse_rr_ratio(self.rr_ratio_var.get())
            params["rr_sl_points"] = int(self.rr_sl_points_var.get().strip())
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
                    engine_mode=engine_mode,
                    strategy=strategy_code,
                    **tpsl_params
                )
                self.root.after(0, lambda r=res: self._apply_dual_results(r))
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda msg=err_msg: self._show_scan_error(msg))
            finally:
                self.root.after(0, lambda: self.btn_run_auto.configure(state=tk.NORMAL, text="⚡ SCAN DUAL SETUPS"))

        threading.Thread(target=worker, daemon=True).start()

    def _show_scan_error(self, err_msg):
        self.dual_summary_title.configure(text="⚠️ Scan Error", fg=RED)
        self.dual_summary_desc.configure(text=f"Gagal melakukan simulasi: {err_msg}")


    def _apply_dual_results(self, res):
        self.dual_results = res
        best_dir = res["best_direction"]
        summary = res["summary"]

        # Update Summary Banner
        col = GREEN if best_dir == "BUY" else (RED if best_dir == "SELL" else GOLD)
        strat_lbl = res.get("strategy_label", "ATR & Swing")
        self.dual_summary_title.configure(text=f"⭐ BEST QUANT EDGE: {best_dir} SETUP", fg=col)
        self.dual_summary_desc.configure(text=f"[{strat_lbl}] {summary}")

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
        self._pan_start_x = event.x
        self._pan_start_y = event.y
        self._is_panning = True
        try:
            event.widget.configure(cursor="fleur")
        except Exception:
            pass

    def _on_chart_pan_motion(self, event):
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
        self._is_panning = False
        try:
            event.widget.configure(cursor="")
        except Exception:
            pass

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

        if price_bounds:
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

        # Store cache for zoom/pan calculations
        self._cached_base_range = base_range
        self._cached_orig_mid = orig_mid
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
        y_tp = to_y(target)
        if pad_top <= y_tp <= h - pad_bottom:
            canvas.create_line(pad_left, y_tp, w - pad_right, y_tp, fill=GREEN, width=2, dash=(6, 4))
            canvas.create_text(w - pad_right - 6, y_tp - 10, text=f"TP ${target:.2f} (+{plan.get('target_r', 0.0):.2f}R)", fill=GREEN, font=("Segoe UI", 9, "bold"), anchor="e")
        elif y_tp < pad_top:
            canvas.create_text(w - pad_right - 6, pad_top + 12, text=f"▲ TP ${target:.2f} (+{plan.get('target_r', 0.0):.1f}R)", fill=GREEN, font=("Segoe UI", 8, "bold"), anchor="e")
        elif y_tp > h - pad_bottom:
            canvas.create_text(w - pad_right - 6, h - pad_bottom - 12, text=f"▼ TP ${target:.2f} (+{plan.get('target_r', 0.0):.1f}R)", fill=GREEN, font=("Segoe UI", 8, "bold"), anchor="e")

        y_sl = to_y(stop)
        if pad_top <= y_sl <= h - pad_bottom:
            canvas.create_line(pad_left, y_sl, w - pad_right, y_sl, fill=RED, width=2, dash=(6, 4))
            canvas.create_text(w - pad_right - 6, y_sl + 10, text=f"SL ${stop:.2f} (-1.0R)", fill=RED, font=("Segoe UI", 9, "bold"), anchor="e")
        elif y_sl < pad_top:
            canvas.create_text(w - pad_right - 6, pad_top + 24, text=f"▲ SL ${stop:.2f} (-1.0R)", fill=RED, font=("Segoe UI", 8, "bold"), anchor="e")
        elif y_sl > h - pad_bottom:
            canvas.create_text(w - pad_right - 6, h - pad_bottom - 24, text=f"▼ SL ${stop:.2f} (-1.0R)", fill=RED, font=("Segoe UI", 8, "bold"), anchor="e")

        y_en = to_y(entry)
        limit_lbl = "Buy Limit" if is_buy else "Sell Limit"
        tag_str = f" [{plan['setup_tag']}]" if plan.get("setup_tag") else ""
        if pad_top <= y_en <= h - pad_bottom:
            canvas.create_line(pad_left, y_en, w - pad_right, y_en, fill="#ffffff", width=1, dash=(3, 3))
            canvas.create_text(pad_left + 8, y_en - 8, text=f"{limit_lbl}{tag_str} ${entry:.2f}", fill="#ffffff", font=("Segoe UI", 8, "bold"), anchor="w")

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

        except Exception:
            pass

def main():
    root = tk.Tk()
    app = TimeMachineProGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
