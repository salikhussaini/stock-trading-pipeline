# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Complete stock features pipeline with 46+ technical indicators
- Parallel data collection with adaptive throttling (8 worker threads)
- Feature engine with multiprocessing (8 worker processes)
- Backtester with 28 trading strategies and result caching
- Query tool for analyzing backtest results
- Centralized logging with rotating file handlers
- DuckDB database for efficient data storage and querying
- Parquet format for fast feature I/O (10x faster than pandas)
- Per-ticker feature computation in wide format
- Per-ticker backtesting with in-memory queries
- Column aliasing for strategy function compatibility

### Infrastructure
- Git configuration (.gitignore, .gitattributes)
- Centralized logging (logger_config.py)
- Comprehensive README with usage examples
- Requirements.txt with pinned dependencies
- Support for 500+ stock tickers (S&P 500)

### Performance Optimizations
- Feature generation: 2.89M rows × 73 columns in ~55 seconds
- Parquet write: 80 seconds (DuckDB COPY, 10x faster than pandas)
- Backtester: Per-ticker queries prevent memory exhaustion
- Caching: Avoids re-running identical strategy-ticker combinations
- Parallel execution: 8 worker processes for CPU-bound tasks

## [1.0.0] - 2026-06-29

### Initial Release

#### Features
- **incremental_collector.py**: Download historical stock data (OHLCV)
  - Parallel downloads with 8 worker threads
  - Adaptive API throttling (auto-adjusts delay on errors)
  - Incremental updates (tracks last_date per ticker)
  - Retry logic with exponential backoff
  - Thread-safe metrics tracking

- **feature_engine.py**: Compute technical indicators
  - 46+ features across 4 categories:
    - Short-term (1-14 day lookback): RSI, Stochastic, MACD, SMA/EMA
    - Long-term (20+ day): Extended RSI, ADX, Bollinger Bands
    - Cross-timeframe divergence: RSI/ROC/MACD divergence
    - Price action: High/Low ratio, Close/Open ratio
  - Parallel processing (8 workers)
  - Data quality checks (outlier removal, minimum data points)
  - Wide format output (1 row per ticker-date, 70+ feature columns)
  - Parquet storage with Snappy compression

- **backtester.py**: Evaluate trading strategies
  - 28 technical analysis strategies:
    - RSI variations (classic, extreme, loose)
    - MACD-based (MACD only, histogram zero-cross)
    - Moving average crossovers (SMA, EMA)
    - Bollinger Bands (standalone and combos)
    - Stochastic oscillator (classic and signal cross)
    - Advanced: Support/Resistance, RSI divergence, OBV trend, Volume RSI
  - Comprehensive metrics: Return, Sharpe ratio, Win rate, Drawdown
  - Result caching (avoids re-running identical tests)
  - Per-ticker data queries (memory efficient)
  - Parallel execution (8 workers)

- **query_backtest_results.py**: Analysis tool
  - Strategy rankings by Sharpe ratio, return, win rate
  - Ticker performance summaries
  - Head-to-head strategy comparisons
  - Flexible filtering and sorting

- **logger_config.py**: Centralized logging
  - File handler (session-specific timestamped logs)
  - Rotating file handler (10MB max, 5 backups)
  - Console handler (INFO level to stdout)
  - Structured metrics logging
  - Pipeline start/end markers
  - Section dividers for readability

#### Results from First Run
- Data: 500+ S&P 500 stocks, 2.89M rows of historical data
- Features: 73 columns (ticker, date, 70 features, close, volume)
- Strategies: 28 strategies × 499 successful tickers = 13,972 tests
- Top Strategy: **roc_filter** (Sharpe: 1.973, Win rate: 47.7%)
- Top Ticker: **AXON** (avg return: 683.2%)
- Execution Time: ~2.5 hours (parallel, 8 workers)

#### Database Structure
- `daily_prices`: Raw OHLCV data (500M rows)
- `stock_features`: Technical indicators (deprecated, using Parquet now)
- `backtest_results`: Strategy performance cache (13,972+ rows)
- `download_log`: Audit trail of data collection
- `pipeline_runs`: High-level summary statistics
- `ticker_state`: Last download date per ticker

### Known Issues
- Extreme outliers detected (TPL: 209%, MNST: 111%, AXON: 683%)
  - Recommend validating for stock splits, data quality
- Some strategies have low Sharpe ratios (rsi_macd_combo: 0.27)
  - Consider improving signal logic or parameter tuning
- Memory usage scales with number of tickers
  - Per-worker queries help, but large backtests still memory-intensive

### Future Improvements
- [ ] Walk-forward validation for strategy robustness
- [ ] Monte Carlo simulations for confidence intervals
- [ ] Portfolio optimization (combine multiple strategies)
- [ ] Regime detection (bull/bear/sideways market states)
- [ ] Real-time trading signals integration
- [ ] Machine learning feature selection
- [ ] Commission/slippage modeling
- [ ] Advanced order types (limit, stop-loss)
- [ ] Risk parity position sizing
- [ ] Sentiment analysis integration

---

## Versioning Notes

### v1.0.0 Baseline
- Stable feature generation pipeline
- 28 strategies with comprehensive metrics
- Caching and parallel execution working correctly
- Database schema stable
- Ready for production use with manual review

### Future Versions (v1.1.0+)
- Enhanced strategy library (additional indicators)
- Real-time data collection from APIs
- Distributed backtesting (multiple machines)
- REST API for live predictions
- Web UI for monitoring and analysis

---

## Contributors

- Initial implementation: Stock Trading Pipeline Team
- Date: 2026-06-29

## License

[Specify your license here - e.g., MIT, Apache 2.0, etc.]
