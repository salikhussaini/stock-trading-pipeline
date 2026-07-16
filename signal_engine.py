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


def trend_following(df):
    signal = np.zeros(len(df))
    
    # Bullish: strong uptrend
    bullish = (df["lt_sma_alignment"] == 1) & (df["lt_macd_histogram"] > 0) & (df["lt_adx_14"] > 20)
    signal[bullish] = 1
    
    # Bearish: strong downtrend
    bearish = (df["lt_sma_alignment"] == 0) & (df["lt_macd_histogram"] < 0) & (df["lt_adx_14"] > 20)
    signal[bearish] = -1
    
    return signal



def momentum_strategy(df):
    signal = np.zeros(len(df))
    
    # Bullish: oversold with positive momentum
    bullish = (df["st_rsi_14"] < 30) & (df["st_return_5d"] > 0) & (df["st_volume_ratio_5d"] > 1)
    signal[bullish] = 1
    
    # Bearish: overbought with negative momentum
    bearish = (df["st_rsi_14"] > 70) & (df["st_return_5d"] < 0) & (df["st_volume_ratio_5d"] > 1)
    signal[bearish] = -1
    
    return signal



def mean_reversion(df):
    signal = np.zeros(len(df))
    
    # Bullish: oversold at lower Bollinger Band
    bullish = (df["lt_bb_position"] < 0.2) & (df["lt_rsi_28"] < 35)
    signal[bullish] = 1
    
    # Bearish: overbought at upper Bollinger Band
    bearish = (df["lt_bb_position"] > 0.8) & (df["lt_rsi_28"] > 65)
    signal[bearish] = -1
    
    return signal



def breakout_strategy(df):
    signal = np.zeros(len(df))
    
    # Bullish: upside breakout with volume and strong trend
    bullish = (df["lt_bb_position"] > 0.9) & (df["lt_volume_ratio_20d"] > 1.5) & (df["lt_adx_14"] > 25)
    signal[bullish] = 1
    
    # Bearish: downside breakout with volume and strong trend
    bearish = (df["lt_bb_position"] < 0.1) & (df["lt_volume_ratio_20d"] > 1.5) & (df["lt_adx_14"] > 25)
    signal[bearish] = -1
    
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
        "breakout": breakout_strategy
    }
    
    # Apply each strategy
    for name, strategy in strategies.items():
        print(f"Running {name}...")
        signals = []
        for ticker, group in df.groupby("ticker"):
            signals.append(strategy(group.reset_index(drop=True)))
        df[name] = np.concatenate(signals)
    
    # Ensemble voting
    strategy_cols = list(strategies.keys())
    df["signal_score"] = df[strategy_cols].sum(axis=1)
    
    # Final signal: requires consensus (2+ votes)
    df["final_signal"] = 0
    df.loc[df["signal_score"] >= 2, "final_signal"] = 1
    df.loc[df["signal_score"] <= -2, "final_signal"] = -1
    
    df["signal_date"] = datetime.today().date()
    
    print("Saving signals...")
    duckdb.from_df(df).write_parquet(str(SIGNAL_PATH))
    print(f"Saved {len(df):,} signals to {SIGNAL_PATH}")


if __name__ == "__main__":
    generate_signals()