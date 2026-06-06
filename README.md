# Tugas Besar — Sistem Cerdas

Proyek ini terdiri dari **2 use case** + **CI/CD pipeline otomatis**:

| # | Use Case | Deskripsi |
|---|----------|-----------|
| 1 | **Ingestion (ETL)** | Scraping data ringkasan saham IDX → database |
| 2 | **Golden Cross Modelling** | Klasifikasi sinyal pasar (BULLISH/NEUTRAL/BEARISH) |

---

## Arsitektur Otomatisasi

```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│   GitHub Actions (cloud) — GRATIS, laptop TIDAK USAH NYALA│
│   │                                                      │
│   ├─ CRON: Senin—Jumat, 17:30 WIB                        │
│   │                                                      │
│   ├─ ① ScraperAPI (proxy residensial)                    │
│   │     └─ bypass Cloudflare IDX → 200 OK                │
│   │                                                      │
│   ├─ ② Extract JSON — Transform (Pandas)                 │
│   │                                                      │
│   └─ ③ Load ke Supabase PostgreSQL (cloud)               │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

| Komponen | Peran | Biaya |
|----------|-------|-------|
| **GitHub Actions** | Menjalankan pipeline setiap hari bursa | Gratis (public repo) |
| **ScraperAPI** | Proxy residensial bypass Cloudflare IDX | Gratis 1000 req/bulan (~22 terpakai) |
| **Supabase** | Database PostgreSQL di cloud | Gratis 500 MB |

---

## Struktur Proyek

```
.
├── .github/
│   └── workflows/
│       └── ingestion.yml                # CI/CD cron job
├── ingestion/
│   ├── ingestion.ipynb                  # Notebook ETL + penjelasan detail
│   ├── ingestion_pipeline.py            # Script production (standalone)
│   ├── idx_stock.db                     # SQLite output (local dev)
│   └── idx_stock_summary.csv            # CSV output (local dev)
├── modeling/
│   ├── golden_cross_modeling.ipynb      # Notebook ML classification
│   ├── golden_cross_model.pkl           # Best model (MLP Neural Net)
│   ├── golden_cross_results.png         # Visualisasi hasil
│   └── transaksi_harian_202605251947.csv # Dataset
├── .gitignore
├── requirements.txt                     # Dependensi Python
└── README.md
```

---

## Setup Awal (Sekali Saja — ~15 menit)

### Step 1 — Daftar ScraperAPI (gratis)

1. Buka https://scraperapi.com → **Sign Up Free**
2. Isi email + password. **Tidak perlu kartu kredit**
3. Setelah login, copy **API Key** dari dashboard (format: `a1b2c3d4...`)

### Step 2 — Daftar Supabase (gratis)

1. Buka https://supabase.com → **Sign in with GitHub**
2. Klik **New project**
3. Isi: nama = `idx-ingestion`, database password = (generate random)
4. Region pilih **Singapore** (paling dekat ke Indonesia)
5. Tunggu ~2 menit sampai database siap
6. Buka **Settings → Database → Connection string** → pilih tab **URI**
7. Copy connection string format:
   ```
   postgresql://postgres:[PASSWORD]@db.xxxxx.supabase.co:6543/postgres
   ```
8. Di dashboard yang sama, klik **Connection Pooling** → copy string dengan **port 6543**:
   ```
   postgresql://postgres.[PROJECT_REF]:[PASSWORD]@aws-1-ap-southeast-2.pooler.supabase.com:6543/postgres
   ```
   (gunakan yang ini untuk GitHub Actions — connection pooler, lebih stabil)

### Step 3 — Simpan Secrets ke GitHub

1. Buka https://github.com/adiityaastr/tugas-sistem-cerdas/settings/secrets/actions
2. Klik **New repository secret** — buat **2 secret**:

| Name | Value |
|------|-------|
| `SCRAPER_API_KEY` | API Key dari ScraperAPI dashboard |
| `SUPABASE_DB_URL` | Connection string pooler Supabase (port 6543) |

> **Tabel tidak perlu dibuat manual** — ORM SQLAlchemy akan otomatis `CREATE TABLE IF NOT EXISTS` saat pipeline pertama berjalan.

### Step 4 — Verifikasi

1. Buka tab **Actions** di repo GitHub
2. Klik **IDX Daily Ingestion** → **Run workflow** → **Run workflow**
3. Tunggu ~2 menit. Kalau sukses:
   ```
   [EXTRACT] BERHASIL via ScraperAPI
   [LOAD] Tersimpan: 959 record
   ```
4. Cek data di Supabase Dashboard → **Table Editor** → tabel `stock_summary`

---

## Menjalankan Secara Manual (Local Development)

### Prasyarat

- Python 3.9+ (`python --version`)
- Git terinstall

### Instalasi

```powershell
# Clone repo
git clone https://github.com/adiityaastr/tugas-sistem-cerdas.git
cd "tugas_besar_sistem cerdas"

# Buat virtual environment
python -m venv .venv
.venv\Scripts\activate    # Windows
# source .venv/bin/activate   # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### Jalankan Notebook Ingestion

```powershell
jupyter notebook ingestion/ingestion.ipynb
```

Lalu **Kernel → Restart & Run All**. Notebook akan:

1. Install library yang dibutuhkan (cell 1)
2. Import semua dependensi (cell 2)
3. Konfigurasi — auto-detect Supabase vs SQLite (cell 3)
   - Jika env var `SUPABASE_DB_URL` diset → konek ke Supabase
   - Jika tidak → fallback ke SQLite lokal
4. Buat tabel database via ORM (cell 4)
5. Extract dari IDX via ScraperAPI → curl_cffi → cloudscraper → requests (cell 5)
6. Transform & bersihkan data (cell 6-7)
7. Load ke database (cell 8)
8. Verifikasi + export CSV (cell 9-11)

> **Catatan**: Saat dijalankan lokal, metode scraping langsung ke IDX (curl_cffi) biasanya berhasil karena IP kamu residensial. ScraperAPI akan dilewati kalau env var tidak diset.

---

## Use Case 1: Ingestion (ETL Pipeline) — Detail

### Tujuan

Mengambil data ringkasan perdagangan saham harian dari IDX dan menyimpannya ke database.

### Data yang Diambil

| Kategori | Kolom | Jumlah |
|----------|-------|--------|
| Identitas | stock_code, stock_name, date | 3 |
| Harga | previous, open_price, high, low, close, change, first_trade | 7 |
| Volume & Nilai | volume, value, frequency, index_individual | 4 |
| Bid & Offer | offer, offer_volume, bid, bid_volume | 4 |
| Saham Beredar | listed_shares, tradeble_shares, weight_for_index | 3 |
| Asing | foreign_sell, foreign_buy | 2 |
| Lain-lain | remarks, delisting_date, non_regular_* | 6 |
| **Total** | | **29 kolom, ~959 saham/hari** |

### Strategi Extract (4 Lapis)

```
┌─────────────────────────────────────────────┐
│ Metode 0: ScraperAPI (proxy residensial)     │ ← Production (GitHub Actions)
│     │  ↓ gagal                              │
│ Metode 1: curl_cffi (chrome/edge/safari/firefox)│ ← Local (IP rumahan lolos)
│     │  ↓ gagal                              │
│ Metode 2: cloudscraper (JS solver, 4x retry)│
│     │  ↓ gagal                              │
│ Metode 3: requests standar                  │
│     │  ↓ gagal                              │
│ Workflow FAILED                             │
└─────────────────────────────────────────────┘
```

### Database Schema

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| `id` | `Integer` | Primary key autoincrement |
| `date` | `String` | Tanggal perdagangan (YYYY-MM-DD) — ada index |
| `stock_code` | `String` | Kode saham — ada index untuk query cepat |
| `stock_name` | `String` | Nama emiten |
| `previous` | `Float` | Harga penutupan kemarin |
| `open_price` | `Float` | Harga pembukaan |
| `high` | `Float` | Harga tertinggi |
| `low` | `Float` | Harga terendah |
| `close` | `Float` | Harga penutupan |
| `change` | `Float` | Perubahan (close — previous) |
| `volume` | `Float` | Volume perdagangan |
| `value` | `Float` | Nilai transaksi (Rp) |
| `frequency` | `Float` | Frekuensi transaksi |
| `foreign_buy` | `Float` | Volume pembelian asing |
| `foreign_sell` | `Float` | Volume penjualan asing |
| `offer` / `bid` | `Float` | Harga offer & bid terbaik |
| ... | `Float` | 14 kolom lainnya |

### Idempotent Load

Setiap kali pipeline jalan, data dengan tanggal yang sama **dihapus dulu** lalu di-insert ulang. Tidak akan ada duplikat, berapa kali pun dijalankan.

---

## Use Case 2: Golden Cross Detection (Modelling)

### Konsep

**Golden Cross** (SMA-50 > SMA-200) → sinyal **bullish** (beli).
**Death Cross** (SMA-50 < SMA-200) → sinyal **bearish** (jual).

Karena data berbentuk cross-sectional (570 saham dalam 1 hari), konsep ini diadaptasi menjadi **klasifikasi 3 kelas**:

| Kelas | Kondisi | Interpretasi |
|-------|---------|---------------|
| **BULLISH** | `changes_pct > +1%` | Sinyal Golden Cross |
| **NEUTRAL** | `-1% ≤ changes_pct ≤ +1%` | Tidak ada sinyal jelas |
| **BEARISH** | `changes_pct < -1%` | Sinyal Death Cross |

### Flow

```
Data CSV (570 saham)
  → Preprocessing (handle NaN, volume=0, open_price=0)
  → Feature Engineering (15 fitur teknikal intraday)
  → Target Labeling (BULLISH / NEUTRAL / BEARISH)
  → Train/Test Split (80/20, stratified)
  → Training 6 Algoritma ML
  → Evaluation → Best Model (MLP Neural Net)
  → Save Model → Predict Top 10 BULLISH & BEARISH
```

### 15 Fitur yang Digunakan

| No | Fitur | Deskripsi |
|----|-------|-----------|
| 1 | `gap_pct` | Gap pembukaan dari previous close |
| 2 | `close_position` | Posisi close relatif thd high-low |
| 3 | `body_pct` | Body candle / prev_price |
| 4 | `is_bullish_candle` | Close > Open (1/0) |
| 5 | `upper_shadow_pct` | Shadow atas candle |
| 6 | `lower_shadow_pct` | Shadow bawah candle |
| 7 | `high_low_range_pct` | Range harga intraday |
| 8 | `volume_per_freq` | Volume / frekuensi |
| 9 | `tx_value_log` | Log nilai transaksi |
| 10 | `bid_offer_ratio` | Bid volume / offer volume |
| 11 | `price_spread_pct` | Spread bid-offer |
| 12 | `high_changes_abs` | Perubahan high dari prev |
| 13 | `low_changes_abs` | Perubahan low dari prev |
| 14 | `gap_up_pct` | Gap up dari prev close |
| 15 | `range_intraday_pct` | Range intraday % |

### Hasil Model (Urut Accuracy)

| Rank | Model | Test Accuracy | CV Accuracy |
|------|-------|:---:|:---:|
| **1** | **MLP Neural Net** | **93.69%** | **92.05%** |
| 2 | Gradient Boosting | 91.89% | 92.27% |
| 3 | Random Forest | 90.99% | 90.23% |
| 4 | Decision Tree | 90.99% | 90.68% |
| 5 | SVM (RBF) | 81.08% | 83.86% |
| 6 | KNN (k=5) | 72.97% | 77.73% |

---

## CI/CD Pipeline — Detail Teknis

### Trigger

| Trigger | Jadwal |
|---------|--------|
| **Cron** | Setiap Senin—Jumat, 17:30 WIB (10:30 UTC) |
| **Manual** | Tab Actions → Run workflow |

### Runtime

| | Detail |
|---|--------|
| **OS** | Ubuntu 22.04 (GitHub Actions runner) |
| **Python** | 3.11 |
| **Durasi** | ~90 detik |
| **Execute** | `jupyter nbconvert --to notebook --execute --inplace ingestion/ingestion.ipynb` |

### Secrets yang Dibutuhkan

| Secret | Sumber | Dipakai di |
|--------|--------|------------|
| `SUPABASE_DB_URL` | Supabase dashboard | Koneksi database |
| `SCRAPER_API_KEY` | ScraperAPI dashboard | Proxy bypass Cloudflare |

### Data Retention

| Komponen | Batas | Utilisasi per-bulan |
|----------|-------|---------------------|
| ScraperAPI | 1.000 request | ~22 request (2%) |
| Supabase storage | 500 MB | ~11 MB (2%) |
| GitHub Actions (public) | Unlimited | ~45 menit |

---

## Troubleshooting

| Masalah | Penyebab | Solusi |
|---------|----------|--------|
| Workflow gagal: `HTTP 403` semua metode | IDX blokir IP datacenter | Pastikan `SCRAPER_API_KEY` sudah diset di GitHub Secrets. Cek dashboard ScraperAPI — jangan sampai kehabisan kuota |
| Workflow gagal: `could not connect to server` | Supabase connection string salah | Cek `SUPABASE_DB_URL` di Secrets — pastikan pakai port **6543** (pooler), bukan 5432 |
| Workflow gagal: `SCRAPER_API_KEY tidak diset` | Secret belum ditambahkan | Buka Settings → Secrets → Actions → tambahkan secret |
| Local notebook: `unable to open database file` | Path SQLite salah | Jangan lompat cell. Jalankan **Kernel → Restart & Run All**. Notebook harus dijalankan dari folder `ingestion/` |
| Local notebook: `NameError: name 'IDX_API_URL' is not defined` | Cell konfigurasi belum dijalankan | Jalankan cell dari atas ke bawah. Jangan skip cell 3 |
| Data di Supabase kosong | Tabel belum dibuat | Tabel auto-create saat pipeline pertama jalan. Atau jalankan manual di notebook cell 4 |
| Supabase "too many connections" | Connection pool habis | Pastikan pakai port 6543 (PgBouncer pooler), bukan 5432 |

---

## Teknologi & Library

| Library | Versi | Fungsi |
|---------|-------|--------|
| `pandas` | ≥ 2.0 | Manipulasi DataFrame |
| `numpy` | ≥ 1.24 | Operasi numerik |
| `matplotlib` | ≥ 3.7 | Visualisasi |
| `scikit-learn` | ≥ 1.3 | 6 algoritma ML + evaluasi |
| `curl_cffi` | ≥ 0.5 | TLS fingerprint impersonation |
| `cloudscraper` | ≥ 1.2 | Cloudflare JS solver |
| `sqlalchemy` | ≥ 2.0 | ORM database |
| `psycopg2-binary` | ≥ 2.9 | PostgreSQL driver |
| `requests` | built-in | HTTP client (ScraperAPI) |

### Install

```bash
pip install -r requirements.txt
```

---

## Catatan Keamanan

- **Jangan commit credential** — semua key & password disimpan di GitHub Secrets, bukan di kode
- **ScraperAPI key** — terbatas 1000 req/bulan gratis. Jangan share ke orang lain
- **Supabase password** — jika terekspos, reset via Supabase Dashboard → Settings → Database → Reset password, lalu update GitHub Secret
- **Rotate password berkala** — direkomendasikan setiap 3 bulan
