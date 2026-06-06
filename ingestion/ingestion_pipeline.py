"""
ingestion_pipeline.py — Production script untuk cron job / GitHub Actions.

Mengambil data ringkasan saham dari API IDX, membersihkan, dan menyimpan
ke Supabase PostgreSQL (atau fallback ke SQLite lokal).

Usage:
    SUPABASE_DB_URL=postgresql://... python ingestion/ingestion_pipeline.py

Tanpa env var, otomatis fallback ke SQLite (dev mode).
"""

import json
import os
import sys
import time
from datetime import datetime

from curl_cffi import requests as cf_requests
import cloudscraper
import pandas as pd
from sqlalchemy import Column, Integer, Float, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════
IDX_API_URL = "https://www.idx.co.id/primary/TradingSummary/GetStockSummary"
IDX_API_PARAMS = {"length": 9999, "start": 0}
REQUEST_TIMEOUT = 30

# Supabase (production) atau SQLite (dev fallback)
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
if SUPABASE_DB_URL:
    DB_URL = SUPABASE_DB_URL
    DB_MODE = "SUPABASE (PostgreSQL)"
else:
    DB_URL = "sqlite:///ingestion/idx_stock.db"
    DB_MODE = "SQLITE (lokal)"

# ═══════════════════════════════════════════════════════════════════
# DATABASE MODEL (SQLAlchemy ORM)
# ═══════════════════════════════════════════════════════════════════
Base = declarative_base()


class StockSummary(Base):
    __tablename__ = "stock_summary"

    id = Column(Integer, primary_key=True, autoincrement=True)
    id_stock_summary = Column(Integer, nullable=False)
    date = Column(String, nullable=False)
    stock_code = Column(String, nullable=False, index=True)
    stock_name = Column(String, nullable=False)
    remarks = Column(String, nullable=True)
    previous = Column(Float, nullable=True)
    open_price = Column(Float, nullable=True)
    first_trade = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    close = Column(Float, nullable=True)
    change = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)
    value = Column(Float, nullable=True)
    frequency = Column(Float, nullable=True)
    index_individual = Column(Float, nullable=True)
    offer = Column(Float, nullable=True)
    offer_volume = Column(Float, nullable=True)
    bid = Column(Float, nullable=True)
    bid_volume = Column(Float, nullable=True)
    listed_shares = Column(Float, nullable=True)
    tradeble_shares = Column(Float, nullable=True)
    weight_for_index = Column(Float, nullable=True)
    foreign_sell = Column(Float, nullable=True)
    foreign_buy = Column(Float, nullable=True)
    delisting_date = Column(String, nullable=True)
    non_regular_volume = Column(Float, nullable=True)
    non_regular_value = Column(Float, nullable=True)
    non_regular_frequency = Column(Float, nullable=True)

    def __repr__(self):
        return f"<StockSummary {self.stock_code} {self.date}>"


# ═══════════════════════════════════════════════════════════════════
# EXTRACT
# ═══════════════════════════════════════════════════════════════════


def extract_from_idx() -> list[dict]:
    """Mengambil data stock summary dari API IDX.

    Strategi:
      0. ScraperAPI — proxy residensial (prioritas utama).
      1. curl_cffi — coba 4 browser impersonation.
      2. cloudscraper — fallback dengan 4x retry.
      3. requests — last resort.

    Returns:
        List of dict dari field "data" di JSON response.
    """
    print(f"[{timestamp()}] EXTRACT - Mulai scraping...")
    print(f"  URL: {IDX_API_URL}")

    success = False
    response = None
    last_error = ""

    # ── Metode 0: ScraperAPI proxy residensial ──
    scraper_key = os.getenv("SCRAPER_API_KEY")
    if scraper_key:
        try:
            print("  [0/3] ScraperAPI (proxy residensial)...")
            target_url = f"{IDX_API_URL}?length=9999&start=0"
            import requests as scraper_requests
            resp = scraper_requests.get(
                "http://api.scraperapi.com/",
                params={
                    "api_key": scraper_key,
                    "url": target_url,
                },
                timeout=90,
            )
            print(f"  Status: {resp.status_code}")
            if resp.status_code == 200 and resp.json().get("data"):
                response = resp
                print("  BERHASIL via ScraperAPI")
                success = True
            else:
                last_error = f"ScraperAPI HTTP {resp.status_code}"
        except Exception as e:
            last_error = f"ScraperAPI: {e}"
            print(f"  Gagal: {e}")
    else:
        print("  [0/3] ScraperAPI dilewati (key tidak diset)")

    # ── Metode 1: curl_cffi multi-impersonation ──
    impersonations = ["chrome", "edge", "safari", "firefox"]
    for browser in impersonations:
        if success:
            break
        try:
            print(f"  curl_cffi — impersonate={browser} ...")
            response = cf_requests.get(
                IDX_API_URL,
                params=IDX_API_PARAMS,
                impersonate=browser,
                timeout=REQUEST_TIMEOUT,
            )
            print(f"  Status: {response.status_code}")
            if response.status_code == 200:
                print(f"  BERHASIL via curl_cffi ({browser})")
                success = True
            else:
                last_error = f"HTTP {response.status_code} ({browser})"
        except Exception as e:
            last_error = str(e)
            print(f"  Gagal ({browser}): {e}")

    # ── Metode 2: cloudscraper ──
    if not success:
        print("  curl_cffi gagal semua. Fallback: cloudscraper ...")
        try:
            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "desktop": True}
            )
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.idx.co.id/",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
            }
            for attempt in range(1, 5):
                try:
                    response = scraper.get(
                        IDX_API_URL,
                        params=IDX_API_PARAMS,
                        timeout=REQUEST_TIMEOUT,
                        headers=headers,
                    )
                    print(f"  Retry {attempt}/4 — Status: {response.status_code}")
                    if response.status_code == 200:
                        print("  BERHASIL via cloudscraper")
                        success = True
                        break
                except Exception as retry_err:
                    print(f"  Retry {attempt}/4 — Error: {retry_err}")
                if attempt < 4:
                    time.sleep(5)
        except Exception as e:
            last_error = f"cloudscraper: {e}"
            print(f"  cloudscraper gagal: {e}")

    # ── Metode 3: requests last resort ──
    if not success:
        print("  Semua metode gagal. Last resort: requests standar ...")
        try:
            import requests as std_requests
            std_headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.idx.co.id/",
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://www.idx.co.id",
            }
            response = std_requests.get(
                IDX_API_URL, params=IDX_API_PARAMS,
                timeout=REQUEST_TIMEOUT, headers=std_headers,
            )
            print(f"  Status: {response.status_code}")
            if response.status_code == 200:
                print("  BERHASIL via requests standar")
                success = True
        except Exception as e:
            last_error = str(e)

    if not success:
        raise RuntimeError(
            f"GAGAL mengambil data setelah semua metode. Error: {last_error}"
        )

    # ── Parse JSON ──
    payload = response.json()
    records = payload.get("data", [])
    total = payload.get("recordsTotal", 0)
    print(f"  Diambil {len(records)} record (total: {total})")
    return records


# ═══════════════════════════════════════════════════════════════════
# TRANSFORM
# ═══════════════════════════════════════════════════════════════════


def transform(records: list[dict]) -> pd.DataFrame:
    """Membersihkan dan menstandarkan data JSON menjadi DataFrame.

    Steps:
      1. Map field PascalCase API → snake_case.
      2. Drop baris tanpa stock_code / date.
      3. Konversi kolom numerik ke float.
      4. Standarisasi string (strip, uppercase).
    """
    print(f"[{timestamp()}] TRANSFORM - Membersihkan data...")

    rows = []
    for item in records:
        rows.append({
            "id_stock_summary": item.get("IDStockSummary"),
            "date": item.get("Date", "")[:10] if item.get("Date") else "",
            "stock_code": item.get("StockCode", ""),
            "stock_name": item.get("StockName", ""),
            "remarks": item.get("Remarks", ""),
            "previous": item.get("Previous"),
            "open_price": item.get("OpenPrice"),
            "first_trade": item.get("FirstTrade"),
            "high": item.get("High"),
            "low": item.get("Low"),
            "close": item.get("Close"),
            "change": item.get("Change"),
            "volume": item.get("Volume"),
            "value": item.get("Value"),
            "frequency": item.get("Frequency"),
            "index_individual": item.get("IndexIndividual"),
            "offer": item.get("Offer"),
            "offer_volume": item.get("OfferVolume"),
            "bid": item.get("Bid"),
            "bid_volume": item.get("BidVolume"),
            "listed_shares": item.get("ListedShares"),
            "tradeble_shares": item.get("TradebleShares"),
            "weight_for_index": item.get("WeightForIndex"),
            "foreign_sell": item.get("ForeignSell"),
            "foreign_buy": item.get("ForeignBuy"),
            "delisting_date": item.get("DelistingDate", ""),
            "non_regular_volume": item.get("NonRegularVolume"),
            "non_regular_value": item.get("NonRegularValue"),
            "non_regular_frequency": item.get("NonRegularFrequency"),
        })

    df = pd.DataFrame(rows)
    print(f"  Mentah: {len(df)} baris")

    # Clean: drop missing identifiers
    before = len(df)
    df = df.dropna(subset=["stock_code", "date"])
    print(f"  Drop tanpa stock_code/date: {before} → {len(df)}")

    # Clean: numeric coercion
    numeric_cols = [
        "previous", "open_price", "first_trade", "high", "low", "close",
        "change", "volume", "value", "frequency", "index_individual",
        "offer", "offer_volume", "bid", "bid_volume", "listed_shares",
        "tradeble_shares", "weight_for_index", "foreign_sell", "foreign_buy",
        "non_regular_volume", "non_regular_value", "non_regular_frequency",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean: string normalization
    df["stock_name"] = df["stock_name"].astype(str).str.strip()
    df["stock_code"] = df["stock_code"].astype(str).str.strip().str.upper()

    print(f"  Bersih: {len(df)} baris × {len(df.columns)} kolom")
    return df


# ═══════════════════════════════════════════════════════════════════
# LOAD
# ═══════════════════════════════════════════════════════════════════


def load(df: pd.DataFrame):
    """Menyimpan DataFrame ke database (idempotent).

    Jika data untuk tanggal tersebut sudah ada → hapus dulu → insert baru.
    """
    print(f"[{timestamp()}] LOAD - Menyimpan ke database ({DB_MODE})...")

    engine = create_engine(DB_URL, echo=False)
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    # Idempotent: delete existing data for this date
    date_val = df["date"].iloc[0] if len(df) > 0 else ""
    existing = session.query(StockSummary).filter(
        StockSummary.date == date_val
    ).count()

    if existing > 0:
        print(f"  Data {date_val} sudah ada ({existing} record) — menghapus...")
        session.query(StockSummary).filter(
            StockSummary.date == date_val
        ).delete()
        session.commit()

    # Konversi DataFrame → ORM objects
    db_records = []
    for _, row in df.iterrows():
        db_records.append(StockSummary(
            id_stock_summary=int(row["id_stock_summary"]) if pd.notna(row["id_stock_summary"]) else 0,
            date=str(row["date"]),
            stock_code=str(row["stock_code"]),
            stock_name=str(row["stock_name"]),
            remarks=str(row.get("remarks", "")),
            previous=float(row["previous"]) if pd.notna(row["previous"]) else None,
            open_price=float(row["open_price"]) if pd.notna(row["open_price"]) else None,
            first_trade=float(row["first_trade"]) if pd.notna(row["first_trade"]) else None,
            high=float(row["high"]) if pd.notna(row["high"]) else None,
            low=float(row["low"]) if pd.notna(row["low"]) else None,
            close=float(row["close"]) if pd.notna(row["close"]) else None,
            change=float(row["change"]) if pd.notna(row["change"]) else None,
            volume=float(row["volume"]) if pd.notna(row["volume"]) else None,
            value=float(row["value"]) if pd.notna(row["value"]) else None,
            frequency=float(row["frequency"]) if pd.notna(row["frequency"]) else None,
            index_individual=float(row["index_individual"]) if pd.notna(row["index_individual"]) else None,
            offer=float(row["offer"]) if pd.notna(row["offer"]) else None,
            offer_volume=float(row["offer_volume"]) if pd.notna(row["offer_volume"]) else None,
            bid=float(row["bid"]) if pd.notna(row["bid"]) else None,
            bid_volume=float(row["bid_volume"]) if pd.notna(row["bid_volume"]) else None,
            listed_shares=float(row["listed_shares"]) if pd.notna(row["listed_shares"]) else None,
            tradeble_shares=float(row["tradeble_shares"]) if pd.notna(row["tradeble_shares"]) else None,
            weight_for_index=float(row["weight_for_index"]) if pd.notna(row["weight_for_index"]) else None,
            foreign_sell=float(row["foreign_sell"]) if pd.notna(row["foreign_sell"]) else None,
            foreign_buy=float(row["foreign_buy"]) if pd.notna(row["foreign_buy"]) else None,
            delisting_date=str(row.get("delisting_date", "")),
            non_regular_volume=float(row["non_regular_volume"]) if pd.notna(row["non_regular_volume"]) else None,
            non_regular_value=float(row["non_regular_value"]) if pd.notna(row["non_regular_value"]) else None,
            non_regular_frequency=float(row["non_regular_frequency"]) if pd.notna(row["non_regular_frequency"]) else None,
        ))

    session.bulk_save_objects(db_records)
    session.commit()

    total = session.query(StockSummary).count()
    print(f"  Tersimpan: {len(db_records)} record (total DB: {total})")
    session.close()


# ═══════════════════════════════════════════════════════════════════
# UTILITY
# ═══════════════════════════════════════════════════════════════════


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print(f"  IDX INGESTION PIPELINE — {timestamp()}")
    print(f"  DB: {DB_MODE}")
    print("=" * 60)

    try:
        # EXTRACT
        records = extract_from_idx()
        if not records:
            print(f"[{timestamp()}] ERROR: Tidak ada data dari API!")
            sys.exit(1)

        # TRANSFORM
        df = transform(records)

        # LOAD
        load(df)

        # SUMMARY
        print("=" * 60)
        print(f"  PIPELINE SELESAI — {timestamp()}")
        print(f"  Record : {len(df)}")
        print(f"  Tanggal: {df['date'].iloc[0] if len(df) > 0 else 'N/A'}")
        print(f"  DB     : {DB_MODE}")
        print("=" * 60)

    except Exception as e:
        print(f"[{timestamp()}] FATAL: {e}", file=sys.stderr)
        sys.exit(1)
