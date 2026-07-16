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


def macd_crossover(df):
    """
    MACD Crossover strategy (NEW).
    MACD line crossing signal line with histogram confirmation.
    """
    signal = np.zeros(len(df))
    
    # Bullish crossover: MACD histogram > 0 and increasing
    # Weak: Just positive histogram
    weak_bullish = df["lt_macd_histogram"] > 0
    # Moderate: Positive histogram + strong histogram value
    moderate_bullish = (df["lt_macd_histogram"] > 0) & (df["lt_macd_histogram"] > 0.5)
    # Strong: Positive + confirmed by trend
    strong_bullish = (df["lt_macd_histogram"] > 0) & (df["lt_sma_alignment"] == 1)
    # Very strong: All conditions + ADX
    very_strong_bullish = strong_bullish & (df["lt_adx_14"] > 25)
    
    signal[weak_bullish] = 0.25
    signal[moderate_bullish] = 0.5
    signal[strong_bullish] = 0.75
    signal[very_strong_bullish] = 1.0
    
    # Bearish crossover: MACD histogram < 0
    weak_bearish = df["lt_macd_histogram"] < 0
    moderate_bearish = (df["lt_macd_histogram"] < 0) & (df["lt_macd_histogram"] < -0.5)
    strong_bearish = (df["lt_macd_histogram"] < 0) & (df["lt_sma_alignment"] == 0)
    very_strong_bearish = strong_bearish & (df["lt_adx_14"] > 25)
    
    signal[weak_bearish] = -0.25
    signal[moderate_bearish] = -0.5
    signal[strong_bearish] = -0.75
    signal[very_strong_bearish] = -1.0
    
    return signal


def stochastic_oscillator(df):
    """
    Stochastic Oscillator strategy (NEW).
    %K and %D crossovers with overbought/oversold levels.
    """
    signal = np.zeros(len(df))
    
    # Check if stochastic features exist, otherwise use RSI as proxy
    if "st_stoch_k_14" in df.columns and "st_stoch_d_14" in df.columns:
        stoch_k = df["st_stoch_k_14"]
        stoch_d = df["st_stoch_d_14"]
    else:
        # Fallback: Use RSI as proxy (already exists)
        stoch_k = df["st_rsi_14"]
        stoch_d = df["st_rsi_14"].rolling(3, min_periods=1).mean()
    
    # Bullish: K > D (upward cross) or oversold
    oversold = stoch_k < 20
    extreme_oversold = stoch_k < 10
    k_above_d = stoch_k > stoch_d
    
    # Very strong: Extreme oversold + K above D
    signal[extreme_oversold & k_above_d] = 1.0
    # Strong: Oversold + K above D
    signal[oversold & k_above_d] = 0.75
    # Moderate: Just K above D (bullish cross)
    signal[k_above_d & (stoch_k < 50)] = 0.5
    # Weak: K in oversold zone
    signal[oversold] = 0.25
    
    # Bearish: K < D (downward cross) or overbought
    overbought = stoch_k > 80
    extreme_overbought = stoch_k > 90
    k_below_d = stoch_k < stoch_d
    
    signal[extreme_overbought & k_below_d] = -1.0
    signal[overbought & k_below_d] = -0.75
    signal[k_below_d & (stoch_k > 50)] = -0.5
    signal[overbought] = -0.25
    
    return signal


def volume_trend(df):
    """
    Volume Trend strategy (NEW).
    Volume increases on up days, decreases on down days (institutional interest).
    """
    signal = np.zeros(len(df))
    
    # Bullish: Positive return + high volume ratio
    positive_return = df["st_return_5d"] > 0
    high_volume = df["st_volume_ratio_5d"] > 1.3
    extreme_volume = df["st_volume_ratio_5d"] > 1.8
    
    large_positive = df["st_return_5d"] > 0.05  # 5%+ move
    
    # Very strong: Large positive return + extreme volume
    signal[large_positive & extreme_volume] = 1.0
    # Strong: Positive return + extreme volume
    signal[positive_return & extreme_volume] = 0.75
    # Moderate: Positive return + high volume
    signal[positive_return & high_volume] = 0.5
    # Weak: Just positive return (light volume)
    signal[positive_return & (df["st_volume_ratio_5d"] > 1.0)] = 0.25
    
    # Bearish: Negative return + high volume
    negative_return = df["st_return_5d"] < 0
    large_negative = df["st_return_5d"] < -0.05
    
    signal[large_negative & extreme_volume] = -1.0
    signal[negative_return & extreme_volume] = -0.75
    signal[negative_return & high_volume] = -0.5
    signal[negative_return & (df["st_volume_ratio_5d"] > 1.0)] = -0.25
    
    return signal


def adx_strength_only(df):
    """
    ADX Strength Only strategy (NEW).
    Strong trend without directional bias - confirms momentum exists.
    Works well with other directional indicators.
    """
    signal = np.zeros(len(df))
    
    # Strong trend detected (ADX > 25)
    strong_trend = df["lt_adx_14"] > 25
    very_strong_trend = df["lt_adx_14"] > 35
    extreme_trend = df["lt_adx_14"] > 45
    
    # Combine with RSI for direction
    rsi_bullish = df["st_rsi_14"] > 50
    rsi_bearish = df["st_rsi_14"] < 50
    
    # Bullish: Strong trend + RSI above 50
    signal[strong_trend & rsi_bullish] = 0.25
    signal[very_strong_trend & rsi_bullish] = 0.5
    signal[extreme_trend & rsi_bullish] = 0.75
    signal[extreme_trend & rsi_bullish & (df["st_return_5d"] > 0)] = 1.0
    
    # Bearish: Strong trend + RSI below 50
    signal[strong_trend & rsi_bearish] = -0.25
    signal[very_strong_trend & rsi_bearish] = -0.5
    signal[extreme_trend & rsi_bearish] = -0.75
    signal[extreme_trend & rsi_bearish & (df["st_return_5d"] < 0)] = -1.0
    
    return signal


def price_action(df):
    """
    Price Action strategy (NEW).
    Based on RSI position and recent return momentum (swing highs/lows proxy).
    """
    signal = np.zeros(len(df))
    
    # Bullish: Higher lows pattern (RSI making higher lows)
    # Proxy: RSI above 40 but below 60 with positive return
    rsi_higher_low = (df["st_rsi_14"] > 40) & (df["st_rsi_14"] < 60)
    positive_return = df["st_return_5d"] > 0
    strong_positive = df["st_return_5d"] > 0.03
    
    # Very strong: Recent strong move + RSI recovery
    signal[(df["st_return_5d"] > 0.08) & (df["st_rsi_14"] > 45)] = 1.0
    # Strong: Positive return + RSI recovery
    signal[strong_positive & (df["st_rsi_14"] > 50)] = 0.75
    # Moderate: Positive return + neutral RSI
    signal[positive_return & rsi_higher_low] = 0.5
    # Weak: Just positive return
    signal[positive_return & (df["st_rsi_14"] < 40)] = 0.25
    
    # Bearish: Lower highs pattern (RSI making lower highs)
    rsi_lower_high = (df["st_rsi_14"] > 40) & (df["st_rsi_14"] < 60)
    negative_return = df["st_return_5d"] < 0
    strong_negative = df["st_return_5d"] < -0.03
    
    signal[(df["st_return_5d"] < -0.08) & (df["st_rsi_14"] < 55)] = -1.0
    signal[strong_negative & (df["st_rsi_14"] < 50)] = -0.75
    signal[negative_return & rsi_lower_high] = -0.5
    signal[negative_return & (df["st_rsi_14"] > 60)] = -0.25
    
    return signal


def bb_squeeze_breakout(df):
    """
    Bollinger Band Squeeze Breakout strategy (NEW).
    Detects narrow bands (squeeze) and subsequent breakouts.
    Different from volatility_contraction - focuses on actual breakout confirmation.
    """
    signal = np.zeros(len(df))
    
    # Breakout above upper band with strong volume
    upper_extreme = df["lt_bb_position"] > 0.95
    upper_strong = df["lt_bb_position"] > 0.85
    volume_surge = df["st_volume_ratio_5d"] > 1.3
    
    # Very strong: Extreme upper + volume + positive return
    signal[upper_extreme & volume_surge & (df["st_return_5d"] > 0.02)] = 1.0
    # Strong: Strong upper + volume
    signal[upper_strong & volume_surge] = 0.75
    # Moderate: Upper + moderate volume
    signal[upper_strong & (df["st_volume_ratio_5d"] > 1.0)] = 0.5
    # Weak: Just upper extreme
    signal[upper_extreme] = 0.25
    
    # Breakout below lower band with strong volume
    lower_extreme = df["lt_bb_position"] < 0.05
    lower_strong = df["lt_bb_position"] < 0.15
    
    signal[lower_extreme & volume_surge & (df["st_return_5d"] < -0.02)] = -1.0
    signal[lower_strong & volume_surge] = -0.75
    signal[lower_strong & (df["st_volume_ratio_5d"] > 1.0)] = -0.5
    signal[lower_extreme] = -0.25
    
    return signal


def return_magnitude(df):
    """
    Return Magnitude strategy (NEW).
    Pure return-based signal - captures directional moves.
    Different from volume_trend as it ignores volume.
    """
    signal = np.zeros(len(df))
    
    # Bullish: Recent strong positive returns
    extreme_return = df["st_return_5d"] > 0.10  # 10%+ move
    large_return = df["st_return_5d"] > 0.05   # 5%+ move
    moderate_return = df["st_return_5d"] > 0.02  # 2%+ move
    positive_return = df["st_return_5d"] > 0
    
    # Very strong: Extreme move
    signal[extreme_return] = 1.0
    # Strong: Large move
    signal[large_return & ~extreme_return] = 0.75
    # Moderate: Moderate move
    signal[moderate_return & ~large_return] = 0.5
    # Weak: Any positive move
    signal[positive_return & ~moderate_return] = 0.25
    
    # Bearish: Recent strong negative returns
    extreme_negative = df["st_return_5d"] < -0.10
    large_negative = df["st_return_5d"] < -0.05
    moderate_negative = df["st_return_5d"] < -0.02
    negative_return = df["st_return_5d"] < 0
    
    signal[extreme_negative] = -1.0
    signal[large_negative & ~extreme_negative] = -0.75
    signal[moderate_negative & ~large_negative] = -0.5
    signal[negative_return & ~moderate_negative] = -0.25
    
    return signal


def rsi_extremes(df):
    """
    RSI Extremes strategy (NEW).
    Pure RSI-based strategy focusing on extreme levels.
    Different from momentum_strategy - no volume confirmation.
    """
    signal = np.zeros(len(df))
    
    # Bullish extremes
    extreme_oversold = df["st_rsi_14"] < 10
    very_oversold = df["st_rsi_14"] < 20
    oversold = df["st_rsi_14"] < 30
    mildly_oversold = df["st_rsi_14"] < 40
    
    # Very strong: Extreme oversold
    signal[extreme_oversold] = 1.0
    # Strong: Very oversold
    signal[very_oversold & ~extreme_oversold] = 0.75
    # Moderate: Oversold
    signal[oversold & ~very_oversold] = 0.5
    # Weak: Mildly oversold
    signal[mildly_oversold & ~oversold] = 0.25
    
    # Bearish extremes
    extreme_overbought = df["st_rsi_14"] > 90
    very_overbought = df["st_rsi_14"] > 80
    overbought = df["st_rsi_14"] > 70
    mildly_overbought = df["st_rsi_14"] > 60
    
    signal[extreme_overbought] = -1.0
    signal[very_overbought & ~extreme_overbought] = -0.75
    signal[overbought & ~very_overbought] = -0.5
    signal[mildly_overbought & ~overbought] = -0.25
    
    return signal



# ======================================================
# SIGNAL ENGINE
# ======================================================

def generate_signals(force=False):
    print("Loading features...")
    df = pd.read_parquet(FEATURE_PATH)
    
    if df.empty:
        raise ValueError(f"No data found in {FEATURE_PATH}")
    
    # Check if signals already exist for today
    today = datetime.today().date()
    if SIGNAL_PATH.exists() and not force:
        existing_signals = pd.read_parquet(SIGNAL_PATH)
        if not existing_signals.empty and existing_signals['signal_date'].max() == today:
            print(f"✅ Signals already calculated for {today}")
            print(f"   File: {SIGNAL_PATH}")
            print(f"   Buy signals: {len(existing_signals[existing_signals['final_signal'] == 1])}")
            print(f"   Sell signals: {len(existing_signals[existing_signals['final_signal'] == -1])}")
            print(f"\n💡 Use --force to recalculate: python signal_engine.py --force")
            return
    
    print(f"Loaded {len(df):,} rows for {df['ticker'].nunique()} tickers")
    df = df.sort_values(["ticker", "report_date"])
    
    strategies = {
        "trend_following": trend_following,
        "momentum": momentum_strategy,
        "mean_reversion": mean_reversion,
        "breakout": breakout_strategy,
        "rsi_divergence": rsi_divergence,
        "volume_analysis": volume_analysis,
        "volatility_contraction": volatility_contraction,
        "macd_crossover": macd_crossover,
        "stochastic_oscillator": stochastic_oscillator,
        "volume_trend": volume_trend,
        "adx_strength_only": adx_strength_only,
        "price_action": price_action,
        "bb_squeeze_breakout": bb_squeeze_breakout,
        "return_magnitude": return_magnitude,
        "rsi_extremes": rsi_extremes
    }
    
    # Apply each strategy
    for name, strategy in strategies.items():
        print(f"Running {name}...")
        signals = []
        for ticker, group in df.groupby("ticker"):
            signals.append(strategy(group.reset_index(drop=True)))
        df[name] = np.concatenate(signals)
    
    # Ensemble voting: sum all strategy scores
    # Range: -15 to +15 (15 strategies with confidence levels 0.25/0.5/0.75/1.0)
    strategy_cols = list(strategies.keys())
    df["signal_score_raw"] = df[strategy_cols].sum(axis=1)
    
    # Scale to 0-4 range for display consistency
    # Preserves differentiation: raw 15 → 4.0, raw 10 → 2.67, raw 5 → 1.33
    df["signal_score"] = (df["signal_score_raw"] / 15.0 * 4.0).clip(-4, 4)
    
    # Final signal: requires MAJORITY consensus (2.0+ on 0-4 scale = ~7.5 raw = 50% of strategies)
    # This ensures we only act on strong setups where multiple indicators align
    df["final_signal"] = 0
    df.loc[df["signal_score"] >= 2.0, "final_signal"] = 1
    df.loc[df["signal_score"] <= -2.0, "final_signal"] = -1
    
    df["signal_date"] = today
    
    print("\n📊 Signal Distribution:")
    print(f"   Buy signals (final_signal=1): {len(df[df['final_signal'] == 1])}")
    print(f"   Sell signals (final_signal=-1): {len(df[df['final_signal'] == -1])}")
    print(f"   Neutral: {len(df[df['final_signal'] == 0])}")
    
    print(f"\n📊 Signal Score Distribution (Buy signals only):")
    buy_signals = df[df["final_signal"] == 1]["signal_score"]
    if len(buy_signals) > 0:
        print(f"   Mean: {buy_signals.mean():.2f}/4")
        print(f"   Min: {buy_signals.min():.2f}, Max: {buy_signals.max():.2f}")
        print(f"   Median: {buy_signals.median():.2f}/4")
        print(f"   Score distribution:")
        for score in sorted(buy_signals.unique(), reverse=True):
            count = len(buy_signals[buy_signals == score])
            pct = (count / len(buy_signals)) * 100
            print(f"      {score:+.1f}/4: {count:3d} signals ({pct:5.1f}%)")
    
    print("\nSaving signals...")
    duckdb.from_df(df).write_parquet(str(SIGNAL_PATH))
    print(f"✅ Saved {len(df):,} signals to {SIGNAL_PATH}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate trading signals")
    parser.add_argument("--force", action="store_true", help="Force recalculation even if signals exist for today")
    args = parser.parse_args()
    
    generate_signals(force=args.force)