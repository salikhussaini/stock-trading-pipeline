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

# Load from .env file
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# =========================================================
# QUERY FUNCTIONS
# =========================================================

def get_sell_opportunities(limit=10):
    """
    Find stocks with strong sell signals based on backtest results.
    Looks for strategies that predict price drops.
    """
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    
    # Query for stocks with highest negative momentum or overbought signals
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
# TELEGRAM FUNCTIONS
# =========================================================

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
        return False

# =========================================================
# MESSAGE FORMATTERS
# =========================================================

def format_sell_alert(df: pd.DataFrame) -> str:
    """Format sell opportunities as Telegram message."""
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    message = f"🔴 *SHORT-TERM SELL IDEAS* 🔴\n"
    message += f"_{timestamp}_\n\n"
    
    if df.empty:
        message += "No strong sell signals at this time.\n"
        return message
    
    message += f"Top {len(df)} stocks with strong sell signals:\n\n"
    
    for idx, row in df.iterrows():
        message += f"*{row['ticker']}* | {row['strategy_name']}\n"
        message += f"  • Return: {row['return_pct']}%\n"
        message += f"  • Sharpe: {row['sharpe']} | Win: {row['win_rate_pct']}%\n"
        message += f"  • Trades: {row['num_trades']} | Avg P&L: ${row['avg_pnl']}\n"
        message += f"  • Max Loss: {row['max_loss']}%\n\n"
    
    message += "⚠️ _This is algorithmic analysis, not financial advice._"
    
    return message

def format_strategy_summary(df: pd.DataFrame) -> str:
    """Format strategy summary as Telegram message."""
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    message = f"📊 *STRATEGY RANKINGS* 📊\n"
    message += f"_{timestamp}_\n\n"
    
    message += "Top 5 strategies by Sharpe ratio:\n\n"
    
    for idx, row in df.iterrows():
        message += f"{idx+1}. *{row['strategy_name']}*\n"
        message += f"   Sharpe: {row['avg_sharpe']} | Return: {row['avg_return']}%\n"
        message += f"   Tickers: {row['ticker_count']}\n\n"
    
    return message

# =========================================================
# MAIN
# =========================================================

def send_sell_ideas(limit=10):
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

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Send trading alerts to Telegram")
    parser.add_argument("--sell", action="store_true", help="Send sell opportunities")
    parser.add_argument("--summary", action="store_true", help="Send strategy summary")
    parser.add_argument("--limit", type=int, default=10, help="Number of results to send")
    
    args = parser.parse_args()
    
    if args.sell:
        send_sell_ideas(args.limit)
    elif args.summary:
        send_strategy_summary()
    else:
        # Default: send both
        send_sell_ideas(args.limit)
        print()
        send_strategy_summary()
