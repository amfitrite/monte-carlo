# ⚡ XAUUSD Time Machine PRO (Frameless Dual-Engine Edition)

Monte Carlo Statistical Odds Engine for Gold (XAUUSD / COMEX GC=F).
Inspired by Jake Schincariol's `trader-timemachine` from [day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill).

---

## 🌟 Fitur Baru di Edisi PRO
1. **Frameless Modern Pro Window**:
   - Tampilan bersih tanpa title bar bawaan Windows yang kaku.
   - Dilengkapi Custom Title Bar elegan bertema Dark Gold, bisa digeser (*draggable*), diminimize (`—`), dimaximize (`▢`), dan diclose (`✕`).
   - Terintegrasi penuh dengan Windows Taskbar (`WS_EX_APPWINDOW`).
2. **Dual-Engine Auto-Analyzer (BUY LIMIT & SELL LIMIT)**:
   - Menghitung level antrean terbaik untuk **BUY LIMIT** (area Support/Discount) dan **SELL LIMIT** (area Resistance/Premium) secara otomatis.
   - Mengunci rasio Risk:Reward sehat (1:2.0 R).
3. **Dual Fan Charts Berdampingan (Side-by-Side Split)**:
   - **Kanvas Kiri (🟢):** Visualisasi kurva probabilitas BUY LIMIT (Pita 90%, Pita 50%, Median, TP, SL, dan Entry).
   - **Kanvas Kanan (🔴):** Visualisasi kurva probabilitas SELL LIMIT (Pita 90%, Pita 50%, Median, TP, SL, dan Entry).
   - Mata Anda bisa langsung membandingkan kedua arah secara horizontal dalam 1 detik.
4. **Dual Data Source (MetaTrader 5 & COMEX Gold)**:
   - Direct Python IPC ke terminal MT5 (Exness, IC Markets, dll.) tanpa perlu pasang EA di chart.
   - Pilihan Timeframe Fleksibel: **M5 (Default)** untuk stabilitas data 60 hari, atau **M1 (Scalper)** untuk presisi tinggi time-of-day scalping.
   - Fallback otomatis ke data COMEX online jika MT5 tidak dibuka.
5. **Mode Manual & Impor Posisi Aktif MT5**:
   - Mendukung input angka kustom atau 1-klik impor posisi aktif yang sedang floating di MT5.
6. **⚙️ Opsi Metodologi Statistik Lengkap (Bebas Dipilih & Dibandingkan)**:
   - **Fan Chart Projection Mode:**
     - **Two-Stream Free Drift (Default / Rekomendasi Utama):** Lintasan harga fan chart terus berayun alami sesuai volatilitas pasar murni tanpa distorsi path beku (*unconstrained price distribution*), sementara Odds Evaluator secara independen menghitung first-passage SL/TP.
     - **Frozen at Exit Level (Versi Asli / Baseline):** Mempertahankan metodologi orisinal Jake Schincariol di mana path yang mengenai SL/TP dibekukan pada level exit untuk perbandingan baseline.
     - **Survival / Active Only (Kaplan-Meier Style):** Menghitung distribusi persentil hanya dari lintasan yang masih aktif (belum exit) pada setiap step bar.
   - **Collision Tie-Break Resolution (Jika SL & TP tersentuh di bar yang sama):**
     - **Smart Candle Anatomy (Default / Rekomendasi Utama):** Mengeliminasi bias pesimistis dengan membaca anatomi candle historis (candle bullish bergerak ke low dulu; candle bearish bergerak ke high dulu; doji 50:50).
     - **Conservative SL First (Versi Asli / Baseline):** Mempertahankan logika orisinal di mana collision selalu dianggap terkena Stop Loss terlebih dahulu.
     - **50:50 Balanced Coin Flip:** Uji Bernoulli seimbang 50% TP vs 50% SL.
   - **Dynamic Horizon Scaling:** Normalisasi horizon waktu dinamis yang mengenali interval bar aktual (M1 vs M5) secara presisi, tanpa hardcode 5 menit.

---

## 🚀 Cara Menjalankan

### Menggunakan Shortcut Desktop (Paling Mudah)
* Double-click shortcut **"XAUUSD Time Machine"** di **Desktop Windows** Anda.
* Atau double-click file [run_gui.bat](file:///d:/Time%20Machine/run_gui.bat) di folder `d:\Time Machine`.

### Menggunakan Command Line (CLI)
```powershell
# Jalankan Auto Analyzer via CLI
python analyzer.py

# Jalankan simulasi manual dengan metodologi rekomendasi (default)
python timemachine.py --source mt5 --horizon 4h --replays 5000 --projection-mode free_drift --tie-break smart

# Jalankan simulasi manual dengan metodologi asli/baseline (untuk membandingkan)
python timemachine.py --source mt5 --horizon 4h --replays 5000 --projection-mode frozen --tie-break conservative
```
