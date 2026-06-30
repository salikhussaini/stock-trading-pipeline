#!/bin/bash

# =========================================================
# run_pipeline.sh
# Run the complete stock trading pipeline sequentially
# =========================================================

set -e  # Exit on any error

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo -e "${BLUE}Virtual environment activated${NC}"
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo -e "${BLUE}Virtual environment activated${NC}"
else
    echo -e "${BLUE}No virtual environment found, using system Python${NC}"
fi

echo ""

# Timing
START_TIME=$(date +%s)

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Stock Trading Pipeline${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# =========================================================
# STEP 1: Download Stock Data
# =========================================================

echo -e "${GREEN}[1/3] Downloading stock data...${NC}"
echo ""

if python incremental_collector.py; then
    echo -e "${GREEN}✓ Data download complete${NC}"
    DOWNLOAD_TIME=$(($(date +%s) - START_TIME))
    echo -e "Time: ${DOWNLOAD_TIME}s"
    echo ""
else
    echo -e "${RED}✗ Data download failed${NC}"
    exit 1
fi

# =========================================================
# STEP 2: Generate Features
# =========================================================

echo -e "${GREEN}[2/3] Generating features...${NC}"
echo ""

if python feature_engine.py; then
    echo -e "${GREEN}✓ Feature generation complete${NC}"
    FEATURE_TIME=$(($(date +%s) - START_TIME - DOWNLOAD_TIME))
    echo -e "Time: ${FEATURE_TIME}s"
    echo ""
else
    echo -e "${RED}✗ Feature generation failed${NC}"
    exit 1
fi

# =========================================================
# STEP 3: Backtest Strategies
# =========================================================

echo -e "${GREEN}[3/3] Backtesting strategies...${NC}"
echo ""

if python backtester.py; then
    echo -e "${GREEN}✓ Backtesting complete${NC}"
    BACKTEST_TIME=$(($(date +%s) - START_TIME - DOWNLOAD_TIME - FEATURE_TIME))
    echo -e "Time: ${BACKTEST_TIME}s"
    echo ""
else
    echo -e "${RED}✗ Backtesting failed${NC}"
    exit 1
fi

# =========================================================
# SUMMARY
# =========================================================

TOTAL_TIME=$(($(date +%s) - START_TIME))

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Pipeline Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Stage Breakdown:"
echo "  Data download  : ${DOWNLOAD_TIME}s"
echo "  Features       : ${FEATURE_TIME}s"
echo "  Backtesting    : ${BACKTEST_TIME}s"
echo "  ─────────────────────"
echo "  Total time     : ${TOTAL_TIME}s (~$((TOTAL_TIME / 60))m)"
echo ""
echo "Results available in:"
echo "  - database/stock_data.duckdb (data & backtest results)"
echo "  - database/stock_features.parquet (features)"
echo "  - logs/pipeline.log (execution log)"
echo ""
echo -e "${GREEN}✓ Ready for analysis!${NC}"
echo ""
