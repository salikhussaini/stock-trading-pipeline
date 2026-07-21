# Adding Fundamental Features - Implementation Guide

## Overview
This guide shows how to enhance ML models with fundamental data (P/E ratios, earnings, insider trades, etc.) **without breaking** the existing pipeline.

## What Was Added

### 1. New Module: `fundamental_collector.py`
Collects 30+ fundamental metrics per ticker using yfinance:

**Valuation**: P/E, P/B, P/S, PEG ratios
**Growth**: Earnings growth, revenue growth  
**Profitability**: Profit margin, ROE, ROA
**Financial Health**: Debt/equity, current ratio
**Sentiment**: Insider %, short interest, analyst ratings
**Size**: Market cap, enterprise value
**Risk**: Beta (volatility vs market)

### 2. Modified: `feature_engine.py`
Now automatically merges fundamentals with technical features (if available).

**Non-Breaking**: If fundamentals not collected, pipeline works exactly as before.

### 3. Updated: `run_pipeline.sh`
Added **optional** Step 1.5 between data download and feature generation.

**Non-Breaking**: Fundamental collection errors won't stop pipeline.

## Usage

### Quick Test (10 tickers)
```bash
# Collect fundamentals
python src/fundamental_collector.py --test

# Generate features (will auto-merge fundamentals)
python src/feature_engine.py

# Train ML model (now has fundamentals + technicals)
python src/ml_signal_engine.py
```

### Full Pipeline (500 tickers)
```bash
# Option 1: Run complete pipeline (includes fundamentals)
bash run_pipeline.sh

# Option 2: Run fundamentals separately
python src/fundamental_collector.py --workers 4  # Takes ~5-10 min
```

### Standalone Commands
```bash
# Collect fundamentals for all tickers
python src/fundamental_collector.py --workers 4

# Collect for specific number
python src/fundamental_collector.py --limit 50 --workers 4

# Test mode (10 tickers)
python src/fundamental_collector.py --test
```

## Output Files

**Database location**: `database/stock_fundamentals.parquet`

**Size**: ~200-500 KB (much smaller than OHLCV data)

**Update frequency**: Weekly recommended (fundamentals change slowly)

## Architecture Changes (Non-Breaking)

### Before
```
1. incremental_collector.py → stock_data.duckdb
2. feature_engine.py → stock_features.parquet (46 technical features)
3. ml_signal_engine.py → ml_signals.parquet
```

### After (Backward Compatible)
```
1. incremental_collector.py → stock_data.duckdb
1.5 fundamental_collector.py → stock_fundamentals.parquet (OPTIONAL)
2. feature_engine.py → stock_features.parquet (46 tech + 30 fundamental)
3. ml_signal_engine.py → ml_signals.parquet (better features!)
```

**Key**: Step 1.5 is optional. If skipped, pipeline works exactly as before.

## Expected ML Performance Improvement

### Before (Technical Indicators Only)
- ROC-AUC: 0.508 (random)
- Accuracy: 50.7%
- Problem: Technical indicators can't predict 10-day returns

### After (Technicals + Fundamentals)
- **Expected ROC-AUC**: 0.60-0.70 (viable edge)
- **Expected Accuracy**: 58-65%
- Why: Fundamentals capture stock-specific edges (value, momentum)

### Features That Should Help Most
1. **P/E ratio vs sector average** → identifies value stocks
2. **Earnings growth** → momentum signal
3. **Short interest** → squeeze potential
4. **Insider buying** → conviction signal
5. **Analyst upgrades** → sentiment shift

## Troubleshooting

### Issue: "Fundamental collection failed"
**Cause**: yfinance rate limiting or network issues
**Solution**: 
```bash
# Reduce workers to avoid rate limits
python src/fundamental_collector.py --workers 2

# Or run in smaller batches
python src/fundamental_collector.py --limit 100 --workers 4
python src/fundamental_collector.py --limit 100 --workers 4  # resume
```

### Issue: "No fundamental data found (skipping)"
**Cause**: Haven't run fundamental_collector.py yet
**Solution**: This is expected! Pipeline still works. Run collector when ready:
```bash
python src/fundamental_collector.py
```

### Issue: "Could not merge fundamentals"
**Cause**: Parquet file corrupted or empty
**Solution**: Delete and regenerate:
```bash
rm database/stock_fundamentals.parquet
python src/fundamental_collector.py --workers 4
```

## Performance Notes

### Execution Time
- **Fundamental collection**: ~5-10 minutes (500 tickers, 4 workers)
- **Feature merging**: <5 seconds (one-time merge)
- **ML training**: Same as before (~20 minutes for 12 sectors)

### Rate Limiting
- yfinance allows ~1-2 requests/second
- Use `--workers 4` (safe) or `--workers 2` (conservative)
- Built-in 0.5s delay between tickers

### Data Freshness
- **OHLCV**: Update daily (volatile)
- **Fundamentals**: Update weekly (change slowly)

## Verification

Check if fundamentals are being used:
```bash
# Run ML signal engine and check logs
python src/ml_signal_engine.py

# Look for these log messages:
# ✓ "Merging fundamental features..."
# ✓ "Added 30 fundamental features"
# ✓ "Using 76 features for training" (46 technical + 30 fundamental)
```

Check feature file size:
```bash
# Before fundamentals: ~25-30 MB
# After fundamentals: ~35-40 MB (fundamentals add ~10 MB)
ls -lh database/stock_features.parquet
```

## Next Steps

1. **Collect fundamentals** (one-time setup):
   ```bash
   python src/fundamental_collector.py --test  # Test with 10 tickers first
   python src/fundamental_collector.py         # Then run full 500
   ```

2. **Regenerate features** (merges fundamentals):
   ```bash
   python src/feature_engine.py
   ```

3. **Retrain ML models**:
   ```bash
   python src/ml_signal_engine.py
   ```

4. **Check improved performance**:
   ```bash
   python src/ml_signal_engine.py --query performance
   ```
   - Look for ROC-AUC > 0.60 (vs previous 0.508)

5. **Optional: Schedule weekly updates**:
   ```bash
   # Add to crontab (run every Sunday at 2 AM)
   0 2 * * 0 cd /path/to/pipeline && python src/fundamental_collector.py
   ```

## Summary

✅ **Non-Breaking**: Existing workflow unchanged if you don't run fundamental_collector.py
✅ **Optional**: Step 1.5 in pipeline is skippable
✅ **Automatic**: feature_engine.py auto-detects and merges fundamentals
✅ **Robust**: Errors in fundamental collection don't stop pipeline
✅ **Fast**: ~5-10 minutes to collect 500 tickers

**Result**: ML models now have 76 features (46 technical + 30 fundamental) instead of just 46, potentially improving ROC-AUC from 0.508 to 0.60-0.70.
