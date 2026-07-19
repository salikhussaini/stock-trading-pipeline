# =========================================================
# daily_collector.py
# Full historical ETL + logging + rate-limit protection
# =========================================================

from pathlib import Path
from datetime import datetime
import uuid
import time
import random

import duckdb
import pandas as pd
import yfinance as yf

# =========================================================
# CONFIG
# =========================================================

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "database" / "stock_data.duckdb"
TICKERS_FILE = BASE_DIR / "tickers.csv"

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

run_id = str(uuid.uuid4())
pipeline_name = "daily_collector"

# =========================================================
# CONNECT DB
# =========================================================

conn = duckdb.connect(str(DB_PATH))

# =========================================================
# TABLES
# =========================================================

conn.execute("""
CREATE TABLE IF NOT EXISTS daily_prices (
    ticker VARCHAR,
    date DATE,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    adj_close DOUBLE,
    volume BIGINT,
    PRIMARY KEY(ticker, date)
)
""")

conn.execute("""
CREATE TABLE IF NOT EXISTS download_log (
    run_id VARCHAR,
    ticker VARCHAR,
    start_date DATE,
    end_date DATE,
    rows_downloaded INTEGER,
    execution_seconds DOUBLE,
    status VARCHAR,
    error_message VARCHAR,
    log_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

conn.execute("""
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id VARCHAR PRIMARY KEY,
    pipeline_name VARCHAR,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    tickers_total INTEGER,
    tickers_success INTEGER,
    tickers_failed INTEGER,
    total_rows INTEGER,
    execution_seconds DOUBLE,
    status VARCHAR
)
""")

# =========================================================
# SAFE YFINANCE DOWNLOAD (RATE LIMIT PROTECTION)
# =========================================================

def safe_yf_download(ticker, start, end, max_retries=3):

    base_delay = 1.0

    for attempt in range(max_retries):

        try:
            df = yf.download(
                ticker,
                start=start,
                end=end,
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False   # IMPORTANT for Yahoo throttling
            )

            if df is None or df.empty:
                raise ValueError("Empty response (rate limit or no data)")

            return df

        except Exception as e:

            wait = base_delay * (2 ** attempt) + random.uniform(0, 0.5)

            print(f"[RATE LIMIT] {ticker} retry {attempt+1}/{max_retries} wait={wait:.2f}s")

            time.sleep(wait)

    return None

# =========================================================
# LOAD TICKERS
# =========================================================

tickers = pd.read_csv(TICKERS_FILE)["ticker"].dropna().unique()

print(f"Starting pipeline: {pipeline_name}")
print(f"Run ID: {run_id}")
print(f"Tickers: {len(tickers)}")

# =========================================================
# METRICS
# =========================================================

overall_start = time.perf_counter()

success = 0
failed = 0
total_rows = 0

# =========================================================
# MAIN LOOP
# =========================================================

for ticker in tickers:

    ticker_start = time.perf_counter()

    status = "SUCCESS"
    error = None
    rows = 0

    start = "2000-01-01"
    end = datetime.today().strftime("%Y-%m-%d")

    try:

        # -------------------------------------------------
        # GLOBAL THROTTLE (prevents burst requests)
        # -------------------------------------------------
        time.sleep(random.uniform(0.2, 0.8))

        # -------------------------------------------------
        # DOWNLOAD WITH RETRY LOGIC
        # -------------------------------------------------
        df = safe_yf_download(ticker, start, end)

        if df is None or df.empty:
            status = "FAILED"
            error = "Rate-limited or empty response after retries"
            failed += 1

        else:

            df = df.reset_index()

            df.rename(columns={
                "Date": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Adj Close": "adj_close",
                "Volume": "volume"
            }, inplace=True)

            df["ticker"] = ticker

            df = df[
                [
                    "ticker", "date",
                    "open", "high", "low", "close",
                    "adj_close", "volume"
                ]
            ]

            conn.register("temp", df)

            conn.execute("""
                INSERT OR REPLACE INTO daily_prices
                SELECT * FROM temp
            """)

            rows = len(df)
            success += 1
            total_rows += rows

    except Exception as e:
        status = "FAILED"
        error = str(e)
        failed += 1

    elapsed = round(time.perf_counter() - ticker_start, 2)

    # =====================================================
    # LOG EACH TICKER
    # =====================================================

    conn.execute("""
        INSERT INTO download_log
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, [
        run_id,
        ticker,
        start,
        end,
        rows,
        elapsed,
        status,
        error
    ])

    print(f"{ticker} | {status} | rows={rows} | {elapsed}s")

# =========================================================
# PIPELINE SUMMARY
# =========================================================

overall_time = round(time.perf_counter() - overall_start, 2)
end_time = datetime.now()

status = "SUCCESS" if failed == 0 else "PARTIAL"

conn.execute("""
INSERT INTO pipeline_runs VALUES (
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
)
""", [
    run_id,
    pipeline_name,
    datetime.now(),
    end_time,
    len(tickers),
    success,
    failed,
    total_rows,
    overall_time,
    status
])

# =========================================================
# FINAL REPORT
# =========================================================

print("\n" + "=" * 60)
print("PIPELINE COMPLETE (RATE LIMIT SAFE)")
print("=" * 60)
print(f"Run ID        : {run_id}")
print(f"Tickers       : {len(tickers)}")
print(f"Success       : {success}")
print(f"Failed        : {failed}")
print(f"Total Rows    : {total_rows}")
print(f"Execution Time: {overall_time:.2f} sec")
print("=" * 60)

conn.close()