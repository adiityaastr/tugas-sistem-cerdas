# Feature Engineering — Data Saham IDX

Modul ini membuat fitur-fitur baru dari tabel `stock_summary` di Supabase untuk keperluan analisis dan model ML.

---

## Struktur File

```
feature_engineering/
├── config.py                    # Konfigurasi fitur & database
├── feature_engineering.py       # Script production (CLI)
├── feature_engineering.ipynb    # Notebook eksplorasi & visualisasi
└── README.md                    # Dokumentasi ini
```

---

## Fitur yang Dihitung

### Tier 1 — Fitur Harian
Fitur yang bisa dihitung dari data 1 hari saja.

| Fitur | Deskripsi |
|---|---|
| `daily_return_pct` | Return harian: `(close - previous) / previous * 100` |
| `intraday_return_pct` | Return intraday: `(close - open) / open * 100` |
| `high_low_range_pct` | Range hari ini: `(high - low) / previous * 100` |
| `spread` | Selisih offer - bid |
| `spread_pct` | Spread relatif terhadap close |
| `bid_offer_imbalance` | Ketidakseimbangan volume bid vs offer |
| `foreign_net` | Net flow asing: `foreign_buy - foreign_sell` |
| `foreign_buy_ratio` | Rasio pembelian asing terhadap volume |
| `foreign_sell_ratio` | Rasio penjualan asing terhadap volume |
| `value_per_frequency` | Rata-rata nilai per transaksi |
| `avg_trade_size` | Rata-rata volume per transaksi |
| `market_cap_proxy` | Proxy market cap: `close * tradeble_shares` |

### Tier 2 — Fitur Lag-Based
Fitur yang membutuhkan history beberapa hari per saham.

| Fitur | Deskripsi |
|---|---|
| `sma_5` | Simple Moving Average 5 hari |
| `sma_10` | Simple Moving Average 10 hari |
| `ema_5` | Exponential Moving Average 5 hari |
| `ema_10` | Exponential Moving Average 10 hari |
| `volatility_5d` | Volatilitas 5 hari (std dev return) |
| `volatility_10d` | Volatilitas 10 hari (std dev return) |

### Tier 3 — Cross-Sectional Ranking
Ranking per hari di antara semua saham.

| Fitur | Deskripsi |
|---|---|
| `rank_change_pct` | Peringkat return harian |
| `rank_volume` | Peringkat volume |
| `rank_value` | Peringkat nilai transaksi |
| `rank_foreign_net` | Peringkat net asing |

---

## Cara Menjalankan

### Prasyarat

Pastikan environment variable `SUPABASE_DB_URL` sudah diset:

```powershell
$env:SUPABASE_DB_URL = "postgresql+psycopg://..."
```

### 1. Generate Fitur untuk Semua Tanggal

```powershell
python feature_engineering/feature_engineering.py --all
```

### 2. Generate Fitur untuk Tanggal Tertentu

```powershell
python feature_engineering/feature_engineering.py --date 2026-06-26
```

### 3. Generate Fitur untuk Rentang Tanggal

```powershell
python feature_engineering/feature_engineering.py --start 2026-06-20 --end 2026-06-26
```

### 4. Export CSV Backup

```powershell
python feature_engineering/feature_engineering.py --all --export-csv
```

### 5. Hanya Export CSV (tidak menyimpan ke database)

```powershell
python feature_engineering/feature_engineering.py --all --csv-only
```

---

## Output

### Database
Hasil disimpan ke tabel `stock_features` di Supabase dengan struktur:

```sql
CREATE TABLE public.stock_features (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    stock_code VARCHAR NOT NULL,
    -- Tier 1: daily features
    daily_return_pct DOUBLE PRECISION,
    intraday_return_pct DOUBLE PRECISION,
    high_low_range_pct DOUBLE PRECISION,
    spread DOUBLE PRECISION,
    spread_pct DOUBLE PRECISION,
    bid_offer_imbalance DOUBLE PRECISION,
    foreign_net DOUBLE PRECISION,
    foreign_buy_ratio DOUBLE PRECISION,
    foreign_sell_ratio DOUBLE PRECISION,
    value_per_frequency DOUBLE PRECISION,
    avg_trade_size DOUBLE PRECISION,
    market_cap_proxy DOUBLE PRECISION,
    -- Tier 2: lag-based features
    sma_5 DOUBLE PRECISION,
    sma_10 DOUBLE PRECISION,
    ema_5 DOUBLE PRECISION,
    ema_10 DOUBLE PRECISION,
    volatility_5d DOUBLE PRECISION,
    volatility_10d DOUBLE PRECISION,
    -- Tier 3: ranking
    rank_change_pct INTEGER,
    rank_volume INTEGER,
    rank_value INTEGER,
    rank_foreign_net INTEGER,
    CONSTRAINT stock_features_date_stock_code UNIQUE (date, stock_code)
);
```

### CSV Backup
File CSV tersimpan di folder `feature_engineering/` dengan format:

```
stock_features_YYYYMMDD_HHMMSS.csv
```

---

## Catatan Penting

1. **Data History**: Fitur lag-based membutuhkan data historis per saham. Dengan 15 hari data, `sma_5`, `sma_10`, `volatility_5d`, dan `volatility_10d` sudah bisa terisi. Fitur seperti RSI 14, MACD, SMA 20, dan Bollinger Bands sengaja belum dibuat karena data masih kurang dari 20 hari.

2. **Idempotent**: Setiap kali script dijalankan, data untuk tanggal yang sama akan dihapus dan diganti dengan yang baru. Tidak ada duplikat.

3. **Missing Values**: Fitur yang tidak bisa dihitung karena kurangnya history atau data tidak valid akan bernilai `NULL` di database dan `NaN` di CSV.

4. **Keamanan**: Jangan menyimpan `SUPABASE_DB_URL` di file code. Gunakan environment variable atau GitHub Secrets.

---

## Integrasi CI/CD

Workflow `feature_engineering.yml` sudah tersedia di `.github/workflows/` dan akan berjalan secara otomatis:

| Trigger | Keterangan |
|---|---|
| `workflow_run` | Jalan otomatis setelah workflow `CD - Deploy to Supabase` sukses |
| `schedule` | Cron Senin—Jumat jam 18:30 WIB (11:30 UTC) sebagai fallback |
| `workflow_dispatch` | Manual trigger via tab Actions, bisa isi tanggal opsional |

### Cara Manual Trigger dari GitHub

1. Buka repo → tab **Actions**
2. Pilih workflow **Feature Engineering**
3. Klik **Run workflow**
4. Isi `date` jika ingin generate untuk tanggal tertentu, atau kosongkan untuk semua tanggal
5. Klik **Run workflow**

Workflow akan:
1. Install dependencies dari `requirements.txt`
2. Jalankan `feature_engineering.py`
3. Upload CSV hasil sebagai artifact
4. Tampilkan summary jumlah row di tabel `stock_features`
