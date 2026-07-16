#!/usr/bin/env python3
"""
Send stock trading alerts to Telegram.
Analyzes backtest results and sends sell/buy recommendations.
"""

import duckdb
import pandas as pd
from pathlib import Path
import requests
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# =========================================================
# CONFIGURATION
# =========================================================

DB_PATH = Path(__file__).parent / "database" / "stock_data.duckdb"
WALK_FORWARD_CSV = Path(__file__).parent / "walk_forward_results.csv"
SIGNALS_PATH = Path(__file__).parent / "database" / "trading_signals.parquet"

# Load from .env file
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# =========================================================
# DEBUG FUNCTIONS
# =========================================================

def debug_signals_data():
    """
    Debug function to inspect the raw signal data and merged result.
    Shows column names and first few rows to identify data issues.
    """
    print("=" * 80)
    print("DEBUG: Inspecting raw signal data...")
    print("=" * 80)
    
    signals_df = get_daily_signals(signal_type="buy", limit=10)
    print(f"\n📊 Raw signals DataFrame (first stage):")
    print(f"   Columns: {signals_df.columns.tolist()}")
    print(f"   Shape: {signals_df.shape}")
    if not signals_df.empty:
        print(f"\n   First row:")
        for col in signals_df.columns:
            print(f"     {col}: {signals_df.iloc[0][col]}")
    
    print("\n" + "=" * 80)
    print("DEBUG: Inspecting merged data with backtest validation...")
    print("=" * 80)
    
    merged_df = get_signals_with_backtest_validation(signal_type="buy", limit=10)
    print(f"\n📊 Merged DataFrame (after backtest join):")
    print(f"   Columns: {merged_df.columns.tolist()}")
    print(f"   Shape: {merged_df.shape}")
    if not merged_df.empty:
        print(f"\n   First row:")
        for col in merged_df.columns:
            print(f"     {col}: {merged_df.iloc[0][col]}")
        
        print(f"\n   Ticker values in merged data:")
        print(f"     {merged_df['ticker'].tolist()}")
    
    print("\n" + "=" * 80)

def debug_backtest_data():
    """
    Debug function to inspect backtest database data.
    Shows what's available in the backtest_results table.
    """
    print("=" * 80)
    print("DEBUG: Inspecting backtest database...")
    print("=" * 80)
    
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    
    try:
        # Check if table exists
        tables_query = "SELECT table_name FROM information_schema.tables WHERE table_schema='memory'"
        tables_result = conn.execute(tables_query).fetchall()
        print(f"\nAvailable tables: {tables_result}")
        
        # Sample backtest data
        sample_query = """
        SELECT 
            ticker,
            strategy_name,
            total_return,
            sharpe_ratio
        FROM backtest_results
        LIMIT 5
        """
        sample_df = conn.execute(sample_query).df()
        print(f"\n📊 Sample backtest_results:")
        print(sample_df)
        
        print(f"\nUnique tickers in backtest: {sample_df['ticker'].unique()}")
        
    except Exception as e:
        print(f"❌ Error querying backtest database: {e}")
    finally:
        conn.close()
    
    print("\n" + "=" * 80)

def debug_signals_file():
    """
    Debug function to inspect the raw signals parquet file.
    Shows unique tickers and summary statistics.
    """
    print("=" * 80)
    print("DEBUG: Inspecting signals parquet file...")
    print("=" * 80)
    
    if not SIGNALS_PATH.exists():
        print(f"⚠️  Signals file not found at: {SIGNALS_PATH}")
        print("Run: python signal_engine.py")
        return
    
    try:
        df = pd.read_parquet(SIGNALS_PATH)
        print(f"\n📊 Signals file info:")
        print(f"   File path: {SIGNALS_PATH}")
        print(f"   Total rows: {len(df)}")
        print(f"   Date range: {df['signal_date'].min()} to {df['signal_date'].max()}")
        
        print(f"\n📊 Unique tickers in signals:")
        unique_tickers = df['ticker'].unique()
        print(f"   Count: {len(unique_tickers)}")
        print(f"   Tickers: {sorted(unique_tickers)}")
        
        print(f"\n📊 Latest signal date: {df['signal_date'].max()}")
        latest_df = df[df['signal_date'] == df['signal_date'].max()]
        print(f"   Signals on this date: {len(latest_df)}")
        print(f"   Tickers with signals: {sorted(latest_df['ticker'].unique())}")
        
        print(f"\n📊 Signal distribution:")
        print(f"   Buy signals (final_signal=1): {len(df[df['final_signal'] == 1])}")
        print(f"   Sell signals (final_signal=-1): {len(df[df['final_signal'] == -1])}")
        print(f"   Neutral (final_signal=0): {len(df[df['final_signal'] == 0])}")
        
    except Exception as e:
        print(f"❌ Error reading signals file: {e}")
    
    print("\n" + "=" * 80)

def debug_features_file():
    """
    Debug function to inspect the features parquet file.
    This is what signal_engine reads as input.
    """
    print("=" * 80)
    print("DEBUG: Inspecting features parquet file (signal_engine input)...")
    print("=" * 80)
    
    features_path = Path(__file__).parent / "database" / "stock_features.parquet"
    
    if not features_path.exists():
        print(f"⚠️  Features file not found at: {features_path}")
        print("Run: python feature_engine.py")
        return
    
    try:
        df = pd.read_parquet(str(features_path))
        print(f"\n📊 Features file info:")
        print(f"   File path: {features_path}")
        print(f"   Total rows: {len(df)}")
        print(f"   Date range: {df['report_date'].min()} to {df['report_date'].max()}")
        
        print(f"\n📊 Unique tickers in features:")
        unique_tickers = df['ticker'].unique()
        print(f"   Count: {len(unique_tickers)}")
        print(f"   Tickers: {sorted(unique_tickers)}")
        
        print(f"\n📊 Ticker value counts:")
        ticker_counts = df['ticker'].value_counts()
        for ticker, count in ticker_counts.items():
            print(f"   {ticker}: {count} rows")
        
    except Exception as e:
        print(f"❌ Error reading features file: {e}")
    
    print("\n" + "=" * 80)

# =========================================================
# QUERY FUNCTIONS
# =========================================================

def get_buy_opportunities(limit=5):
    """
    Find stocks with strong BUY signals based on backtest results.
    Looks for strategies with positive returns and good risk metrics.
    """
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    
    query = """
    WITH latest_signals AS (
        SELECT 
            ticker,
            strategy_name,
            total_return,
            sharpe_ratio,
            win_rate,
            num_trades,
            avg_pnl,
            max_loss,
            ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY sharpe_ratio DESC) as rn
        FROM backtest_results
        WHERE sharpe_ratio > 1.0
        AND num_trades >= 5
        AND win_rate > 0.6
        AND total_return > 0
    )
    SELECT 
        ticker,
        strategy_name,
        ROUND(total_return, 2) as return_pct,
        ROUND(sharpe_ratio, 2) as sharpe,
        ROUND(win_rate * 100, 1) as win_rate_pct,
        num_trades,
        ROUND(avg_pnl, 2) as avg_pnl,
        ROUND(max_loss, 2) as max_loss
    FROM latest_signals
    WHERE rn = 1
    ORDER BY sharpe_ratio DESC
    LIMIT ?
    """
    
    df = conn.execute(query, [limit]).df()
    conn.close()
    return df

def get_sell_opportunities(limit=5):
    """
    Find stocks with strong SELL signals based on backtest results.
    Looks for stocks with negative momentum or poor performance.
    """
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    
    query = """
    WITH latest_signals AS (
        SELECT 
            ticker,
            strategy_name,
            total_return,
            sharpe_ratio,
            win_rate,
            num_trades,
            avg_pnl,
            max_loss,
            ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY total_return ASC) as rn
        FROM backtest_results
        WHERE num_trades >= 5
        AND total_return < 0
    )
    SELECT 
        ticker,
        strategy_name,
        ROUND(total_return, 2) as return_pct,
        ROUND(sharpe_ratio, 2) as sharpe,
        ROUND(win_rate * 100, 1) as win_rate_pct,
        num_trades,
        ROUND(avg_pnl, 2) as avg_pnl,
        ROUND(max_loss, 2) as max_loss
    FROM latest_signals
    WHERE rn = 1
    ORDER BY total_return ASC
    LIMIT ?
    """
    
    df = conn.execute(query, [limit]).df()
    conn.close()
    return df

def get_strategy_summary():
    """Get summary of top performing strategies."""
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    
    query = """
    SELECT 
        strategy_name,
        ROUND(AVG(sharpe_ratio), 2) as avg_sharpe,
        ROUND(AVG(total_return), 2) as avg_return,
        COUNT(*) as ticker_count
    FROM backtest_results
    WHERE sharpe_ratio > 0.5
    GROUP BY strategy_name
    ORDER BY avg_sharpe DESC
    LIMIT 5
    """
    
    df = conn.execute(query).df()
    conn.close()
    return df

# =========================================================
# DAILY SIGNAL QUERY FUNCTIONS
# =========================================================

def get_daily_signals(signal_type="buy", limit=10):
    """
    Get today's trading signals from signal_engine.
    
    Args:
        signal_type: "buy" (final_signal==1), "sell" (final_signal==-1), or "all"
        limit: Number of signals to return
    """
    if not SIGNALS_PATH.exists():
        print(f"⚠️  Trading signals not found. Run: python signal_engine.py")
        return pd.DataFrame()
    
    df = pd.read_parquet(SIGNALS_PATH)
    
    if df.empty:
        return df
    
    # Get latest date
    latest_date = df['signal_date'].max()
    df = df[df['signal_date'] == latest_date].copy()
    
    # Filter by signal type
    if signal_type == "buy":
        df = df[df['final_signal'] == 1]
    elif signal_type == "sell":
        df = df[df['final_signal'] == -1]
    
    # Sort by signal consensus (higher = stronger)
    df = df.sort_values('signal_score', ascending=False)
    
    return df.head(limit)

def get_signals_with_backtest_validation(signal_type="buy", limit=10):
    """
    Get today's signals combined with backtest validation.
    Only returns signals for stocks with positive backtest performance.
    
    Args:
        signal_type: "buy" or "sell"
        limit: Number of results to return
    """
    signals_df = get_daily_signals(signal_type=signal_type, limit=50)
    
    if signals_df.empty:
        return pd.DataFrame()
    
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    
    # Get best strategy for each ticker from backtest
    backtest_query = """
    WITH best_strategy AS (
        SELECT 
            ticker,
            strategy_name,
            total_return,
            sharpe_ratio,
            win_rate,
            num_trades,
            ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY sharpe_ratio DESC) as rn
        FROM backtest_results
        WHERE total_return > 0
        AND sharpe_ratio > 0.5
    )
    SELECT 
        ticker,
        strategy_name as best_strategy,
        ROUND(total_return, 2) as backtest_return,
        ROUND(sharpe_ratio, 2) as backtest_sharpe
    FROM best_strategy
    WHERE rn = 1
    """
    
    backtest_df = conn.execute(backtest_query).df()
    conn.close()
    
    # Merge signals with backtest validation
    result = signals_df.merge(
        backtest_df,
        on='ticker',
        how='inner'  # Only keep signals with positive backtest
    )
    
    return result.head(limit)

def get_signal_summary():
    """
    Get today's signal summary (counts and distribution).
    """
    signals_df = get_daily_signals(limit=500)
    
    if signals_df.empty:
        return {}
    
    buy_count = len(signals_df[signals_df['final_signal'] == 1])
    sell_count = len(signals_df[signals_df['final_signal'] == -1])
    neutral_count = len(signals_df[signals_df['final_signal'] == 0])
    
    # Strategy breakdown
    strategy_signals = signals_df[['trend_following', 'momentum', 'mean_reversion', 'breakout']].sum()
    
    return {
        'buy': buy_count,
        'sell': sell_count,
        'neutral': neutral_count,
        'total': len(signals_df),
        'strategies': strategy_signals.to_dict()
    }

# =========================================================
# WALK-FORWARD QUERY FUNCTIONS (Anti-Overfitting)
# =========================================================

def get_walk_forward_buy_opportunities(limit=10, strategy=None):
    """
    Get buy recommendations from walk-forward analysis.
    These are more reliable than standard backtests (out-of-sample tested).
    
    Filters for:
    - Consistency >= 50% (profitable in ≥50% of test windows)
    - Total Return > 0%
    - Sharpe Ratio > 0.5
    
    Args:
        limit: Number of recommendations to return
        strategy: Filter by strategy name (None = all strategies)
    """
    if not WALK_FORWARD_CSV.exists():
        print(f"⚠️  Walk-forward results not found. Run: python backtester.py --walk-forward --limit 50")
        return pd.DataFrame()
    
    df = pd.read_csv(WALK_FORWARD_CSV)
    
    # Filter by strategy if specified
    if strategy and 'strategy' in df.columns:
        df = df[df['strategy'] == strategy]
    
    # Apply buy criteria
    buy_candidates = df[
        (df['consistency'] >= 0.5) &
        (df['total_return'] > 0) &
        (df['avg_sharpe'] > 0.5)
    ].copy()
    
    # Sort by composite score (best overall)
    buy_candidates = buy_candidates.sort_values('composite_score', ascending=False)
    
    return buy_candidates.head(limit)

def get_walk_forward_conservative(limit=5, strategy=None):
    """
    Get highly conservative buy recommendations.
    
    Filters for:
    - Consistency >= 60% (very consistent)
    - Total Return > 5%
    - Sharpe Ratio > 0.7
    
    Args:
        limit: Number of recommendations to return
        strategy: Filter by strategy name (None = all strategies)
    """
    if not WALK_FORWARD_CSV.exists():
        return pd.DataFrame()
    
    df = pd.read_csv(WALK_FORWARD_CSV)
    
    # Filter by strategy if specified
    if strategy and 'strategy' in df.columns:
        df = df[df['strategy'] == strategy]
    
    conservative = df[
        (df['consistency'] >= 0.6) &
        (df['total_return'] > 0.05) &
        (df['avg_sharpe'] > 0.7)
    ].copy()
    
    return conservative.nlargest(limit, 'composite_score')

def get_walk_forward_aggressive(limit=5, strategy=None):
    """
    Get aggressive high-return candidates.
    `
    Filters for:
    - Total Return > 15%
    - Sharpe Ratio > 0.8
    - Consistency >= 45% (slightly lower, accepting more volatility)
    
    Args:
        limit: Number of recommendations to return
        strategy: Filter by strategy name (None = all strategies)
    """
    if not WALK_FORWARD_CSV.exists():
        return pd.DataFrame()
    
    df = pd.read_csv(WALK_FORWARD_CSV)
    
    # Filter by strategy if specified
    if strategy and 'strategy' in df.columns:
        df = df[df['strategy'] == strategy]
    
    aggressive = df[
        (df['total_return'] > 0.15) &
        (df['avg_sharpe'] > 0.8) &
        (df['consistency'] >= 0.45)
    ].copy()
    
    return aggressive.nlargest(limit, 'total_return')

def get_walk_forward_portfolio(num_stocks=10, strategy=None):
    """
    Get portfolio allocation based on walk-forward results.
    Score-weighted allocation for better risk-adjusted returns.
    
    Args:
        num_stocks: Number of stocks in portfolio
        strategy: Filter by strategy name (None = all strategies)
    """
    buy_candidates = get_walk_forward_buy_opportunities(limit=50, strategy=strategy)
    
    if buy_candidates.empty:
        return pd.DataFrame()
    
    # Top N by composite score
    portfolio = buy_candidates.head(num_stocks).copy()
    
    # Score-weighted allocation
    total_score = portfolio['composite_score'].sum()
    portfolio['allocation_pct'] = (portfolio['composite_score'] / total_score) * 100
    
    return portfolio

# =========================================================
# TELEGRAM FUNCTIONS
# =========================================================

def escape_markdown(text: str) -> str:
    """Escape special characters for Telegram Markdown."""
    # Characters that need escaping in Telegram Markdown
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

def send_telegram_message(message: str):
    """Send a message to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  Telegram credentials not configured!")
        print("Edit the .env file and add your TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
        print("\nWould send this message:")
        print("=" * 60)
        print(message)
        print("=" * 60)
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print("✅ Message sent to Telegram successfully!")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to send Telegram message: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response content: {e.response.text}")
        print("\nMessage that failed to send:")
        print("=" * 60)
        print(message)
        print("=" * 60)
        return False

# =========================================================
# MESSAGE FORMATTERS
# =========================================================

def format_buy_alert(df: pd.DataFrame) -> str:
    """Format buy opportunities as Telegram message."""
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    message = f"🟢 *TOP BUY IDEAS* 🟢\n"
    message += f"_{timestamp}_\n\n"
    
    if df.empty:
        message += "No strong buy signals at this time\\.\n"
        return message
    
    message += f"Top {len(df)} stocks with strong buy signals:\n\n"
    
    for idx, row in df.iterrows():
        # Escape special characters in variable data
        ticker = escape_markdown(str(row['ticker']))
        strategy = escape_markdown(str(row['strategy_name']))
        
        message += f"*{ticker}* \\| {strategy}\n"
        message += f"  • Return: {row['return_pct']}%\n"
        message += f"  • Sharpe: {row['sharpe']} \\| Win: {row['win_rate_pct']}%\n"
        message += f"  • Trades: {row['num_trades']} \\| Avg P&L: ${row['avg_pnl']}\n"
        message += f"  • Max Loss: {row['max_loss']}%\n\n"
    
    message += "⚠️ _This is algorithmic analysis, not financial advice\\._"
    
    return message

def format_sell_alert(df: pd.DataFrame) -> str:
    """Format sell opportunities as Telegram message."""
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    message = f"🔴 *SHORT-TERM SELL IDEAS* 🔴\n"
    message += f"_{timestamp}_\n\n"
    
    if df.empty:
        message += "No strong sell signals at this time\\.\n"
        return message
    
    message += f"Top {len(df)} stocks with strong sell signals:\n\n"
    
    for idx, row in df.iterrows():
        # Escape special characters in variable data
        ticker = escape_markdown(str(row['ticker']))
        strategy = escape_markdown(str(row['strategy_name']))
        
        message += f"*{ticker}* \\| {strategy}\n"
        message += f"  • Return: {row['return_pct']}%\n"
        message += f"  • Sharpe: {row['sharpe']} \\| Win: {row['win_rate_pct']}%\n"
        message += f"  • Trades: {row['num_trades']} \\| Avg P&L: ${row['avg_pnl']}\n"
        message += f"  • Max Loss: {row['max_loss']}%\n\n"
    
    message += "⚠️ _This is algorithmic analysis, not financial advice\\._"
    
    return message

def format_strategy_summary(df: pd.DataFrame) -> str:
    """Format strategy summary as Telegram message."""
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    message = f"📊 *STRATEGY RANKINGS* 📊\n"
    message += f"_{timestamp}_\n\n"
    
    message += "Top 5 strategies by Sharpe ratio:\n\n"
    
    for idx, row in df.iterrows():
        strategy = escape_markdown(str(row['strategy_name']))
        message += f"{idx+1}\\. *{strategy}*\n"
        message += f"   Sharpe: {row['avg_sharpe']} \\| Return: {row['avg_return']}%\n"
        message += f"   Tickers: {row['ticker_count']}\n\n"
    
    return message

def format_daily_signals_alert(df: pd.DataFrame) -> str:
    """Format today's trading signals as Telegram message."""
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    message = f"📊 *TODAY'S TRADING SIGNALS* 📊\n"
    message += f"_{timestamp}_\n\n"
    
    if df.empty:
        message += "No signals generated yet\\. Run: `python signal_engine.py`\n"
        return message
    
    message += f"*{len(df)} signals with backtest validation:*\n\n"
    
    for idx, row in df.iterrows():
        ticker = escape_markdown(str(row['ticker']))
        best_strat = escape_markdown(str(row.get('best_strategy', 'N/A')))
        signal_type = "🟢 BUY" if row['final_signal'] == 1 else "🔴 SELL"
        
        message += f"{signal_type} *{ticker}*\n"
        message += f"  Signal Score: {row['signal_score']}/4 \\| Consensus: {row['signal_score']*25}%\n"
        message += f"  Best Strategy: {best_strat}\n"
        
        if 'backtest_return' in row:
            message += f"  Backtest Return: {row['backtest_return']}% \\| Sharpe: {row['backtest_sharpe']}\n"
        
        # Individual strategy signals
        strategies = []
        if row.get('trend_following') == 1:
            strategies.append("Trend")
        if row.get('momentum') == 1:
            strategies.append("Momentum")
        if row.get('mean_reversion') == 1:
            strategies.append("MeanRev")
        if row.get('breakout') == 1:
            strategies.append("Breakout")
        
        if strategies:
            message += f"  Strategies: {', '.join(strategies)}\n"
        
        message += "\n"
    
    message += "⚠️ _Real\\-time signals combined with backtest validation\\._"
    
    return message

def format_signal_summary_alert(summary: dict) -> str:
    """Format trading signal summary as Telegram message."""
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    message = f"📈 *SIGNAL SUMMARY* 📈\n"
    message += f"_{timestamp}_\n\n"
    
    if not summary:
        message += "No signals available\\. Run: `python signal_engine.py`\n"
        return message
    
    message += f"*Today's Signal Breakdown:*\n"
    message += f"  🟢 Buy Signals: {summary.get('buy', 0)}\n"
    message += f"  🔴 Sell Signals: {summary.get('sell', 0)}\n"
    message += f"  ⚪ Neutral: {summary.get('neutral', 0)}\n"
    message += f"  Total Analyzed: {summary.get('total', 0)}\n\n"
    
    message += f"*Strategy Votes (Total Signals):*\n"
    strategies = summary.get('strategies', {})
    if strategies:
        for strat, count in strategies.items():
            message += f"  • {strat}: {int(count)} signals\n"
    
    message += "\n⚠️ _Ensemble voting system: stronger signals require more strategy agreement\\._"
    
    return message

def format_walk_forward_alert(df: pd.DataFrame, alert_type: str = "buy", strategy: str = None) -> str:
    """Format walk-forward buy opportunities as Telegram message."""
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    strategy_label = f" ({strategy})" if strategy else ""
    
    if alert_type == "buy":
        message = f"🟢 *WALK\\-FORWARD BUY IDEAS{escape_markdown(strategy_label)}* 🟢\n"
        message += f"_Anti\\-Overfitting Analysis_\n"
        message += f"_{timestamp}_\n\n"
    elif alert_type == "conservative":
        message = f"🛡️ *CONSERVATIVE BUY IDEAS{escape_markdown(strategy_label)}* 🛡️\n"
        message += f"_High Consistency Picks_\n"
        message += f"_{timestamp}_\n\n"
    else:  # aggressive
        message = f"🚀 *AGGRESSIVE BUY IDEAS{escape_markdown(strategy_label)}* 🚀\n"
        message += f"_High Return Potential_\n"
        message += f"_{timestamp}_\n\n"
    
    if df.empty:
        message += "No stocks meet criteria at this time\\.\n"
        message += "\n_Run walk\\-forward analysis:_\n"
        message += "`python backtester.py --walk-forward --limit 50`"
        return message
    
    message += f"Top {len(df)} stocks based on out\\-of\\-sample testing:\n\n"
    
    for idx, row in df.iterrows():
        ticker = escape_markdown(str(row['ticker']))
        
        message += f"*{ticker}*"
        if 'strategy' in row and pd.notna(row['strategy']) and not strategy:
            strat = escape_markdown(str(row['strategy']))
            message += f" \\| {strat}"
        message += "\n"
        
        message += f"  • Return: {row['total_return']*100:+.1f}% \\| Consistency: {row['consistency']*100:.0f}%\n"
        message += f"  • Sharpe: {row['avg_sharpe']:.2f} \\| Score: {row['composite_score']:.3f}\n"
        message += f"  • Windows: {row['num_windows']} \\| Wins: {row['winning_windows']}\n"
        
        if row['beats_buy_hold']:
            message += f"  ✅ Beats buy\\-and\\-hold\n"
        
        message += "\n"
    
    message += "💡 _Walk\\-forward prevents overfitting by testing on unseen data\\._\n"
    message += "⚠️ _This is algorithmic analysis, not financial advice\\._"
    
    return message

def format_portfolio_alert(df: pd.DataFrame, strategy: str = None) -> str:
    """Format portfolio allocation as Telegram message."""
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    strategy_label = f" ({strategy})" if strategy else ""
    
    message = f"📊 *PORTFOLIO ALLOCATION{escape_markdown(strategy_label)}* 📊\n"
    message += f"_Score\\-Weighted Portfolio_\n"
    message += f"_{timestamp}_\n\n"
    
    if df.empty:
        message += "No portfolio available\\. Run walk\\-forward analysis first\\.\n"
        return message
    
    message += f"{len(df)} stocks with optimized allocation:\n\n"
    
    for idx, row in df.iterrows():
        ticker = escape_markdown(str(row['ticker']))
        message += f"*{ticker}* \\- {row['allocation_pct']:.1f}%\n"
        message += f"  Return: {row['total_return']*100:+.1f}% \\| Consistency: {row['consistency']*100:.0f}%\n\n"
    
    # Portfolio stats
    weighted_return = (df['total_return'] * df['allocation_pct'] / 100).sum()
    avg_consistency = df['consistency'].mean()
    avg_sharpe = df['avg_sharpe'].mean()
    
    message += f"📈 *Portfolio Metrics:*\n"
    message += f"  Expected Return: {weighted_return*100:+.2f}%\n"
    message += f"  Avg Consistency: {avg_consistency*100:.0f}%\n"
    message += f"  Avg Sharpe: {avg_sharpe:.2f}\n\n"
    
    message += "⚠️ _This is algorithmic analysis, not financial advice\\._"
    
    return message

def format_comparison_alert(wf_df: pd.DataFrame, std_df: pd.DataFrame) -> str:
    """Compare walk-forward vs standard backtest recommendations."""
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    message = f"⚖️ *WALK\\-FORWARD vs STANDARD* ⚖️\n"
    message += f"_{timestamp}_\n\n"
    
    # Find common tickers
    if not wf_df.empty and not std_df.empty:
        wf_tickers = set(wf_df['ticker'].tolist())
        std_tickers = set(std_df['ticker'].tolist())
        common = wf_tickers.intersection(std_tickers)
        
        if common:
            message += f"✅ *Both methods agree on:*\n"
            for ticker in sorted(list(common))[:5]:
                ticker_escaped = escape_markdown(ticker)
                message += f"  • {ticker_escaped}\n"
            message += "\n"
        
        wf_only = wf_tickers - std_tickers
        if wf_only:
            message += f"🔍 *Walk\\-forward only* \\(more robust\\):\n"
            for ticker in sorted(list(wf_only))[:5]:
                ticker_escaped = escape_markdown(ticker)
                message += f"  • {ticker_escaped}\n"
            message += "\n"
        
        std_only = std_tickers - wf_tickers
        if std_only:
            message += f"⚠️ *Standard only* \\(may be overfit\\):\n"
            for ticker in sorted(list(std_only))[:5]:
                ticker_escaped = escape_markdown(ticker)
                message += f"  • {ticker_escaped}\n"
            message += "\n"
    
    message += "💡 _Prefer stocks that appear in walk\\-forward results\\._"
    
    return message

# =========================================================
# MAIN
# =========================================================

def send_buy_ideas(limit=5):
    """Query and send buy opportunities to Telegram."""
    print(f"🔍 Querying top {limit} buy opportunities...")
    
    df = get_buy_opportunities(limit)
    
    if df.empty:
        print("No buy opportunities found.")
        return
    
    print(f"Found {len(df)} opportunities")
    
    message = format_buy_alert(df)
    send_telegram_message(message)

def send_sell_ideas(limit=5):
    """Query and send sell opportunities to Telegram."""
    print(f"🔍 Querying top {limit} sell opportunities...")
    
    df = get_sell_opportunities(limit)
    
    if df.empty:
        print("No sell opportunities found.")
        return
    
    print(f"Found {len(df)} opportunities")
    
    message = format_sell_alert(df)
    send_telegram_message(message)

def send_strategy_summary():
    """Send strategy summary to Telegram."""
    print("🔍 Querying strategy summary...")
    
    df = get_strategy_summary()
    message = format_strategy_summary(df)
    send_telegram_message(message)

def send_walk_forward_ideas(limit=10, mode="buy", strategy=None):
    """Send walk-forward buy opportunities to Telegram."""
    strategy_label = f" ({strategy})" if strategy else ""
    print(f"🔍 Querying walk-forward {mode} opportunities{strategy_label}...")
    
    if mode == "conservative":
        df = get_walk_forward_conservative(limit, strategy=strategy)
        alert_type = "conservative"
    elif mode == "aggressive":
        df = get_walk_forward_aggressive(limit, strategy=strategy)
        alert_type = "aggressive"
    else:  # buy
        df = get_walk_forward_buy_opportunities(limit, strategy=strategy)
        alert_type = "buy"
    
    if df.empty:
        print(f"No {mode} opportunities found in walk-forward results{strategy_label}.")
        return
    
    print(f"Found {len(df)} opportunities")
    
    message = format_walk_forward_alert(df, alert_type=alert_type, strategy=strategy)
    send_telegram_message(message)

def send_portfolio_allocation(num_stocks=10, strategy=None):
    """Send portfolio allocation to Telegram."""
    strategy_label = f" ({strategy})" if strategy else ""
    print(f"🔍 Generating {num_stocks}-stock portfolio from walk-forward results{strategy_label}...")
    
    df = get_walk_forward_portfolio(num_stocks, strategy=strategy)
    
    if df.empty:
        print(f"No portfolio available{strategy_label}. Run walk-forward analysis first.")
        return
    
    print(f"Portfolio generated with {len(df)} stocks")
    
    message = format_portfolio_alert(df, strategy=strategy)
    send_telegram_message(message)

def send_comparison_alert(limit=5):
    """Send comparison between walk-forward and standard backtest."""
    print("🔍 Comparing walk-forward vs standard backtest...")
    
    wf_df = get_walk_forward_buy_opportunities(limit)
    std_df = get_buy_opportunities(limit)
    
    message = format_comparison_alert(wf_df, std_df)
    send_telegram_message(message)

def send_daily_signals(signal_type="buy", limit=10):
    """Send today's trading signals to Telegram."""
    signal_label = "buy" if signal_type == "buy" else "sell"
    print(f"🔍 Querying today's {signal_label} signals with backtest validation...")
    
    df = get_signals_with_backtest_validation(signal_type=signal_type, limit=limit)
    
    if df.empty:
        print(f"No {signal_label} signals found.")
        return
    
    print(f"Found {len(df)} signals")
    
    message = format_daily_signals_alert(df)
    send_telegram_message(message)

def send_signal_summary():
    """Send today's signal summary to Telegram."""
    print("🔍 Generating signal summary...")
    
    summary = get_signal_summary()
    
    if not summary:
        print("No signals available.")
        return
    
    message = format_signal_summary_alert(summary)
    send_telegram_message(message)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Send trading alerts to Telegram",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # DAILY SIGNALS (Real-Time - RECOMMENDED)
  # Today's buy signals with backtest validation
  python telegram_sender.py --signals-buy
  
  # Today's sell signals
  python telegram_sender.py --signals-sell
  
  # Today's signal breakdown summary
  python telegram_sender.py --signal-summary
  
  # WALK-FORWARD ALERTS (More Reliable)
  # Send walk-forward buy recommendations (anti-overfitting)
  python telegram_sender.py --wf-buy
  
  # Conservative picks (high consistency)
  python telegram_sender.py --wf-conservative
  
  # Aggressive picks (high return)
  python telegram_sender.py --wf-aggressive
  
  # Portfolio allocation (10 stocks)
  python telegram_sender.py --portfolio 10
  
  # Compare walk-forward vs standard
  python telegram_sender.py --compare
  
  # STANDARD BACKTEST ALERTS (Legacy)
  # Standard buy/sell opportunities
  python telegram_sender.py --buy
  python telegram_sender.py --sell
  
  # Strategy summary
  python telegram_sender.py --summary
  
  # Send all alerts
  python telegram_sender.py --all
        """
    )
    
    # Walk-forward options (recommended)
    parser.add_argument("--wf-buy", action="store_true", help="Send walk-forward buy recommendations (anti-overfitting)")
    parser.add_argument("--wf-conservative", action="store_true", help="Send conservative walk-forward picks")
    parser.add_argument("--wf-aggressive", action="store_true", help="Send aggressive walk-forward picks")
    parser.add_argument("--wf-strategy", type=str, help="Filter walk-forward by strategy (rsi_classic, macd_only, bollinger_bands, etc.)")
    parser.add_argument("--portfolio", type=int, help="Send portfolio allocation (specify number of stocks)")
    parser.add_argument("--compare", action="store_true", help="Compare walk-forward vs standard backtest")
    
    # Daily signal options (REAL-TIME - new)
    parser.add_argument("--signals-buy", action="store_true", help="Send today's buy signals with backtest validation (REAL-TIME)")
    parser.add_argument("--signals-sell", action="store_true", help="Send today's sell signals with backtest validation (REAL-TIME)")
    parser.add_argument("--signal-summary", action="store_true", help="Send today's signal breakdown summary")
    
    # Standard backtest options
    parser.add_argument("--buy", action="store_true", help="Send standard buy opportunities")
    parser.add_argument("--sell", action="store_true", help="Send standard sell opportunities")
    parser.add_argument("--summary", action="store_true", help="Send strategy summary")
    
    # Debug options
    parser.add_argument("--debug-signals", action="store_true", help="Debug: Inspect raw signal data and merged results")
    parser.add_argument("--debug-backtest", action="store_true", help="Debug: Inspect backtest database contents")
    parser.add_argument("--debug-signals-file", action="store_true", help="Debug: Inspect signals parquet file for data quality")
    parser.add_argument("--debug-features", action="store_true", help="Debug: Inspect features parquet file (signal_engine input)")
    
    # General options
    parser.add_argument("--all", action="store_true", help="Send all alerts (signals + walk-forward + standard)")
    parser.add_argument("--limit", type=int, default=5, help="Number of results to send (default: 5)")
    
    args = parser.parse_args()
    
    # Debug commands (first priority)
    if args.debug_signals:
        debug_signals_data()
    elif args.debug_backtest:
        debug_backtest_data()
    elif args.debug_signals_file:
        debug_signals_file()
    elif args.debug_features:
        debug_features_file()
    # Daily signal alerts (REAL-TIME - most timely)
    elif args.signals_buy:
        send_daily_signals(signal_type="buy", limit=args.limit)
    elif args.signals_sell:
        send_daily_signals(signal_type="sell", limit=args.limit)
    elif args.signal_summary:
        send_signal_summary()
    
    # Walk-forward alerts (robust)
    elif args.wf_buy:
        send_walk_forward_ideas(limit=args.limit, mode="buy", strategy=args.wf_strategy)
    elif args.wf_conservative:
        send_walk_forward_ideas(limit=args.limit, mode="conservative", strategy=args.wf_strategy)
    elif args.wf_aggressive:
        send_walk_forward_ideas(limit=args.limit, mode="aggressive", strategy=args.wf_strategy)
    elif args.portfolio:
        send_portfolio_allocation(num_stocks=args.portfolio, strategy=args.wf_strategy)
    elif args.compare:
        send_comparison_alert(limit=args.limit)
    
    # Standard backtest alerts (legacy)
    elif args.buy:
        send_buy_ideas(args.limit)
    elif args.sell:
        send_sell_ideas(args.limit)
    elif args.summary:
        send_strategy_summary()
    
    # Send all alerts
    elif args.all:
        print("📤 Sending comprehensive alert package...\n")
        send_daily_signals(signal_type="buy", limit=10)
        print()
        send_signal_summary()
        print()
        send_walk_forward_ideas(limit=10, mode="buy")
        print()
        send_portfolio_allocation(num_stocks=10)
    
    # Default: daily buy signals (real-time + backtest validated)
    else:
        print("💡 No option specified. Sending today's buy signals (use --help for options)\n")
        send_daily_signals(signal_type="buy", limit=10)
