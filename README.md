# Tugas Besar - Sistem Cerdas

Proyek ini terdiri dari 2 use case: **Ingestion (ETL)** dan **Golden Cross Detection (Modelling)**.

## Struktur Proyek

```
.
├── ingestion/
│   └── ingestion.ipynb                  # Use Case 1: Scraping IDX → Database
├── modeling/
│   ├── golden_cross_modeling.ipynb      # Use Case 2: Modelling Golden Cross
│   └── transaksi_harian_202605251947.csv # Dataset transaksi harian IDX
└── README.md
```

---

## Persyaratan

### 1. Instalasi Python

Pastikan Python 3.9+ sudah terinstall. Cek dengan:

```bash
python --version
```

### 2. Install Library

```bash
pip install pandas numpy matplotlib scikit-learn curl_cffi sqlalchemy cloudscraper
```

Atau install dari file requirements (jika disediakan):

```bash
pip install -r requirements.txt
```

### 3. Jalankan di Google Colab (Rekomendasi)

1. Upload folder `ingestion/` dan `modeling/` ke Google Drive
2. Buka file `.ipynb` di Google Colab
3. Jalankan setiap cell secara berurutan dari atas ke bawah

### 4. Jalankan di Jupyter Notebook (Lokal)

```bash
# Aktifkan virtual environment (opsional)
python -m venv venv
source venv/bin/activate      # Linux/Mac
venv\Scripts\activate          # Windows

# Install library
pip install pandas numpy matplotlib scikit-learn curl_cffi sqlalchemy cloudscraper

# Jalankan Jupyter
jupyter notebook

# Buka file notebook:
# - ingestion/ingestion.ipynb
# - modeling/golden_cross_modeling.ipynb
```

---

## Use Case 1: Ingestion (ETL Pipeline)

### Tujuan
Mengambil (scraping) data ringkasan perdagangan saham dari website IDX dan menyimpannya ke database SQLite.

### Flow Eksekusi
```
Extract → Transform → Load
   ↓         ↓         ↓
 IDX API   Clean    SQLite DB
```

1. **Extract** — Mengambil data dari API IDX (`https://www.idx.co.id/primary/TradingSummary/GetStockSummary?length=9999&start=0`) menggunakan `curl_cffi` (bypass Cloudflare). Jika gagal, fallback ke `cloudscraper` dengan retry 3x.
2. **Transform** — Pembersihan data: konversi kolom numerik, hapus baris kosong, standardisasi string (strip, uppercase untuk kode saham).
3. **Load** — Simpan ke database SQLite menggunakan SQLAlchemy ORM. Jika data tanggal tersebut sudah ada, hapus dulu lalu insert ulang (idempotent).

### Langkah Menjalankan

1. Buka `ingestion/ingestion.ipynb`
2. Jalankan **Cell 1** — Install library: `!pip install curl_cffi pandas sqlalchemy`
3. Jalankan **Cell 2** — Import library
4. Jalankan **Cell 3** — Konfigurasi (URL API, path database)
5. Jalankan **Cell 4** — Definisi model database (SQLAlchemy ORM)
6. Jalankan **Cell 5** — **Extract**: Scraping data dari IDX API. Jika muncul error 403, program akan otomatis retry dan fallback ke metode alternatif
7. Jalankan **Cell 6** — **Transform**: Pembersihan data (lihat output DataFrame)
8. Jalankan **Cell 7** — **Load**: Simpan ke SQLite database
9. Jalankan **Cell 8** — Verifikasi: Query data dari database
10. Jalankan **Cell 9** — Statistik deskriptif
11. Jalankan **Cell 10** — Ekspor ke CSV (opsional)

### Output yang Diharapkan

| Cell | Output |
|------|--------|
| Cell 5 (Extract) | `[EXTRACT] Berhasil mengambil 959 record (total: 959)` |
| Cell 7 (Load) | `[LOAD] Berhasil menyimpan 959 record.` |
| Cell 9 (CSV) | File `idx_stock_summary.csv` |

### Tabel Database (`stock_summary`)

| Kolom | Tipe | Deskripsi |
|-------|------|-----------|
| `id` | Integer | Primary key (auto-increment) |
| `date` | String | Tanggal perdagangan |
| `stock_code` | String | Kode saham (misal: AADI, BBCA) |
| `stock_name` | String | Nama emiten |
| `open_price` | Float | Harga pembukaan |
| `high` | Float | Harga tertinggi |
| `low` | Float | Harga terendah |
| `close` | Float | Harga penutupan |
| `volume` | Float | Volume perdagangan |
| `value` | Float | Nilai transaksi |
| `frequency` | Float | Frekuensi transaksi |
| `foreign_buy` | Float | Pembelian asing |
| `foreign_sell` | Float | Penjualan asing |
| ... | ... | Dan kolom lainnya |

---

## Use Case 2: Golden Cross Detection (Modelling)

### Konsep Golden Cross

**Golden Cross** adalah pola teknikal di mana **SMA-50 menyilang di atas SMA-200**, mengindikasikan potensi tren **bullish** (naik). Kebalikannya, **Death Cross** (SMA-50 di bawah SMA-200) mengindikasikan tren **bearish** (turun).

Pada data cross-sectional (570 saham dalam 1 hari), konsep Golden Cross diadaptasi menjadi **klasifikasi sinyal pasar**:

| Kelas | Kondisi | Interpretasi |
|-------|---------|---------------|
| **BULLISH (+1)** | `changes_pct > 1%` | Sinyal Golden Cross — potensi naik |
| **NEUTRAL (0)** | `-1% ≤ changes_pct ≤ 1%` | Tidak ada sinyal jelas |
| **BEARISH (-1)** | `changes_pct < -1%` | Sinyal Death Cross — potensi turun |

### Flow Eksekusi
```
Data CSV
    ↓
Preprocessing (handle nilai 0, NaN)
    ↓
Feature Engineering (15 fitur)
    ↓
Target Labeling (BULLISH / NEUTRAL / BEARISH)
    ↓
Train/Test Split (80/20, stratified)
    ↓
Training 6 Algoritma ML
    ↓
Evaluation & Best Model Selection
    ↓
Save Model → Prediction
```

### Langkah Menjalankan

1. Pastikan file `transaksi_harian_202605251947.csv` berada di folder yang sama dengan notebook
2. Buka `modeling/golden_cross_modeling.ipynb`
3. Jalankan **Cell 1** — Install library: `!pip install pandas numpy matplotlib scikit-learn`
4. Jalankan **Cell 2** — Import library
5. Jalankan **Cell 3** — Konfigurasi (threshold, test size, path CSV). **Ubah `CSV_PATH` jika nama file CSV berbeda**
6. Jalankan **Cell 4** — Load data CSV (otomatis deteksi separator `;`)
7. Jalankan **Cell 5** — Statistik deskriptif
8. Jalankan **Cell 6** — Preprocessing: handle `open_price=0`, `range_intraday_pct` NaN, hapus `volume=0`
9. Jalankan **Cell 7** — Target labeling: BULLISH/NEUTRAL/BEARISH berdasarkan `changes_pct`
10. Jalankan **Cell 8** — Visualisasi distribusi target
11. Jalankan **Cell 9** — EDA (Exploratory Data Analysis)
12. Jalankan **Cell 10** — Feature engineering (15 fitur derivatif)
13. Jalankan **Cell 11** — Persiapan fitur & split data
14. Jalankan **Cell 12** — Train/test split
15. Jalankan **Cell 13** — Training 6 model ML (±1-5 menit)
16. Jalankan **Cell 14** — Evaluasi detail best model
17. Jalankan **Cell 15** — Visualisasi hasil (4 plot)
18. Jalankan **Cell 16** — Ringkasan perbandingan model
19. Jalankan **Cell 17** — Simpan model ke `golden_cross_model.pkl`
20. Jalankan **Cell 18** — Prediksi dengan model (menampilkan Top 10 BULLISH & BEARISH)

### Output yang Diharapkan

| Cell | Output |
|------|--------|
| Cell 4 | Data dimuat: 570 baris, 19 kolom |
| Cell 6 | Data setelah preprocessing: ~451 baris (setelah hapus volume=0) |
| Cell 7 | Distribusi target: BULLISH ~47%, NEUTRAL ~33%, BEARISH ~20% |
| Cell 13 | Hasil training 6 model (accuracy, precision, recall, F1, CV) |
| Cell 17 | Model disimpan ke `golden_cross_model.pkl` |
| Cell 18 | Top 10 BULLISH & Top 10 BEARISH saham |

### Feature Engineering (15 Fitur)

| No | Fitur | Deskripsi | Relevansi Golden Cross |
|----|-------|-----------|------------------------|
| 1 | `gap_pct` | Gap pembukaan dari previous close | Sinyal pembukaan market |
| 2 | `close_position` | Posisi close relatif thd high-low | Kekuatan buyer vs seller |
| 3 | `body_pct` | Body candle / prev_price | Besar pergerakan |
| 4 | `is_bullish_candle` | Close > Open (1/0) | Arah candle |
| 5 | `upper_shadow_pct` | Shadow atas candle | Tekanan jual |
| 6 | `lower_shadow_pct` | Shadow bawah candle | Tekanan beli |
| 7 | `high_low_range_pct` | Range harga intraday | Volatilitas |
| 8 | `volume_per_freq` | Volume / frekuensi | Likuiditas per transaksi |
| 9 | `tx_value_log` | Log nilai transaksi | Skala transaksi |
| 10 | `bid_offer_ratio` | Bid volume / offer volume | Tekanan beli vs jual |
| 11 | `price_spread_pct` | Spread bid-offer | Likuiditas pasar |
| 12 | `high_changes_abs` | Perubahan high dari prev | Jangkauan atas |
| 13 | `low_changes_abs` | Perubahan low dari prev | Jangkauan bawah |
| 14 | `gap_up_pct` | Gap up dari prev close | Sentimen pembukaan |
| 15 | `range_intraday_pct` | Range intraday % | Volatilitas keseluruhan |

### Algoritma yang Digunakan

| No | Algoritma | Deskripsi | Kelebihan |
|----|-----------|-----------|-----------|
| 1 | **Random Forest** | Ensemble decision tree dengan bagging | Robust, anti-overfitting, feature importance |
| 2 | **Gradient Boosting** | Ensemble sequential, fokus error sebelumnya | Akurasi tinggi |
| 3 | **SVM (RBF)** | Support Vector Machine kernel RBF | Efektif untuk boundary non-linear |
| 4 | **KNN (k=5)** | K-Nearest Neighbors | Sederhana, interpretable |
| 5 | **Decision Tree** | Pohon keputusan tunggal | Interpretable, cepat |
| 6 | **MLP Neural Net** | Multi-Layer Perceptron (64,32) | Menangkap pola kompleks |

### Hasil Evaluasi

| Model | Test Accuracy | CV Accuracy |
|-------|--------------|-------------|
| **MLP Neural Net** | **93.69%** | **92.05%** |
| Gradient Boosting | 91.89% | 92.27% |
| Random Forest | 90.99% | 90.23% |
| Decision Tree | 90.99% | 90.68% |
| SVM (RBF) | 81.08% | 83.86% |
| KNN (k=5) | 72.97% | 77.73% |

> **Best Model: MLP Neural Net** dengan accuracy 93.69% dan CV accuracy 92.05%

### Library yang Digunakan
| Library | Fungsi |
|---------|--------|
| `pandas` | Manipulasi data |
| `numpy` | Operasi numerik |
| `matplotlib` | Visualisasi (plot, chart) |
| `scikit-learn` | Machine learning (6 algoritma klasifikasi, evaluasi, preprocessing) |
| `pickle` | Serialisasi model |

---

## Penjelasan Untuk Presentasi

### Use Case 1 — Ingestion (Bagian yang Perlu Dijelaskan)

1. **Mengapa menggunakan `curl_cffi` bukan `requests`?**
   - Website IDX dilindungi Cloudflare yang memblokir request dari bot/scraper biasa. `curl_cffi` mengimitasi TLS handshake browser Chrome asli sehingga bisa bypass proteksi tersebut.

2. **Apa itu ETL Pipeline?**
   - **Extract**: Mengambil data mentah dari sumber (IDX API)
   - **Transform**: Membersihkan dan menstandarkan format data
   - **Load**: Menyimpan data yang bersih ke database

3. **Mengapa SQLAlchemy ORM?**
   - ORM memungkinkan kita mendefinisikan tabel database sebagai class Python, sehingga kode lebih terstruktur dan mudah di-maintain dibanding raw SQL.

4. **Apa arti "idempotent"?**
   - Jika data tanggal tersebut sudah ada di database, program akan menghapus data lama lalu insert ulang (tidak ada duplikasi).

5. **Data apa yang diambil dari IDX API?**
   - Stock Summary: kode saham, nama emiten, harga (open/high/low/close), volume, value, frequency, foreign buy/sell, bid/offer, dll. Sekitar 959 saham per hari.

6. **Kenapa perdua metode scraping (curl_cffi + cloudscraper)?**
   - `curl_cffi` lebih andal tapi kadang tidak terinstall di Colab. `cloudscraper` sebagai fallback memastikan program tetap berjalan jika salah satu gagal.

---

### Use Case 2 — Golden Cross Modelling (Bagian yang Perlu Dijelaskan)

1. **Apa itu Golden Cross dan Death Cross?**
   - **Golden Cross**: SMA-50 menyilang di atas SMA-200 → sinyal **bullish** (waktu beli)
   - **Death Cross**: SMA-50 menyilang di bawah SMA-200 → sinyal **bearish** (waktu jual)

2. **Kenapa data cross-sectional, bukan time-series?**
   - Data yang diberikan berisi 570 saham dalam 1 hari (snapshot), bukan 1 saham dalam 250+ hari. Sehingga kita tidak bisa menghitung SMA-50/200 per saham. Adaptasi: kita menggunakan **fitur teknikal intraday** untuk memprediksi kelas sinyal (BULLISH/NEUTRAL/BEARISH).

3. **Mengapa 3 kelas (bukan 2)?**
   - Tidak semua saham punya tren jelas. Kelas NEUTRAL menampung saham yang perubahannya kecil (-1% s/d +1%), sehingga model fokus membedakan sinyal kuat (bullish/bearish).

4. **Bagaimana cara kerja setiap algoritma?**
   - **Random Forest**: Membuat 100 pohon keputusan dari subset data acak, lalu voting mayoritas. Anti-overfitting.
   - **Gradient Boosting**: Membuat pohon secara berurutan, setiap pohon baru memperbaiki error pohon sebelumnya.
   - **SVM (RBF)**: Mencari hyperplane pemisah terbaik menggunakan kernel RBF untuk data non-linear.
   - **KNN**: Mengklasifikasikan data berdasarkan 5 tetangga terdekat di ruang fitur.
   - **Decision Tree**: Membuat pohon keputusan berdasarkan fitur yang paling informatif (information gain).
   - **MLP Neural Net**: Jaringan saraf tiruan dengan 2 hidden layer (64 dan 32 neuron) yang belajar pola non-linear.

5. **Mengapa MLP Neural Net akurasinya paling tinggi?**
   - MLP mampu menangkap hubungan non-linear antar fitur yang kompleks (misalnya: bid_offer_ratio yang tinggi + gap_up + candle bullish → sinyal BULLISH).

6. **Apa itu Feature Importance?**
   - Metode untuk mengetahui fitur mana yang paling berpengaruh dalam keputusan model. Pada Random Forest/Gradient Boosting, fitur dengan importance tinggi berarti fitur tersebut paling sering digunakan untuk splitting.

7. **Bagaimana preprocessing menangani data kotor?**
   - `open_price=0`: Diisi dengan `prev_price` (saham tidak diperdagangkan di sesi pembukaan)
   - `range_intraday_pct NaN`: Diisi dengan 0 (saham tanpa pergerakan intraday)
   - `volume=0`: Baris dihapus (saham tidak diperdagangkan sama sekali, tidak relevan untuk analisis)
   - Setelah preprocessing: 570 → ~451 baris

8. **Apa arti threshold +1% dan -1%?**
   - Threshold menentukan batas kelas. Saham yang naik >1% dikategorikan BULLISH (sinyal beli), yang turun <-1% dikategorikan BEARISH (sinyal jual), dan sisanya NEUTRAL.

---

## Troubleshooting

| Masalah | Solusi |
|---------|--------|
| `[EXTRACT] HTTP Status: 403` | IDX API memblokir request. Program otomatis retry dengan fallback ke `cloudscraper`. Jika tetap gagal, coba jalankan ulang setelah beberapa menit. |
| `ModuleNotFoundError: No module named 'curl_cffi'` | Jalankan `!pip install curl_cffi` di cell pertama notebook |
| `FileNotFoundError: transaksi_harian_...csv` | Pastikan file CSV berada di folder yang sama dengan notebook, atau ubah `CSV_PATH` di Cell 3 |
| `ValueError: Cannot use stratify with only 1 sample` | Data terlalu sedikit untuk stratifikasi. Kurangi jumlah kelas atau tambah data |
| Plot tidak muncul di Jupyter | Tambahkan `%matplotlib inline` di awal notebook |

---

## Requirements

```
pandas>=2.0
numpy>=1.24
matplotlib>=3.7
scikit-learn>=1.3
curl_cffi>=0.5
cloudscraper>=1.2
sqlalchemy>=2.0
```

Install semua sekaligus:
```bash
pip install pandas numpy matplotlib scikit-learn curl_cffi cloudscraper sqlalchemy
```