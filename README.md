# Tugas Besar — Sistem Cerdas

Proyek ini terdiri dari **1 use case** + **CI/CD pipeline otomatis**:

| # | Use Case | Deskripsi |
|---|----------|-----------|
| 1 | **Ingestion (ETL)** | Scraping data ringkasan saham IDX → database |

---

## Arsitektur Otomatisasi

```
┌──────────────────────────────────────────────────────────────────┐
│                    GITHUB ACTIONS (cloud)                        │
│                                                                  │
│  ┌──────────────────────────┐  ┌────────────────────────────┐   │
│  │ ingestion.yml            │  │ retry_failed.yml           │   │
│  │ ┌──────────────────────┐ │  │ ┌────────────────────────┐ │   │
│  │ │ Trigger:             │ │  │ │ Trigger:               │ │   │
│  │ │ • push main          │ │  │ │ • cron tiap 2 jam      │ │   │
│  │ │ • cron Mon-Fri 17:30 │ │  │ │ • workflow_dispatch    │ │   │
│  │ │ • workflow_dispatch  │ │  │ └───────────┬────────────┘ │   │
│  │ │   input: date (opt)  │ │  │             │              │   │
│  │ └──────────┬───────────┘ │  │             ▼              │   │
│  │            │              │  │  Query ingestion_log      │   │
│  │            ▼              │  │  Cari tanggal gagal       │   │
│  │   ingestion_pipeline.py   │  │  Jalankan ulang pipeline  │   │
│  │   Extract → Transform     │  │  per tanggal gagal        │   │
│  │   → Load → Log            │  └───────────────────────────┘   │
│  └──────────────────────────┘                                   │
│                                                                  │
│                    │                          ▲                  │
│                    ▼                          │                  │
│  ┌────────────────────────────────────────────┴─────────────┐   │
│  │              SUPABASE / SQLITE                           │   │
│  │  ┌──────────────┐  ┌──────────────┐                     │   │
│  │  │ stock_summary │  │ingestion_log │                     │   │
│  │  │ (data saham)  │  │(tracking     │                     │   │
│  │  │ 29 kolom      │  │ status/retry)│                     │   │
│  │  └──────────────┘  └──────────────┘                     │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### Dua Workflow, Dua Peran

| | `ingestion.yml` | `retry_failed.yml` |
|---|---|---|
| **Peran** | **Eksekutor** — scrape & simpan data | **Supervisor** — cek log & retry yang gagal |
| **Trigger** | Cron 1x/hari + push + manual | Cron tiap 2 jam + manual |
| **Yang dijalankan** | `ingestion_pipeline.py` langsung | Query `ingestion_log` → panggil `.py` per tanggal gagal |
| **Target** | 1 tanggal (hari ini / input manual) | n tanggal (hasil query `ingestion_log`) |
| **Tabel** | `stock_summary` | `ingestion_log` (baca) → `stock_summary` (via subprocess) |

### Timeline Ilustrasi

```
08:00 ─ cron ingestion berjalan
         → gagal (IP diblokir / timeout)
         → catat di ingestion_log: "2025-06-13 | failed | retry=1"

10:00 ─ cron retry_failed cek ingestion_log
         → "oh, 13 Juni gagal. Coba lagi."
         → panggil ingestion_pipeline.py untuk 2025-06-13
         → BERHASIL! Update log: "2025-06-13 | success"

12:00 ─ cron retry_failed cek log lagi
         → "tidak ada yang gagal" → selesai (no-op)
```

### State Machine — ingestion_log

```
PENDING ──► RUNNING ──┬──► SUCCESS     (selesai, tidak di-retry)
                       ├──► EMPTY       (max 3x retry, lalu EMPTY_FINAL)
                       └──► FAILED      (max 5x retry, lalu DEAD LETTER — butuh intervensi manual)
```

### Hari Libur & Data Kosong

**Contoh:** 16 Juni 2026 menunjukkan 0 records, bukan error.

**Alasan:** 16 Juni 2026 adalah **Hari Libur Nasional (Tanggal Merah)**, sehingga:
- IDX tutup → tidak ada trading
- API mengembalikan 0 records (normal)
- Pipeline mencatat status `empty` (bukan `failed`)
- Tidak perlu retry lebih lanjut

| Tanggal | Hari | Records | Status |
|---------|------|---------|--------|
| 2026-06-15 | Senin | 959 ✓ | Normal |
| **2026-06-16** | **Selasa** | **0** | **Hari Libur** |
| 2026-06-17 | Rabu | 959 ✓ | Normal |

**Cek status di Supabase:**
```sql
SELECT date, status, record_count, error_message
FROM ingestion_log
WHERE status = 'empty'
ORDER BY date DESC;
```

### OpenCode MCP Integration (Optional)

Jika menggunakan [OpenCode](https://opencode.ai), database bisa diakses langsung:

```bash
# 1. Configure MCP
# Tambahkan di ~/.config/opencode/opencode.json:
{
  "mcp": {
    "supabase": {
      "type": "remote",
      "url": "https://mcp.supabase.com/mcp?project_ref=YOUR_REF&read_only=true&features=database",
      "enabled": true
    }
  }
}

# 2. Authenticate
opencode mcp auth supabase

# 3. Verify
opencode mcp list
```

**Query langsung dari OpenCode:**
```sql
-- Cek ingestion status
SELECT date, status, record_count FROM ingestion_log ORDER BY date DESC LIMIT 5;

-- Cek data availability
SELECT COUNT(*), COUNT(DISTINCT date) FROM stock_summary;

-- Cek recent failures
SELECT * FROM ingestion_log WHERE status = 'failed' ORDER BY date DESC;
```

### Cara Backfill Tanggal Tertentu

```
GitHub Actions → "CD - Deploy to Supabase" → Run workflow
  │
  ├─ Isi field "date": 2025-01-15
  └─ Klik "Run workflow"
```

Pipeline akan mengirim parameter `date=2025-01-15` ke semua 4 metode scraping (ScraperAPI + curl_cffi + cloudscraper + requests). Jika IDX API mendukung parameter `date`, data historis akan diambil. Jika tidak, data yang diambil adalah data hari ini.

Status disimpan di `ingestion_log` — kamu bisa cek hasilnya di Supabase dashboard → Table Editor → `ingestion_log`.

### Cara Cek Status Ingestion

Buka **Supabase Dashboard → SQL Editor**, jalankan:

```sql
SELECT date, status, record_count, retry_count, extraction_method, error_message
FROM ingestion_log
ORDER BY date DESC;
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
│       ├── ci.yml                     # CI pipeline (PR validation)
│       ├── ingestion.yml              # CI/CD ingestion harian + backfill
│       └── retry_failed.yml           # Auto-retry tanggal gagal
├── ingestion/
│   ├── ingestion.ipynb                # Notebook ETL + penjelasan detail
│   ├── ingestion_pipeline.py          # Script production (standalone)
│   ├── idx_stock.db                   # SQLite output (local dev)
│   └── idx_stock_summary.csv          # CSV output (local dev)
├── scripts/
│   ├── backfill.py                    # Manual backfill tool
│   └── health_check.py               # Supabase health check
├── modeling/
│   ├── golden_cross_modeling.ipynb    # Notebook ML classification
│   ├── golden_cross_model.pkl         # Best model (MLP Neural Net)
│   ├── golden_cross_results.png       # Visualisasi hasil
│   └── transaksi_harian_202605251947.csv # Dataset
├── .gitignore
├── requirements.txt                   # Dependensi Python
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
2. Klik **CD - Deploy to Supabase** → **Run workflow** → **Run workflow**
3. Tunggu ~2 menit. Kalau sukses:
    ```
    [EXTRACT] BERHASIL via ScraperAPI
    [LOAD] Tersimpan: 959 record
    ```
4. Cek data di Supabase Dashboard → **Table Editor** → tabel `stock_summary`

### Step 5 — Health Check (Opsional)

Untuk verify Supabase connection dan data integrity:

```bash
python scripts/health_check.py
```

Output berhasil:
```
[OK] Connection successful
[OK] All required tables exist
[OK] Latest date: 2026-06-19, Total records: 959
[OVERALL] HEALTHY ✓
```

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

## CI/CD Pipeline — Detail Teknis

### Trigger

| Trigger | Jadwal |
|---------|--------|
| **Cron (ingestion)** | Setiap Senin—Jumat, 17:30 WIB (10:30 UTC) |
| **Cron (retry)** | Setiap Senin—Jumat, 08:00—18:00 WIB tiap 2 jam |
| **Manual ingestion** | Tab Actions → Run workflow → isi `date` (opsional, untuk backfill) |
| **Manual retry** | Tab Actions → Retry Failed Ingestion → Run workflow |

### Runtime

| | Detail |
|---|--------|
| **OS** | Ubuntu 22.04 (GitHub Actions runner) |
| **Python** | 3.11 |
| **Durasi** | ~90 detik |
| **Execute** | `python ingestion/ingestion_pipeline.py` |

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

## Manual Operations

### Backfill Data Untuk Tanggal Tertentu

#### Cara 1: GitHub Actions (Recommended)

1. Buka repo GitHub → **Actions** tab
2. Cari workflow **"Manual Backfill"** (atau buat jika belum ada)
3. Klik **"Run workflow"** → dropdown
4. Isi **Date** field dengan tanggal (YYYY-MM-DD), atau kosongkan untuk retry semua failed dates
5. Klik **"Run workflow"**
6. Monitor progress di job logs

#### Cara 2: Local Command

```powershell
# Single date
python scripts/backfill.py --date 2026-06-16

# Date range
python scripts/backfill.py --start 2026-06-10 --end 2026-06-20

# All failed dates
python scripts/backfill.py --all-failed

# Dry-run (preview only, tidak execute)
python scripts/backfill.py --date 2026-06-16 --dry-run
```

#### Output Contoh

```
================================================================================
BACKFILL PREVIEW
================================================================================

Will retry 1 date(s):

  2026-06-16 | status: empty | records:    0 | retries: 6 | Hari Libur (Tanggal Merah)

Proceed with backfill? (y/n): y

================================================================================
EXECUTING BACKFILL
================================================================================

[1/1] Retrying 2026-06-16...
[SUCCESS] 2026-06-16 completed

================================================================================
BACKFILL SUMMARY
================================================================================
Total:     1 date(s)
Success:   1 ✓
Failed:    0 ✗
================================================================================
```

### Health Check

Untuk verify Supabase connection dan data integrity:

```powershell
python scripts/health_check.py
```

Output:
```
================================================================================
SUPABASE HEALTH CHECK
================================================================================

[CHECK] Database connection...
  [OK] Connection successful

[CHECK] Database tables...
  [OK] All required tables exist: ['stock_summary', 'ingestion_log']

[CHECK] Recent data...
  [OK] Latest date: 2026-06-19, Total records: 959

[CHECK] Ingestion log status...
  [OK] Status breakdown: {'success': 50, 'empty': 10, 'failed': 0}

[CHECK] Storage usage...
  [OK] Estimated usage: ~11.0 MB / 500 MB

================================================================================
HEALTH CHECK SUMMARY
================================================================================
  ✓ PASS: Db Connection
  ✓ PASS: Tables Exist
  ✓ PASS: Recent Data
  ✓ PASS: Ingestion Log
  ✓ PASS: Storage

[OVERALL] HEALTHY ✓
================================================================================
```

---

## Troubleshooting

### Pipeline Errors

| Masalah | Penyebab | Solusi |
|---------|----------|--------|
| Workflow gagal: `HTTP 403` semua metode | IDX blokir IP datacenter | Pastikan `SCRAPER_API_KEY` sudah diset di GitHub Secrets. Cek dashboard ScraperAPI — jangan sampai kehabisan kuota |
| Workflow gagal: `could not connect to server` | Supabase connection string salah | Cek `SUPABASE_DB_URL` di Secrets — pastikan pakai port **6543** (pooler), bukan 5432 |
| Workflow gagal: `SCRAPER_API_KEY tidak diset` | Secret belum ditambahkan | Buka Settings → Secrets → Actions → tambahkan secret |
| Data di Supabase kosong | Tabel belum dibuat | Tabel auto-create saat pipeline pertama jalan. Atau jalankan manual di notebook cell 4 |
| Supabase "too many connections" | Connection pool habis | Pastikan pakai port 6543 (PgBouncer pooler), bukan 5432 |
| `ingestion_log` kosong setelah pipeline | Tabel belum dibuat | Auto-create saat pipeline pertama jalan. Cek dengan `SELECT * FROM ingestion_log` |
| 0 records pada hari kerja | Hari libur nasional (tanggal merah) | Normal — IDX tutup pada hari libur. Status dicatat sebagai `empty`, bukan `failed` |

### CI/CD Errors

| Masalah | Penyebab | Solusi |
|---------|----------|--------|
| CI workflow: `No module named psycopg2` | Driver versi lama | Update `requirements.txt` ke `psycopg[binary]>=3.0` |
| CI workflow: `Invalid format: must start with postgresql` | `SUPABASE_DB_URL` format salah | Pastikan format: `postgresql+psycopg://postgres.[REF]:[PASS]@aws-1-ap-southeast-2.pooler.supabase.com:6543/postgres` |
| CI workflow: `Wrong port: use 6543` | Port 5432 terpakai | Ganti ke port **6543** (connection pooler) di Supabase dashboard |
| CI workflow timeout | Notebook execution > 300 detik | Pastikan `ExecutePreprocessor.timeout` cukup (default 300s) |
| Retry workflow: `exit code 1` | Pipeline gagal saat retry | Cek ingestion_log untuk error detail. Jalankan `health_check.py` |

### Local Development Errors

| Masalah | Penyebab | Solusi |
|---------|----------|--------|
| Local notebook: `unable to open database file` | Path SQLite salah | Jangan lompat cell. Jalankan **Kernel → Restart & Run All**. Notebook harus dijalankan dari folder `ingestion/` |
| Local notebook: `NameError: name 'IDX_API_URL' is not defined` | Cell konfigurasi belum dijalankan | Jalankan cell dari atas ke bawah. Jangan skip cell 3 |
| `pip install psycopg` gagal | Build tools belum terinstall | Windows: install Visual C++ Build Tools. Linux: `apt install libpq-dev` |
| Tanggal gagal tidak di-retry | `retry_count` sudah max (failed=5x, empty=3x) | Gunakan backfill tool: `python scripts/backfill.py --date 2026-06-16` atau reset via SQL: `UPDATE ingestion_log SET retry_count=0 WHERE date='...'` |

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
| `psycopg` | ≥ 3.0 | PostgreSQL driver (modern) |
| `tenacity` | ≥ 8.0 | Retry logic dengan exponential backoff |
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
