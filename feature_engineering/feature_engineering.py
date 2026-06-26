"""
feature_engineering.py — Production script untuk membuat fitur saham IDX.

Script ini membaca data dari tabel `stock_summary` (Supabase/SQLite),
menghitung fitur teknikal dan statistik, lalu menyimpan hasilnya ke
tabel `stock_features` secara idempotent.

Usage:
    # Semua tanggal yang tersedia di database
    python feature_engineering/feature_engineering.py --all

    # Tanggal tertentu
    python feature_engineering/feature_engineering.py --date 2026-06-26

    # Rentang tanggal
    python feature_engineering/feature_engineering.py --start 2026-06-20 --end 2026-06-26

    # Simpan CSV backup juga
    python feature_engineering/feature_engineering.py --all --export-csv
"""

import argparse
import os
import sys
import time
from datetime import datetime

# Supaya `config.py` bisa di-import baik saat script dijalankan langsung
# (`python feature_engineering/feature_engineering.py`) maupun saat di-import
# sebagai modul (`from feature_engineering.feature_engineering import ...`).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
from sqlalchemy import Column, Date, Float, Integer, String, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from config import (
    ALL_FEATURES,
    BID_OFFER_COLS,
    DB_MODE,
    DB_URL,
    DEFAULT_CSV_DIR,
    DAILY_FEATURES,
    EMA_WINDOWS,
    ENABLE_DAILY_FEATURES,
    ENABLE_LAG_FEATURES,
    ENABLE_RANK_FEATURES,
    FOREIGN_COLS,
    LAG_FEATURES,
    PRICE_COLS,
    RANK_FEATURES,
    SHARE_COLS,
    SMA_WINDOWS,
    SOURCE_TABLE,
    TARGET_TABLE,
    VOLATILITY_WINDOWS,
    VOLUME_COLS,
)

# ═══════════════════════════════════════════════════════════════════
# DATABASE MODEL (SQLAlchemy ORM)
# ═══════════════════════════════════════════════════════════════════
Base = declarative_base()


class StockFeatures(Base):
    __tablename__ = TARGET_TABLE

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    stock_code = Column(String, nullable=False, index=True)

    # Tier 1: daily features
    daily_return_pct = Column(Float, nullable=True)
    intraday_return_pct = Column(Float, nullable=True)
    high_low_range_pct = Column(Float, nullable=True)
    spread = Column(Float, nullable=True)
    spread_pct = Column(Float, nullable=True)
    bid_offer_imbalance = Column(Float, nullable=True)
    foreign_net = Column(Float, nullable=True)
    foreign_buy_ratio = Column(Float, nullable=True)
    foreign_sell_ratio = Column(Float, nullable=True)
    value_per_frequency = Column(Float, nullable=True)
    avg_trade_size = Column(Float, nullable=True)
    market_cap_proxy = Column(Float, nullable=True)

    # Tier 2: lag-based features
    sma_5 = Column(Float, nullable=True)
    sma_10 = Column(Float, nullable=True)
    ema_5 = Column(Float, nullable=True)
    ema_10 = Column(Float, nullable=True)
    volatility_5d = Column(Float, nullable=True)
    volatility_10d = Column(Float, nullable=True)

    # Tier 3: cross-sectional ranking
    rank_change_pct = Column(Integer, nullable=True)
    rank_volume = Column(Integer, nullable=True)
    rank_value = Column(Integer, nullable=True)
    rank_foreign_net = Column(Integer, nullable=True)

    def __repr__(self):
        return f"<StockFeatures {self.stock_code} {self.date}>"


# ═══════════════════════════════════════════════════════════════════
# UTILITY
# ═══════════════════════════════════════════════════════════════════
def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_divide(a: pd.Series, b: pd.Series) -> pd.Series:
    """Pembagian aman yang menghasilkan NaN jika pembagi nol."""
    return np.where(b != 0, a / b, np.nan)


# ═══════════════════════════════════════════════════════════════════
# LOAD RAW DATA
# ═══════════════════════════════════════════════════════════════════
def load_raw_data(date_filter: str | None = None,
                  start_date: str | None = None,
                  end_date: str | None = None) -> pd.DataFrame:
    """Membaca data mentah dari tabel stock_summary."""
    print(f"[{timestamp()}] LOAD RAW - Membaca data dari {DB_MODE}...")

    engine = create_engine(DB_URL, echo=False)

    query = f"SELECT * FROM {SOURCE_TABLE}"
    conditions = []
    params = {}

    if date_filter:
        conditions.append("date = :date_filter")
        params["date_filter"] = date_filter
    else:
        if start_date:
            conditions.append("date >= :start_date")
            params["start_date"] = start_date
        if end_date:
            conditions.append("date <= :end_date")
            params["end_date"] = end_date

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY stock_code, date"

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn, params=params)

    print(f"  Loaded: {len(df):,} baris × {len(df.columns)} kolom")
    if not df.empty:
        print(f"  Rentang tanggal: {df['date'].min()} s/d {df['date'].max()}")
        print(f"  Jumlah saham unik: {df['stock_code'].nunique()}")

    return df


# ═══════════════════════════════════════════════════════════════════
# FEATURE COMPUTATION
# ═══════════════════════════════════════════════════════════════════
def compute_daily_features(df: pd.DataFrame) -> pd.DataFrame:
    """Menghitung fitur harian (tidak membutuhkan history)."""
    print(f"[{timestamp()}] FEATURES - Menghitung fitur harian...")

    # Pastikan kolom numerik dalam tipe float
    numeric_cols = PRICE_COLS + VOLUME_COLS + FOREIGN_COLS + BID_OFFER_COLS + SHARE_COLS
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Return & perubahan harga
    df["daily_return_pct"] = safe_divide((df["close"] - df["previous"]), df["previous"]) * 100
    df["intraday_return_pct"] = safe_divide((df["close"] - df["open_price"]), df["open_price"]) * 100
    df["high_low_range_pct"] = safe_divide((df["high"] - df["low"]), df["previous"]) * 100

    # Bid-offer spread
    df["spread"] = df["offer"] - df["bid"]
    df["spread_pct"] = safe_divide(df["spread"], df["close"]) * 100
    bid_offer_vol_sum = df["bid_volume"] + df["offer_volume"]
    df["bid_offer_imbalance"] = safe_divide(
        (df["bid_volume"] - df["offer_volume"]), bid_offer_vol_sum
    )

    # Foreign flow
    df["foreign_net"] = df["foreign_buy"] - df["foreign_sell"]
    df["foreign_buy_ratio"] = safe_divide(df["foreign_buy"], df["volume"])
    df["foreign_sell_ratio"] = safe_divide(df["foreign_sell"], df["volume"])

    # Volume & likuiditas
    df["value_per_frequency"] = safe_divide(df["value"], df["frequency"])
    df["avg_trade_size"] = safe_divide(df["volume"], df["frequency"])

    # Market cap proxy
    df["market_cap_proxy"] = df["close"] * df["tradeble_shares"]

    return df


def compute_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    """Menghitung fitur lag-based per stock_code."""
    print(f"[{timestamp()}] FEATURES - Menghitung fitur lag-based...")

    df = df.sort_values(["stock_code", "date"]).copy()

    # Simple Moving Average (SMA)
    for window in SMA_WINDOWS:
        df[f"sma_{window}"] = (
            df.groupby("stock_code")["close"]
            .transform(lambda x: x.rolling(window=window, min_periods=window).mean())
        )

    # Exponential Moving Average (EMA)
    for window in EMA_WINDOWS:
        df[f"ema_{window}"] = (
            df.groupby("stock_code")["close"]
            .transform(lambda x: x.ewm(span=window, min_periods=window).mean())
        )

    # Volatilitas (std dev dari daily_return_pct)
    df["_daily_return"] = safe_divide((df["close"] - df["previous"]), df["previous"])
    for window in VOLATILITY_WINDOWS:
        df[f"volatility_{window}d"] = (
            df.groupby("stock_code")["_daily_return"]
            .transform(lambda x: x.rolling(window=window, min_periods=window).std() * 100)
        )

    df = df.drop(columns=["_daily_return"])
    return df


def compute_rank_features(df: pd.DataFrame) -> pd.DataFrame:
    """Menghitung ranking cross-sectional per tanggal."""
    print(f"[{timestamp()}] FEATURES - Menghitung ranking harian...")

    df["rank_change_pct"] = (
        df.groupby("date")["daily_return_pct"]
        .rank(method="min", ascending=False, na_option="keep")
        .astype("Int64")
    )
    df["rank_volume"] = (
        df.groupby("date")["volume"]
        .rank(method="min", ascending=False, na_option="keep")
        .astype("Int64")
    )
    df["rank_value"] = (
        df.groupby("date")["value"]
        .rank(method="min", ascending=False, na_option="keep")
        .astype("Int64")
    )
    df["rank_foreign_net"] = (
        df.groupby("date")["foreign_net"]
        .rank(method="min", ascending=False, na_option="keep")
        .astype("Int64")
    )

    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Pipeline utama feature engineering."""
    print(f"[{timestamp()}] BUILD - Memulai feature engineering...")

    if df.empty:
        raise ValueError("Data mentah kosong. Tidak ada fitur yang dihitung.")

    # Konversi date ke datetime
    df["date"] = pd.to_datetime(df["date"]).dt.date

    # Tier 1: daily features
    if ENABLE_DAILY_FEATURES:
        df = compute_daily_features(df)

    # Tier 2: lag-based features
    if ENABLE_LAG_FEATURES:
        df = compute_lag_features(df)

    # Tier 3: cross-sectional ranking (bergantung pada daily features)
    if ENABLE_RANK_FEATURES:
        df = compute_rank_features(df)

    # Pilih kolom output
    keep_cols = ["date", "stock_code"] + ALL_FEATURES
    output_df = df[keep_cols].copy()

    # Ganti inf dengan NaN
    output_df = output_df.replace([np.inf, -np.inf], np.nan)

    print(f"  Output: {len(output_df):,} baris × {len(output_df.columns)} kolom")
    return output_df


# ═══════════════════════════════════════════════════════════════════
# SAVE TO DATABASE
# ═══════════════════════════════════════════════════════════════════
def save_to_database(df: pd.DataFrame):
    """Menyimpan fitur ke tabel stock_features secara idempotent.

    Menggunakan pandas to_sql dengan multi-value insert untuk performa
    yang jauh lebih cepat dibanding bulk_save_objects per row.
    """
    print(f"[{timestamp()}] SAVE DB - Menyimpan ke {DB_MODE} (tabel {TARGET_TABLE})...")

    engine = create_engine(DB_URL, echo=False)
    Base.metadata.create_all(engine)

    # Hapus data untuk tanggal yang akan di-insert
    dates = df["date"].unique().tolist()
    print(f"  Tanggal yang akan di-update: {len(dates)} tanggal")

    with engine.connect() as conn:
        result = conn.execute(
            text(f"DELETE FROM {TARGET_TABLE} WHERE date = ANY(:dates)"),
            {"dates": dates},
        )
        conn.commit()
        print(f"  Deleted existing rows: {result.rowcount:,}")

    # Insert data baru dengan pandas to_sql (bulk multi-value)
    insert_df = df.copy()
    insert_df["date"] = pd.to_datetime(insert_df["date"])

    # Pastikan tipe rank integer (bukan Int64 nullable yang bisa bermasalah di to_sql)
    for col in ["rank_change_pct", "rank_volume", "rank_value", "rank_foreign_net"]:
        insert_df[col] = insert_df[col].astype("Int64")

    insert_df.to_sql(
        TARGET_TABLE,
        con=engine,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=1000,
    )

    with engine.connect() as conn:
        total = conn.execute(text(f"SELECT COUNT(*) FROM {TARGET_TABLE}")).scalar()
    print(f"  Inserted: {len(insert_df):,} rows")
    print(f"  Total rows in {TARGET_TABLE}: {total:,}")


# ═══════════════════════════════════════════════════════════════════
# EXPORT CSV
# ═══════════════════════════════════════════════════════════════════
def export_csv(df: pd.DataFrame, suffix: str | None = None) -> str:
    """Mengekspor fitur ke CSV sebagai backup."""
    os.makedirs(DEFAULT_CSV_DIR, exist_ok=True)

    if suffix is None:
        suffix = datetime.now().strftime("%Y%m%d_%H%M%S")

    filename = f"{TARGET_TABLE}_{suffix}.csv"
    filepath = os.path.join(DEFAULT_CSV_DIR, filename)

    df.to_csv(filepath, index=False)
    print(f"[{timestamp()}] EXPORT CSV - Tersimpan di: {filepath}")
    print(f"  Total: {len(df):,} baris × {len(df.columns)} kolom")
    return filepath


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="Feature Engineering untuk data saham IDX"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate fitur untuk semua tanggal di database",
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Generate fitur untuk tanggal tertentu (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--start",
        type=str,
        help="Tanggal awal rentang (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=str,
        help="Tanggal akhir rentang (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--export-csv",
        action="store_true",
        help="Export hasil ke CSV backup",
    )
    parser.add_argument(
        "--csv-only",
        action="store_true",
        help="Hanya export CSV, tidak menyimpan ke database",
    )

    args = parser.parse_args()

    # Validasi argumen
    if not (args.all or args.date or (args.start and args.end)):
        parser.print_help()
        print("\n[ERROR] Pilih salah satu: --all, --date, atau --start + --end")
        sys.exit(1)

    start_time = time.time()
    print("=" * 60)
    print(f"  FEATURE ENGINEERING PIPELINE — {timestamp()}")
    print(f"  DB: {DB_MODE}")
    print(f"  Source: {SOURCE_TABLE}")
    print(f"  Target: {TARGET_TABLE}")
    print("=" * 60)

    try:
        # LOAD
        df_raw = load_raw_data(
            date_filter=args.date,
            start_date=args.start,
            end_date=args.end,
        )

        # BUILD FEATURES
        df_features = build_features(df_raw)

        # SAVE
        if not args.csv_only:
            save_to_database(df_features)

        if args.export_csv or args.csv_only:
            export_csv(df_features)

        elapsed = time.time() - start_time
        print("=" * 60)
        print(f"  PIPELINE SELESAI — {timestamp()}")
        print(f"  Baris fitur: {len(df_features):,}")
        print(f"  Kolom fitur: {len(df_features.columns)}")
        print(f"  Durasi: {elapsed:.1f} detik")
        print(f"  DB: {DB_MODE}")
        print("=" * 60)

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"[{timestamp()}] FATAL: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
