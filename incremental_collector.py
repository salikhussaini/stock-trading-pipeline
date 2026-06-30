# =========================================================
# incremental_collector.py
# Hardened + Parallel + Adaptive + Thread-Safe
# =========================================================

from pathlib import Path
from datetime import datetime, timedelta, date
import uuid
import time
import random
import queue
import threading

import duckdb
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse

from logger_config import (
    log_info, log_error, log_warning, log_exception,
    log_section, log_pipeline_start, log_pipeline_end, log_metrics
)

# ================================================================
# HELPERS
# =========================================================

def get_last_trading_day():
    """
    Returns the last COMPLETE trading day (skips weekends/holidays).
    Subtracts 1 day first to avoid requesting incomplete intraday data.
    """
    today = datetime.today().date() - timedelta(days=1)  # Go back 1 day to ensure complete data
    # Weekday: 0=Mon, 1=Tue, ..., 5=Sat, 6=Sun
    while today.weekday() > 4:  # Skip Saturday (5) and Sunday (6)
        today -= timedelta(days=1)
    return today

# =========================================================
# CONFIG
# =========================================================

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "database" / "stock_data.duckdb"
TICKERS_FILE = BASE_DIR / "tickers.csv"

run_id = str(uuid.uuid4())
pipeline_name = "incremental_collector_hardened"

# -------------------------
# CLI flags for test runs
# -------------------------
parser = argparse.ArgumentParser(description="Incremental stock data collector")
parser.add_argument("--test", action="store_true", help="Run a quick test using a small subset of tickers")
parser.add_argument("--limit", type=int, default=0, help="Limit number of tickers (0 = all)")
parser.add_argument("--workers", type=int, default=8, help="Number of worker threads")
args = parser.parse_args()


# =========================================================
# GLOBAL ADAPTIVE THROTTLE
# =========================================================

global_delay = 0.4
delay_lock = threading.Lock()

def increase_delay():
    global global_delay
    with delay_lock:
        global_delay = min(3.0, global_delay + 0.5)

def decrease_delay():
    global global_delay
    with delay_lock:
        global_delay = max(0.2, global_delay - 0.05)

# =========================================================
# LOG QUEUE - REMOVED (using global logger instead)
# =========================================================
# Logging is now handled by logger_config.py

# =========================================================
# TABLE INIT (main connection only)
# =========================================================

main_conn = duckdb.connect(str(DB_PATH))

main_conn.execute("""
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

main_conn.execute("""
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

main_conn.execute("""
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

main_conn.execute("""
CREATE TABLE IF NOT EXISTS ticker_state (
    ticker VARCHAR PRIMARY KEY,
    last_date DATE
)
""")

# =========================================================
# LOAD S&P 500 (CLEANED)
# =========================================================
try:
    local = TICKERS_FILE
    if local.exists():
        df_local = pd.read_csv(local)
        if "Symbol" in df_local.columns:
            tickers = df_local["Symbol"].str.replace(".", "-", regex=False).tolist()
        else:
            # assume one symbol per line
            tickers = df_local.iloc[:, 0].astype(str).str.strip().tolist()
    else:
        raise FileNotFoundError("tickers.csv not found")
except Exception as e2:
    print("Error: no tickers available:", repr(e2))
    raise

log_info(f"Tickers loaded: {len(tickers)}")
log_info(f"Run ID: {run_id}")

# apply CLI test/limit flags
if args.test and args.limit <= 0:
    args.limit = 10

if args.limit and args.limit > 0:
    tickers = tickers[: args.limit]
    log_info(f"Using limited tickers: {len(tickers)}")

# =========================================================
# METRICS
# =========================================================

success = 0
failed = 0
total_rows = 0
metrics_lock = threading.Lock()
overall_start = time.perf_counter()

# =========================================================
# SAFE DOWNLOAD
# =========================================================
def safe_yf_download(ticker, start, end, retries=3):

    base_delay = 1.0

    # ensure start/end are strings in ISO format
    if isinstance(start, (datetime, date)):
        start = start.strftime("%Y-%m-%d")
    if isinstance(end, (datetime, date)):
        end = end.strftime("%Y-%m-%d")

    for i in range(retries):

        try:
            df = yf.download(
                ticker,
                start=start,
                end=end,
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False
            )

            if df is None or df.empty:
                raise ValueError("empty response")

            return df

        except Exception as e:
            # wait then retry
            time.sleep(base_delay * (2 ** i) + random.uniform(0, 0.5))

    return None

# =========================================================
# WORKER
# =========================================================

def process_ticker(ticker):

    global success, failed, total_rows, global_delay

    start_time = time.perf_counter()

    status = "SUCCESS"
    error = None
    rows = 0
    start_date = None
    end_date = None

    try:
        # -------------------------
        # LOCAL DB CONNECTION (THREAD SAFE)
        # -------------------------
        conn = duckdb.connect(str(DB_PATH))

        # -------------------------
        # STATE LOOKUP
        # -------------------------
        latest = conn.execute("""
            SELECT last_date FROM ticker_state WHERE ticker = ?
        """, [ticker]).fetchone()

        if not latest or latest[0] is None:
            start_date = date(2000, 1, 1)
        else:
            ld = latest[0]
            # ld may be a datetime.date, datetime.datetime, or pandas Timestamp
            if isinstance(ld, datetime):
                start_date = (ld + timedelta(days=1)).date()
            else:
                # ld is already a date object from the database
                start_date = ld + timedelta(days=1)

        end_date = get_last_trading_day()

        if start_date >= end_date:
            conn.close()
            status = "SKIPPED"
            error = "Already up-to-date"
        else:
            # -------------------------
            # ADAPTIVE THROTTLE
            # -------------------------
            with delay_lock:
                delay = global_delay

            time.sleep(delay + random.uniform(0.1, 0.5))

            # -------------------------
            # DOWNLOAD
            # -------------------------
            df = safe_yf_download(ticker, start_date, end_date)

            if df is None or df.empty:
                raise ValueError("download failed")

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
                ["ticker", "date", "open", "high", "low", "close", "adj_close", "volume"]
            ]

            # -------------------------
            # WRITE DATA: clear existing records for this ticker+date range then insert
            # (using DuckDB append() for direct DataFrame insert)
            min_date = df["date"].min()
            max_date = df["date"].max()
            conn.execute("""
                DELETE FROM daily_prices WHERE ticker = ? AND date >= ? AND date <= ?
            """, [ticker, min_date, max_date])

            # Use DuckDB's append() for direct DataFrame insert (more reliable than register+SELECT)
            conn.append("daily_prices", df)

            rows = len(df)

            # -------------------------
            # UPDATE STATE
            # -------------------------
            # -------------------------
            # TICKER STATE UPSERT
            # -------------------------
            last_date = df["date"].max()
            # ensure last_date is a string/date
            if isinstance(last_date, (datetime, date)):
                last_date_val = last_date.strftime("%Y-%m-%d")
            else:
                last_date_val = str(last_date)

            conn.execute("""
                MERGE INTO ticker_state AS t
                USING (SELECT ? AS ticker, ?::DATE AS last_date) AS s
                ON t.ticker = s.ticker
                WHEN MATCHED THEN UPDATE SET last_date = s.last_date
                WHEN NOT MATCHED THEN INSERT (ticker, last_date) VALUES (s.ticker, s.last_date)
            """, [ticker, last_date_val])

            conn.close()

            with metrics_lock:
                success += 1
                total_rows += rows

            decrease_delay()

        # Close connection if it wasn't already closed
        if conn and not conn.closed:
            conn.close()

    except Exception as e:

        status = "FAILED"
        error = str(e)
        with metrics_lock:
            failed += 1

        increase_delay()
        log_error(f"{ticker} failed: {str(e)}")

    elapsed = round(time.perf_counter() - start_time, 2)
    
    # Log the result
    if status == "SUCCESS":
        log_info(f"{ticker} | {status} | rows={rows} | {elapsed}s")
    elif status == "SKIPPED":
        log_info(f"{ticker} | {status} | {error}")
    else:
        log_error(f"{ticker} | {status} | {error}")

# =========================================================
# LOG WRITER - REMOVED (using global logger instead)
# =========================================================
# Logging is now handled by logger_config.py

# =========================================================
# PARALLEL EXECUTION
# =========================================================

log_pipeline_start(
    "Incremental Collector",
    workers=args.workers,
    tickers=len(tickers)
)

with ThreadPoolExecutor(max_workers=args.workers) as executor:
    futures = [executor.submit(process_ticker, t) for t in tickers]
    for fut in as_completed(futures):
        try:
            fut.result()
        except Exception as e:
            log_exception(e, "Worker exception")

# =========================================================
# SUMMARY
# =========================================================

total_time = round(time.perf_counter() - overall_start, 2)
start_time = datetime.fromtimestamp(overall_start)
end_time = datetime.now()

main_conn.execute("""
INSERT INTO pipeline_runs VALUES (
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
)
""", [
    run_id,
    pipeline_name,
    start_time,
    end_time,
    len(tickers),
    success,
    failed,
    total_rows,
    total_time,
    "SUCCESS" if failed == 0 else "PARTIAL"
])

main_conn.close()

# =========================================================
# FINAL OUTPUT
# =========================================================

metrics = {
    "Run ID": run_id,
    "Tickers": len(tickers),
    "Success": success,
    "Failed": failed,
    "Total Rows": total_rows,
    "Time (s)": f"{total_time:.2f}"
}

log_pipeline_end(
    "Incremental Collector",
    status="SUCCESS" if failed == 0 else "PARTIAL",
    **metrics
)
