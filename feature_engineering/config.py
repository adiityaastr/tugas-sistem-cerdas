"""
config.py — Konfigurasi feature engineering untuk data saham IDX.

File ini memusatkan konstanta dan daftar fitur sehingga script utama
lebih bersih dan mudah di-extend.
"""

import os
from urllib.parse import urlparse, quote


# ═══════════════════════════════════════════════════════════════════
# DATABASE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════
def get_database_url() -> tuple[str, str]:
    """Menghasilkan SQLAlchemy DB_URL dan label DB_MODE.

    Logic sama dengan ingestion_pipeline.py: Supabase jika env var
    SUPABASE_DB_URL tersedia, fallback ke SQLite lokal.
    """
    supabase_db_url = os.getenv("SUPABASE_DB_URL")
    if supabase_db_url:
        supabase_db_url = supabase_db_url.strip().strip('"').strip("'")
        if "+psycopg" not in supabase_db_url:
            parsed = urlparse(supabase_db_url)
            if parsed.username and parsed.password:
                encoded_username = parsed.username.replace('.', '%2E')
                encoded_password = quote(parsed.password, safe='')
                db_url = (
                    f"postgresql+psycopg://{encoded_username}:{encoded_password}"
                    f"@{parsed.hostname}:{parsed.port}{parsed.path}"
                )
                db_mode = "SUPABASE (PostgreSQL)"
            else:
                db_url = "sqlite:///ingestion/idx_stock.db"
                db_mode = "SQLITE (fallback - invalid DB URL)"
        else:
            db_url = supabase_db_url
            db_mode = "SUPABASE (PostgreSQL)"
    else:
        db_url = "sqlite:///ingestion/idx_stock.db"
        db_mode = "SQLITE (lokal)"

    return db_url, db_mode


DB_URL, DB_MODE = get_database_url()


# ═══════════════════════════════════════════════════════════════════
# SOURCE & TARGET TABLES
# ═══════════════════════════════════════════════════════════════════
SOURCE_TABLE = "stock_summary"
TARGET_TABLE = "stock_features"


# ═══════════════════════════════════════════════════════════════════
# FEATURE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════
# Kolom numerik yang dibutuhkan untuk perhitungan fitur
PRICE_COLS = ["previous", "open_price", "high", "low", "close"]
VOLUME_COLS = ["volume", "value", "frequency"]
FOREIGN_COLS = ["foreign_buy", "foreign_sell"]
BID_OFFER_COLS = ["bid", "offer", "bid_volume", "offer_volume"]
SHARE_COLS = ["listed_shares", "tradeble_shares"]

# Window sizes untuk fitur lag-based
# Dipilih berdasarkan ketersediaan data (15 hari kerja).
# Window 20 dibiarkan di config tetapi fitur yang membutuhkannya
# (SMA20, Bollinger, RSI14, MACD) akan di-disable secara default.
SMA_WINDOWS = [5, 10]
EMA_WINDOWS = [5, 10]
VOLATILITY_WINDOWS = [5, 10]

# Fitur yang akan dihitung
ENABLE_DAILY_FEATURES = True
ENABLE_LAG_FEATURES = True
ENABLE_RANK_FEATURES = True

# Fitur advanced yang membutuhkan history panjang.
# Di-disable default karena data baru 15 hari kerja.
ENABLE_RSI = False
ENABLE_MACD = False
ENABLE_LONG_SMA = False  # SMA 20
ENABLE_BOLLINGER = False


# ═══════════════════════════════════════════════════════════════════
# COLUMN NAMES FOR OUTPUT
# ═══════════════════════════════════════════════════════════════════
DAILY_FEATURES = [
    "daily_return_pct",
    "intraday_return_pct",
    "high_low_range_pct",
    "spread",
    "spread_pct",
    "bid_offer_imbalance",
    "foreign_net",
    "foreign_buy_ratio",
    "foreign_sell_ratio",
    "value_per_frequency",
    "avg_trade_size",
    "market_cap_proxy",
]

LAG_FEATURES = (
    [f"sma_{w}" for w in SMA_WINDOWS]
    + [f"ema_{w}" for w in EMA_WINDOWS]
    + [f"volatility_{w}d" for w in VOLATILITY_WINDOWS]
)

RANK_FEATURES = [
    "rank_change_pct",
    "rank_volume",
    "rank_value",
    "rank_foreign_net",
]

ALL_FEATURES = DAILY_FEATURES + LAG_FEATURES + RANK_FEATURES


# ═══════════════════════════════════════════════════════════════════
# DEFAULT EXPORT PATH
# ═══════════════════════════════════════════════════════════════════
DEFAULT_CSV_DIR = "feature_engineering"
