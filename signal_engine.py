# signal_engine.py
from pathlib import Path
import pandas as pd
import duckdb
import numpy as np
from datetime import datetime

FEATURE_PATH = Path(__file__).parent / "database" / "stock_features.parquet"
SIGNAL_PATH = Path(__file__).parent / "database" / "trading_signals.parquet"


# ======================================================
# STRATEGY FUNCTIONS
# ======================================================


# ======================================================
# STRATEGY FUNCTIONS (WITH CONFIDENCE SCORING)
# ======================================================


def trend_following(df):
    """
    Trend following with confidence levels.
    Scores: 0 (no signal), 0.25 (weak), 0.5 (moderate), 0.75 (strong), 1.0 (very strong)
    """
    signal = np.zeros(len(df))
    
    # Bullish signals at different confidence levels
    # Weak bullish: Just SMA alignment
    weak_bullish = (df["lt_sma_alignment"] == 1)
    # Moderate: SMA + MACD
    moderate_bullish = weak_bullish & (df["lt_macd_histogram"] > 0)
    # Strong: SMA + MACD + ADX
    strong_bullish = moderate_bullish & (df["lt_adx_14"] > 20)
    # Very strong: SMA + MACD + High ADX
    very_strong_bullish = moderate_bullish & (df["lt_adx_14"] > 30)
    
    signal[weak_bullish] = 0.25
    signal[moderate_bullish] = 0.5
    signal[strong_bullish] = 0.75
    signal[very_strong_bullish] = 1.0
    
    # Bearish signals
    weak_bearish = (df["lt_sma_alignment"] == 0)
    moderate_bearish = weak_bearish & (df["lt_macd_histogram"] < 0)
    strong_bearish = moderate_bearish & (df["lt_adx_14"] > 20)
    very_strong_bearish = moderate_bearish & (df["lt_adx_14"] > 30)
    
    signal[weak_bearish] = -0.25
    signal[moderate_bearish] = -0.5
    signal[strong_bearish] = -0.75
    signal[very_strong_bearish] = -1.0
    
    return signal


def momentum_strategy(df):
    """
    Momentum with confidence levels.
    Focuses on extreme RSI + volume confirmation.
    """
    signal = np.zeros(len(df))
    
    # Bullish: Extreme oversold with volume
    extreme_oversold = df["st_rsi_14"] < 20
    oversold = (df["st_rsi_14"] < 35)
    volume_surge = df["st_volume_ratio_5d"] > 1.2
    
    # Very strong: Extreme oversold + volume surge
    signal[extreme_oversold & volume_surge] = 1.0
    # Strong: Oversold + volume surge
    signal[oversold & volume_surge & (df["st_rsi_14"] < 30)] = 0.75
    # Moderate: Just oversold + volume
    signal[oversold & volume_surge] = 0.5
    # Weak: Just oversold
    signal[oversold] = 0.25
    
    # Bearish: Extreme overbought with volume
    extreme_overbought = df["st_rsi_14"] > 80
    overbought = (df["st_rsi_14"] > 65)
    
    signal[extreme_overbought & volume_surge] = -1.0
    signal[overbought & volume_surge & (df["st_rsi_14"] > 70)] = -0.75
    signal[overbought & volume_surge] = -0.5
    signal[overbought] = -0.25
    
    return signal


def mean_reversion(df):
    """
    Mean reversion with confidence levels.
    Uses Bollinger Bands + RSI for mean reversion plays.
    """
    signal = np.zeros(len(df))
    
    # Bullish: Deep oversold at lower band
    extreme_lower = df["lt_bb_position"] < 0.1
    lower_band = df["lt_bb_position"] < 0.3
    extreme_rsi = df["lt_rsi_28"] < 30
    moderate_rsi = df["lt_rsi_28"] < 40
    
    # Very strong: Extreme lower band + extreme RSI
    signal[extreme_lower & extreme_rsi] = 1.0
    # Strong: Lower band + extreme RSI
    signal[lower_band & extreme_rsi] = 0.75
    # Moderate: Lower band + moderate RSI
    signal[lower_band & moderate_rsi] = 0.5
    # Weak: Just at lower band
    signal[lower_band] = 0.25
    
    # Bearish: Deep overbought at upper band
    extreme_upper = df["lt_bb_position"] > 0.9
    upper_band = df["lt_bb_position"] > 0.7
    extreme_rsi_high = df["lt_rsi_28"] > 70
    moderate_rsi_high = df["lt_rsi_28"] > 60
    
    signal[extreme_upper & extreme_rsi_high] = -1.0
    signal[upper_band & extreme_rsi_high] = -0.75
    signal[upper_band & moderate_rsi_high] = -0.5
    signal[upper_band] = -0.25
    
    return signal


def breakout_strategy(df):
    """
    Breakout with confidence levels.
    Requires volume + trend confirmation + BB extremes.
    """
    signal = np.zeros(len(df))
    
    high_volume = df["lt_volume_ratio_20d"] > 1.5
    extreme_volume = df["lt_volume_ratio_20d"] > 2.0
    strong_trend = df["lt_adx_14"] > 25
    extreme_trend = df["lt_adx_14"] > 35
    
    # Bullish breakout
    upper_breakout = df["lt_bb_position"] > 0.85
    extreme_upper = df["lt_bb_position"] > 0.95
    
    # Very strong: Extreme upper + extreme volume + extreme trend
    signal[extreme_upper & extreme_volume & extreme_trend] = 1.0
    # Strong: Upper + high volume + strong trend
    signal[upper_breakout & high_volume & strong_trend] = 0.75
    # Moderate: Upper + volume
    signal[upper_breakout & high_volume] = 0.5
    # Weak: Just upper breakout
    signal[upper_breakout] = 0.25
    
    # Bearish breakout
    lower_breakout = df["lt_bb_position"] < 0.15
    extreme_lower = df["lt_bb_position"] < 0.05
    
    signal[extreme_lower & extreme_volume & extreme_trend] = -1.0
    signal[lower_breakout & high_volume & strong_trend] = -0.75
    signal[lower_breakout & high_volume] = -0.5
    signal[lower_breakout] = -0.25
    
    return signal


def rsi_divergence(df):
    """
    RSI Divergence strategy (NEW).
    Detects price making new extremes while RSI diverges.
    """
    signal = np.zeros(len(df))
    
    # Bullish divergence: Price makes lower low, RSI makes higher low (reversal signal)
    # Use short-term RSI for recent divergence
    price_near_low = df["lt_bb_position"] < 0.2
    rsi_recovering = df["st_rsi_14"] > 40  # RSI not making new low
    
    signal[price_near_low & rsi_recovering] = 0.5
    
    # Extreme: Price at bottom, RSI well recovered
    extreme_low = df["lt_bb_position"] < 0.05
    signal[extreme_low & (df["st_rsi_14"] > 50)] = 1.0
    
    # Bearish divergence
    price_near_high = df["lt_bb_position"] > 0.8
    rsi_weakening = df["st_rsi_14"] < 60
    
    signal[price_near_high & rsi_weakening] = -0.5
    
    extreme_high = df["lt_bb_position"] > 0.95
    signal[extreme_high & (df["st_rsi_14"] < 50)] = -1.0
    
    return signal


def volume_analysis(df):
    """
    Volume-based strategy (NEW).
    Heavy volume on direction moves, relative to baseline.
    """
    signal = np.zeros(len(df))
    
    high_volume = df["st_volume_ratio_5d"] > 1.5
    extreme_volume = df["st_volume_ratio_5d"] > 2.0
    
    # Bullish: High volume on positive return
    positive_return = df["st_return_5d"] > 0.02  # 2%+ return
    large_positive = df["st_return_5d"] > 0.05   # 5%+ return
    
    signal[high_volume & positive_return] = 0.5
    signal[extreme_volume & positive_return] = 0.75
    signal[extreme_volume & large_positive] = 1.0
    
    # Bearish: High volume on negative return
    negative_return = df["st_return_5d"] < -0.02
    large_negative = df["st_return_5d"] < -0.05
    
    signal[high_volume & negative_return] = -0.5
    signal[extreme_volume & negative_return] = -0.75
    signal[extreme_volume & large_negative] = -1.0
    
    return signal


def volatility_contraction(df):
    """
    Volatility contraction strategy (NEW).
    Low volatility before breakout (Bollinger Bands squeeze).
    """
    signal = np.zeros(len(df))
    
    # Calculate rolling volatility
    # Low volatility = bands are narrow = squeeze
    # High BB position = overbought/breakout
    
    # Bullish: Squeeze near bottom = potential upside
    bb_near_lower = df["lt_bb_position"] < 0.4
    rsi_neutral = (df["lt_rsi_28"] > 40) & (df["lt_rsi_28"] < 60)  # Not extreme
    
    signal[bb_near_lower & rsi_neutral] = 0.25  # Waiting setup
    signal[bb_near_lower & (df["lt_rsi_28"] > 50)] = 0.5  # Positive bias
    
    # Bullish confirmation: Squeeze breaks to upside
    bb_at_upper = df["lt_bb_position"] > 0.7
    signal[bb_at_upper & (df["lt_rsi_28"] > 60)] = 0.75
    
    # Bearish: Squeeze near top = potential downside
    bb_near_upper = df["lt_bb_position"] > 0.6
    signal[bb_near_upper & rsi_neutral] = -0.25
    signal[bb_near_upper & (df["lt_rsi_28"] < 50)] = -0.5
    
    bb_at_lower = df["lt_bb_position"] < 0.3
    signal[bb_at_lower & (df["lt_rsi_28"] < 40)] = -0.75
    
    return signal



# ======================================================
# SIGNAL ENGINE
# ======================================================

def generate_signals():
    print("Loading features...")
    df = pd.read_parquet(FEATURE_PATH)
    
    if df.empty:
        raise ValueError(f"No data found in {FEATURE_PATH}")
    
    print(f"Loaded {len(df):,} rows for {df['ticker'].nunique()} tickers")
    df = df.sort_values(["ticker", "report_date"])
    
    strategies = {
        "trend_following": trend_following,
        "momentum": momentum_strategy,
        "mean_reversion": mean_reversion,
        "breakout": breakout_strategy,
        "rsi_divergence": rsi_divergence,           # NEW
        "volume_analysis": volume_analysis,         # NEW
        "volatility_contraction": volatility_contraction  # NEW
    }
    
    # Apply each strategy
    for name, strategy in strategies.items():
        print(f"Running {name}...")
        signals = []
        for ticker, group in df.groupby("ticker"):
            signals.append(strategy(group.reset_index(drop=True)))
        df[name] = np.concatenate(signals)
    
    # Ensemble voting with confidence scores
    # Sum all strategy signals (each 0 to 1, or -1 to 0)
    # Possible range: -7 to +7 (7 strategies)
    strategy_cols = list(strategies.keys())
    df["signal_score"] = df[strategy_cols].sum(axis=1)
    
    # Convert to 0-4 scale for consistency with old system
    # -7 to -4 → -4/4, -3 to 0 → 0/4, 0 to 3 → 0 to 3/4, 4 to 7 → 4/4
    df["signal_score_normalized"] = df["signal_score"].clip(-4, 4)
    
    # Final signal: requires consensus (1+ votes in confidence scale)
    df["final_signal"] = 0
    df.loc[df["signal_score_normalized"] >= 1.5, "final_signal"] = 1    # 2+ moderate signals
    df.loc[df["signal_score_normalized"] <= -1.5, "final_signal"] = -1
    
    # Store raw score for ranking (telegram will use this)
    df["signal_score"] = df["signal_score_normalized"]
    
    df["signal_date"] = datetime.today().date()
    
    print("\n📊 Signal Distribution:")
    print(f"   Buy signals (final_signal=1): {len(df[df['final_signal'] == 1])}")
    print(f"   Sell signals (final_signal=-1): {len(df[df['final_signal'] == -1])}")
    print(f"   Neutral: {len(df[df['final_signal'] == 0])}")
    
    print(f"\n📊 Signal Score Distribution (Buy signals only):")
    buy_signals = df[df["final_signal"] == 1]["signal_score"]
    if len(buy_signals) > 0:
        print(f"   Mean: {buy_signals.mean():.2f}")
        print(f"   Min: {buy_signals.min():.2f}, Max: {buy_signals.max():.2f}")
        print(f"   Median: {buy_signals.median():.2f}")
        print(f"   Score distribution:")
        for score in sorted(buy_signals.unique(), reverse=True):
            count = len(buy_signals[buy_signals == score])
            pct = (count / len(buy_signals)) * 100
            print(f"      {score:+.1f}/4: {count:3d} signals ({pct:5.1f}%)")
    
    print("\nSaving signals...")
    duckdb.from_df(df).write_parquet(str(SIGNAL_PATH))
    print(f"✅ Saved {len(df):,} signals to {SIGNAL_PATH}")


if __name__ == "__main__":
    generate_signals()