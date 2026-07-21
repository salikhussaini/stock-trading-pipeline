# =========================================================
# fundamental_collector.py
# Collect fundamental data for ML feature enhancement
# Adds: P/E, P/B, short ratio, insider holdings, etc.
# =========================================================

import numpy as np
import pandas as pd
import yfinance as yf
import duckdb
from pathlib import Path
from datetime import datetime
import time
import sys
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from logger_config import (
    log_info, log_error, log_exception, log_warning,
    log_section, log_pipeline_start, log_pipeline_end, log_metrics
)

# Configuration
BASE_DIR = Path(__file__).parent.parent
TICKERS_FILE = BASE_DIR / "tickers.csv"
FUNDAMENTALS_PATH = BASE_DIR / "database" / "stock_fundamentals.parquet"

# CLI arguments
parser = argparse.ArgumentParser(description="Collect fundamental data for stocks")
parser.add_argument("--test", action="store_true", help="Test mode (10 tickers)")
parser.add_argument("--limit", type=int, default=0, help="Limit number of tickers")
parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers")
args = parser.parse_args()

# =========================================================
# FUNDAMENTAL DATA COLLECTOR
# =========================================================

def get_ticker_fundamentals(ticker):
    """
    Fetch fundamental data for a single ticker using yfinance.
    Returns dict with fundamental metrics.
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Extract key fundamental metrics
        fundamentals = {
            'ticker': ticker,
            'update_date': datetime.now().date(),
            
            # Valuation metrics
            'pe_ratio': info.get('forwardPE', np.nan),
            'trailing_pe': info.get('trailingPE', np.nan),
            'pb_ratio': info.get('priceToBook', np.nan),
            'ps_ratio': info.get('priceToSalesTrailing12Months', np.nan),
            'peg_ratio': info.get('pegRatio', np.nan),
            
            # Growth metrics
            'earnings_growth': info.get('earningsQuarterlyGrowth', np.nan),
            'revenue_growth': info.get('revenueGrowth', np.nan),
            
            # Profitability
            'profit_margin': info.get('profitMargins', np.nan),
            'operating_margin': info.get('operatingMargins', np.nan),
            'roe': info.get('returnOnEquity', np.nan),
            'roa': info.get('returnOnAssets', np.nan),
            
            # Financial health
            'debt_to_equity': info.get('debtToEquity', np.nan),
            'current_ratio': info.get('currentRatio', np.nan),
            'quick_ratio': info.get('quickRatio', np.nan),
            
            # Ownership & sentiment
            'insider_pct': info.get('heldPercentInsiders', np.nan),
            'institution_pct': info.get('heldPercentInstitutions', np.nan),
            'short_ratio': info.get('shortRatio', np.nan),
            'short_pct_float': info.get('shortPercentOfFloat', np.nan),
            
            # Analyst ratings
            'target_mean_price': info.get('targetMeanPrice', np.nan),
            'target_median_price': info.get('targetMedianPrice', np.nan),
            'recommendation_mean': info.get('recommendationMean', np.nan),  # 1=Strong Buy, 5=Sell
            'num_analyst_opinions': info.get('numberOfAnalystOpinions', np.nan),
            
            # Dividend
            'dividend_yield': info.get('dividendYield', np.nan),
            'payout_ratio': info.get('payoutRatio', np.nan),
            
            # Size
            'market_cap': info.get('marketCap', np.nan),
            'enterprise_value': info.get('enterpriseValue', np.nan),
            
            # Beta (volatility vs market)
            'beta': info.get('beta', np.nan),
        }
        
        log_info(f"{ticker} | SUCCESS | P/E={fundamentals['pe_ratio']:.2f if not np.isnan(fundamentals['pe_ratio']) else 'N/A'}")
        return fundamentals
        
    except Exception as e:
        log_error(f"{ticker} | FAILED | {str(e)[:100]}")
        return {
            'ticker': ticker,
            'update_date': datetime.now().date(),
            'error': str(e)
        }

def collect_fundamentals(tickers, workers=4):
    """
    Collect fundamental data for all tickers in parallel.
    """
    log_section("Fundamental Data Collection")
    log_info(f"Collecting fundamentals for {len(tickers)} tickers with {workers} workers")
    
    all_fundamentals = []
    success_count = 0
    fail_count = 0
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(get_ticker_fundamentals, ticker): ticker for ticker in tickers}
        
        for future in as_completed(futures):
            result = future.result()
            all_fundamentals.append(result)
            
            if 'error' not in result:
                success_count += 1
            else:
                fail_count += 1
            
            # Rate limiting (yfinance allows ~1-2 req/sec)
            time.sleep(0.5)
    
    df = pd.DataFrame(all_fundamentals)
    
    # Report statistics
    log_metrics({
        "Total Tickers": len(tickers),
        "Success": success_count,
        "Failed": fail_count,
        "Features Collected": len(df.columns) - 2  # Exclude ticker, update_date
    })
    
    return df

# =========================================================
# MAIN EXECUTION
# =========================================================

if __name__ == "__main__":
    log_pipeline_start("Fundamental Collector", tickers="loading...")
    
    try:
        # Load tickers
        df_tickers = pd.read_csv(TICKERS_FILE)
        tickers = df_tickers['ticker'].dropna().unique().tolist()
        log_info(f"Loaded {len(tickers)} tickers from {TICKERS_FILE.name}")
        
        # Apply test/limit flags
        if args.test and args.limit <= 0:
            args.limit = 10
        
        if args.limit > 0:
            tickers = tickers[:args.limit]
            log_info(f"Limited to {len(tickers)} tickers (test mode)")
        
        # Collect fundamentals
        start_time = time.perf_counter()
        df_fundamentals = collect_fundamentals(tickers, workers=args.workers)
        elapsed = time.perf_counter() - start_time
        
        # Save to parquet
        FUNDAMENTALS_PATH.parent.mkdir(parents=True, exist_ok=True)
        log_info(f"Saving fundamentals to {FUNDAMENTALS_PATH.name}...")
        
        conn = duckdb.connect()
        conn.execute(f"COPY df_fundamentals TO '{FUNDAMENTALS_PATH}' (FORMAT PARQUET, COMPRESSION 'snappy')")
        conn.close()
        
        file_size_mb = FUNDAMENTALS_PATH.stat().st_size / (1024 * 1024)
        log_info(f"Saved {len(df_fundamentals):,} rows, {file_size_mb:.1f} MB")
        
        log_pipeline_end("Fundamental Collector", status="SUCCESS", elapsed=f"{elapsed:.1f}s")
        
    except KeyboardInterrupt:
        log_warning("Pipeline interrupted by user")
        log_pipeline_end("Fundamental Collector", status="INTERRUPTED")
        sys.exit(1)
    except Exception as e:
        log_exception(e, "Fundamental Collector failed")
        log_pipeline_end("Fundamental Collector", status="FAILED")
        sys.exit(1)
