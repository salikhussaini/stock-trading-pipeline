# =========================================================
# LOGGER INTEGRATION GUIDE
# =========================================================

## Quick Start

Add this import to the top of each script:
```python
from logger_config import (
    log_info, log_debug, log_error, log_warning, 
    log_exception, log_section, log_subsection, log_metrics, 
    log_pipeline_start, log_pipeline_end
)
```

---

## 1. INCREMENTAL_COLLECTOR.py

Replace the custom log_queue logic with global logger:

### BEFORE (remove these lines):
```python
log_queue = queue.Queue()

def log_writer():
    # ... entire log writer function
```

### AFTER (add this):
```python
from logger_config import log_info, log_debug, log_error, log_exception, log_pipeline_start, log_pipeline_end, log_metrics

# At the start of main execution:
log_pipeline_start("Incremental Collector", workers=args.workers, tickers=len(tickers))

# In process_ticker() function, replace print() with log_info():
# OLD: print(f"{ticker} | {status} | rows={rows} | {elapsed}s")
log_info(f"{ticker} | {status} | rows={rows} | {elapsed}s")

# For exceptions:
# OLD: print(f"{ticker} exception: {repr(e)}")
log_error(f"{ticker} failed: {str(e)}")

# At the end:
metrics = {
    "Run ID": run_id,
    "Tickers": len(tickers),
    "Success": success,
    "Failed": failed,
    "Total Rows": total_rows,
    "Time (s)": total_time
}
log_pipeline_end("Incremental Collector", status="SUCCESS" if failed == 0 else "PARTIAL", **metrics)
```

---

## 2. FEATURE_ENGINE.py

Add structured logging for pipeline progress:

### Add at top:
```python
from logger_config import log_info, log_error, log_exception, log_pipeline_start, log_pipeline_end, log_metrics

# At the start of main execution:
log_pipeline_start("Feature Engine", tickers="all")

# In compute_ticker_features() for errors:
# OLD: just return None, ticker, error_msg
log_error(f"{ticker}: {error_msg}")

# After pool processing:
log_metrics({
    "Total Tickers": len(tickers),
    "Success": successful_count,
    "Failed": failed_count,
    "Rows Inserted": total_rows
}, title="Feature Engine Results")

# At the end:
log_pipeline_end("Feature Engine", status="COMPLETE")
```

---

## 3. BACKTESTER.py

Add logging for strategy execution progress:

### Add at top:
```python
from logger_config import log_info, log_debug, log_error, log_pipeline_start, log_pipeline_end, log_metrics

# In run_backtest() at start:
log_pipeline_start(
    "Backtester",
    strategies=len(strategies),
    tickers=len(all_tickers),
    workers=num_workers
)

# For cache hits:
# OLD: just silently use cached result
log_debug(f"Cache hit: {strategy_name} on {ticker}")

# For work items:
log_info(f"Testing {len(strategies)} strategies × {len(all_tickers)} tickers")
log_info(f"Cache status: {total_cached} cached, {total_new} to run")

# After results:
metrics = {
    "Total Tests": total_items,
    "Cached": total_cached,
    "New": total_new,
    "Execution Time": f"{total_time:.2f}s"
}
log_pipeline_end("Backtester", status="COMPLETE", **metrics)
```

---

## Log Output

Logs are saved to:
- `logs/pipeline_YYYYMMDD_HHMMSS.log` - Session-specific log
- `logs/pipeline.log` - Rolling log (keeps last 5 files, 10MB each)

Console output shows INFO level and above.
File logs show DEBUG level and above.

---

## Usage Examples

```python
from logger_config import log_info, log_error, log_metrics

# Simple messages
log_info("Processing ticker AAPL")

# Metrics dictionary
metrics = {"success": 100, "failed": 2, "time": 45.2}
log_metrics(metrics, title="Pipeline Summary")

# Exception handling
try:
    risky_operation()
except Exception as e:
    log_error(f"Operation failed: {str(e)}")
```

---

## Features

✓ Automatic timestamped logs to file
✓ Rolling file handler (doesn't fill disk)
✓ Console + file output simultaneously
✓ Color-coded severity levels
✓ Prevents duplicate handlers on re-import
✓ Thread-safe logging
✓ Structured metrics logging
✓ Clean section dividers for readability
