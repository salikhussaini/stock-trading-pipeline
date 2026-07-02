# =========================================================
# backtester.py
# Technical Analysis Strategy Backtester
# Evaluates trading signals from stock_features
# =========================================================

from pathlib import Path
from datetime import timedelta
from multiprocessing import Pool
import duckdb
import pandas as pd
import numpy as np
from typing import Dict, Tuple, List
import argparse
import sys

from logger_config import (
    log_info, log_debug, log_error, log_warning,
    log_section, log_pipeline_start, log_pipeline_end, log_metrics
)

DB_PATH = Path(__file__).parent / "database" / "stock_data.duckdb"
FEATURES_PATH = Path(__file__).parent / "database" / "stock_features.parquet"

# =========================================================
# SIGNAL GENERATION - MULTIPLE STRATEGIES
# =========================================================

def rsi_classic(df: pd.DataFrame, buy_threshold: int = 30, sell_threshold: int = 70) -> pd.DataFrame:
    """RSI Overbought/Oversold (Classic)"""
    df = df.copy()
    df['signal'] = 0
    df.loc[df['rsi_14'] < buy_threshold, 'signal'] = 1
    df.loc[df['rsi_14'] > sell_threshold, 'signal'] = -1
    return df

def rsi_extreme(df: pd.DataFrame) -> pd.DataFrame:
    """RSI Extreme: More aggressive (< 20 / > 80)"""
    return rsi_classic(df, buy_threshold=20, sell_threshold=80)

def rsi_loose(df: pd.DataFrame) -> pd.DataFrame:
    """RSI Loose: More conservative (< 40 / > 60)"""
    return rsi_classic(df, buy_threshold=40, sell_threshold=60)

def macd_only(df: pd.DataFrame) -> pd.DataFrame:
    """MACD Crossover only"""
    df = df.copy()
    df['signal'] = 0
    
    macd_buy = (df['macd'] > df['macd_signal']) & (df['macd_histogram'] > 0)
    macd_sell = (df['macd'] < df['macd_signal']) & (df['macd_histogram'] < 0)
    
    df.loc[macd_buy, 'signal'] = 1
    df.loc[macd_sell, 'signal'] = -1
    
    return df

def rsi_macd_combo(df: pd.DataFrame) -> pd.DataFrame:
    """RSI + MACD: Both must agree"""
    df = df.copy()
    df['signal'] = 0
    
    # BUY: RSI oversold AND MACD positive
    buy = (df['rsi_14'] < 30) & (df['macd'] > df['macd_signal'])
    # SELL: RSI overbought AND MACD negative
    sell = (df['rsi_14'] > 70) & (df['macd'] < df['macd_signal'])
    
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    return df

def bollinger_bands_strategy(df: pd.DataFrame) -> pd.DataFrame:
    """Bollinger Bands: Price extremes"""
    df = df.copy()
    df['signal'] = 0
    
    # BUY when price hits lower band
    df.loc[df['bb_position'] < 0.2, 'signal'] = 1
    # SELL when price hits upper band
    df.loc[df['bb_position'] > 0.8, 'signal'] = -1
    
    return df

def rsi_bollinger_combo(df: pd.DataFrame) -> pd.DataFrame:
    """RSI + Bollinger Bands: Both signals reinforce"""
    df = df.copy()
    df['signal'] = 0
    
    # BUY: Low RSI AND price near lower band
    buy = (df['rsi_14'] < 30) & (df['bb_position'] < 0.3)
    # SELL: High RSI AND price near upper band
    sell = (df['rsi_14'] > 70) & (df['bb_position'] > 0.7)
    
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    return df

def volatility_momentum(df: pd.DataFrame) -> pd.DataFrame:
    """Volatility + Momentum: Trade when volatility rises + momentum positive"""
    df = df.copy()
    df['signal'] = 0
    
    # BUY: Rising volatility + positive momentum
    buy = (df['rolling_vol_20d'] > df['rolling_vol_20d'].rolling(20).mean()) & (df['momentum_20'] > 0)
    # SELL: Rising volatility + negative momentum
    sell = (df['rolling_vol_20d'] > df['rolling_vol_20d'].rolling(20).mean()) & (df['momentum_20'] < 0)
    
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    return df

def stochastic_oscillator(df: pd.DataFrame) -> pd.DataFrame:
    """Stochastic Oscillator: Buy oversold, Sell overbought"""
    df = df.copy()
    df['signal'] = 0
    
    # BUY when K < 20 (oversold)
    df.loc[df['stoch_k'] < 20, 'signal'] = 1
    # SELL when K > 80 (overbought)
    df.loc[df['stoch_k'] > 80, 'signal'] = -1
    
    return df

def stochastic_signal_cross(df: pd.DataFrame) -> pd.DataFrame:
    """Stochastic Crossover: K crosses above/below D line"""
    df = df.copy()
    df['signal'] = 0
    
    # BUY when K crosses above D (in oversold region)
    buy = (df['stoch_k'] > df['stoch_d']) & (df['stoch_k'] < 50) & (df['stoch_k'].shift(1) <= df['stoch_d'].shift(1))
    # SELL when K crosses below D (in overbought region)
    sell = (df['stoch_k'] < df['stoch_d']) & (df['stoch_k'] > 50) & (df['stoch_k'].shift(1) >= df['stoch_d'].shift(1))
    
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    return df

def moving_average_crossover(df: pd.DataFrame) -> pd.DataFrame:
    """Moving Average Crossover: SMA 10 crosses SMA 50 (Golden Cross)"""
    df = df.copy()
    df['signal'] = 0
    
    # BUY when SMA10 > SMA50 AND was below last period (bullish cross)
    buy = (df['sma_10'] > df['sma_50']) & (df['sma_10'].shift(1) <= df['sma_50'].shift(1))
    # SELL when SMA10 < SMA50 AND was above last period (bearish cross)
    sell = (df['sma_10'] < df['sma_50']) & (df['sma_10'].shift(1) >= df['sma_50'].shift(1))
    
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    return df

def ema_crossover(df: pd.DataFrame) -> pd.DataFrame:
    """EMA Crossover: EMA 10 crosses EMA 20"""
    df = df.copy()
    df['signal'] = 0
    
    # BUY when EMA10 > EMA20
    buy = (df['ema_10'] > df['ema_20']) & (df['ema_10'].shift(1) <= df['ema_20'].shift(1))
    # SELL when EMA10 < EMA20
    sell = (df['ema_10'] < df['ema_20']) & (df['ema_10'].shift(1) >= df['ema_20'].shift(1))
    
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    return df

def atr_breakout(df: pd.DataFrame) -> pd.DataFrame:
    """ATR Breakout: Trade on volatility expansion + price momentum"""
    df = df.copy()
    df['signal'] = 0
    
    # High ATR ratio means volatility expansion
    high_atr = df['atr_ratio'] > df['atr_ratio'].rolling(20).mean()
    
    # BUY: High volatility + positive momentum
    buy = high_atr & (df['momentum_20'] > 0) & (df['rsi_14'] < 60)
    # SELL: High volatility + negative momentum
    sell = high_atr & (df['momentum_20'] < 0) & (df['rsi_14'] > 40)
    
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    return df

def volume_rsi_combo(df: pd.DataFrame) -> pd.DataFrame:
    """Volume Confirmation + RSI: RSI signal + volume confirmation"""
    df = df.copy()
    df['signal'] = 0
    
    # High volume (above 20-day average)
    high_vol = df['volume_zscore_20d'] > 0.5
    
    # BUY: RSI oversold + high volume
    buy = (df['rsi_14'] < 30) & high_vol
    # SELL: RSI overbought + high volume
    sell = (df['rsi_14'] > 70) & high_vol
    
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    return df

def rsi_stochastic_combo(df: pd.DataFrame) -> pd.DataFrame:
    """RSI + Stochastic: Both must signal same direction (confluence)"""
    df = df.copy()
    df['signal'] = 0
    
    # BUY: Both RSI and Stochastic oversold
    buy = (df['rsi_14'] < 30) & (df['stoch_k'] < 30)
    # SELL: Both RSI and Stochastic overbought
    sell = (df['rsi_14'] > 70) & (df['stoch_k'] > 70)
    
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    return df

def price_action_mean_reversion(df: pd.DataFrame) -> pd.DataFrame:
    """Mean Reversion: Price extremes revert to mean (bands + momentum)"""
    df = df.copy()
    df['signal'] = 0
    
    # BUY: Price near lower band + positive momentum reversal
    buy = (df['bb_position'] < 0.2) & (df['return_5d'] < 0) & (df['momentum_10'] > 0)
    # SELL: Price near upper band + negative momentum reversal
    sell = (df['bb_position'] > 0.8) & (df['return_5d'] > 0) & (df['momentum_10'] < 0)
    
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    return df

def macd_histogram_zero(df: pd.DataFrame) -> pd.DataFrame:
    """MACD Histogram Zero Cross: Trade when histogram crosses zero"""
    df = df.copy()
    df['signal'] = 0
    
    # BUY when histogram crosses above zero (growing bullish)
    buy = (df['macd_histogram'] > 0) & (df['macd_histogram'].shift(1) <= 0)
    # SELL when histogram crosses below zero (growing bearish)
    sell = (df['macd_histogram'] < 0) & (df['macd_histogram'].shift(1) >= 0)
    
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    return df

def trend_with_pullback(df: pd.DataFrame) -> pd.DataFrame:
    """Trend + Pullback: Trade pullbacks in trending market"""
    df = df.copy()
    df['signal'] = 0
    
    # Uptrend: Price above all SMAs
    uptrend = (df['close'] > df['sma_10']) & (df['sma_10'] > df['sma_20']) & (df['sma_20'] > df['sma_50'])
    # Downtrend: Price below all SMAs
    downtrend = (df['close'] < df['sma_10']) & (df['sma_10'] < df['sma_20']) & (df['sma_20'] < df['sma_50'])
    
    # BUY: Uptrend + price pulled back to support (RSI < 40)
    buy = uptrend & (df['rsi_14'] < 40)
    # SELL: Downtrend + price bounced to resistance (RSI > 60)
    sell = downtrend & (df['rsi_14'] > 60)
    
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    return df

def volatility_expansion(df: pd.DataFrame) -> pd.DataFrame:
    """Volatility Expansion: Trade on volatility breakouts"""
    df = df.copy()
    df['signal'] = 0
    
    # High volatility vs recent average
    vol_expansion = df['rolling_vol_20d'] > (df['rolling_vol_50d'] * 1.5)
    
    # BUY: Vol expansion + positive momentum
    buy = vol_expansion & (df['momentum_20'] > 0)
    # SELL: Vol expansion + negative momentum
    sell = vol_expansion & (df['momentum_20'] < 0)
    
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    return df

def williams_percent_r(df: pd.DataFrame) -> pd.DataFrame:
    """Williams %R Equivalent: Use RSI as proxy (similar behavior)"""
    df = df.copy()
    df['signal'] = 0
    
    # Use RSI as a proxy for Williams %R (similar oversold/overbought behavior)
    # Williams %R typically ranges from -100 to 0, RSI from 0-100
    # Both measure momentum in similar ways
    
    # BUY when RSI < 25 (extreme oversold, like %R < -75)
    df.loc[df['rsi_14'] < 25, 'signal'] = 1
    # SELL when RSI > 75 (extreme overbought, like %R > -25)
    df.loc[df['rsi_14'] > 75, 'signal'] = -1
    
    return df

def support_resistance_breakout(df: pd.DataFrame) -> pd.DataFrame:
    """Support/Resistance Breakout: Trade key price levels using price action"""
    df = df.copy()
    df['signal'] = 0
    
    # Calculate support/resistance from close prices and price position
    # Support: low prices in recent period (estimated from close - volatility)
    vol = df['rolling_vol_20d']
    close_sma = df['close'].rolling(20).mean()
    support = close_sma - (2 * vol)
    resistance = close_sma + (2 * vol)
    
    # BUY when price breaks above resistance with momentum
    buy = (df['close'] > resistance) & (df['momentum_20'] > 0)
    # SELL when price breaks below support with momentum
    sell = (df['close'] < support) & (df['momentum_20'] < 0)
    
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    return df

def rsi_divergence(df: pd.DataFrame) -> pd.DataFrame:
    """RSI Divergence: Price makes new low but RSI doesn't (bullish)"""
    df = df.copy()
    df['signal'] = 0
    
    # Find local bottoms (troughs) in price and RSI
    price_trough = df['close'] < df['close'].rolling(5, center=True).min()
    rsi_trough = df['rsi_14'] < df['rsi_14'].rolling(5, center=True).min()
    
    # Bullish divergence: Price lower but RSI higher
    buy = (df['close'] < df['close'].shift(10)) & (df['rsi_14'] > df['rsi_14'].shift(10)) & (df['rsi_14'] < 40)
    # Bearish divergence: Price higher but RSI lower
    sell = (df['close'] > df['close'].shift(10)) & (df['rsi_14'] < df['rsi_14'].shift(10)) & (df['rsi_14'] > 60)
    
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    return df

def volume_obv_trend(df: pd.DataFrame) -> pd.DataFrame:
    """OBV Trend: On-Balance Volume confirms trend"""
    df = df.copy()
    df['signal'] = 0
    
    # On-Balance Volume (simplified)
    obv = pd.Series(index=df.index, dtype=float)
    obv.iloc[0] = 0
    for i in range(1, len(df)):
        if df['close'].iloc[i] > df['close'].iloc[i-1]:
            obv.iloc[i] = obv.iloc[i-1] + df['volume'].iloc[i]
        elif df['close'].iloc[i] < df['close'].iloc[i-1]:
            obv.iloc[i] = obv.iloc[i-1] - df['volume'].iloc[i]
        else:
            obv.iloc[i] = obv.iloc[i-1]
    
    obv_sma = obv.rolling(20).mean()
    
    # BUY: OBV above its SMA + price above SMA50
    buy = (obv > obv_sma) & (df['close'] > df['sma_50'])
    # SELL: OBV below its SMA + price below SMA50
    sell = (obv < obv_sma) & (df['close'] < df['sma_50'])
    
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    return df

def multi_timeframe_ma(df: pd.DataFrame) -> pd.DataFrame:
    """Multi-Timeframe: Short/Medium/Long MA alignment"""
    df = df.copy()
    df['signal'] = 0
    
    # Bullish alignment: Fast > Medium > Slow
    bullish = (df['sma_10'] > df['sma_20']) & (df['sma_20'] > df['sma_50'])
    # Bearish alignment: Fast < Medium < Slow
    bearish = (df['sma_10'] < df['sma_20']) & (df['sma_20'] < df['sma_50'])
    
    # BUY: Bullish alignment + price above SMA10
    buy = bullish & (df['close'] > df['sma_10'])
    # SELL: Bearish alignment + price below SMA10
    sell = bearish & (df['close'] < df['sma_10'])
    
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    return df

def roc_momentum_filter(df: pd.DataFrame) -> pd.DataFrame:
    """Rate of Change (ROC) with momentum filter"""
    df = df.copy()
    df['signal'] = 0
    
    # Strong positive ROC
    strong_up = df['roc_10'] > df['roc_10'].rolling(20).mean()
    # Strong negative ROC
    strong_down = df['roc_10'] < df['roc_10'].rolling(20).mean()
    
    # BUY: Strong positive ROC + RSI < 70 (not overbought)
    buy = strong_up & (df['rsi_14'] < 70)
    # SELL: Strong negative ROC + RSI > 30 (not oversold)
    sell = strong_down & (df['rsi_14'] > 30)
    
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    return df

def bb_squeeze(df: pd.DataFrame) -> pd.DataFrame:
    """Bollinger Band Squeeze: Low volatility before breakout"""
    df = df.copy()
    df['signal'] = 0
    
    # BB width (squeeze when narrow)
    bb_narrow = df['bb_width'] < df['bb_width'].rolling(20).quantile(0.25)
    
    # BUY: Squeeze + breakout up
    buy = bb_narrow & (df['close'] > df['bb_upper'])
    # SELL: Squeeze + breakout down
    sell = bb_narrow & (df['close'] < df['bb_lower'])
    
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    return df

def combined_oscillators(df: pd.DataFrame) -> pd.DataFrame:
    """Combined Oscillators: RSI, Stochastic, MACD all agree"""
    df = df.copy()
    df['signal'] = 0
    
    rsi_buy = df['rsi_14'] < 30
    stoch_buy = df['stoch_k'] < 30
    macd_buy = df['macd_histogram'] > 0
    
    rsi_sell = df['rsi_14'] > 70
    stoch_sell = df['stoch_k'] > 70
    macd_sell = df['macd_histogram'] < 0
    
    # All three indicators agree
    buy = rsi_buy & stoch_buy & macd_buy
    sell = rsi_sell & stoch_sell & macd_sell
    
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    return df

def price_above_below_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """VWAP Strategy: Price above/below VWAP confirmation"""
    df = df.copy()
    df['signal'] = 0
    
    # BUY: Price above VWAP + RSI < 50
    buy = (df['close'] > df['vwap_20']) & (df['rsi_14'] < 50)
    # SELL: Price below VWAP + RSI > 50
    sell = (df['close'] < df['vwap_20']) & (df['rsi_14'] > 50)
    
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    
    return df

# Available strategies
STRATEGIES = {
    'rsi_classic': rsi_classic,
    'rsi_extreme': rsi_extreme,
    'rsi_loose': rsi_loose,
    'macd_only': macd_only,
    'rsi_macd_combo': rsi_macd_combo,
    'bollinger_bands': bollinger_bands_strategy,
    'rsi_bollinger_combo': rsi_bollinger_combo,
    'volatility_momentum': volatility_momentum,
    'stochastic': stochastic_oscillator,
    'stochastic_cross': stochastic_signal_cross,
    'sma_crossover': moving_average_crossover,
    'ema_crossover': ema_crossover,
    'atr_breakout': atr_breakout,
    'volume_rsi': volume_rsi_combo,
    'rsi_stochastic': rsi_stochastic_combo,
    'mean_reversion': price_action_mean_reversion,
    'macd_histogram': macd_histogram_zero,
    'trend_pullback': trend_with_pullback,
    'volatility_expansion': volatility_expansion,
    'williams_r': williams_percent_r,
    'support_resistance': support_resistance_breakout,
    'rsi_divergence': rsi_divergence,
    'obv_trend': volume_obv_trend,
    'ma_alignment': multi_timeframe_ma,
    'roc_filter': roc_momentum_filter,
    'bb_squeeze': bb_squeeze,
    'all_oscillators': combined_oscillators,
    'vwap_strategy': price_above_below_vwap,
}

# =========================================================
# BACKTEST LOGIC
# =========================================================

# =========================================================
# WALK-FORWARD ANALYSIS (Anti-Overfitting)
# =========================================================

def optimize_rsi_params(df: pd.DataFrame) -> Dict:
    """
    Optimize RSI parameters on training data.
    Grid search over buy/sell thresholds.
    
    Returns best parameters based on Sharpe ratio.
    """
    best_sharpe = -999
    best_params = {'buy_threshold': 30, 'sell_threshold': 70}
    
    # Grid search
    for buy_thresh in [20, 25, 30, 35, 40]:
        for sell_thresh in [60, 65, 70, 75, 80]:
            if sell_thresh <= buy_thresh:
                continue
            
            test_df = rsi_classic(df.copy(), buy_threshold=buy_thresh, sell_threshold=sell_thresh)
            result = backtest_strategy(test_df, initial_capital=10000)
            
            if 'error' not in result and result['sharpe_ratio'] > best_sharpe:
                best_sharpe = result['sharpe_ratio']
                best_params = {'buy_threshold': buy_thresh, 'sell_threshold': sell_thresh}
    
    return best_params

def optimize_macd_params(df: pd.DataFrame) -> Dict:
    """
    Optimize MACD signal thresholds on training data.
    Grid search over histogram threshold for entry.
    
    Returns best parameters based on Sharpe ratio.
    """
    best_sharpe = -999
    best_params = {'histogram_threshold': 0}
    
    # Grid search over histogram thresholds
    for hist_thresh in [-0.5, -0.3, -0.1, 0, 0.1, 0.3, 0.5]:
        test_df = df.copy()
        test_df['signal'] = 0
        
        # BUY when MACD crosses above signal AND histogram > threshold
        macd_buy = (test_df['macd'] > test_df['macd_signal']) & (test_df['macd_histogram'] > hist_thresh)
        # SELL when MACD crosses below signal AND histogram < -threshold
        macd_sell = (test_df['macd'] < test_df['macd_signal']) & (test_df['macd_histogram'] < -hist_thresh)
        
        test_df.loc[macd_buy, 'signal'] = 1
        test_df.loc[macd_sell, 'signal'] = -1
        
        result = backtest_strategy(test_df, initial_capital=10000)
        
        if 'error' not in result and result['sharpe_ratio'] > best_sharpe:
            best_sharpe = result['sharpe_ratio']
            best_params = {'histogram_threshold': hist_thresh}
    
    return best_params

def optimize_bb_params(df: pd.DataFrame) -> Dict:
    """
    Optimize Bollinger Bands position thresholds on training data.
    Grid search over upper/lower band position thresholds.
    
    Returns best parameters based on Sharpe ratio.
    """
    best_sharpe = -999
    best_params = {'lower_threshold': 0.2, 'upper_threshold': 0.8}
    
    # Grid search over BB position thresholds
    for lower_thresh in [0.1, 0.15, 0.2, 0.25, 0.3]:
        for upper_thresh in [0.7, 0.75, 0.8, 0.85, 0.9]:
            if upper_thresh <= lower_thresh:
                continue
            
            test_df = df.copy()
            test_df['signal'] = 0
            
            # BUY when price hits lower band
            test_df.loc[test_df['bb_position'] < lower_thresh, 'signal'] = 1
            # SELL when price hits upper band
            test_df.loc[test_df['bb_position'] > upper_thresh, 'signal'] = -1
            
            result = backtest_strategy(test_df, initial_capital=10000)
            
            if 'error' not in result and result['sharpe_ratio'] > best_sharpe:
                best_sharpe = result['sharpe_ratio']
                best_params = {'lower_threshold': lower_thresh, 'upper_threshold': upper_thresh}
    
    return best_params

def optimize_ma_crossover_params(df: pd.DataFrame) -> Dict:
    """
    Optimize Moving Average crossover pair on training data.
    Tests different MA combinations to find best performing pair.
    
    Returns best parameters based on Sharpe ratio.
    """
    best_sharpe = -999
    best_params = {'short_ma': 'sma_10', 'long_ma': 'sma_50'}
    
    # Test different MA combinations
    ma_pairs = [
        ('sma_10', 'sma_20'),
        ('sma_10', 'sma_50'),
        ('sma_20', 'sma_50'),
        ('ema_10', 'ema_20'),
        ('ema_10', 'sma_50'),
    ]
    
    for short_ma, long_ma in ma_pairs:
        # Skip if columns don't exist
        if short_ma not in df.columns or long_ma not in df.columns:
            continue
        
        test_df = df.copy()
        test_df['signal'] = 0
        
        # BUY when short MA crosses above long MA
        buy = (test_df[short_ma] > test_df[long_ma]) & (test_df[short_ma].shift(1) <= test_df[long_ma].shift(1))
        # SELL when short MA crosses below long MA
        sell = (test_df[short_ma] < test_df[long_ma]) & (test_df[short_ma].shift(1) >= test_df[long_ma].shift(1))
        
        test_df.loc[buy, 'signal'] = 1
        test_df.loc[sell, 'signal'] = -1
        
        result = backtest_strategy(test_df, initial_capital=10000)
        
        if 'error' not in result and result['sharpe_ratio'] > best_sharpe:
            best_sharpe = result['sharpe_ratio']
            best_params = {'short_ma': short_ma, 'long_ma': long_ma}
    
    return best_params

def walk_forward_analysis(
    df: pd.DataFrame,
    strategy_name: str = 'rsi_classic',
    train_days: int = 252,  # 1 year training
    test_days: int = 63,    # 1 quarter testing
    step_days: int = 21     # Roll forward 1 month at a time
) -> Dict:
    """
    Walk-Forward Analysis: Prevents overfitting by testing on unseen data.
    
    Process:
    1. Train on Year 1 → Optimize parameters
    2. Test on Quarter 1 of Year 2 (out-of-sample)
    3. Roll forward by 1 month
    4. Repeat until end of data
    
    Supported Strategies with Optimization:
    - 'rsi_classic': Optimizes buy/sell thresholds
    - 'macd_only': Optimizes histogram threshold
    - 'bollinger_bands': Optimizes band position thresholds
    - 'sma_crossover', 'ema_crossover', 'ma_crossover': Optimizes MA pair selection
    - Other strategies: Uses fixed parameters (no optimization)
    
    Args:
        df: Historical data (must have 'report_date' sorted)
        strategy_name: Strategy to test
        train_days: Training window size (252 = 1 year)
        test_days: Testing window size (63 = 1 quarter)
        step_days: Roll forward step (21 = 1 month)
    
    Returns:
        Dictionary with walk-forward results
    """
    df = df.sort_values('report_date').reset_index(drop=True)
    
    if len(df) < train_days + test_days:
        return {
            'error': f'Insufficient data: need {train_days + test_days} days, have {len(df)}',
            'ticker': df.iloc[0]['ticker'] if 'ticker' in df.columns else 'UNKNOWN'
        }
    
    all_trades = []
    window_results = []
    total_portfolio_value = 10000
    
    # Walk forward through time
    start_idx = 0
    window_num = 1
    
    while start_idx + train_days + test_days <= len(df):
        # Split into train and test
        train_df = df.iloc[start_idx : start_idx + train_days].copy()
        test_df = df.iloc[start_idx + train_days : start_idx + train_days + test_days].copy()
        
        train_start = train_df.iloc[0]['report_date']
        train_end = train_df.iloc[-1]['report_date']
        test_start = test_df.iloc[0]['report_date']
        test_end = test_df.iloc[-1]['report_date']
        
        # Optimize on training data based on strategy
        if strategy_name == 'rsi_classic':
            best_params = optimize_rsi_params(train_df)
            test_df = rsi_classic(test_df, **best_params)
        
        elif strategy_name == 'macd_only':
            best_params = optimize_macd_params(train_df)
            # Apply optimized MACD strategy to test data
            test_df['signal'] = 0
            hist_thresh = best_params['histogram_threshold']
            macd_buy = (test_df['macd'] > test_df['macd_signal']) & (test_df['macd_histogram'] > hist_thresh)
            macd_sell = (test_df['macd'] < test_df['macd_signal']) & (test_df['macd_histogram'] < -hist_thresh)
            test_df.loc[macd_buy, 'signal'] = 1
            test_df.loc[macd_sell, 'signal'] = -1
        
        elif strategy_name == 'bollinger_bands':
            best_params = optimize_bb_params(train_df)
            # Apply optimized Bollinger Bands strategy to test data
            test_df['signal'] = 0
            lower_thresh = best_params['lower_threshold']
            upper_thresh = best_params['upper_threshold']
            test_df.loc[test_df['bb_position'] < lower_thresh, 'signal'] = 1
            test_df.loc[test_df['bb_position'] > upper_thresh, 'signal'] = -1
        
        elif strategy_name in ['sma_crossover', 'ema_crossover', 'ma_crossover']:
            best_params = optimize_ma_crossover_params(train_df)
            # Apply optimized MA crossover strategy to test data
            test_df['signal'] = 0
            short_ma = best_params['short_ma']
            long_ma = best_params['long_ma']
            buy = (test_df[short_ma] > test_df[long_ma]) & (test_df[short_ma].shift(1) <= test_df[long_ma].shift(1))
            sell = (test_df[short_ma] < test_df[long_ma]) & (test_df[short_ma].shift(1) >= test_df[long_ma].shift(1))
            test_df.loc[buy, 'signal'] = 1
            test_df.loc[sell, 'signal'] = -1
        
        else:
            # Default: use fixed strategy (no optimization)
            strategy_func = STRATEGIES.get(strategy_name, rsi_classic)
            test_df = strategy_func(test_df)
            best_params = {}
        
        # Backtest on out-of-sample test data
        test_result = backtest_strategy(test_df, initial_capital=total_portfolio_value)
        
        if 'error' not in test_result:
            window_results.append({
                'window': window_num,
                'train_start': train_start,
                'train_end': train_end,
                'test_start': test_start,
                'test_end': test_end,
                'params': str(best_params),
                'return': test_result['total_return'],
                'sharpe': test_result['sharpe_ratio'],
                'trades': test_result['num_trades'],
                'win_rate': test_result['win_rate']
            })
            
            # Update portfolio value for next window
            total_portfolio_value = test_result['final_value']
            
            # Collect trades
            if 'trades' in test_result and not test_result['trades'].empty:
                all_trades.append(test_result['trades'])
        
        # Roll forward
        start_idx += step_days
        window_num += 1
    
    if not window_results:
        return {
            'error': 'No valid walk-forward windows',
            'ticker': df.iloc[0]['ticker'] if 'ticker' in df.columns else 'UNKNOWN'
        }
    
    # Aggregate results
    wf_df = pd.DataFrame(window_results)
    all_trades_df = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    
    # Calculate walk-forward metrics
    total_return = (total_portfolio_value - 10000) / 10000
    avg_window_return = wf_df['return'].mean()
    avg_sharpe = wf_df['sharpe'].mean()
    win_windows = (wf_df['return'] > 0).sum()
    total_windows = len(wf_df)
    consistency = win_windows / total_windows
    
    # Compare to buy & hold
    buy_hold_return = (df.iloc[-1]['close'] - df.iloc[0]['close']) / df.iloc[0]['close']
    
    return {
        'ticker': df.iloc[0]['ticker'] if 'ticker' in df.columns else 'UNKNOWN',
        'strategy': strategy_name,
        'total_return': total_return,
        'buy_hold_return': buy_hold_return,
        'avg_window_return': avg_window_return,
        'avg_sharpe': avg_sharpe,
        'num_windows': total_windows,
        'winning_windows': win_windows,
        'consistency': consistency,
        'final_value': total_portfolio_value,
        'window_details': wf_df,
        'all_trades': all_trades_df
    }

def run_walk_forward_batch(
    tickers: List[str] = None,
    strategy_name: str = 'rsi_classic',
    limit: int = None,
    train_days: int = 252,
    test_days: int = 63,
    step_days: int = 21
) -> pd.DataFrame:
    """
    Run walk-forward analysis on multiple tickers.
    Ranks stocks by consistency and out-of-sample performance.
    
    Args:
        tickers: List of tickers (None = all from database)
        strategy_name: Strategy to test
        limit: Limit number of tickers
        train_days: Training window (252 = 1 year)
        test_days: Testing window (63 = 1 quarter)
        step_days: Roll forward step (21 = 1 month)
    
    Returns:
        DataFrame with ranked results
    """
    conn = duckdb.connect(str(DB_PATH))
    
    # Get tickers
    if tickers is None:
        all_tickers_query = f"SELECT DISTINCT ticker FROM read_parquet('{FEATURES_PATH}') ORDER BY ticker"
        all_tickers = conn.execute(all_tickers_query).df()['ticker'].tolist()
    else:
        all_tickers = tickers
    
    if limit:
        all_tickers = all_tickers[:limit]
    
    log_pipeline_start(
        "Walk-Forward Analysis",
        strategy=strategy_name,
        tickers=len(all_tickers),
        train_days=train_days,
        test_days=test_days,
        step_days=step_days
    )
    
    results = []
    
    for idx, ticker in enumerate(all_tickers, 1):
        log_info(f"[{idx}/{len(all_tickers)}] Analyzing {ticker}...")
        
        # Load ticker data
        query = f"""
            SELECT *
            FROM read_parquet('{FEATURES_PATH}')
            WHERE ticker = '{ticker}'
            ORDER BY report_date
        """
        ticker_df = conn.execute(query).df()
        
        if ticker_df.empty:
            continue
        
        # Rename columns for strategy functions
        if 'report_date' in ticker_df.columns:
            ticker_df = ticker_df.rename(columns={'report_date': 'date'})
        
        # Map feature columns
        if 'lt_rsi_28' in ticker_df.columns and 'rsi_14' not in ticker_df.columns:
            ticker_df['rsi_14'] = ticker_df.get('st_rsi_14', ticker_df['lt_rsi_28'])
        if 'lt_macd' in ticker_df.columns and 'macd' not in ticker_df.columns:
            ticker_df['macd'] = ticker_df['lt_macd']
            ticker_df['macd_signal'] = ticker_df['lt_macd_signal']
            ticker_df['macd_histogram'] = ticker_df['lt_macd_histogram']
        if 'lt_sma_20' in ticker_df.columns and 'sma_10' not in ticker_df.columns:
            ticker_df['sma_10'] = ticker_df.get('st_sma_10', ticker_df['lt_sma_20'])
            ticker_df['sma_20'] = ticker_df['lt_sma_20']
            ticker_df['sma_50'] = ticker_df['lt_sma_50']
        
        # Rename back for walk_forward_analysis
        if 'date' in ticker_df.columns:
            ticker_df = ticker_df.rename(columns={'date': 'report_date'})
        
        # Run walk-forward analysis
        wf_result = walk_forward_analysis(
            ticker_df,
            strategy_name=strategy_name,
            train_days=train_days,
            test_days=test_days,
            step_days=step_days
        )
        
        if 'error' not in wf_result:
            results.append({
                'ticker': ticker,
                'strategy': strategy_name,
                'total_return': wf_result['total_return'],
                'buy_hold_return': wf_result['buy_hold_return'],
                'avg_window_return': wf_result['avg_window_return'],
                'avg_sharpe': wf_result['avg_sharpe'],
                'consistency': wf_result['consistency'],
                'num_windows': wf_result['num_windows'],
                'winning_windows': wf_result['winning_windows'],
                'beats_buy_hold': wf_result['total_return'] > wf_result['buy_hold_return'],
                'final_value': wf_result['final_value']
            })
            
            log_info(f"  ✓ Return: {wf_result['total_return']*100:+6.2f}% | Consistency: {wf_result['consistency']*100:.1f}% | Sharpe: {wf_result['avg_sharpe']:.2f}")
        else:
            log_warning(f"  ✗ {wf_result.get('error', 'Unknown error')}")
    
    conn.close()
    
    if not results:
        log_error("No valid walk-forward results")
        return pd.DataFrame()
    
    # Create summary DataFrame
    results_df = pd.DataFrame(results)
    
    # Calculate composite score
    # Score = (Consistency * 0.4) + (Normalized Return * 0.3) + (Normalized Sharpe * 0.3)
    results_df['return_zscore'] = (results_df['total_return'] - results_df['total_return'].mean()) / results_df['total_return'].std()
    results_df['sharpe_zscore'] = (results_df['avg_sharpe'] - results_df['avg_sharpe'].mean()) / results_df['avg_sharpe'].std()
    results_df['composite_score'] = (
        results_df['consistency'] * 0.4 +
        results_df['return_zscore'] * 0.3 +
        results_df['sharpe_zscore'] * 0.3
    )
    
    # Sort by composite score
    results_df = results_df.sort_values('composite_score', ascending=False)
    
    # Display top recommendations
    log_section("WALK-FORWARD ANALYSIS RESULTS")
    log_info(f"\nTop Stocks to Consider (Ranked by Robustness):\n")
    
    display_cols = ['ticker', 'total_return', 'consistency', 'avg_sharpe', 'beats_buy_hold', 'composite_score']
    top_10 = results_df.head(10)[display_cols].copy()
    top_10['total_return'] = top_10['total_return'].apply(lambda x: f"{x*100:+6.2f}%")
    top_10['consistency'] = top_10['consistency'].apply(lambda x: f"{x*100:.1f}%")
    top_10['avg_sharpe'] = top_10['avg_sharpe'].apply(lambda x: f"{x:.2f}")
    top_10['composite_score'] = top_10['composite_score'].apply(lambda x: f"{x:.3f}")
    
    log_info(f"\n{top_10.to_string(index=False)}")
    
    log_section("BUY RECOMMENDATIONS")
    buy_candidates = results_df[
        (results_df['consistency'] >= 0.5) &  # Win at least 50% of windows
        (results_df['total_return'] > 0) &    # Positive total return
        (results_df['avg_sharpe'] > 0.5)      # Decent risk-adjusted return
    ]
    
    if buy_candidates.empty:
        log_warning("No stocks meet all buy criteria (consistency >= 50%, positive return, Sharpe > 0.5)")
    else:
        log_info(f"\n{len(buy_candidates)} stocks meet buy criteria:\n")
        buy_display = buy_candidates[['ticker', 'total_return', 'consistency', 'avg_sharpe', 'composite_score']].head(20).copy()
        buy_display['total_return'] = buy_display['total_return'].apply(lambda x: f"{x*100:+6.2f}%")
        buy_display['consistency'] = buy_display['consistency'].apply(lambda x: f"{x*100:.1f}%")
        buy_display['avg_sharpe'] = buy_display['avg_sharpe'].apply(lambda x: f"{x:.2f}")
        buy_display['composite_score'] = buy_display['composite_score'].apply(lambda x: f"{x:.3f}")
        log_info(f"\n{buy_display.to_string(index=False)}")
    
    metrics = {
        "Total Analyzed": len(results_df),
        "Buy Candidates": len(buy_candidates),
        "Avg Consistency": f"{results_df['consistency'].mean()*100:.1f}%",
        "Median Return": f"{results_df['total_return'].median()*100:+.2f}%"
    }
    log_pipeline_end("Walk-Forward Analysis", status="SUCCESS", **metrics)
    
    return results_df

# =========================================================
# STANDARD BACKTEST LOGIC
# =========================================================

def backtest_strategy(df: pd.DataFrame, initial_capital: float = 10000) -> Dict:
    """
    Backtest a trading strategy on historical data.
    Assumes we trade at next day's open price after signal.
    
    Args:
        df: DataFrame with signal column (sorted by date)
        initial_capital: Starting portfolio value
    
    Returns:
        Dictionary with performance metrics
    """
    df = df.sort_values('report_date').reset_index(drop=True)
    
    if df.empty or 'signal' not in df.columns:
        return {'error': 'Invalid input data or missing signal column'}
    
    position = 0  # 0 = no position, 1 = long
    entry_price = 0
    trades = []
    portfolio_values = [initial_capital]
    cash = initial_capital
    
    for i in range(len(df) - 1):  # -1 because we execute next day
        current_date = df.loc[i, 'report_date']
        current_close = df.loc[i, 'close']
        signal = df.loc[i, 'signal']
        
        next_close = df.loc[i + 1, 'close']  # Execute at next day's open
        next_date = df.loc[i + 1, 'report_date']
        
        # -------------------------
        # BUY SIGNAL
        # -------------------------
        if signal == 1 and position == 0:
            shares = cash / next_close
            position = 1
            entry_price = next_close
            entry_date = next_date
        
        # -------------------------
        # SELL SIGNAL
        # -------------------------
        elif signal == -1 and position == 1:
            exit_price = next_close
            exit_date = next_date
            
            pnl = (exit_price - entry_price) * shares
            pnl_pct = (exit_price - entry_price) / entry_price
            
            trades.append({
                'entry_date': entry_date,
                'entry_price': entry_price,
                'exit_date': exit_date,
                'exit_price': exit_price,
                'shares': shares,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'holding_days': (exit_date - entry_date).days
            })
            
            cash = cash + pnl
            position = 0
        
        # -------------------------
        # CALCULATE PORTFOLIO VALUE
        # -------------------------
        if position == 1:
            portfolio_value = cash + (shares * next_close)
        else:
            portfolio_value = cash
        
        portfolio_values.append(portfolio_value)
    
    # Close final position if open
    if position == 1:
        final_price = df.iloc[-1]['close']
        pnl = (final_price - entry_price) * shares
        pnl_pct = (final_price - entry_price) / entry_price
        trades.append({
            'entry_date': entry_date,
            'entry_price': entry_price,
            'exit_date': df.iloc[-1]['report_date'],
            'exit_price': final_price,
            'shares': shares,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'holding_days': (df.iloc[-1]['report_date'] - entry_date).days
        })
    
    # -------------------------
    # CALCULATE METRICS
    # -------------------------
    trades_df = pd.DataFrame(trades)
    
    total_return = (portfolio_values[-1] - initial_capital) / initial_capital
    num_trades = len(trades)
    
    if num_trades == 0:
        return {
            'ticker': df.iloc[0]['ticker'] if 'ticker' in df.columns else 'UNKNOWN',
            'start_date': df.iloc[0]['report_date'],
            'end_date': df.iloc[-1]['report_date'],
            'initial_capital': initial_capital,
            'final_value': portfolio_values[-1],
            'total_return': total_return,
            'num_trades': 0,
            'win_rate': 0,
            'avg_pnl': 0,
            'avg_holding_days': 0,
            'max_loss': 0,
            'sharpe_ratio': 0,
            'buy_hold_return': (df.iloc[-1]['close'] - df.iloc[0]['close']) / df.iloc[0]['close'],
        }
    
    winning_trades = trades_df[trades_df['pnl'] > 0]
    losing_trades = trades_df[trades_df['pnl'] <= 0]
    
    win_rate = len(winning_trades) / num_trades if num_trades > 0 else 0
    avg_pnl = trades_df['pnl'].mean()
    avg_holding_days = trades_df['holding_days'].mean()
    max_loss = trades_df['pnl'].min()
    
    # Simple Sharpe ratio (daily returns)
    daily_returns = pd.Series(portfolio_values).pct_change().dropna()
    sharpe = (daily_returns.mean() / daily_returns.std() * np.sqrt(252)) if daily_returns.std() > 0 else 0
    
    # Buy & hold baseline
    buy_hold_return = (df.iloc[-1]['close'] - df.iloc[0]['close']) / df.iloc[0]['close']
    
    return {
        'ticker': df.iloc[0]['ticker'] if 'ticker' in df.columns else 'UNKNOWN',
        'start_date': df.iloc[0]['report_date'],
        'end_date': df.iloc[-1]['report_date'],
        'initial_capital': initial_capital,
        'final_value': portfolio_values[-1],
        'total_return': total_return,
        'num_trades': num_trades,
        'win_rate': win_rate,
        'avg_pnl': avg_pnl,
        'avg_holding_days': avg_holding_days,
        'max_loss': max_loss,
        'sharpe_ratio': sharpe,
        'buy_hold_return': buy_hold_return,
        'trades': trades_df
    }

# =========================================================
# MAIN PIPELINE
# =========================================================

# =========================================================
# MAIN PIPELINE - WITH CACHING
# =========================================================

def init_backtest_db(conn):
    """Initialize backtest results table"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS backtest_results (
            strategy_name VARCHAR,
            ticker VARCHAR,
            start_date DATE,
            end_date DATE,
            total_return DOUBLE,
            buy_hold_return DOUBLE,
            num_trades INTEGER,
            win_rate DOUBLE,
            sharpe_ratio DOUBLE,
            avg_pnl DOUBLE,
            max_loss DOUBLE,
            run_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(strategy_name, ticker)
        )
    """)

def get_cached_result(conn, strategy_name: str, ticker: str) -> Dict:
    """Load cached backtest result from database"""
    result = conn.execute("""
        SELECT total_return, buy_hold_return, num_trades, win_rate, sharpe_ratio, avg_pnl, max_loss, run_date
        FROM backtest_results
        WHERE strategy_name = ? AND ticker = ?
    """, [strategy_name, ticker]).fetchone()
    
    if result:
        return {
            'total_return': result[0],
            'buy_hold_return': result[1],
            'num_trades': result[2],
            'win_rate': result[3],
            'sharpe_ratio': result[4],
            'avg_pnl': result[5],
            'max_loss': result[6],
            'run_date': result[7],
            'cached': True
        }
    return None

def save_result(conn, strategy_name: str, ticker: str, result: Dict):
    """Save backtest result to database"""
    conn.execute("""
        INSERT OR REPLACE INTO backtest_results 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, [
        strategy_name,
        ticker,
        result['start_date'],
        result['end_date'],
        result['total_return'],
        result['buy_hold_return'],
        result['num_trades'],
        result['win_rate'],
        result['sharpe_ratio'],
        result['avg_pnl'],
        result['max_loss']
    ])

# =========================================================
# MULTIPROCESSING WORKER
# =========================================================

def backtest_worker(args: Tuple) -> Dict:
    """
    Worker function for multiprocessing.
    Tests a single strategy on a single ticker.
    Queries parquet directly (no DB joins, avoids memory issues).
    """
    strategy_name, strategy_func, ticker, features_path = args
    
    # Open local connection in worker (avoid multiprocessing issues)
    conn_local = duckdb.connect(':memory:')
    
    # Query ONLY this ticker's data from parquet
    query = f"""
        SELECT *
        FROM read_parquet('{features_path}')
        WHERE ticker = '{ticker}'
        ORDER BY report_date
    """
    
    try:
        ticker_df = conn_local.execute(query).df()
        conn_local.close()
        
        if ticker_df.empty:
            return {
                'strategy': strategy_name,
                'ticker': ticker,
                'return': 0,
                'buy_hold': 0,
                'trades': 0,
                'win_rate': 0,
                'sharpe': 0,
                'avg_pnl': 0,
                'max_loss': 0,
                'start_date': None,
                'end_date': None,
                'error': 'No data'
            }
        
        # Rename report_date to date for strategy functions
        if 'report_date' in ticker_df.columns:
            ticker_df = ticker_df.rename(columns={'report_date': 'date'})
        
        # Add standard aliases for strategy functions (map long-term to default names)
        # Strategies expect columns like rsi_14, macd, sma_20, etc.
        if 'lt_rsi_28' in ticker_df.columns and 'rsi_14' not in ticker_df.columns:
            ticker_df['rsi_14'] = ticker_df.get('st_rsi_14', ticker_df['lt_rsi_28'])
        if 'lt_macd' in ticker_df.columns and 'macd' not in ticker_df.columns:
            ticker_df['macd'] = ticker_df['lt_macd']
            ticker_df['macd_signal'] = ticker_df['lt_macd_signal']
            ticker_df['macd_histogram'] = ticker_df['lt_macd_histogram']
        if 'lt_sma_20' in ticker_df.columns and 'sma_10' not in ticker_df.columns:
            ticker_df['sma_10'] = ticker_df.get('st_sma_10', ticker_df['lt_sma_20'])
            ticker_df['sma_20'] = ticker_df['lt_sma_20']
            ticker_df['sma_50'] = ticker_df['lt_sma_50']
        if 'lt_ema_20' in ticker_df.columns and 'ema_10' not in ticker_df.columns:
            ticker_df['ema_10'] = ticker_df.get('st_ema_10', ticker_df['lt_ema_20'])
            ticker_df['ema_20'] = ticker_df['lt_ema_20']
        if 'st_stoch_k_14' in ticker_df.columns and 'stoch_k' not in ticker_df.columns:
            ticker_df['stoch_k'] = ticker_df['st_stoch_k_14']
            ticker_df['stoch_d'] = ticker_df['st_stoch_d_14']
        if 'lt_bb_upper' in ticker_df.columns and 'bb_position' not in ticker_df.columns:
            ticker_df['bb_position'] = ticker_df.get('lt_bb_position', 0.5)
            ticker_df['bb_upper'] = ticker_df['lt_bb_upper']
            ticker_df['bb_lower'] = ticker_df['lt_bb_lower']
            ticker_df['bb_width'] = ticker_df['lt_bb_width']
        if 'st_atr_ratio' in ticker_df.columns and 'atr_ratio' not in ticker_df.columns:
            ticker_df['atr_ratio'] = ticker_df['st_atr_ratio']
        if 'lt_volume_zscore_20d' in ticker_df.columns and 'volume_zscore_20d' not in ticker_df.columns:
            ticker_df['volume_zscore_20d'] = ticker_df['lt_volume_zscore_20d']
        if 'st_return_5d' in ticker_df.columns and 'return_5d' not in ticker_df.columns:
            ticker_df['return_5d'] = ticker_df['st_return_5d']
        if 'lt_momentum_20' in ticker_df.columns and 'momentum_20' not in ticker_df.columns:
            ticker_df['momentum_20'] = ticker_df['lt_momentum_20']
            ticker_df['momentum_10'] = ticker_df.get('st_momentum_10', ticker_df['lt_momentum_20'])
        if 'lt_roc_20' in ticker_df.columns and 'roc_10' not in ticker_df.columns:
            ticker_df['roc_10'] = ticker_df.get('st_roc_7', ticker_df['lt_roc_20'])
        if 'lt_vol_20d' in ticker_df.columns and 'rolling_vol_20d' not in ticker_df.columns:
            ticker_df['rolling_vol_20d'] = ticker_df['lt_vol_20d']
            ticker_df['rolling_vol_50d'] = ticker_df['lt_vol_50d']
        if 'lt_adx_14' in ticker_df.columns and 'adx' not in ticker_df.columns:
            ticker_df['adx'] = ticker_df['lt_adx_14']
        if 'lt_sma_50' in ticker_df.columns and 'vwap_20' not in ticker_df.columns:
            ticker_df['vwap_20'] = ticker_df['lt_sma_50']  # Use SMA50 as proxy for VWAP
        
        # Generate signals
        ticker_df = strategy_func(ticker_df)
        
        # Rename back to report_date for backtest_strategy
        if 'date' in ticker_df.columns and 'report_date' not in ticker_df.columns:
            ticker_df = ticker_df.rename(columns={'date': 'report_date'})
        
        result = backtest_strategy(ticker_df)
        
        return {
            'strategy': strategy_name,
            'ticker': ticker,
            'return': result['total_return'],
            'buy_hold': result['buy_hold_return'],
            'trades': result['num_trades'],
            'win_rate': result['win_rate'],
            'sharpe': result['sharpe_ratio'],
            'avg_pnl': result['avg_pnl'],
            'max_loss': result['max_loss'],
            'start_date': result['start_date'],
            'end_date': result['end_date']
        }
    except Exception as e:
        conn_local.close()
        return {
            'strategy': strategy_name,
            'ticker': ticker,
            'return': 0,
            'buy_hold': 0,
            'trades': 0,
            'win_rate': 0,
            'sharpe': 0,
            'avg_pnl': 0,
            'max_loss': 0,
            'start_date': None,
            'end_date': None,
            'error': f"{type(e).__name__}: {str(e)[:50]}"
        }

def run_backtest(strategies: List[str] = None, tickers: List[str] = None, limit: int = None, force_rerun: bool = False, num_workers: int = 8):
    """
    Run backtest for specified strategies and tickers.
    Caches results to avoid re-running.
    Uses multiprocessing for parallel execution.
    Queries parquet per-ticker to avoid memory exhaustion.
    
    Args:
        strategies: List of strategy names (None = all)
        tickers: List of tickers to backtest (None = all)
        limit: Limit number of tickers (None = all)
        force_rerun: Force recompute even if cached (default: False)
        num_workers: Number of worker processes (default: 8)
    """
    conn = duckdb.connect(str(DB_PATH))
    init_backtest_db(conn)
    
    # -------------------------
    # GET LIST OF TICKERS FROM PARQUET (without loading full data)
    # -------------------------
    all_tickers_query = f"SELECT DISTINCT ticker FROM read_parquet('{FEATURES_PATH}') ORDER BY ticker"
    all_tickers = conn.execute(all_tickers_query).df()['ticker'].tolist()
    
    if not all_tickers:
        log_error("No tickers found in features. Run feature_engine.py first.")
        conn.close()
        return
    
    # Filter if specified
    if tickers:
        all_tickers = [t for t in all_tickers if t in tickers]
    
    if limit:
        all_tickers = all_tickers[:limit]
    
    # Determine which strategies to run
    if strategies is None:
        strategies = list(STRATEGIES.keys())
    else:
        strategies = [s for s in strategies if s in STRATEGIES]
    
    log_pipeline_start(
        "Backtester",
        strategies=len(strategies),
        tickers=len(all_tickers),
        workers=num_workers
    )
    
    log_info(f"Available strategies ({len(STRATEGIES)}): {', '.join(list(STRATEGIES.keys())[:5])}... + {len(STRATEGIES)-5} more")
    
    # -------------------------
    # CHECK CACHE & PREPARE WORK ITEMS
    # -------------------------
    work_items = []
    cached_results = []
    total_possible = len(strategies) * len(all_tickers)
    
    for strategy_name in strategies:
        strategy_func = STRATEGIES[strategy_name]
        for ticker in all_tickers:
            if not force_rerun:
                # Check if cached
                cached = get_cached_result(conn, strategy_name, ticker)
                if cached:
                    cached_results.append({
                        'strategy': strategy_name,
                        'ticker': ticker,
                        'return': cached['total_return'],
                        'buy_hold': cached['buy_hold_return'],
                        'trades': cached['num_trades'],
                        'win_rate': cached['win_rate'],
                        'sharpe': cached['sharpe_ratio'],
                        'avg_pnl': cached['avg_pnl'],
                        'max_loss': cached['max_loss']
                    })
                    continue
            
            # Add to work queue (pass paths and ticker, not data)
            work_items.append((strategy_name, strategy_func, ticker, FEATURES_PATH))
    
    total_cached = len(cached_results)
    total_new = len(work_items)
    total_items = total_cached + total_new
    
    log_info(f"Total tests: {total_items} | Cached: {total_cached} | To run: {total_new}")
    
    # -------------------------
    # PARALLEL EXECUTION (only non-cached items)
    # -------------------------
    new_results = []
    
    if total_new > 0:
        with Pool(num_workers) as pool:
            for idx, result in enumerate(pool.imap_unordered(backtest_worker, work_items), 1):
                new_results.append(result)
                
                # Print progress every 10 items
                if idx % 10 == 0 or idx == total_new:
                    pct = (idx / total_new) * 100
                    error_msg = f" ERROR: {result.get('error', '')}" if result.get('error') else ""
                    print(f"[{idx:3d}/{total_new}] {pct:5.1f}% | {result['strategy']:25} {result['ticker']:6} | Return: {result['return']*100:+7.2f}% | Sharpe: {result['sharpe']:.2f}{error_msg}")
    
    # -------------------------
    # SAVE NEW RESULTS TO DB
    # -------------------------
    for result in new_results:
        if result.get('error'):
            continue  # Skip errored results
        
        # Reconstruct full result dict for save_result
        full_result = {
            'start_date': result['start_date'],
            'end_date': result['end_date'],
            'total_return': result['return'],
            'buy_hold_return': result['buy_hold'],
            'num_trades': result['trades'],
            'win_rate': result['win_rate'],
            'sharpe_ratio': result['sharpe'],
            'avg_pnl': result['avg_pnl'],
            'max_loss': result['max_loss']
        }
        save_result(conn, result['strategy'], result['ticker'], full_result)
    
    conn.close()
    
    # -------------------------
    # MERGE ALL RESULTS
    # -------------------------
    all_results = cached_results + [r for r in new_results if not r.get('error')]
    all_df = pd.DataFrame(all_results)
    
    if all_df.empty:
        log_error("No valid backtest results")
        return
    
    # -------------------------
    # SUMMARY STATISTICS
    # -------------------------
    log_section("STRATEGY RANKINGS (by Avg Sharpe Ratio)")
    
    strategy_stats = []
    for strat in sorted(all_df['strategy'].unique()):
        strat_df = all_df[all_df['strategy'] == strat]
        wins = (strat_df['return'] > 0).sum()
        beats_bh = (strat_df['return'] > strat_df['buy_hold']).sum()
        
        strategy_stats.append({
            'strategy': strat,
            'avg_return': strat_df['return'].mean(),
            'avg_sharpe': strat_df['sharpe'].mean(),
            'avg_win_rate': strat_df['win_rate'].mean(),
            'winning_tickers': f"{wins}/{len(strat_df)}",
            'beats_buy_hold': f"{beats_bh}/{len(strat_df)}"
        })
    
    strategy_summary = pd.DataFrame(strategy_stats).sort_values('avg_sharpe', ascending=False)
    log_info(f"\n{strategy_summary[['strategy', 'avg_return', 'avg_sharpe', 'avg_win_rate', 'winning_tickers', 'beats_buy_hold']].to_string(index=False)}")
    
    metrics_final = {
        "Total Tests": total_items,
        "Cached": total_cached,
        "New": total_new,
        "Results Table": "backtest_results (in database)"
    }
    log_pipeline_end("Backtester", status="SUCCESS", **metrics_final)
    
    return all_df

# =========================================================
# EXAMPLE USAGE
# =========================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backtest trading strategies on historical stock data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # STANDARD BACKTEST (all strategies)
  # Test all 28 strategies on 10 tickers (8 workers)
  python backtester.py --limit 10
  
  # Test specific strategies
  python backtester.py --strategies rsi_classic macd_only all_oscillators --limit 5
  
  # Test all strategies on all available tickers
  python backtester.py
  
  # Force re-run without using cache
  python backtester.py --limit 20 --force-rerun
  
  # Use more workers for faster execution
  python backtester.py --limit 50 --workers 16
  
  # Test on specific tickers
  python backtester.py --tickers AAPL MSFT GOOGL NVDA
  
  # WALK-FORWARD ANALYSIS (find stocks to buy)
  # Analyze 20 stocks with walk-forward (prevents overfitting)
  python backtester.py --walk-forward --limit 20
  
  # Walk-forward on specific tickers
  python backtester.py --walk-forward --tickers AAPL MSFT GOOGL NVDA TSLA
  
  # Custom walk-forward windows (6 months train, 1 month test)
  python backtester.py --walk-forward --limit 10 --train-days 126 --test-days 21
        """
    )
    
    parser.add_argument(
        '--walk-forward',
        action='store_true',
        help='Run walk-forward analysis (anti-overfitting) instead of standard backtest'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit number of tickers to backtest (default: all)'
    )
    
    parser.add_argument(
        '--strategies',
        nargs='+',
        default=None,
        help=f'Specific strategies to test. Available: {", ".join(list(STRATEGIES.keys())[:10])}... (default: all 28)'
    )
    
    parser.add_argument(
        '--tickers',
        nargs='+',
        default=None,
        help='Specific tickers to backtest (default: all from database)'
    )
    
    parser.add_argument(
        '--workers',
        type=int,
        default=8,
        help='Number of worker processes (default: 8, only for standard backtest)'
    )
    
    parser.add_argument(
        '--force-rerun',
        action='store_true',
        help='Force re-run without using cached results (standard backtest only)'
    )
    
    parser.add_argument(
        '--train-days',
        type=int,
        default=252,
        help='Walk-forward training window in days (default: 252 = 1 year)'
    )
    
    parser.add_argument(
        '--test-days',
        type=int,
        default=63,
        help='Walk-forward testing window in days (default: 63 = 1 quarter)'
    )
    
    parser.add_argument(
        '--step-days',
        type=int,
        default=21,
        help='Walk-forward step size in days (default: 21 = 1 month)'
    )
    
    parser.add_argument(
        '--wf-strategy',
        type=str,
        default='rsi_classic',
        choices=['rsi_classic', 'macd_only', 'bollinger_bands', 'sma_crossover', 'ema_crossover', 'ma_crossover'],
        help='Walk-forward strategy (default: rsi_classic). Supported: rsi_classic, macd_only, bollinger_bands, sma_crossover, ema_crossover, ma_crossover'
    )
    
    args = parser.parse_args()
    
    # =========================================================
    # WALK-FORWARD ANALYSIS MODE
    # =========================================================
    if args.walk_forward:
        log_info(f"Running WALK-FORWARD ANALYSIS mode (anti-overfitting) with {args.wf_strategy}")
        
        results = run_walk_forward_batch(
            tickers=args.tickers,
            strategy_name=args.wf_strategy,
            limit=args.limit,
            train_days=args.train_days,
            test_days=args.test_days,
            step_days=args.step_days
        )
        
        if not results.empty:
            # Save results
            output_path = Path(__file__).parent / "walk_forward_results.csv"
            results.to_csv(output_path, index=False)
            log_info(f"\nResults saved to: {output_path}")
    
    # =========================================================
    # STANDARD BACKTEST MODE
    # =========================================================
    else:
        log_info("Running STANDARD BACKTEST mode")
        
        # Validate strategy names
        if args.strategies:
            invalid = [s for s in args.strategies if s not in STRATEGIES]
            if invalid:
                print(f"Error: Invalid strategies: {', '.join(invalid)}")
                print(f"Available strategies: {', '.join(sorted(STRATEGIES.keys()))}")
                sys.exit(1)
        
        # Run backtest with provided arguments
        results = run_backtest(
            strategies=args.strategies,
            tickers=args.tickers,
            limit=args.limit,
            force_rerun=args.force_rerun,
            num_workers=args.workers
        )
