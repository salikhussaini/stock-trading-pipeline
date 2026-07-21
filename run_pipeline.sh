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

PYTHON="/mnt/external/stock-trading-pipeline/.venv-stock/bin/python"
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
WORKERS=2  # Reduced from 4 to avoid rate limits
BATCH_SIZE=100  # Tickers per batch download request (0 = disabled, individual downloads)
BACKTEST_MODE="both"  # standard, walk-forward, or both
WALK_FORWARD_LIMIT=50  # Number of tickers for walk-forward analysis
TELEGRAM_MODE="signals"  # signals, wf, std, all (signals = today's real-time alerts)

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
    --workers N         Number of parallel workers (default: 2)
    --batch-size N      Tickers per batch download request (default: 100, 0 = disabled)
    
    BACKTEST OPTIONS:
    --walk-forward      Run walk-forward analysis only (anti-overfitting)
    --standard          Run standard backtest only (28 strategies)
    --both              Run both standard and walk-forward (default: all tickers)
    --wf-limit N        Number of tickers for walk-forward (default: 50, only for --walk-forward)
    
    TELEGRAM OPTIONS (Real-Time Daily Signals Recommended):
    --telegram-signals  Send today's buy signals with backtest validation (DEFAULT - real-time)
    --telegram-summary  Send today's signal breakdown summary
    --telegram-wf       Send walk-forward analysis alerts (anti-overfitting)
    --telegram-std      Send standard backtest alerts (legacy)
    --telegram-all      Send comprehensive alerts (signals + walk-forward + backtest)
    
    --help              Show this help message

EXAMPLES:
    $0                              # Full pipeline: both modes, all tickers, daily signals
    $0 --walk-forward               # Walk-forward analysis (anti-overfitting)
    $0 --both                       # Run both standard + walk-forward (all tickers)
    $0 --walk-forward --wf-limit 100  # Walk-forward on 100 tickers
    $0 --test                       # Quick test with 10 tickers
    $0 --skip-download              # Skip download, run features + backtest
    $0 --workers 4                  # Use 4 parallel workers
    $0 --telegram-all               # Send comprehensive alerts

RECOMMENDED:
    # Daily: Real-time signals + backtest validation
    $0 --telegram-signals
    
    # Weekly: Walk-forward analysis for robust recommendations
    $0 --walk-forward --telegram-wf
    
    # Monthly: Comprehensive comparison
    $0 --both --telegram-all

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
        --batch-size)
            BATCH_SIZE="$2"
            shift 2
            ;;
        --walk-forward)
            BACKTEST_MODE="walk-forward"
            shift
            ;;
        --standard)
            BACKTEST_MODE="standard"
            shift
            ;;
        --both)
            BACKTEST_MODE="both"
            shift
            ;;
        --wf-limit)
            WALK_FORWARD_LIMIT="$2"
            shift 2
            ;;
        --telegram-wf)
            TELEGRAM_MODE="wf"
            shift
            ;;
        --telegram-std)
            TELEGRAM_MODE="std"
            shift
            ;;
        --telegram-all)
            TELEGRAM_MODE="all"
            shift
            ;;
        --telegram-signals)
            TELEGRAM_MODE="signals"
            shift
            ;;
        --telegram-summary)
            TELEGRAM_MODE="summary"
            shift
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
fi

case $BACKTEST_MODE in
    walk-forward)
        log_info "📊 MODE: Walk-Forward Analysis (Anti-Overfitting)"
        log_info "    Analyzing $WALK_FORWARD_LIMIT tickers"
        ;;
    standard)
        log_info "📊 MODE: Standard Backtest (28 Strategies)"
        ;;
    both)
        log_info "📊 MODE: Standard + Walk-Forward (Comprehensive)"
        log_info "    Analyzing all tickers"
        ;;
esac

echo ""

START_TIME=$(date +%s)

# =========================================================
# STEP 1: Download Stock Data
# =========================================================

STEP1_START=$(date +%s)

if [ "$SKIP_DOWNLOAD" = true ]; then
    log_warn "[1/5] Skipping data download (--skip-download)"
    echo ""
    DOWNLOAD_TIME=0
else
    log_step "[1/5] Downloading stock data..."
    echo ""
    
    CMD="$PYTHON src/incremental_collector.py --workers $WORKERS --batch-size $BATCH_SIZE"
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
# STEP 1.5: Collect Fundamental Data (OPTIONAL - enhances ML)
# =========================================================

STEP1_5_START=$(date +%s)

log_step "[1.5/5] Collecting fundamental data (OPTIONAL)..."
log_info "This step adds P/E, earnings, insider trades, etc. for better ML predictions"
echo ""

# Run fundamental collector (non-blocking - pipeline continues even if this fails)
if $PYTHON src/fundamental_collector.py --workers 4 2>/dev/null; then
    FUNDAMENTAL_TIME=$(($(date +%s) - STEP1_5_START))
    log_step "✓ Fundamental data collection complete"
    log_info "Time: $(format_time $FUNDAMENTAL_TIME)"
    echo ""
else
    log_warning "⚠ Fundamental data collection skipped or failed (pipeline will continue)"
    log_info "ML models will use technical indicators only"
    echo ""
fi

# =========================================================
# STEP 2: Generate Features
# =========================================================

STEP2_START=$(date +%s)

log_step "[2/5] Generating features..."
echo ""

if $PYTHON src/feature_engine.py; then
    FEATURE_TIME=$(($(date +%s) - STEP2_START))
    log_step "✓ Feature generation complete"
    log_info "Time: $(format_time $FEATURE_TIME)"
    echo ""
else
    log_error "✗ Feature generation failed"
    exit 1
fi

# =========================================================
# STEP 3: Generate Trading Signals
# =========================================================

STEP3_START=$(date +%s)

log_step "[3/5] Generating trading signals..."
echo ""

if $PYTHON src/signal_engine.py; then
    SIGNAL_TIME=$(($(date +%s) - STEP3_START))
    log_step "✓ Signal generation complete"
    log_info "Time: $(format_time $SIGNAL_TIME)"
    echo ""
else
    log_error "✗ Signal generation failed"
    exit 1
fi

# =========================================================
# STEP 4: Backtest Strategies
# =========================================================

STEP4_START=$(date +%s)

log_step "[4/5] Backtesting strategies..."
echo ""

BACKTEST_SUCCESS=true

# Run based on mode
if [ "$BACKTEST_MODE" = "both" ]; then
    log_info "Running both standard backtest + walk-forward analysis..."
    log_info "Walk-forward on all tickers..."
    
    if $PYTHON src/backtester.py; then
        log_step "✓ Both modes complete"
    else
        log_error "✗ Backtesting failed"
        BACKTEST_SUCCESS=false
    fi
    echo ""
    
elif [ "$BACKTEST_MODE" = "standard" ]; then
    log_info "Running standard backtest (28 strategies)..."
    
    if $PYTHON src/backtester.py --standard; then
        log_step "✓ Standard backtest complete"
    else
        log_error "✗ Standard backtest failed"
        BACKTEST_SUCCESS=false
    fi
    echo ""
    
elif [ "$BACKTEST_MODE" = "walk-forward" ]; then
    log_info "Running walk-forward analysis (anti-overfitting)..."
    log_info "Analyzing $WALK_FORWARD_LIMIT tickers..."
    
    if $PYTHON src/backtester.py --walk-forward --limit $WALK_FORWARD_LIMIT; then
        log_step "✓ Walk-forward analysis complete"
    else
        log_error "✗ Walk-forward analysis failed"
        BACKTEST_SUCCESS=false
    fi
    echo ""
fi

if [ "$BACKTEST_SUCCESS" = true ]; then
    BACKTEST_TIME=$(($(date +%s) - STEP4_START))
    log_step "✓ Backtesting complete"
    log_info "Time: $(format_time $BACKTEST_TIME)"
    echo ""
else
    log_error "✗ Backtesting failed"
    exit 1
fi

# =========================================================
# STEP 5: Send Telegram Notification
# =========================================================

STEP5_START=$(date +%s)

if [ "$SKIP_TELEGRAM" = true ]; then
    log_warn "[5/5] Skipping Telegram notification (--skip-telegram)"
    echo ""
    TELEGRAM_TIME=0
else
    log_step "[5/5] Sending Telegram notification..."
    echo ""
    
    # Determine telegram mode based on backtest mode if not explicitly set
    if [ "$TELEGRAM_MODE" = "signals" ]; then
        TELEGRAM_MODE="signals"  # Explicit, use as-is
    fi
    
    TELEGRAM_CMD="$PYTHON src/telegram_sender.py"
    
    case $TELEGRAM_MODE in
        signals)
            log_info "Sending today's buy signals with backtest validation (REAL-TIME)..."
            TELEGRAM_CMD="$TELEGRAM_CMD --signals-buy"
            ;;
        summary)
            log_info "Sending today's signal breakdown summary..."
            TELEGRAM_CMD="$TELEGRAM_CMD --signal-summary"
            ;;
        wf)
            log_info "Sending walk-forward buy recommendations..."
            TELEGRAM_CMD="$TELEGRAM_CMD --wf-buy"
            ;;
        std)
            log_info "Sending standard backtest alerts..."
            TELEGRAM_CMD="$TELEGRAM_CMD --buy"
            ;;
        all)
            log_info "Sending comprehensive alerts (real-time signals + walk-forward + backtest)..."
            TELEGRAM_CMD="$TELEGRAM_CMD --all"
            ;;
    esac
    
    if $TELEGRAM_CMD; then
        TELEGRAM_TIME=$(($(date +%s) - STEP5_START))
        log_step "✓ Telegram notification sent"
        log_info "Time: $(format_time $TELEGRAM_TIME)"
        echo ""
    else
        log_warn "⚠ Telegram notification failed (non-fatal)"
        TELEGRAM_TIME=$(($(date +%s) - STEP5_START))
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
echo "Configuration:"
printf "  %-20s : %s\n" "Backtest mode" "$BACKTEST_MODE"
if [ "$BACKTEST_MODE" = "walk-forward" ]; then
    printf "  %-20s : %s tickers\n" "Walk-forward limit" "$WALK_FORWARD_LIMIT"
fi

# Format telegram mode for display
case $TELEGRAM_MODE in
    signals)
        TELEGRAM_DISPLAY="Real-time daily signals (validated)"
        ;;
    summary)
        TELEGRAM_DISPLAY="Signal breakdown summary"
        ;;
    wf)
        TELEGRAM_DISPLAY="Walk-forward recommendations"
        ;;
    std)
        TELEGRAM_DISPLAY="Standard backtest alerts"
        ;;
    all)
        TELEGRAM_DISPLAY="Comprehensive (all modes)"
        ;;
    *)
        TELEGRAM_DISPLAY="$TELEGRAM_MODE"
        ;;
esac
printf "  %-20s : %s\n" "Telegram alerts" "$TELEGRAM_DISPLAY"
echo ""
echo "Stage Breakdown:"
printf "  %-20s : %s\n" "Data download" "$(format_time $DOWNLOAD_TIME)"
printf "  %-20s : %s\n" "Features" "$(format_time $FEATURE_TIME)"
printf "  %-20s : %s\n" "Trading signals" "$(format_time $SIGNAL_TIME)"
printf "  %-20s : %s\n" "Backtesting" "$(format_time $BACKTEST_TIME)"
printf "  %-20s : %s\n" "Telegram" "$(format_time $TELEGRAM_TIME)"
echo "  ────────────────────────────────"
printf "  %-20s : %s\n" "Total time" "$(format_time $TOTAL_TIME)"
echo ""
echo "Results available in:"
echo "  📊 database/stock_data.duckdb (data & backtest results)"
echo "  📈 database/stock_features.parquet (features)"
echo "  🎯 database/trading_signals.parquet (trading signals)"
if [ "$BACKTEST_MODE" = "walk-forward" ] || [ "$BACKTEST_MODE" = "both" ]; then
    echo "  🔍 walk_forward_results.csv (anti-overfitting analysis)"
fi
echo "  📝 logs/pipeline.log (execution log)"
echo ""
log_step "✓ Ready for analysis!"
echo ""
log_info "📊 Analyze Results:"
echo "   python query_backtest_results.py --walk-forward"
echo "   python query_backtest_results.py --portfolio 10"
echo ""
log_info "📈 Send Additional Alerts:"
echo "   python telegram_sender.py --signals-buy     # Today's buy signals"
echo "   python telegram_sender.py --wf-buy          # Walk-forward picks"
echo "   python telegram_sender.py --all             # Comprehensive package"
echo ""
