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

---

## 🚀 Cara Menjalankan

### Menggunakan Shortcut Desktop (Paling Mudah)
* Double-click shortcut **"XAUUSD Time Machine"** di **Desktop Windows** Anda.
* Atau double-click file [run_gui.bat](file:///d:/Time%20Machine/run_gui.bat) di folder `d:\Time Machine`.

### Menggunakan Command Line (CLI)
```powershell
# Jalankan Auto Analyzer via CLI
python analyzer.py

# Jalankan simulasi manual
python timemachine.py --source mt5 --horizon 4h --replays 5000
```
