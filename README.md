# Stock Trading Pipeline

A production-grade Python system for analyzing stock market data with technical indicators and strategy backtesting.

**Features:**
- 📊 Download & process 500+ stock tickers with parallel execution
- 🔧 Compute 46+ technical indicators (RSI, MACD, Bollinger Bands, etc.)
- 🎯 Generate real-time trading signals (4-strategy ensemble voting)
- 📈 Backtest 28 trading strategies + walk-forward anti-overfitting analysis
- 💾 DuckDB + Parquet for efficient data storage
- 📲 Send Telegram alerts with real-time signals + backtest validation
- ⚡ Parallel execution: 8 workers (optimized for your hardware)
- 📝 Centralized logging with file rotation
- 🎯 Production-ready with comprehensive error handling

**Results:**
- ✅ 13,972 backtest tests (28 strategies × 499 tickers) completed
- 🏆 Top strategy: **roc_filter** (Sharpe ratio 1.973)

**Execution Times (8 workers):**
- Data download: 2-3 min (first run), 30s (incremental)
- Feature generation: 55s (2.89M rows × 73 columns)
- Backtesting: ~2.5 hours (full run) | ~30-60s (test mode, 280 tests)

## Quick Start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Run complete pipeline (5 steps sequentially)
# On macOS/Linux:
bash run_pipeline.sh

# On Windows (PowerShell):
.\run_pipeline.ps1

# Or run individual steps:
python incremental_collector.py --test   # Step 1: Download data (test mode)
python feature_engine.py                  # Step 2: Generate features
python signal_engine.py                   # Step 3: Generate trading signals
python backtester.py --limit 10          # Step 4: Backtest strategies
python telegram_sender.py --signals-buy  # Step 5: Send real-time signals

# 3. Analyze & send alerts
python query_backtest_results.py                    # View backtest rankings
python telegram_sender.py --signals-buy --limit 10 # Send today's buy signals
python telegram_sender.py --all                    # Send comprehensive package
```

**For complete setup instructions, see [docs/QUICKSTART.md](docs/QUICKSTART.md)**

## Documentation

All detailed documentation is in the [`docs/`](docs/) folder:

| File | Purpose |
|------|---------|
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | 5-minute setup guide |
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | How to contribute |
| [docs/GIT_SETUP.md](docs/GIT_SETUP.md) | Git workflow |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Version history |
| [docs/LICENSE](docs/LICENSE) | MIT License |
| [docs/INDEX.md](docs/INDEX.md) | Full documentation index |

## Project Structure

```
stock-trading-pipeline/
├── README.md                       (you are here)
├── docs/                           (all documentation)
│   ├── QUICKSTART.md               (start here!)
│   ├── CONTRIBUTING.md
│   ├── GIT_SETUP.md
│   ├── CHANGELOG.md
│   ├── LICENSE
│   └── [more docs...]
│
├── Core Pipeline Scripts (5 Steps):
│   ├── incremental_collector.py    (STEP 1: download stock data, 8 threads)
│   ├── feature_engine.py           (STEP 2: compute 46+ indicators, 8 workers)
│   ├── signal_engine.py            (STEP 3: generate trading signals, 4-strategy voting)
│   ├── backtester.py               (STEP 4: evaluate 28 strategies, 8 workers)
│   ├── telegram_sender.py          (STEP 5: send real-time alerts with validation)
│   ├── query_backtest_results.py   (analyze results & rankings)
│   └── logger_config.py            (centralized logging)
│
├── Configuration Files:
│   ├── requirements.txt            (Python dependencies)
│   ├── tickers.csv                 (S&P 500 symbols)
│   ├── run_pipeline.sh             (execute all 5 steps - Unix/Linux)
│   └── run_pipeline.ps1            (execute all 5 steps - Windows)
│
└── database/                       (git-ignored, auto-created)
    ├── stock_data.duckdb          (raw data, features, backtest results)
    ├── stock_features.parquet     (computed technical indicators)
    └── trading_signals.parquet    (daily trading signals with votes)
```

| Category | Strategies |
|----------|------------|
| **RSI** | rsi_classic (30/70), rsi_extreme (20/80), rsi_loose (40/60) |
| **MACD** | macd_only (crossover), rsi_macd_combo (confluence), macd_histogram (zero cross) |
| **Moving Averages** | sma_crossover (golden cross 10/50), ema_crossover (10/20), ma_alignment (10>20>50) |
| **Bollinger Bands** | bollinger_bands (extremes), rsi_bollinger_combo, bb_squeeze (volatility breakout) |
| **Stochastic** | stochastic (K 20/80), stochastic_cross (K crosses D) |
| **Volume/Momentum** | volume_rsi, obv_trend, volatility_momentum, volatility_expansion, roc_filter |
| **Multi-Indicator** | rsi_stochastic (both), all_oscillators (RSI+Stochastic+MACD), mean_reversion, vwap_strategy |
| **Advanced** | atr_breakout (volatility+momentum), williams_r (oversold/overbought), support_resistance (SMA±volatility), rsi_divergence, trend_pullback |

**Key Functions**:
- `run_backtest(strategies=None, tickers=None, limit=None, force_rerun=False, num_workers=8)`: Main orchestrator
- `backtest_strategy(df, initial_capital=10000)`: Core backtest engine (simulates trades, calculates metrics)
- `backtest_worker(args)`: Multiprocessing worker function
- `get_cached_result()`: Retrieve previously computed results
- `save_result()`: Store results in backtest_results table

**Output Table**:
- `backtest_results`: strategy_name, ticker, total_return, buy_hold_return, sharpe_ratio, win_rate, num_trades, avg_pnl, max_loss, start_date, end_date

**Example Output**:
```
Backtesting 28 strategies × 10 tickers (8 workers)...
Total tests: 280 | Cached: 39 | To run: 241

[ 50/241]  20.7% | rsi_macd_combo            MSFT   | Return: +145.32% | Sharpe: 0.89
[100/241]  41.5% | bollinger_bands           NVDA   | Return: +892.15% | Sharpe: 1.45
[200/241]  82.9% | all_oscillators           TSLA   | Return:  +75.23% | Sharpe: 0.62

====================================================================================================
STRATEGY RANKINGS (by Avg Sharpe Ratio)
====================================================================================================
       strategy  avg_return  avg_sharpe  avg_win_rate winning_tickers beats_buy_hold
      macd_only   16.772599    1.419622      0.461070             9/10            4/10
    rsi_classic    1.767763    0.767688      0.693616             8/10            2/10
all_oscillators    0.231362    0.202336      0.722222             7/10            1/10
```

### 4. signal_engine.py
**Purpose**: Generate real-time trading signals from technical features using ensemble voting

**How It Works**:
- Loads computed features from step 2
- Applies 4 independent trading strategies:
  - **Trend Following**: SMA alignment + MACD + ADX
  - **Momentum**: RSI + returns + volatility
  - **Mean Reversion**: Bollinger Bands + RSI
  - **Breakout**: BB position + volume + ADX
- **Ensemble Voting**: Scores each strategy (1 for bullish, -1 for bearish, 0 for neutral)
  - **Buy Signal**: 2+ strategies agree (score ≥ 2)
  - **Sell Signal**: 2+ strategies bearish (score ≤ -2)
  - **Neutral**: Mixed signals (score between -1 and 1)

**Output**:
- `trading_signals.parquet`: ticker, signal_date, final_signal (-1/0/1), signal_score (0-4), individual strategy votes

**Key Features**:
- Real-time signal generation (runs daily with fresh features)
- Avoids false signals through consensus voting
- Tracks individual strategy votes for transparency
- Perfect for combining with backtest validation in telegram alerts

**Example Usage**:
```bash
python signal_engine.py
```

### 5. backtester.py
**Purpose**: Validate strategies on historical data (standard backtest + walk-forward anti-overfitting)

**Standard Backtest**: In-sample testing on full historical data
**Walk-Forward Analysis**: Out-of-sample testing in rolling windows (prevents overfitting)

**Key Functions**:
- `run_backtest(strategies=None, tickers=None, limit=None, force_rerun=False, num_workers=8)`: Main orchestrator
- `backtest_strategy(df, initial_capital=10000)`: Core backtest engine (simulates trades, calculates metrics)
- `backtest_worker(args)`: Multiprocessing worker function
- `get_cached_result()`: Retrieve previously computed results
- `save_result()`: Store results in backtest_results table

**Output Table**:
- `backtest_results`: strategy_name, ticker, total_return, buy_hold_return, sharpe_ratio, win_rate, num_trades, avg_pnl, max_loss, start_date, end_date

### 6. telegram_sender.py
**Purpose**: Query results and send Telegram trading alerts with real-time signals + backtest validation

**3 Alert Types** (in priority order):
1. **Real-Time Daily Signals** (RECOMMENDED for daily use)
   - Today's buy/sell signals with backtest validation
   - Merges signal_engine output with historical strategy performance
   - Only shows signals for stocks with profitable strategies (Sharpe > 0.5)
   - Highest confidence due to dual validation (real-time + historical)
   
2. **Walk-Forward Recommendations** (RECOMMENDED for weekly use)
   - Anti-overfitting analysis using rolling time windows
   - More robust than standard backtest (tests on unseen data)
   - Filters by consistency ≥ 50%, return > 0%, Sharpe > 0.5
   - Conservative and Aggressive modes available
   
3. **Standard Backtest Alerts** (Legacy, in-sample only)
   - Historical strategy performance rankings
   - Higher risk of overfitting
   - Good for understanding strategy mechanics

**Real-Time Signal Example**:
- Signals come from trading_signals.parquet (today's signals)
- Each signal is validated against backtest_results (best strategy for that ticker)
- Inner join: only shows signals for stocks with positive backtest performance
- Displays: signal strength (0-4), best strategy, backtest return %, Sharpe ratio, individual strategy votes

**CLI Options** (Daily Signals - RECOMMENDED):
```bash
python telegram_sender.py --signals-buy       # Today's buy signals with validation
python telegram_sender.py --signals-sell      # Today's sell signals  
python telegram_sender.py --signal-summary    # Today's signal breakdown (counts, votes)
```

**CLI Options** (Walk-Forward - More Reliable):
```bash
python telegram_sender.py --wf-buy            # Anti-overfitting recommendations
python telegram_sender.py --wf-conservative   # High-consistency picks
python telegram_sender.py --wf-aggressive     # High-return picks
python telegram_sender.py --portfolio 10      # 10-stock weighted allocation
python telegram_sender.py --compare           # Walk-forward vs standard
```

**CLI Options** (Standard Backtest - Legacy):
```bash
python telegram_sender.py --buy                # Buy opportunities
python telegram_sender.py --sell               # Sell opportunities
python telegram_sender.py --summary            # Strategy rankings
```

**Comprehensive**:
```bash
python telegram_sender.py --all                # All alert types combined
```

### 7. query_backtest_results.py
**Purpose**: Query, analyze, and rank backtest results

**Key Functions**:
- `query_results(sort_by='sharpe', strategy=None, ticker=None, min_trades=0, min_return=None)`: Flexible filtering and sorting
- `strategy_summary(sort_by='sharpe')`: Aggregate stats by strategy (count, avg_return, median_return, std_return, avg_sharpe, win_rate, positive_tickers, beats_buy_hold)
- `ticker_summary(sort_by='return')`: Aggregate stats by ticker with best/worst strategies
- `strategy_vs_strategy(strategy1, strategy2)`: Head-to-head comparison
- `top_strategies(n=10, metric='sharpe')`: Ranked list of top performers
- `worst_strategies(n=10, metric='sharpe')`: Ranked list of worst performers
- `get_stats(strategy=None, ticker=None)`: Detailed statistics dictionary
- `print_strategy_report()`: Formatted console output with rankings and statistics
- `print_ticker_report()`: Ticker-level performance summary
- `print_comparison()`: Head-to-head strategy comparison

**Example Usage**:
```python
from query_backtest_results import top_strategies, strategy_vs_strategy, query_results

# Top 5 strategies by Sharpe ratio
top_5 = top_strategies(n=5, metric='sharpe')
print(top_5)

# Head-to-head comparison
comparison = strategy_vs_strategy('all_oscillators', 'rsi_stochastic')
print(comparison)

# Filter results: only strategies with 100+ trades and 0% minimum return
best = query_results(sort_by='sharpe', min_trades=100, min_return=0.0)
print(best)
```

### 4. query_backtest_results.py
**Purpose**: Query, analyze, and rank backtest results

**Key Functions**:
- `query_results(sort_by='sharpe', strategy=None, ticker=None, min_trades=0, min_return=None)`: Flexible filtering and sorting
- `strategy_summary(sort_by='sharpe')`: Aggregate stats by strategy (count, avg_return, median_return, std_return, avg_sharpe, win_rate, positive_tickers, beats_buy_hold)
- `ticker_summary(sort_by='return')`: Aggregate stats by ticker with best/worst strategies
- `strategy_vs_strategy(strategy1, strategy2)`: Head-to-head comparison
- `top_strategies(n=10, metric='sharpe')`: Ranked list of top performers
- `worst_strategies(n=10, metric='sharpe')`: Ranked list of worst performers
- `get_stats(strategy=None, ticker=None)`: Detailed statistics dictionary
- `print_strategy_report()`: Formatted console output with rankings and statistics

## Database Schema

### daily_prices
Raw OHLCV data from Yahoo Finance
```sql
PRIMARY KEY (ticker, date)
Columns: ticker, date, open, high, low, close, adj_close, volume
```

### stock_features
Computed technical indicators
```sql
PRIMARY KEY (ticker, report_date)
Columns: ticker, report_date, [46 feature columns]
```

### ticker_state
Tracks download progress
```sql
PRIMARY KEY (ticker)
Columns: ticker, last_date
```

### download_log
Audit trail for all downloads
```sql
Columns: run_id, ticker, start_date, end_date, rows_downloaded,
         execution_seconds, status, error_message, log_time
```

### pipeline_runs
High-level execution summary
```sql
PRIMARY KEY (run_id)
Columns: run_id, pipeline_name, start_time, end_time, tickers_total,
         tickers_success, tickers_failed, total_rows, execution_seconds, status
```

### trading_signals (Parquet file)
Daily trading signals from 4-strategy ensemble voting
```
Columns: ticker, signal_date, final_signal (-1/0/1), signal_score (0-4),
         trend_following, momentum, mean_reversion, breakout
         
Final Signal Interpretation:
  1 = BUY (2+ strategies bullish)
  -1 = SELL (2+ strategies bearish)
  0 = NEUTRAL (mixed signals)
  
Signal Score: 0-4 (consensus strength, higher = more strategies agree)
```

### backtest_results
Strategy backtesting results (caches computed metrics to avoid re-running)
```sql
PRIMARY KEY (strategy_name, ticker)
Columns: strategy_name, ticker, total_return, buy_hold_return, sharpe_ratio,
         win_rate, num_trades, avg_pnl, max_loss, start_date, end_date, computed_at
```

## Usage Examples

### Download data for 50 stocks
```bash
python incremental_collector.py --limit 50
```

### Compute features
```bash
python feature_engine.py
```

### Backtest strategies
```bash
# Quick test: 2 strategies × 5 tickers
python -c "from backtester import run_backtest; run_backtest(limit=5, strategies=['rsi_classic', 'macd_only'], num_workers=2)"

# Full backtest: all 28 strategies × all available tickers
python -c "from backtester import run_backtest; run_backtest()"

# Force re-run without using cache
python -c "from backtester import run_backtest; run_backtest(force_rerun=True)"
```

### Generate daily trading signals
```bash
# Generate today's buy/sell signals
python signal_engine.py

# View signals
python -c "
import pandas as pd
df = pd.read_parquet('database/trading_signals.parquet')
print(df[df['final_signal'] != 0].tail(20))  # Show today's signals
"
```

### Send Telegram alerts (RECOMMENDED - Real-Time Daily Signals)
```bash
# Today's buy signals with backtest validation (REAL-TIME)
python telegram_sender.py --signals-buy --limit 10

# Today's sell signals
python telegram_sender.py --signals-sell --limit 5

# Today's signal breakdown summary
python telegram_sender.py --signal-summary

# Walk-forward recommendations (more conservative, weekly)
python telegram_sender.py --wf-buy --limit 10

# Comprehensive package (all alerts)
python telegram_sender.py --all
```

### Analyze backtest results
```bash
# Generate full strategy report with rankings
python query_backtest_results.py

# Query results in Python
python -c "
from query_backtest_results import top_strategies, query_results
print('Top 10 strategies by Sharpe ratio:')
print(top_strategies(n=10, metric='sharpe'))

print('\nAll results for AAPL stock:')
print(query_results(ticker='AAPL', sort_by='sharpe'))
"
```

### Query results in Python
```python
import duckdb

conn = duckdb.connect("database/stock_data.duckdb")

# Get latest features for a stock
df = conn.execute("""
    SELECT ticker, report_date, close, rsi_14, macd, bb_position
    FROM stock_features
    WHERE ticker = 'AAPL'
    ORDER BY report_date DESC
    LIMIT 30
""").df()

print(df)
conn.close()
```

### Query results in SQL
```bash
duckdb database/stock_data.duckdb
```

```sql
-- High RSI with bullish MACD cross
SELECT ticker, report_date, rsi_14, macd, macd_signal
FROM stock_features
WHERE rsi_14 > 70 AND macd > macd_signal
ORDER BY report_date DESC
LIMIT 20;
```

## Performance

Complete execution times from full pipeline run on standard hardware (8 CPU cores):

### Download Performance (incremental_collector.py)
- **First run (all 500 tickers)**: ~2-3 minutes (~500K OHLCV rows)
- **Incremental updates**: ~30 seconds (~5K new rows)
- **Rate**: ~3,000-5,000 rows/second with 8 workers
- **API delay**: 0.2s-3.0s (adaptive throttle based on success/failure)

### Feature Computation (feature_engine.py)
- **Full S&P 500 (499 tickers)**: ~55 seconds (2.89M rows × 73 columns)
- **Rate**: ~60,000 rows/second I/O throughput
- **Parallelism**: 8 workers (multiprocessing), CPU-bound operations

### Signal Generation (signal_engine.py)
- **Full S&P 500 (499 tickers)**: ~5-10 seconds (4 strategies × 499 tickers)
- **Rate**: Very fast (only applies voting logic, no backtesting)
- **Output**: trading_signals.parquet (ready for real-time Telegram alerts)

### Backtesting (backtester.py)
- **Full 28 strategies × 499 tickers**: ~2.5 hours (13,972 tests)
- **Test mode (10 tickers)**: ~30-60 seconds (280 tests)
- **Rate**: ~50-150 tests/second with 8 workers (varies by strategy complexity)
- **Caching benefit**: Subsequent runs with same strategy-ticker pairs skip computation
- **Memory**: ~100-200 MB per worker process

### Total Pipeline Time
- **First run (all 500 tickers)**: ~3 hours (download + features + signals + backtest)
- **Incremental run**: ~3 hours (features + signals + backtest only, data is incremental)
- **Signal-only run**: ~1 minute (features already exist, generate signals + send alerts)
- **Test run (10 tickers)**: ~1-2 minutes

### Storage
- **daily_prices**: ~2-3 GB for 20 years × 500 stocks
- **stock_features**: ~4-5 GB (46 features per row)
- **trading_signals**: ~10-20 MB (daily signals, kept last 90 days)
- **backtest_results**: ~50 KB per 1000 cached results

## Architecture Decisions

### Parallelism Strategy
- **incremental_collector**: ThreadPoolExecutor (I/O-bound network requests)
- **feature_engine**: multiprocessing.Pool (CPU-bound computation)
- **backtester**: multiprocessing.Pool with WorkerProcess per strategy-ticker pair (CPU-bound simulation)

### Backtesting Caching
- **PRIMARY KEY(strategy_name, ticker)**: Prevents duplicate computations
- **Cache lookup in main process**: Avoids file locking issues with multiprocessing
- **Workers bypass DB I/O**: Only compute; main process handles all database operations
- **INSERT OR REPLACE**: Allows re-running with force_rerun=True

### State Management
- **Incremental updates**: ticker_state table tracks last download date
- **Idempotent inserts**: PRIMARY KEY constraints + INSERT OR IGNORE prevent duplicates
- **Run tracking**: run_id UUID ties all operations to a specific pipeline execution
- **Backtest dates**: Each result stores start_date and end_date for reproducibility

### Throttling
- **Adaptive delay**: Increases on API failures, decreases on success
- **Random jitter**: Prevents synchronized requests across workers
- **Exponential backoff**: Up to 3 retry attempts

### Error Handling
- **Worker isolation**: Single ticker/strategy failure doesn't crash pipeline
- **Audit trail**: All errors logged with context (ticker, date range, error message)
- **Partial success**: Reports success/failed counts separately
- **Graceful degradation**: Returns available results even if some tests fail

## Monitoring & Debugging

### Check download progress
```sql
SELECT ticker, last_date FROM ticker_state ORDER BY last_date DESC LIMIT 20;
```

### View failed downloads
```sql
SELECT ticker, error_message, execution_seconds
FROM download_log
WHERE status = 'FAILED'
ORDER BY log_time DESC;
```

### Get pipeline summary
```sql
SELECT run_id, tickers_total, tickers_success, tickers_failed, 
       execution_seconds, status
FROM pipeline_runs
ORDER BY start_time DESC
LIMIT 10;
```

### Profile feature computation
```sql
SELECT 
    COUNT(*) as rows,
    COUNT(DISTINCT ticker) as tickers,
    MIN(report_date) as earliest,
    MAX(report_date) as latest
FROM stock_features;
```

### View backtest results
```sql
-- Top 5 strategies by average Sharpe ratio
SELECT strategy_name, 
       COUNT(*) as tickers,
       ROUND(AVG(total_return), 4) as avg_return,
       ROUND(AVG(sharpe_ratio), 4) as avg_sharpe,
       ROUND(AVG(win_rate), 4) as avg_win_rate
FROM backtest_results
GROUP BY strategy_name
ORDER BY avg_sharpe DESC
LIMIT 5;

-- Best performing strategies for a specific ticker
SELECT strategy_name, total_return, sharpe_ratio, win_rate, num_trades
FROM backtest_results
WHERE ticker = 'AAPL'
ORDER BY sharpe_ratio DESC
LIMIT 10;

-- Compare strategy A vs strategy B across all tickers
SELECT ticker, 
       strategy_name,
       total_return,
       sharpe_ratio,
       win_rate
FROM backtest_results
WHERE strategy_name IN ('rsi_classic', 'macd_only')
ORDER BY ticker, strategy_name;

-- Check cache status
SELECT COUNT(*) as cached_results,
       COUNT(DISTINCT strategy_name) as unique_strategies,
       COUNT(DISTINCT ticker) as unique_tickers
FROM backtest_results;
```

## Dependencies

See `requirements.txt` for full list:
- **duckdb**: Embedded SQL database
- **pandas**: Data manipulation & analysis
- **yfinance**: Yahoo Finance API client
- **numpy**: Numerical computation

## Notes

- **Database**: Uses DuckDB (embedded, no server required)
- **Data source**: Yahoo Finance (daily data, adjusted close prices)
- **Update frequency**: Run incremental_collector.py daily for fresh data
- **Feature scaling**: Consider normalizing features before ML models

## Project Roadmap

### Phase 1: Technical Analysis Backtesting ✅ (Complete)
- [x] Data pipeline: Download OHLCV data + compute 46 technical indicators
- [x] Backtesting engine: 28 trading strategies with comprehensive metrics
- [x] Result caching: Avoid re-running identical strategy-ticker tests
- [x] Parallel execution: 8 workers for downloads, features, and backtests
- [x] Analysis tools: Query and rank strategy performance
- [x] Real-time signal generation: 4-strategy ensemble voting (buy/sell/neutral)
- [x] Telegram integration: Send daily signals with backtest validation
- [x] Walk-forward analysis: Anti-overfitting validation for robust recommendations
- **Current**: All 28 strategies tested, daily signals + Telegram alerts working

### Phase 2: Machine Learning Predictions (Planned)
- [ ] Feature engineering: Use technical indicators as ML features
- [ ] Model training: XGBoost/LightGBM for 1/5/20-day price prediction
- [ ] Walk-forward validation: Avoid lookahead bias with time-series splits
- [ ] Ensemble methods: Combine technical + ML predictions
- [ ] Backtesting: Compare ML strategies vs technical analysis

### Phase 3: Production Deployment (Planned)
- [ ] Real-time signal generation: Live market data integration
- [ ] Portfolio optimization: Sharpe ratio / risk-adjusted returns
- [ ] Trade execution: Integration with brokerage APIs
- [ ] Risk monitoring: Position sizing, correlation analysis, drawdown limits

## License

MIT

## Support

For issues or questions, check the database audit tables:
- `download_log`: See which downloads failed and why
- `pipeline_runs`: See high-level execution summary
- `ticker_state`: Verify which tickers are up-to-date
