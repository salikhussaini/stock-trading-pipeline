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
WORKERS=2  # Reduced from 4 to avoid rate limits
BATCH_SIZE=100  # Tickers per batch download request (0 = disabled, individual downloads)
BACKTEST_MODE="both"  # standard, walk-forward, or both
WALK_FORWARD_LIMIT=50  # Number of tickers for walk-forward analysis
TELEGRAM_MODE="auto"  # auto, wf, std, all

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
    --walk-forward      Run walk-forward analysis (anti-overfitting, recommended)
    --standard          Run standard backtest only (default)
    --both              Run both standard and walk-forward
    --wf-limit N        Number of tickers for walk-forward (default: 50)
    
    TELEGRAM OPTIONS:
    --telegram-wf       Send walk-forward alerts (default when --walk-forward used)
    --telegram-std      Send standard backtest alerts
    --telegram-all      Send all alerts (walk-forward + standard + portfolio)
    
    --help              Show this help message

EXAMPLES:
    $0                              # Full pipeline with standard backtest
    $0 --walk-forward               # Walk-forward analysis (anti-overfitting)
    $0 --both                       # Run both standard + walk-forward
    $0 --walk-forward --wf-limit 100  # Walk-forward on 100 tickers
    $0 --test                       # Quick test with 10 tickers
    $0 --skip-download              # Skip download, run features + backtest
    $0 --workers 4                  # Use 4 parallel workers
    $0 --telegram-all               # Send comprehensive alerts

RECOMMENDED:
    # Daily/Weekly: Walk-forward analysis for buy recommendations
    $0 --walk-forward --telegram-wf
    
    # Monthly: Compare both methods
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
        log_info "    Walk-forward on $WALK_FORWARD_LIMIT tickers"
        ;;
esac

echo ""

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
    
    CMD="$PYTHON incremental_collector.py --workers $WORKERS --batch-size $BATCH_SIZE"
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

BACKTEST_SUCCESS=true

# Run standard backtest
if [ "$BACKTEST_MODE" = "standard" ] || [ "$BACKTEST_MODE" = "both" ]; then
    log_info "Running standard backtest (28 strategies)..."
    
    if $PYTHON backtester.py; then
        log_step "✓ Standard backtest complete"
    else
        log_error "✗ Standard backtest failed"
        BACKTEST_SUCCESS=false
    fi
    echo ""
fi

# Run walk-forward analysis
if [ "$BACKTEST_MODE" = "walk-forward" ] || [ "$BACKTEST_MODE" = "both" ]; then
    log_info "Running walk-forward analysis (anti-overfitting)..."
    log_info "Analyzing $WALK_FORWARD_LIMIT tickers..."
    
    if $PYTHON backtester.py --walk-forward --limit $WALK_FORWARD_LIMIT; then
        log_step "✓ Walk-forward analysis complete"
    else
        log_error "✗ Walk-forward analysis failed"
        BACKTEST_SUCCESS=false
    fi
    echo ""
fi

if [ "$BACKTEST_SUCCESS" = true ]; then
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
    
    # Determine telegram mode based on backtest mode if auto
    if [ "$TELEGRAM_MODE" = "auto" ]; then
        case $BACKTEST_MODE in
            walk-forward)
                TELEGRAM_MODE="wf"
                ;;
            standard)
                TELEGRAM_MODE="std"
                ;;
            both)
                TELEGRAM_MODE="all"
                ;;
        esac
    fi
    
    TELEGRAM_CMD="$PYTHON telegram_sender.py"
    
    case $TELEGRAM_MODE in
        wf)
            log_info "Sending walk-forward buy recommendations..."
            TELEGRAM_CMD="$TELEGRAM_CMD --wf-buy"
            ;;
        std)
            log_info "Sending standard backtest alerts..."
            TELEGRAM_CMD="$TELEGRAM_CMD --buy"
            ;;
        all)
            log_info "Sending comprehensive alerts (walk-forward + standard + portfolio)..."
            TELEGRAM_CMD="$TELEGRAM_CMD --all"
            ;;
    esac
    
    if $TELEGRAM_CMD; then
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
echo "Configuration:"
printf "  %-20s : %s\n" "Backtest mode" "$BACKTEST_MODE"
if [ "$BACKTEST_MODE" = "walk-forward" ] || [ "$BACKTEST_MODE" = "both" ]; then
    printf "  %-20s : %s tickers\n" "Walk-forward limit" "$WALK_FORWARD_LIMIT"
fi
printf "  %-20s : %s\n" "Telegram mode" "$TELEGRAM_MODE"
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
if [ "$BACKTEST_MODE" = "walk-forward" ] || [ "$BACKTEST_MODE" = "both" ]; then
    echo "  🔍 walk_forward_results.csv (anti-overfitting analysis)"
fi
echo "  📝 logs/pipeline.log (execution log)"
echo ""
log_step "✓ Ready for analysis!"
if [ "$BACKTEST_MODE" = "walk-forward" ] || [ "$BACKTEST_MODE" = "both" ]; then
    echo ""
    log_info "💡 Query walk-forward results:"
    echo "   python query_backtest_results.py --walk-forward"
    echo "   python query_backtest_results.py --portfolio 10"
fi
echo ""
