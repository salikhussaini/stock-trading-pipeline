#!/bin/bash
# =========================================================
# run_pipeline.sh
# Run the complete stock trading pipeline sequentially
# =========================================================

# Set PATH for cron compatibility
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export SHELL=/bin/bash
export LC_ALL=C.UTF-8
export LANG=C.UTF-8

set -euo pipefail  # e=exit on error, u=undefined vars, o pipefail=pipe errors

# =========================================================
# CONFIGURATION
# =========================================================

PYTHON="/home/piuser/.venv-stock/bin/python"
LOCK_FILE="/tmp/stock_pipeline.lock"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Default options
SKIP_DOWNLOAD=false
SKIP_TELEGRAM=false
TEST_MODE=false
WORKERS=4

# =========================================================
# HELPER FUNCTIONS
# =========================================================

usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Run the complete stock trading pipeline sequentially.

OPTIONS:
    --skip-download     Skip data download step (use existing data)
    --skip-telegram     Skip sending Telegram notifications
    --test              Test mode (process only 10 tickers)
    --workers N         Number of parallel workers (default: 4)
    --help              Show this help message

EXAMPLES:
    $0                          # Full pipeline with defaults
    $0 --test                   # Quick test with 10 tickers
    $0 --skip-download          # Skip download, run features + backtest
    $0 --workers 8              # Use 8 parallel workers

EOF
    exit 0
}

log_step() {
    echo -e "${GREEN}$1${NC}"
}

log_info() {
    echo -e "${BLUE}$1${NC}"
}

log_warn() {
    echo -e "${YELLOW}$1${NC}"
}

log_error() {
    echo -e "${RED}$1${NC}"
}

format_time() {
    local seconds=$1
    if [ $seconds -lt 60 ]; then
        echo "${seconds}s"
    else
        echo "${seconds}s (~$((seconds / 60))m $((seconds % 60))s)"
    fi
}

cleanup() {
    rm -f "$LOCK_FILE"
}

# =========================================================
# PARSE ARGUMENTS
# =========================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-download)
            SKIP_DOWNLOAD=true
            shift
            ;;
        --skip-telegram)
            SKIP_TELEGRAM=true
            shift
            ;;
        --test)
            TEST_MODE=true
            shift
            ;;
        --workers)
            WORKERS="$2"
            shift 2
            ;;
        --help)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

# =========================================================
# PREFLIGHT CHECKS
# =========================================================

# Check if pipeline is already running
if [ -f "$LOCK_FILE" ]; then
    log_error "ERROR: Pipeline already running (lock file exists: $LOCK_FILE)"
    log_info "If this is incorrect, remove the lock file: rm $LOCK_FILE"
    exit 1
fi

# Set trap to cleanup on exit
trap cleanup EXIT INT TERM

# Create lock file
touch "$LOCK_FILE"

# Change to script directory
cd "$SCRIPT_DIR"

# Check Python virtual environment
if [ ! -x "$PYTHON" ]; then
    log_error "ERROR: Virtual environment not found at $PYTHON"
    log_info "Create it with:"
    log_info "  python3 -m venv /home/piuser/.venv-stock"
    log_info "  source /home/piuser/.venv-stock/bin/activate"
    log_info "  pip install -r requirements.txt"
    exit 1
fi

# Check required files
if [ ! -f "tickers.csv" ]; then
    log_error "ERROR: tickers.csv not found"
    exit 1
fi

# Create necessary directories
mkdir -p database logs

# =========================================================
# START PIPELINE
# =========================================================

echo ""
log_info "========================================"
log_info "     Stock Trading Pipeline"
log_info "========================================"
echo ""

if [ "$TEST_MODE" = true ]; then
    log_warn "🧪 TEST MODE: Processing only 10 tickers"
    echo ""
fi

START_TIME=$(date +%s)

# =========================================================
# STEP 1: Download Stock Data
# =========================================================

STEP1_START=$(date +%s)

if [ "$SKIP_DOWNLOAD" = true ]; then
    log_warn "[1/4] Skipping data download (--skip-download)"
    echo ""
    DOWNLOAD_TIME=0
else
    log_step "[1/4] Downloading stock data..."
    echo ""
    
    CMD="$PYTHON incremental_collector.py --workers $WORKERS"
    if [ "$TEST_MODE" = true ]; then
        CMD="$CMD --test"
    fi
    
    if $CMD; then
        DOWNLOAD_TIME=$(($(date +%s) - STEP1_START))
        log_step "✓ Data download complete"
        log_info "Time: $(format_time $DOWNLOAD_TIME)"
        echo ""
    else
        log_error "✗ Data download failed"
        exit 1
    fi
fi

# =========================================================
# STEP 2: Generate Features
# =========================================================

STEP2_START=$(date +%s)

log_step "[2/4] Generating features..."
echo ""

if $PYTHON feature_engine.py; then
    FEATURE_TIME=$(($(date +%s) - STEP2_START))
    log_step "✓ Feature generation complete"
    log_info "Time: $(format_time $FEATURE_TIME)"
    echo ""
else
    log_error "✗ Feature generation failed"
    exit 1
fi

# =========================================================
# STEP 3: Backtest Strategies
# =========================================================

STEP3_START=$(date +%s)

log_step "[3/4] Backtesting strategies..."
echo ""

if $PYTHON backtester.py; then
    BACKTEST_TIME=$(($(date +%s) - STEP3_START))
    log_step "✓ Backtesting complete"
    log_info "Time: $(format_time $BACKTEST_TIME)"
    echo ""
else
    log_error "✗ Backtesting failed"
    exit 1
fi

# =========================================================
# STEP 4: Send Telegram Notification
# =========================================================

STEP4_START=$(date +%s)

if [ "$SKIP_TELEGRAM" = true ]; then
    log_warn "[4/4] Skipping Telegram notification (--skip-telegram)"
    echo ""
    TELEGRAM_TIME=0
else
    log_step "[4/4] Sending Telegram notification..."
    echo ""
    
    if $PYTHON telegram_sender.py; then
        TELEGRAM_TIME=$(($(date +%s) - STEP4_START))
        log_step "✓ Telegram notification sent"
        log_info "Time: $(format_time $TELEGRAM_TIME)"
        echo ""
    else
        log_warn "⚠ Telegram notification failed (non-fatal)"
        TELEGRAM_TIME=$(($(date +%s) - STEP4_START))
        echo ""
    fi
fi

# =========================================================
# SUMMARY
# =========================================================

TOTAL_TIME=$(($(date +%s) - START_TIME))

log_info "========================================"
log_step "     Pipeline Complete! ✓"
log_info "========================================"
echo ""
echo "Stage Breakdown:"
printf "  %-20s : %s\n" "Data download" "$(format_time $DOWNLOAD_TIME)"
printf "  %-20s : %s\n" "Features" "$(format_time $FEATURE_TIME)"
printf "  %-20s : %s\n" "Backtesting" "$(format_time $BACKTEST_TIME)"
printf "  %-20s : %s\n" "Telegram" "$(format_time $TELEGRAM_TIME)"
echo "  ────────────────────────────────"
printf "  %-20s : %s\n" "Total time" "$(format_time $TOTAL_TIME)"
echo ""
echo "Results available in:"
echo "  📊 database/stock_data.duckdb (data & backtest results)"
echo "  📈 database/stock_features.parquet (features)"
echo "  📝 logs/pipeline.log (execution log)"
echo ""
log_step "✓ Ready for analysis!"
echo ""
