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

### Library yang Digunakan
| Library | Fungsi |
|---------|--------|
| `curl_cffi` | HTTP request dengan TLS fingerprint impersonation (bypass Cloudflare) |
| `cloudscraper` | Fallback scraper jika curl_cffi gagal |
| `pandas` | Manipulasi dan transformasi data |
| `sqlalchemy` | ORM dan koneksi ke database SQLite |

### Cara Menjalankan
1. Buka `ingestion/ingestion.ipynb` di Jupyter Notebook / Google Colab
2. Jalankan setiap cell secara berurutan
3. Hasil: file `idx_stock.db` (database SQLite) dengan tabel `stock_summary` berisi ~959 record

### Output
Database SQLite (`idx_stock.db`) dengan tabel `stock_summary` yang memiliki kolom:

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
| 12 | `high_changes_abs` | |Perubahan high dari prev| Jangkauan atas |
| 13 | `low_changes_abs` | |Perubahan low dari prev| Jangkauan bawah |
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

| Model | Accuracy | Precision | Recall | F1-Score | CV Accuracy |
|-------|----------|-----------|--------|----------|-------------|
| MLP Neural Net | 93.69% | - | - | - | 92.05% |
| Gradient Boosting | 91.89% | - | - | - | 92.27% |
| Random Forest | 90.99% | - | - | - | 90.23% |
| Decision Tree | 90.99% | - | - | - | 90.68% |
| SVM (RBF) | 81.08% | - | - | - | 83.86% |
| KNN (k=5) | 72.97% | - | - | - | 77.73% |

> **Best Model: MLP Neural Net** dengan accuracy 93.69% dan CV accuracy 92.05%

### Library yang Digunakan
| Library | Fungsi |
|---------|--------|
| `pandas` | Manipulasi data |
| `numpy` | Operasi numerik |
| `matplotlib` | Visualisasi (plot, chart) |
| `scikit-learn` | Machine learning (6 algoritma klasifikasi, evaluasi, preprocessing) |
| `pickle` | Serialisasi model |

### Cara Menjalankan
1. Upload file `transaksi_harian_202605251947.csv` ke folder yang sama dengan notebook
2. Buka `modeling/golden_cross_modeling.ipynb` di Jupyter Notebook / Google Colab
3. Jalankan setiap cell secara berurutan
4. Output: model terbaik (`golden_cross_model.pkl`), visualisasi (`golden_cross_results.png`), dan prediction report

---

## Penjelasan Untuk Presentasi

### Use Case 1 — Ingestion (Bagian yang Perlu Dijelaskan)

**Pertanyaan yang mungkin ditanyakan:**

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

---

## Requirements

```
pandas
numpy
matplotlib
scikit-learn
curl_cffi
sqlalchemy
```

Install semua:
```bash
pip install pandas numpy matplotlib scikit-learn curl_cffi sqlalchemy
```