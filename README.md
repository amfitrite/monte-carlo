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
   - **Seasonality Filter (Day-of-Week Aware):** Opsi filter hari dalam seminggu (Senin s/d Jumat) untuk membedakan karakteristik volatilitas harian emas.
7. **💾 Auto-Save Settings Persistence**:
   - Seluruh preferensi pengguna (mode, data source, timeframe, horizon, replays, spread buffer, pilihan metodologi statistik, hingga level angka manual) **otomatis tersimpan saat aplikasi ditutup**.
   - Saat aplikasi dibuka kembali, pengaturan terakhir langsung terisi otomatis tanpa perlu disetel ulang dari nol.
8. **🔍 Interactive Chart Zoom & Dynamic Adaptive Price Grid**:
   - **Interactive Navigation & Shortcuts:**
     - `Ctrl` + Scroll Mouse Wheel: Zoom vertikal pada sumbu harga (*Price / Y-axis*).
     - `Shift` + Scroll Mouse Wheel: Zoom horizontal pada sumbu waktu (*Time / X-axis*).
     - Regular Scroll Mouse Wheel: Zoom proporsional terpusat pada posisi kursor mouse (*cursor-centered*).
     - Klik-Kiri Drag: Menggeser (*pan*) grafik secara bebas dengan pelacakan pergerakan kursor 1:1.
     - Double-Click (atau `Ctrl` + `0`): Reset zoom dan posisi geser seketika kembali ke 100% (*Auto-Fit*).
     - Tombol `[⟲ Reset Zoom]` langsung di header chart untuk kemudahan 1-klik.
     - Hotkey Keyboard: `Ctrl` + `+` / `Ctrl` + `=` untuk zoom in, `Ctrl` + `-` untuk zoom out.
   - **Dynamic Adaptive Price Grid:**
     - Garis grid harga beradaptasi secara dinamis menggunakan algoritma *Nice Round Numbers* (angka bulat bersih kelipatan 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50).
     - Semakin grafik dizoom-in, garis grid otomatis bertambah rapat dan detail; semakin dizoom-out, garis grid otomatis berkurang agar tetap rapi tanpa angka acak desimal tak beraturan.
   - **Auto-Sync Dual Fan Charts:**
     - Skala harga dan waktu pada grafik BUY (kiri) dan SELL (kanan) tersinkronisasi otomatis secara side-by-side, memudahkan perbandingan level harga langsung secara horizontal.
   - **Off-Screen Target/Stop Indicators:**
     - Menampilkan indikator penunjuk arah (`▲ TP` / `▼ SL`) di tepi layar jika level target atau stop loss berada di luar pandangan saat grafik dizoom-in secara mendalam.

---

## 🌟 Fitur & Peningkatan Mutakhir (Merged & Verified)
* **📅 Seasonality Filter Support (`explain-accuracy`)**:
  - Filter hari dalam seminggu (`seasonality=True/False`) untuk memisahkan pool slot candle sesuai hari transaksi (Senin s/d Jumat).
* **⚡ Batching NumPy Percentile Calculations (`bolt`)**:
  - Menggabungkan kalkulasi 5 persentil fan chart `[5, 25, 50, 75, 95]` ke dalam satu panggilan batch array terpadu.
  - Memangkas overhead perpindahan *Python ↔ C runtime*, menghasilkan akselerasi kecepatan komputasi hingga **~70% lebih cepat** tanpa mengubah output matematika/probabilitas (100% konsisten).

* **🎨 Keyboard Focus Indicators on Flat Entry Widgets (`palette`)**:
  - Menambahkan styling `highlightthickness=1`, `highlightbackground=PANEL_BG`, dan `highlightcolor=GOLD` pada seluruh form input teks (`Spread`, `Entry`, `SL`, `TP`).
  - Memberikan feedback visual berupa garis tepi aksen emas (*Gold Focus Ring*) saat kotak input aktif diklik atau dinavigasi via keyboard `Tab`.

* **🛡️ URL Parameter & File Extension Security Sanitization (`sentinel`)**:
  - Menggunakan `urllib.parse.urlencode` dan validasi `.isalnum()` untuk mencegah *HTTP Parameter Pollution* pada API Yahoo Finance.
  - Memvalidasi ekstensi file `.csv` lokal untuk mencegah *arbitrary file inclusion* / *path traversal*.

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


## 🧪 Enhanced OHLC V2 (Optional)

Legacy V1 remains intact and is still the default engine for existing users and
new installations. The GUI engine selector offers:

- **Legacy V1 (Default):** unchanged original simulation path.
- **Enhanced OHLC V2:** contiguous block-bootstrap sampling of historical OHLC
  returns, preserving local sequence inside sampled blocks.
- **Compare V1 vs V2:** runs both engines against the same generated entry,
  stop, target, horizon, spread assumption, and input history. V1 remains the
  displayed baseline; V2 comparison statistics are shown alongside it.

V2 does not infer the order of high/low touches from candle color. If one OHLC
bar touches both TP and SL, the primary V2 estimate counts the outcome as
stop-first and reports the optimistic TP-first bound separately. The true
intrabar order remains unknown without lower-timeframe or tick data.

**Important:** Compare mode compares two simulation methodologies, not their
real-world predictive accuracy. Neither engine is calibrated or validated by
this comparison alone. To establish trading usefulness, run chronological
walk-forward tests against unseen historical outcomes and include realistic
spread, commission, slippage, limit-order fill probability, and execution
constraints. V2's block length is configurable in the engine API (default 10
bars); it is a modeling parameter, not a proven optimum.

Run the unit tests with:

```bash
python -m unittest discover -s tests -v
```


## Dual Auto Analyzer: candidate discovery & Parameter Sweep Grid

Dual Auto Analyzer is the inverse workflow to Manual Monte Carlo:

- **Manual:** the trader supplies Entry, Stop Loss, and Take Profit; the engine evaluates that fixed plan.
- **Dual Auto:** the analyzer creates multiple BUY LIMIT and SELL LIMIT candidates from the chosen entry strategy, assigns each candidate an SL/TP using ATR risk, point limits, or locked Risk:Reward scenarios, evaluates candidates, and returns the highest-expectancy candidate on each side.

### 🎛️ Dynamic Candidate Grid (Parameter Sweep Fine-Tuning)
Untuk menemukan titik entri paling optimal di XAUUSD, Dual Auto Analyzer kini dilengkapi fitur **Candidate Grid**:
- **0 (Versi Asli / Baseline - Default):** Menjalankan jalur kode 100% baseline orisinal tanpa variasi tambahan (menjaga kompatibilitas dan identitas penuh versi lama).
- **5 Variasi (Cepat):** Menghasilkan hingga 5 variasi level entri adaptif di seputar zona strategi setelah filter & deduplikasi.
- **10 Variasi (Seimbang):** Menghasilkan hingga 10 variasi level entri bertingkat.
- **20 Variasi (Optimal Brute-Force):** Menghasilkan hingga 20 variasi mesh level entri presisi tinggi untuk fine-tuning maksimal.

*(Catatan: Jumlah entri yang dievaluasi merupakan batas atas unik yang lolos validasi spread broker & filter struktur pasar).*

Fitur ini bersinergi secara mulus dengan:
- **Pilihan Replays Cepat:** Mendukung pilihan `100`, `250`, `500`, `1,000`, `3,000`, `5,000`, dan `10,000` replays. Pengujian 20 variasi kombinasi entri dengan 100 replays dapat selesai dalam hitungan detik.
- **Mode Risk:Reward Terkunci:** Misalnya dengan target RR 1:5.0, setiap variasi entri yang dihasilkan grid tetap mengunci rasio 1:5.0 secara ketat, sementara Monte Carlo mencari level entri yang memiliki touch-adjusted simulated expectancy tertinggi.
- **Mode TP/SL Range Adaptif:** Kuota entri dibatasi secara dinamis ketika dikombinasikan dengan grid TP/SL Range agar total candidate plan tidak melebihi batas 200 plan per arah.

The scan evaluates candidate plans, using a capped replay count for coarse candidate ranking, then re-runs the selected winning BUY and SELL candidates at the requested full replay count. Ranking is based primarily on simulated average R (expectancy); TP-first probability and RR are displayed as supporting statistics.

**No-trade behavior:** if neither side has positive simulated average R, the analyzer reports `NO TRADE` instead of promoting the least-bad setup. If both sides have positive and similar expectancy, it reports `EQUAL`.

**Limit-order touch proxy:** candidate ranking now weights simulated average R by the historical frequency with which the same ATR-normalized limit distance was touched within the selected horizon. The GUI shows this as **Touch**, plus the median bars-to-touch and touch sample metadata in the analyzer result. This is an OHLC touch-rate proxy, not actual broker fill probability: queue priority, bid/ask execution, liquidity, gaps, and partial fills are not modeled. TP/SL probabilities remain conditional on entry fill and are not calibrated live probabilities. A chronological walk-forward test with realistic execution costs is still required.

Compare mode discovers candidates using Legacy V1 (the preserved baseline), then evaluates the same selected BUY and SELL plans with Enhanced V2. This isolates the engine comparison on the final plans; it does not establish out-of-sample predictive accuracy.


## Dual Auto Analyzer TP/SL controls

The GUI's Dual Auto Analyzer offers four TP/SL search modes:

- **Auto Optimize (default):** preserves the ATR/structure-derived TP and SL candidate grid.
- **Fixed TP/SL:** users specify fixed TP and SL distances in broker points; the analyzer continues searching entry prices independently for BUY LIMIT and SELL LIMIT.
- **TP/SL Range:** users define minimum, maximum, and step for TP and SL points. The analyzer tests the Cartesian grid of TP/SL combinations for each candidate entry.
- **Risk Reward:** users select or specify a target Risk:Reward ratio (e.g. 1:1.5, 1:2.0, 1:3.0, 1:5.0, 1:10.0) and custom Stop Loss points; the engine locks the exact ratio and discovers the highest-expectancy BUY LIMIT and SELL LIMIT entries.

**Point conversion:** one point is converted to price using point_size (the price value of one broker point). MT5 source data now includes symbol_info.point when available. For COMEX data or older cached MT5 files, verify or enter the correct point size manually; the UI's 0.01 starting value is only a convenience default, not a universal XAUUSD convention.

The range grid is limited to 20 TP/SL combinations and 200 total candidate plans per direction to bound scan time. Invalid ranges, non-positive values, and non-integral point inputs are rejected. Existing ATR/structure behavior remains the default.

Candidate ranking still uses touch-adjusted simulated average R. Historical OHLC touch frequency remains a proxy, not broker fill probability; simulated TP/SL outcomes are conditional on a filled limit entry.

---

## 💡 Roadmap & Implementasi Strategi Monte Carlo (Total 9 Strategi)

> **Prinsip Utama:** Strategi versi asli (**ATR Pullback & Swing Structure**) dijamin **100% tetap dipertahankan sebagai baseline default (tidak dibuang/diubah)**. Seluruh strategi dapat dipilih secara bebas via dropdown **Strategy Selector** di GUI scanner sehingga pengguna bebas memilih atau membandingkan hasil uji odds Monte Carlo antar strategi.

Berikut adalah daftar lengkap 9 strategi yang terintegrasi penuh dalam Dual Scanner:

### 1. ATR Pullback & Swing Structure *(Default / Versi Asli - Tetap Dipertahankan)*
- **Konsep:** Strategi baseline Jake Schincariol & Time Machine PRO. Menghitung level diskon/premium bertingkat ($0.25, 0.5, 0.75, 1.0 \times \text{ATR}$) serta level swing high/low 24 bar terakhir untuk menempatkan limit order BUY & SELL.
- **Karakter:** Mean-reversion intraday stabil dengan batasan volatilitas dinamis.

### 2. Breakout + Retest Point of Control (POC) / Volume Profile
- **Konsep:** Mendeteksi breakout struktur/range konsolidasi, menghitung distribusi Volume Profile (VPVR) menggunakan tick volume MT5, lalu menempatkan Limit Order tepat di level Point of Control (POC) atau Value Area (VAH/VAL) untuk menangkap retest.
- **Keunggulan Monte Carlo:** Mengukur apakah harga memiliki tendensi retest jemput POC sebelum melanjutkan ekspansi, serta menguji ketahanan SL di luar zona konsolidasi.

### 3. ICT / SMC: Liquidity Sweep + Fair Value Gap (FVG) Retest
- **Konsep:** Mendeteksi pembersihan likuiditas (false break/sweep swing high/low) yang diikuti pembentukan candle imbalance 3 bar (FVG). Memasang Limit Order di batas atau median (50% Consequent Encroachment) dari FVG.
- **Keunggulan Monte Carlo:** Mensimulasikan kekuatan tarikan area imbalance dalam menjemput order dan mengeksekusi probabilitas TP vs SL.

### 4. Session Open Range Breakout (ORB) / Sesi Asia – London – NY
- **Konsep:** Mengidentifikasi jam pembukaan sesi trading mayor (Asia 00:00, London 08:00, New York 13:00 UTC) dalam 1 hari terakhir, lalu menguji batas Open Range Breakout untuk entri retest.
- **Keunggulan Monte Carlo:** Memanfaatkan anomali lonjakan volatilitas jam buka pasar (*time-of-day seasonality*) untuk mengukur reliabilitas kelanjutan tren sesi.

### 5. Mean Reversion & Stat-Arb: Bollinger Bands Extremes + Z-Score
- **Konsep:** Menghitung Z-score atau deviasi harga terhadap Bollinger Bands ($\pm 2.0$ sigma). Memasang Limit Order saat pasar mengalami overbought/oversold ekstrem dengan target TP kembali ke mean (garis tengah).
- **Keunggulan Monte Carlo:** Sangat akurat dalam menguji seberapa sering ekor distribusi (*tail risk*) mengalami pembalikan kembali ke nilai rata-rata historis.

### 6. Accumulation + Inverse Fair Value Gap (IFVG)
- **Konsep:** Mengidentifikasi rentang konsolidasi akumulasi yang diikuti sweep likuiditas dan displacement agresif yang menembus FVG berlawanan (*Inverse FVG*). Menempatkan limit order pada retest area IFVG.
- **Keunggulan Monte Carlo:** Menguji ketahanan zona transisi likuiditas setelah terjadi pembalikan momentum kuat.

### 7. Liquidity Sweep + Market Structure Shift (SMS) + Order Block
- **Konsep:** Mendeteksi false breakout/sweep pada swing high/low signifikan, disusul pergeseran struktur tren pasar (*Shift in Market Structure* / SMS), lalu menempatkan limit order retest pada Order Block (OB) pemicu.
- **Keunggulan Monte Carlo:** Menguji probabilitas reaksi harga di zona mitigasi institusional (*Order Block*) setelah konfirmasi perubahan tren.

### 8. Liquidity Absorption + Volume Bubbles (Bookmap Proxy)
- **Konsep:** Mendeteksi penyerapan pesanan agresif pada level swing ekstrem yang ditandai lonjakan volume di atas $1.5\times$ rata-rata (*Volume Bubble*), disusul penutupan kembali (*reclaim*) ke dalam range.
- **Keunggulan Monte Carlo:** Mengukur efektivitas pantulan harga dari zona likuiditas yang baru saja menyerap pesanan besar.

### 9. Order Flow Footprint Proxy (Bid/Ask Delta & Wick Absorption)
- **Konsep:** Proxy jejak order flow yang mencari sweep level likuiditas disertai volume tinggi dan sumbu penolakan panjang (*rejection wick* $> 1.5\times$ badan candle). Memasang entri retest di level sweep atau kedalaman sumbu penolakan (*deep wick*).
- **Keunggulan Monte Carlo:** Memetakan probabilitas pembalikan harga saat pesanan agresif terbukti tertahan oleh likuiditas pasif.

---

### Arsitektur Modul Terpadu:
- Tiap strategi diimplementasikan sebagai generator kandidat independen (`_candidate_entries_atr_swing`, `_candidate_entries_poc`, `_candidate_entries_fvg`, dll.).
- Seluruh kandidat dievaluasi oleh mesin inti Monte Carlo yang sama sehingga hasil scoring, touch probability, dan expected R dapat dibandingkan secara objektif (*apple-to-apple*).


