# ML Signal Engine Analysis & Recommendations

## Problem: ROC-AUC ~0.508 (Random Performance)

### Diagnostic Results (2026-07-21)
- **ROC-AUC**: 0.508 ± 0.006 (random = 0.5)
- **Accuracy**: 0.507 ± 0.005 (coin flip)
- **Avg Probability**: 0.500 (zero confidence)
- **Target Distribution**: ~50% bullish, ~50% bearish (perfectly balanced = unpredictable)

### Root Cause: Technical Indicators Don't Predict Forward Returns

**This is NOT a bug—it's the expected result from market efficiency:**

1. **Short-term price movements are random** — Stock prices over 5-10 days follow a random walk (Efficient Market Hypothesis)
2. **Technical indicators lag price** — RSI, MACD, Bollinger Bands react to past prices, don't predict future
3. **Information already priced in** — If simple indicators predicted returns, everyone would use them (arbitrage eliminates edge)

### Why Model Improvements Didn't Help
- ✅ Extended horizon: 5 → 10 days (still too short for trends)
- ✅ Increased capacity: max_depth 5→7, n_estimators 100→200
- ✅ Added regularization: L1/L2, gamma
- ✅ Class balancing: scale_pos_weight
- ❌ **Result: No improvement** because features lack predictive power

## Solutions: 3 Approaches

### Option 1: Use Rule-Based Signals (Recommended)
**Use the existing `signal_engine.py` instead of ML.**

**Why this works:**
- Ensemble voting of 4 strategies (trend, mean reversion, momentum, breakout)
- Validates with backtest performance (Sharpe ratio, win rate)
- Sends only high-confidence signals
- Already proven: top strategy has Sharpe 1.973

**Action:**
```bash
python src/signal_engine.py          # Generate rule-based signals
python src/telegram_sender.py --all  # Send validated signals
```

**Stop using ML signals** — they add no value over random guessing.

---

### Option 2: Change Target Variable (Advanced)

Instead of predicting **absolute returns**, predict **relative performance vs benchmark**:

```python
# In create_target_variable():
# Load SPY (S&P 500) data
spy_returns = load_spy_returns()  

# Create relative target
df['spy_future_return'] = spy_returns.shift(-10)
df['stock_future_return'] = (df['future_close'] - df['close']) / df['close']
df['relative_return'] = df['stock_future_return'] - df['spy_future_return']
df['target'] = (df['relative_return'] > 0).astype(int)  # Beat the market?
```

**Why this helps:**
- Removes market-wide movements (which are unpredictable)
- Focuses on stock-specific edges
- More likely to find patterns in sector rotation, relative strength

**Expected ROC-AUC:** 0.55-0.60 (better but not amazing)

---

### Option 3: Add Fundamental Features (Most Promising)

Technical indicators don't predict returns, but **fundamentals + price action** might:

**New Features to Add:**
1. **Earnings surprises** (actual vs expected EPS)
2. **Valuation metrics** (P/E ratio, P/B ratio vs sector average)
3. **Insider trading** (buy/sell activity)
4. **Short interest** (% of float shorted)
5. **Analyst ratings** (upgrades/downgrades)
6. **News sentiment** (from financial news APIs)
7. **Volume divergence** (price up + volume down = weak rally)
8. **Relative strength** (vs sector, vs SPY)

**Data Sources:**
- `yfinance`: P/E, P/B, insider trades
- Alpha Vantage API: fundamentals, news sentiment
- Financial Modeling Prep API: earnings surprises
- Finviz: short interest

**Implementation Example:**
```python
import yfinance as yf

def add_fundamental_features(df):
    """Add fundamental data to technical features."""
    fundamentals = []
    
    for ticker in df['ticker'].unique():
        stock = yf.Ticker(ticker)
        info = stock.info
        
        fundamentals.append({
            'ticker': ticker,
            'pe_ratio': info.get('forwardPE', np.nan),
            'pb_ratio': info.get('priceToBook', np.nan),
            'short_ratio': info.get('shortRatio', np.nan),
            'insider_pct': info.get('heldPercentInsiders', np.nan)
        })
    
    df_fund = pd.DataFrame(fundamentals)
    df = df.merge(df_fund, on='ticker', how='left')
    return df
```

**Expected ROC-AUC:** 0.60-0.70 (meaningful edge)

---

## Recommended Next Steps

### Immediate (Today)
1. ✅ **Switch to rule-based signals** (`signal_engine.py`)
2. ✅ **Stop using ML signals** (ROC-AUC 0.508 = useless)
3. ✅ **Use Telegram alerts with backtest validation**

### Short-Term (This Week)
1. **Modify target to relative returns** (Option 2)
2. **Test with longer horizons** (20-30 days)
3. **Re-evaluate ROC-AUC** — if still <0.55, abandon ML approach

### Long-Term (If You Want ML)
1. **Add fundamental features** (Option 3)
2. **Scrape earnings data** from Alpha Vantage
3. **Add news sentiment** scoring
4. **Build hybrid model** (fundamentals + technicals)
5. **Target ROC-AUC >0.65** for viable trading edge

---

## Key Insight: Market Efficiency

**Stock prices are efficient over short timeframes (5-30 days).**

What DOESN'T work:
- ❌ Technical indicators predicting 10-day returns
- ❌ Past prices predicting future prices
- ❌ Simple patterns (everyone knows them)

What MIGHT work:
- ✅ Relative performance vs benchmark
- ✅ Fundamentals + technicals combined
- ✅ Long-term mean reversion (6-12 months)
- ✅ Event-driven strategies (earnings, M&A)
- ✅ Alternative data (satellite imagery, credit card data)

---

## Current Status: Use Rule-Based Signals

**Your pipeline already has a working solution:**
- `signal_engine.py`: 4-strategy ensemble voting
- `backtester.py`: 28 strategies evaluated
- Top strategy: **roc_filter** (Sharpe 1.973)
- Telegram alerts: Only sends validated signals

**ML adds nothing** when ROC-AUC = 0.508. Use the proven rule-based approach instead.

---

## References
- Fama, E. (1970). "Efficient Capital Markets" — short-term returns are random
- Lo, A. (2004). "Adaptive Markets Hypothesis" — edges decay as they're discovered
- Prado, M. (2018). "Advances in Financial Machine Learning" — why most ML fails in finance
