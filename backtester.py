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
        """
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
        help='Number of worker processes (default: 8)'
    )
    
    parser.add_argument(
        '--force-rerun',
        action='store_true',
        help='Force re-run without using cached results'
    )
    
    args = parser.parse_args()
    
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
