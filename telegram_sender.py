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

# Load from .env file
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

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

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Send trading alerts to Telegram",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # WALK-FORWARD ALERTS (Recommended - More Reliable)
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
  
  # Send all alerts (standard + walk-forward)
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
    
    # Standard backtest options
    parser.add_argument("--buy", action="store_true", help="Send standard buy opportunities")
    parser.add_argument("--sell", action="store_true", help="Send standard sell opportunities")
    parser.add_argument("--summary", action="store_true", help="Send strategy summary")
    
    # General options
    parser.add_argument("--all", action="store_true", help="Send all alerts (walk-forward + standard)")
    parser.add_argument("--limit", type=int, default=5, help="Number of results to send (default: 5)")
    
    args = parser.parse_args()
    
    # Walk-forward alerts (preferred)
    if args.wf_buy:
        send_walk_forward_ideas(limit=args.limit, mode="buy", strategy=args.wf_strategy)
    elif args.wf_conservative:
        send_walk_forward_ideas(limit=args.limit, mode="conservative", strategy=args.wf_strategy)
    elif args.wf_aggressive:
        send_walk_forward_ideas(limit=args.limit, mode="aggressive", strategy=args.wf_strategy)
    elif args.portfolio:
        send_portfolio_allocation(num_stocks=args.portfolio, strategy=args.wf_strategy)
    elif args.compare:
        send_comparison_alert(limit=args.limit)
    
    # Standard backtest alerts
    elif args.buy:
        send_buy_ideas(args.limit)
    elif args.sell:
        send_sell_ideas(args.limit)
    elif args.summary:
        send_strategy_summary()
    
    # Send all alerts
    elif args.all:
        print("📤 Sending comprehensive alert package...\n")
        send_walk_forward_ideas(limit=10, mode="buy")
        print()
        send_portfolio_allocation(num_stocks=10)
        print()
        send_comparison_alert(limit=5)
        print()
        send_strategy_summary()
    
    # Default: walk-forward buy ideas (most reliable)
    else:
        print("💡 No option specified. Sending walk-forward buy recommendations (use --help for options)\n")
        send_walk_forward_ideas(limit=10, mode="buy")
