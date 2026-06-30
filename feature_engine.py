# =========================================================
# feature_engine.py
# Stock Feature Generation Pipeline (DuckDB → Features)
# SHORT-TERM vs LONG-TERM Indicator Organization
# Parallel Processing by Ticker with 75+ Advanced Indicators
# =========================================================

from pathlib import Path
import duckdb
import pandas as pd
import numpy as np
import traceback
import time
import sys
import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed

from logger_config import (
    log_info, log_error, log_exception, log_warning,
    log_section, log_pipeline_start, log_pipeline_end, log_metrics
)

DB_PATH = Path(__file__).parent / "database" / "stock_data.duckdb"
FEATURES_PATH = Path(__file__).parent / "database" / "stock_features.parquet"

# Configuration
MIN_DATA_POINTS = 50  # Minimum rows required to compute features
CHUNK_SIZE = 50000  # Batch insert size (increased for better I/O)
MAX_NAN_RATIO = 0.3  # Drop rows where >30% of features are NaN

# =========================================================
# FEATURE CATEGORIES BY TIMEFRAME
# =========================================================
# SHORT-TERM (1-14 day lookback): Scalping, day trading, swing trading
#   - Fast RSI (7, 14), Fast Stochastic (5, 14), Fast MACD
#   - Short-term moving averages (5, 10 days)
#   - Quick momentum & volatility metrics
#
# LONG-TERM (20+ day lookback): Trend following, position trading
#   - Slow RSI (28, 42), Extended Stochastic (28)
#   - Long-term moving averages (20, 50 days)
#   - ADX trend strength, sustained momentum
#
# CROSS-TIMEFRAME DIVERGENCE:
#   - RSI/ROC/MACD divergence between short & long term
#   - Volatility ratio, momentum alignment for confluence signals
# =========================================================

# =========================================================
# HELPER FUNCTIONS (Module-level for multiprocessing compatibility)
# =========================================================

def rsi(series, period=14):
    """Compute Relative Strength Index"""
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def stochastic(high, low, close, period=14):
    """Compute Stochastic Oscillator %K"""
    lowest_low = low.rolling(period).min()
    highest_high = high.rolling(period).max()
    k = 100 * (close - lowest_low) / (highest_high - lowest_low + 1e-9)
    return k

def atr(high, low, close, period=14):
    """Compute Average True Range"""
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def adx(high, low, close, period=14):
    """Compute Average Directional Index (trend strength)"""
    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    plus_dm = plus_dm.where(plus_dm > minus_dm, 0)
    minus_dm = minus_dm.where(minus_dm > plus_dm, 0)
    
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_val = tr.rolling(period).mean()
    
    plus_di = 100 * plus_dm.rolling(period).mean() / (atr_val + 1e-9)
    minus_di = 100 * minus_dm.rolling(period).mean() / (atr_val + 1e-9)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    adx_val = dx.rolling(period).mean()
    return adx_val

# =========================================================
# FEATURE ENGINEERING FOR SINGLE TICKER (Worker Function)
# =========================================================

def compute_ticker_features(args: tuple) -> tuple:
    """
    Compute all features for a single ticker.
    Loads data directly from DuckDB to avoid passing large DataFrames across processes.
    Returns (DataFrame, ticker, error_msg or None)
    """
    ticker, db_path = args
    try:
        conn = duckdb.connect(db_path, read_only=True)
        ticker_data = conn.execute("""
            SELECT ticker, date, open, high, low, close, adj_close, volume
            FROM daily_prices
            WHERE ticker = ?
            ORDER BY date
        """, [ticker]).df()
        conn.close()

        # Skip if insufficient data
        if len(ticker_data) < MIN_DATA_POINTS:
            return None, ticker, f"Insufficient data ({len(ticker_data)} rows < {MIN_DATA_POINTS})"
        
        ticker_data = ticker_data.reset_index(drop=True)
        
        # Remove outliers (close > 3 std from mean)
        close_mean = ticker_data["close"].mean()
        close_std = ticker_data["close"].std()
        mask = (ticker_data["close"] - close_mean).abs() <= 3 * close_std
        if not mask.all():
            ticker_data = ticker_data[mask].reset_index(drop=True)

        # =========================================================
        # SHORT-TERM INDICATORS (1-14 day lookback)
        # =========================================================
        
        # Short-term Returns
        ticker_data["st_return_1d"] = ticker_data["close"].pct_change(1)
        ticker_data["st_return_5d"] = ticker_data["close"].pct_change(5)
        ticker_data["st_return_7d"] = ticker_data["close"].pct_change(7)
        
        # Short-term Moving Averages & Positioning
        ticker_data["st_sma_5"] = ticker_data["close"].rolling(5).mean()
        ticker_data["st_sma_10"] = ticker_data["close"].rolling(10).mean()
        ticker_data["st_ema_5"] = ticker_data["close"].ewm(span=5, adjust=False).mean()
        ticker_data["st_ema_10"] = ticker_data["close"].ewm(span=10, adjust=False).mean()
        
        # Short-term vs Moving Averages (trend alignment)
        ticker_data["st_above_sma5"] = (ticker_data["close"] > ticker_data["st_sma_5"]).astype(int)
        ticker_data["st_above_ema10"] = (ticker_data["close"] > ticker_data["st_ema_10"]).astype(int)
        
        # Short-term Volatility
        ticker_data["st_vol_5d"] = ticker_data["close"].pct_change().rolling(5).std()
        ticker_data["st_vol_10d"] = ticker_data["close"].pct_change().rolling(10).std()
        
        # Short-term RSI (fast oscillator)
        ticker_data["st_rsi_7"] = rsi(ticker_data["close"], 7)
        ticker_data["st_rsi_14"] = rsi(ticker_data["close"], 14)
        
        # Short-term Stochastic (fast)
        ticker_data["st_stoch_k_5"] = stochastic(
            ticker_data["high"], ticker_data["low"], ticker_data["close"], 5
        )
        ticker_data["st_stoch_k_14"] = stochastic(
            ticker_data["high"], ticker_data["low"], ticker_data["close"], 14
        )
        ticker_data["st_stoch_d_5"] = ticker_data["st_stoch_k_5"].rolling(3).mean()
        ticker_data["st_stoch_d_14"] = ticker_data["st_stoch_k_14"].rolling(3).mean()
        
        # Short-term Momentum
        ticker_data["st_momentum_5"] = ticker_data["close"] - ticker_data["close"].shift(5)
        ticker_data["st_momentum_10"] = ticker_data["close"] - ticker_data["close"].shift(10)
        ticker_data["st_roc_5"] = ticker_data["close"].pct_change(5)
        ticker_data["st_roc_7"] = ticker_data["close"].pct_change(7)
        
        # Short-term MACD (fast)
        st_ema5 = ticker_data["close"].ewm(span=5, adjust=False).mean()
        st_ema13 = ticker_data["close"].ewm(span=13, adjust=False).mean()
        ticker_data["st_macd"] = st_ema5 - st_ema13
        ticker_data["st_macd_signal"] = ticker_data["st_macd"].ewm(span=5, adjust=False).mean()
        ticker_data["st_macd_histogram"] = ticker_data["st_macd"] - ticker_data["st_macd_signal"]
        
        # Short-term ATR
        ticker_data["st_atr_7"] = atr(ticker_data["high"], ticker_data["low"], ticker_data["close"], 7)
        ticker_data["st_atr_ratio"] = ticker_data["st_atr_7"] / ticker_data["close"]
        
        # Short-term Volume
        vol_mean_5 = ticker_data["volume"].rolling(5).mean()
        vol_std_5 = ticker_data["volume"].rolling(5).std()
        ticker_data["st_volume_zscore_5d"] = (ticker_data["volume"] - vol_mean_5) / (vol_std_5 + 1e-9)
        ticker_data["st_volume_ratio_5d"] = ticker_data["volume"] / vol_mean_5

        # =========================================================
        # LONG-TERM INDICATORS (20+ day lookback)
        # =========================================================
        
        # Long-term Returns
        ticker_data["lt_return_20d"] = ticker_data["close"].pct_change(20)
        ticker_data["lt_return_50d"] = ticker_data["close"].pct_change(50)
        
        # Long-term Moving Averages & Positioning
        ticker_data["lt_sma_20"] = ticker_data["close"].rolling(20).mean()
        ticker_data["lt_sma_50"] = ticker_data["close"].rolling(50).mean()
        ticker_data["lt_ema_20"] = ticker_data["close"].ewm(span=20, adjust=False).mean()
        ticker_data["lt_ema_50"] = ticker_data["close"].ewm(span=50, adjust=False).mean()
        
        # Long-term vs Moving Averages (trend alignment)
        ticker_data["lt_above_sma20"] = (ticker_data["close"] > ticker_data["lt_sma_20"]).astype(int)
        ticker_data["lt_above_sma50"] = (ticker_data["close"] > ticker_data["lt_sma_50"]).astype(int)
        ticker_data["lt_sma_alignment"] = (ticker_data["lt_sma_20"] > ticker_data["lt_sma_50"]).astype(int)
        
        # Long-term Volatility
        ticker_data["lt_vol_20d"] = ticker_data["close"].pct_change().rolling(20).std()
        ticker_data["lt_vol_50d"] = ticker_data["close"].pct_change().rolling(50).std()
        
        # Long-term RSI (slow oscillator)
        ticker_data["lt_rsi_28"] = rsi(ticker_data["close"], 28)
        ticker_data["lt_rsi_42"] = rsi(ticker_data["close"], 42)
        
        # Long-term Stochastic
        ticker_data["lt_stoch_k_28"] = stochastic(
            ticker_data["high"], ticker_data["low"], ticker_data["close"], 28
        )
        ticker_data["lt_stoch_d_28"] = ticker_data["lt_stoch_k_28"].rolling(3).mean()
        
        # Long-term Momentum
        ticker_data["lt_momentum_20"] = ticker_data["close"] - ticker_data["close"].shift(20)
        ticker_data["lt_momentum_50"] = ticker_data["close"] - ticker_data["close"].shift(50)
        ticker_data["lt_roc_20"] = ticker_data["close"].pct_change(20)
        ticker_data["lt_roc_50"] = ticker_data["close"].pct_change(50)
        
        # Long-term MACD (standard)
        lt_ema12 = ticker_data["close"].ewm(span=12, adjust=False).mean()
        lt_ema26 = ticker_data["close"].ewm(span=26, adjust=False).mean()
        ticker_data["lt_macd"] = lt_ema12 - lt_ema26
        ticker_data["lt_macd_signal"] = ticker_data["lt_macd"].ewm(span=9, adjust=False).mean()
        ticker_data["lt_macd_histogram"] = ticker_data["lt_macd"] - ticker_data["lt_macd_signal"]
        
        # Long-term ADX (trend strength)
        ticker_data["lt_adx_14"] = adx(ticker_data["high"], ticker_data["low"], ticker_data["close"], 14)
        ticker_data["lt_adx_28"] = adx(ticker_data["high"], ticker_data["low"], ticker_data["close"], 28)
        
        # Long-term ATR
        ticker_data["lt_atr_14"] = atr(ticker_data["high"], ticker_data["low"], ticker_data["close"], 14)
        ticker_data["lt_atr_ratio"] = ticker_data["lt_atr_14"] / ticker_data["close"]
        
        # Long-term Bollinger Bands
        lt_sma20 = ticker_data["close"].rolling(20).mean()
        lt_std20 = ticker_data["close"].rolling(20).std()
        ticker_data["lt_bb_upper"] = lt_sma20 + (lt_std20 * 2)
        ticker_data["lt_bb_lower"] = lt_sma20 - (lt_std20 * 2)
        ticker_data["lt_bb_width"] = (ticker_data["lt_bb_upper"] - ticker_data["lt_bb_lower"]) / lt_sma20
        ticker_data["lt_bb_position"] = (ticker_data["close"] - ticker_data["lt_bb_lower"]) / (
            ticker_data["lt_bb_upper"] - ticker_data["lt_bb_lower"] + 1e-9
        )
        
        # Long-term Volume
        vol_mean_20 = ticker_data["volume"].rolling(20).mean()
        vol_std_20 = ticker_data["volume"].rolling(20).std()
        ticker_data["lt_volume_zscore_20d"] = (ticker_data["volume"] - vol_mean_20) / (vol_std_20 + 1e-9)
        ticker_data["lt_volume_ratio_20d"] = ticker_data["volume"] / vol_mean_20

        # =========================================================
        # PRICE ACTION (Timeframe-agnostic)
        # =========================================================
        ticker_data["high_low_ratio"] = ticker_data["high"] / ticker_data["low"]
        ticker_data["close_open_ratio"] = ticker_data["close"] / ticker_data["open"]
        ticker_data["close_position"] = (ticker_data["close"] - ticker_data["low"]) / (
            ticker_data["high"] - ticker_data["low"] + 1e-9
        )

        # =========================================================
        # CROSS-TIMEFRAME COMPARATIVE METRICS (ST vs LT divergence)
        # =========================================================
        ticker_data["rsi_divergence_7_28"] = ticker_data["st_rsi_7"] - ticker_data["lt_rsi_28"]
        ticker_data["roc_divergence_5_20"] = ticker_data["st_roc_5"] - ticker_data["lt_roc_20"]
        ticker_data["macd_divergence"] = ticker_data["st_macd"] - ticker_data["lt_macd"]
        ticker_data["vol_ratio_st_lt"] = ticker_data["st_vol_5d"] / (ticker_data["lt_vol_20d"] + 1e-9)
        ticker_data["momentum_alignment"] = (
            (ticker_data["st_momentum_5"] > 0).astype(int) + 
            (ticker_data["lt_momentum_20"] > 0).astype(int)
        )  # 0=both down, 1=divergence, 2=both up

        return ticker_data, ticker, None

    except Exception as e:
        ticker = ticker_data["ticker"].iloc[0] if len(ticker_data) > 0 else "UNKNOWN"
        error_msg = f"{type(e).__name__}: {str(e)}"
        return None, ticker, error_msg

# =========================================================
# MAIN PIPELINE (PARALLEL BY TICKER)
# =========================================================

def run_feature_pipeline(num_workers=8):
    """
    Run feature engineering pipeline with parallel processing.
    Each worker loads its own data from DuckDB and computes features independently.
    Uses ProcessPoolExecutor on Linux/Mac (true multiprocessing via fork).
    Uses ThreadPoolExecutor on Windows (avoids pickling issues).
    """
    conn = duckdb.connect(str(DB_PATH))

    # -------------------------
    # VALIDATE INPUT
    # -------------------------
    ticker_count = conn.execute("SELECT COUNT(DISTINCT ticker) FROM daily_prices").fetchone()[0]
    if ticker_count == 0:
        log_error("No data found in daily_prices")
        conn.close()
        return

    tickers = [row[0] for row in conn.execute("SELECT DISTINCT ticker FROM daily_prices ORDER BY ticker").fetchall()]
    total_rows = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
    conn.close()

    num_tickers = len(tickers)
    
    # -------------------------
    # SELECT EXECUTOR (Platform-specific optimization)
    # -------------------------
    if sys.platform == 'win32':
        executor_class = ThreadPoolExecutor
        executor_type = "Threading"
    else:
        executor_class = ProcessPoolExecutor
        executor_type = "Multiprocessing"
    
    log_info(f"Processing {num_tickers} tickers ({total_rows:,} rows) with {num_workers} workers ({executor_type})...")

    # -------------------------
    # PARALLEL FEATURE COMPUTATION WITH PROGRESS TRACKING
    # Workers load their own data from DuckDB (avoids forking large DataFrames)
    # -------------------------
    db_path = str(DB_PATH)
    task_args = [(ticker, db_path) for ticker in tickers]

    all_results = []
    failed_tickers = []
    successful_tickers = []
    
    load_start = time.perf_counter()
    process_start = load_start
    
    try:
        with executor_class(max_workers=num_workers) as executor:
            # Submit all tasks as (ticker, db_path) tuples - no large DataFrame passing
            futures = {executor.submit(compute_ticker_features, args): args[0]
                      for args in task_args}
            
            # Process results as they complete (with progress tracking)
            completed = 0
            for future in as_completed(futures):
                ticker = futures[future]
                try:
                    result_df, ticker_name, error = future.result()
                    completed += 1
                    
                    if error:
                        failed_tickers.append((ticker_name, error))
                        if completed % 50 == 0:  # Log progress every 50 tickers
                            log_info(f"  Progress: {completed}/{num_tickers} ({completed/num_tickers*100:.0f}%)")
                    else:
                        all_results.append(result_df)
                        successful_tickers.append(ticker_name)
                        if completed % 50 == 0:
                            log_info(f"  Progress: {completed}/{num_tickers} ({completed/num_tickers*100:.0f}%)")
                        
                except Exception as e:
                    failed_tickers.append((ticker, f"Processing error: {str(e)}"))
                    completed += 1
                    
    except Exception as e:
        log_exception(e, "Parallel processing failed")
        conn.close()
        return

    process_time = time.perf_counter() - process_start
    log_info(f"Feature computation: {process_time:.1f}s ({num_tickers/process_time:.1f} tickers/sec)")
    log_info(f"Success: {len(successful_tickers)}/{num_tickers} | Failed: {len(failed_tickers)}")

    if failed_tickers:
        log_warning(f"Failed tickers ({len(failed_tickers)}):")
        for ticker, error in failed_tickers[:10]:  # Show first 10 errors
            log_warning(f"  {ticker}: {error}")
        if len(failed_tickers) > 10:
            log_warning(f"  ... and {len(failed_tickers)-10} more")

    if not all_results:
        log_error("No valid features generated")
        conn.close()
        return

    # -------------------------
    # COMBINE RESULTS (already in wide format)
    # -------------------------
    log_info("Combining results...")
    combine_start = time.perf_counter()
    df_feat = pd.concat(all_results, ignore_index=True)
    combine_time = time.perf_counter() - combine_start

    # rename date → report_date
    df_feat = df_feat.rename(columns={"date": "report_date"})

    # -------------------------
    # DATA QUALITY CHECKS
    # -------------------------
    feature_cols = [col for col in df_feat.columns if col not in ['ticker', 'report_date', 'close', 'volume']]
    initial_rows = len(df_feat)
    
    # Count NaN values per row
    nan_counts = df_feat[feature_cols].isna().sum(axis=1)
    nan_ratio = nan_counts / len(feature_cols)
    
    # Filter rows with too many NaN features
    valid_mask = nan_ratio <= MAX_NAN_RATIO
    rows_dropped = (~valid_mask).sum()
    
    if rows_dropped > 0:
        df_feat = df_feat[valid_mask].reset_index(drop=True)
        log_info(f"Dropped {rows_dropped:,} rows with >{MAX_NAN_RATIO*100:.0f}% NaN features ({rows_dropped/initial_rows*100:.1f}%)")

    log_info(f"Generated {len(df_feat):,} feature rows ({df_feat['ticker'].nunique()} tickers) with {len(feature_cols)} features")
    log_info(f"  Combine time: {combine_time:.1f}s")
    
    # Log feature NaN statistics
    nan_pct = df_feat[feature_cols].isna().mean() * 100
    if nan_pct.max() > 0:
        worst_features = nan_pct.nlargest(5)
        log_info(f"  Top NaN features: {', '.join([f'{col}({pct:.1f}%)' for col, pct in worst_features.items()])}")

    # -------------------------
    # WRITE TO PARQUET (Fast, compressed storage via DuckDB)
    # Keep only ticker, report_date, close, volume, and computed features (drop raw OHLCV)
    # -------------------------
    raw_cols = ["open", "high", "low", "adj_close"]
    df_feat = df_feat.drop(columns=raw_cols, errors="ignore")
    
    log_info(f"Writing to parquet...")
    write_start = time.perf_counter()
    # Use DuckDB to write parquet (10x faster than pandas.to_parquet for large datasets)
    conn.execute(f"COPY df_feat TO '{FEATURES_PATH}' (FORMAT PARQUET, COMPRESSION 'snappy')")
    write_time = time.perf_counter() - write_start

    file_size_mb = FEATURES_PATH.stat().st_size / (1024 * 1024)
    
    conn.close()

    log_info(f"Parquet write: {write_time:.1f}s ({len(df_feat)/write_time:,.0f} rows/sec)")
    log_info(f"File size: {file_size_mb:.1f} MB")
    log_info(f"Features saved to: {FEATURES_PATH}")
    
    # -------------------------
    # FINAL METRICS
    # -------------------------
    total_time = time.perf_counter() - process_start
    log_metrics({
        "Total Time": f"{total_time:.1f}s",
        "Tickers Processed": f"{len(successful_tickers)}/{num_tickers}",
        "Feature Rows": f"{len(df_feat):,}",
        "Features": len(feature_cols),
        "File Size": f"{file_size_mb:.1f} MB"
    })

# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Stock feature engineering pipeline")
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 4), 
                       help="Number of parallel workers (default: min(8, CPU count))")
    args = parser.parse_args()
    
    log_pipeline_start("Feature Engine", tickers="all", workers=args.workers)
    
    try:
        run_feature_pipeline(num_workers=args.workers)
        log_pipeline_end("Feature Engine", status="SUCCESS")
    except KeyboardInterrupt:
        log_warning("Pipeline interrupted by user")
        log_pipeline_end("Feature Engine", status="INTERRUPTED")
        sys.exit(1)
    except Exception as e:
        log_exception(e, "Feature Engine failed")
        log_pipeline_end("Feature Engine", status="FAILED")
        sys.exit(1)