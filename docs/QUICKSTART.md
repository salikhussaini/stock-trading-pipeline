# Quick Start Guide

Get the stock trading pipeline up and running in 5 minutes.

## Prerequisites

- Python 3.9 or later
- pip (Python package manager)
- ~500MB disk space (database + logs)
- Internet connection (for yfinance API)

## 1. Initial Setup (2 minutes)

### Clone or Download

```bash
# Clone from GitHub
git clone https://github.com/yourusername/stock-trading-pipeline.git
cd stock-trading-pipeline

# Or download ZIP and extract
```

### Create Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

## 2. Quick Test (1 minute)

Test the pipeline with a small sample:

```bash
# Download data for 10 tickers (test mode)
python incremental_collector.py --test

# Generate features
python feature_engine.py

# Backtest 5 tickers, 5 strategies
python backtester.py --limit 5 --num-workers 2
```

**Expected Output:**
- ✅ Logs show successful data downloads
- ✅ Feature file created: `database/stock_features.parquet`
- ✅ Backtest results stored in database
- ✅ Results printed with strategy rankings

## 3. Full Pipeline (Optional, takes ~3 hours)

Run the complete backtester on all 500 tickers:

```bash
python backtester.py
```

Monitor progress with logs:
```bash
tail -f logs/pipeline.log      # macOS/Linux
Get-Content logs/pipeline.log -Tail 20 -Wait  # Windows PowerShell
```

## 4. Analyze Results

Query backtester results:

```bash
python query_backtest_results.py
```

Or in Python:
```python
from query_backtest_results import *
import duckdb

conn = duckdb.connect('database/stock_data.duckdb')

# Top strategies
top_strats = conn.execute("""
    SELECT strategy_name, AVG(sharpe_ratio) as avg_sharpe, COUNT(*) as num_tests
    FROM backtest_results
    GROUP BY strategy_name
    ORDER BY avg_sharpe DESC
    LIMIT 10
""").fetchall()

for row in top_strats:
    print(f"{row[0]}: Sharpe {row[1]:.2f} ({row[2]} tests)")

# Top tickers
top_tickers = conn.execute("""
    SELECT ticker, AVG(total_return) as avg_return
    FROM backtest_results
    WHERE total_return > 0
    GROUP BY ticker
    ORDER BY avg_return DESC
    LIMIT 10
""").fetchall()

for row in top_tickers:
    print(f"{row[0]}: {row[1]:.1f}% return")
```

## Directory Structure

```
stock-trading-pipeline/
├── database/                      # Created after first run
│   ├── stock_data.duckdb         # Historical prices & cache
│   └── stock_features.parquet    # Computed features
│
├── logs/                          # Created after first run
│   ├── pipeline.log              # Rolling log file
│   └── pipeline_YYYYMMDD_*.log   # Session-specific logs
│
├── backtester.py                  # Strategy backtesting
├── feature_engine.py              # Feature generation
├── incremental_collector.py       # Data collection
├── logger_config.py               # Logging configuration
├── tickers.csv                    # Stock symbols to analyze
└── requirements.txt               # Python packages
```

## Common Tasks

### Download Latest Data

```bash
# Download data for all tickers (incremental, only new dates)
python incremental_collector.py

# Download specific ticker
python incremental_collector.py --tickers AAPL,MSFT

# Limit to N tickers
python incremental_collector.py --limit 50

# Parallel downloads (more workers = faster, but more API calls)
python incremental_collector.py --workers 4
```

### Regenerate Features

```bash
# Compute technical indicators for all tickers
python feature_engine.py

# Use more workers for faster computation
python feature_engine.py  # Default 8 workers
```

### Backtest Strategies

```bash
# Quick test (10 tickers, all strategies)
python backtester.py --limit 10

# Full backtest (all tickers, all strategies)
python backtester.py

# Specific strategy only
python -c "from backtester import run_backtest; run_backtest(strategies=['rsi_classic'])"

# Test with different worker count
python backtester.py --num-workers 4
```

### Add New Tickers

Edit `tickers.csv`:
```csv
AAPL
GOOGL
MSFT
YOUR_TICKER_HERE
```

Then:
```bash
python incremental_collector.py --tickers YOUR_TICKER_HERE
python feature_engine.py
python backtester.py --limit 1  # Test one ticker
```

## Customizing the Pipeline

### Change Stock Universe

Edit `tickers.csv` to add/remove tickers:
```csv
# Add your tickers
SPY
QQQ
IWM
```

### Adjust Features

Edit `feature_engine.py`, modify `compute_ticker_features()`:
```python
# Example: Add custom indicator
df['my_indicator'] = ...  # Your calculation
```

### Create Custom Strategy

Edit `backtester.py`, add to `STRATEGIES`:
```python
def my_strategy(df: pd.DataFrame) -> pd.DataFrame:
    """Your strategy logic here"""
    df = df.copy()
    df['signal'] = 0
    
    # Buy condition
    buy = (df['rsi_14'] < 30)
    df.loc[buy, 'signal'] = 1
    
    # Sell condition  
    sell = (df['rsi_14'] > 70)
    df.loc[sell, 'signal'] = -1
    
    return df

STRATEGIES['my_strategy'] = my_strategy
```

Test it:
```bash
python backtester.py --limit 10  # Will include your new strategy
```

## Logging

All operations log to:
- **Console**: INFO level (progress updates)
- **logs/pipeline.log**: Rolling file (10MB max, 5 backups)
- **logs/pipeline_[timestamp].log**: Session-specific detailed logs

View logs:
```bash
# Watch live logs
tail -f logs/pipeline.log              # macOS/Linux

# View session logs
ls -la logs/pipeline_*.log

# View specific date range
grep "2026-06-29" logs/pipeline.log
```

## Troubleshooting

### Import Error: "No module named 'duckdb'"

```bash
# Reinstall dependencies
pip install -r requirements.txt

# Or install individually
pip install duckdb pandas yfinance
```

### "SSL: CERTIFICATE_VERIFY_FAILED"

On macOS, run:
```bash
/Applications/Python\ 3.x/Install\ Certificates.command
```

Or install certificates via homebrew:
```bash
brew install --cask python-tk
```

### "ConnectionRefusedError" or Database locked

```bash
# The database might be in use by another process
# Make sure no other Python processes are running

# On Windows:
taskkill /F /IM python.exe

# On macOS/Linux:
pkill -f python
```

### Memory Error

If you get `MemoryError`, reduce parallel workers:
```bash
python feature_engine.py --workers 2
python backtester.py --num-workers 2
```

### No Data for Ticker

Some tickers might not have enough historical data:
- Less than 50 days → excluded by feature_engine.py
- Check logs for which tickers were skipped
- Add more tickers to `tickers.csv`

## Performance Tips

### Faster Execution

- **More Workers**: `python backtester.py --num-workers 8` (if you have CPU cores)
- **Fewer Tickers**: `python backtester.py --limit 50` for testing
- **Cache Reuse**: Don't force re-run: `python backtester.py` (not `--force-rerun`)

### Slower Execution (More Accurate)

- **Fewer Workers**: Better for I/O limited systems
- **More Tickers**: Full dataset = longer runtime but better statistics
- **Smaller Lookback**: Modify features to use shorter windows

## Next Steps

1. **Understand Results**: Read [CHANGELOG.md](CHANGELOG.md) for strategy details
2. **Explore Code**: See [README.md](README.md) for architecture overview
3. **Contribute**: Check [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines
4. **Version Control**: See [GIT_SETUP.md](GIT_SETUP.md) for git workflow

## Quick Reference

```bash
# One-liner to run entire pipeline
python incremental_collector.py && python feature_engine.py && python backtester.py

# Watch progress
tail -f logs/pipeline.log

# Check database
python -c "import duckdb; c = duckdb.connect('database/stock_data.duckdb'); print(c.execute('SELECT COUNT(*) FROM daily_prices').fetchall())"

# Clean up (DELETE ALL DATA!)
rm database/stock_data.duckdb database/stock_features.parquet logs/*.log*
```

## FAQ

**Q: Can I run this on Windows/Mac/Linux?**  
A: Yes, fully cross-platform (Python 3.9+)

**Q: How much data do you need?**  
A: Minimum 50 days per ticker, typically 5+ years recommended

**Q: Can I modify strategies?**  
A: Yes! Edit backtester.py and add your own in STRATEGIES dict

**Q: How do I avoid API rate limits?**  
A: Use `--limit` for testing, incremental_collector.py automatically throttles

**Q: Why is the first run slow?**  
A: Initial download and feature computation can take 1-2 hours for 500 tickers

**Q: Can I use this for real trading?**  
A: ⚠️ No! This is educational. See LICENSE for disclaimer.

---

**Ready to start?** Run: `python incremental_collector.py --test`

For detailed documentation, see [README.md](README.md)
