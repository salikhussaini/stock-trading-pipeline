#!/usr/bin/env python3
"""
Query and analyze backtest results from DuckDB.
Rank strategies, compare performance, and generate reports.
"""

import duckdb
import pandas as pd
from pathlib import Path
from typing import List, Optional, Dict
import numpy as np

# =========================================================
# CONFIGURATION
# =========================================================

DB_PATH = Path(__file__).parent / "database" / "stock_data.duckdb"

# =========================================================
# QUERY FUNCTIONS
# =========================================================

def query_results(
    sort_by: str = 'sharpe',
    strategy: Optional[str] = None,
    ticker: Optional[str] = None,
    min_trades: int = 0,
    min_return: float = None
) -> pd.DataFrame:
    """
    Flexible query of backtest results with filtering and sorting.
    
    Args:
        sort_by: Column to sort by (sharpe, return, win_rate, trades, avg_pnl)
        strategy: Filter by strategy name (None = all)
        ticker: Filter by ticker (None = all)
        min_trades: Minimum number of trades required
        min_return: Minimum return threshold
    
    Returns:
        DataFrame with filtered and sorted results
    """
    conn = duckdb.connect(str(DB_PATH))
    
    query = "SELECT * FROM backtest_results WHERE 1=1"
    params = []
    
    if strategy:
        query += " AND strategy_name = ?"
        params.append(strategy)
    
    if ticker:
        query += " AND ticker = ?"
        params.append(ticker)
    
    if min_trades > 0:
        query += " AND num_trades >= ?"
        params.append(min_trades)
    
    if min_return is not None:
        query += " AND total_return >= ?"
        params.append(min_return)
    
    # Sort by requested column
    sort_col = {
        'sharpe': 'sharpe_ratio',
        'return': 'total_return',
        'win_rate': 'win_rate',
        'trades': 'num_trades',
        'avg_pnl': 'avg_pnl'
    }.get(sort_by, 'sharpe_ratio')
    
    query += f" ORDER BY {sort_col} DESC"
    
    results = conn.execute(query, params).df()
    conn.close()
    
    return results

def strategy_summary(sort_by: str = 'sharpe') -> pd.DataFrame:
    """
    Aggregate statistics by strategy across all tickers.
    
    Args:
        sort_by: Metric to rank strategies (sharpe, return, win_rate)
    
    Returns:
        DataFrame with strategy-level statistics
    """
    conn = duckdb.connect(str(DB_PATH))
    
    # Get all unique strategies
    strategies = conn.execute("SELECT DISTINCT strategy_name FROM backtest_results ORDER BY strategy_name").df()['strategy_name'].tolist()
    
    summary = []
    for strat in strategies:
        results = conn.execute(
            "SELECT * FROM backtest_results WHERE strategy_name = ?",
            [strat]
        ).df()
        
        summary.append({
            'strategy': strat,
            'count': len(results),
            'avg_return': results['total_return'].mean(),
            'median_return': results['total_return'].median(),
            'std_return': results['total_return'].std(),
            'min_return': results['total_return'].min(),
            'max_return': results['total_return'].max(),
            'avg_sharpe': results['sharpe_ratio'].mean(),
            'median_sharpe': results['sharpe_ratio'].median(),
            'avg_win_rate': results['win_rate'].mean(),
            'avg_trades': results['num_trades'].mean(),
            'avg_pnl': results['avg_pnl'].mean(),
            'positive_tickers': (results['total_return'] > 0).sum(),
            'beats_buy_hold': (results['total_return'] > results['buy_hold_return']).sum(),
        })
    
    summary_df = pd.DataFrame(summary)
    
    # Sort by requested metric
    sort_col = {
        'sharpe': 'avg_sharpe',
        'return': 'avg_return',
        'win_rate': 'avg_win_rate'
    }.get(sort_by, 'avg_sharpe')
    
    summary_df = summary_df.sort_values(sort_col, ascending=False)
    conn.close()
    
    return summary_df

def ticker_summary(sort_by: str = 'return') -> pd.DataFrame:
    """
    Aggregate statistics by ticker across all strategies.
    
    Args:
        sort_by: Metric to rank tickers (return, sharpe, win_rate)
    
    Returns:
        DataFrame with ticker-level statistics
    """
    conn = duckdb.connect(str(DB_PATH))
    
    # Get all unique tickers
    tickers = conn.execute("SELECT DISTINCT ticker FROM backtest_results ORDER BY ticker").df()['ticker'].tolist()
    
    summary = []
    for tick in tickers:
        results = conn.execute(
            "SELECT * FROM backtest_results WHERE ticker = ?",
            [tick]
        ).df()
        
        summary.append({
            'ticker': tick,
            'count': len(results),
            'avg_return': results['total_return'].mean(),
            'median_return': results['total_return'].median(),
            'avg_sharpe': results['sharpe_ratio'].mean(),
            'best_strategy': results.loc[results['sharpe_ratio'].idxmax(), 'strategy_name'],
            'best_sharpe': results['sharpe_ratio'].max(),
            'worst_strategy': results.loc[results['sharpe_ratio'].idxmin(), 'strategy_name'],
            'worst_sharpe': results['sharpe_ratio'].min(),
            'winning_strategies': (results['total_return'] > 0).sum(),
            'total_strategies': len(results),
        })
    
    summary_df = pd.DataFrame(summary)
    
    # Sort by requested metric
    sort_col = {
        'return': 'avg_return',
        'sharpe': 'avg_sharpe',
        'win_rate': 'winning_strategies'
    }.get(sort_by, 'avg_return')
    
    summary_df = summary_df.sort_values(sort_col, ascending=False)
    conn.close()
    
    return summary_df

def strategy_vs_strategy(strategy1: str, strategy2: str, sort_by: str = 'return') -> pd.DataFrame:
    """
    Head-to-head comparison of two strategies across all tickers.
    
    Args:
        strategy1: First strategy name
        strategy2: Second strategy name
        sort_by: Column to sort by (return, sharpe, win_rate)
    
    Returns:
        DataFrame with side-by-side comparison
    """
    conn = duckdb.connect(str(DB_PATH))
    
    strat1 = conn.execute(
        "SELECT ticker, total_return, sharpe_ratio, win_rate, num_trades FROM backtest_results WHERE strategy_name = ? ORDER BY ticker",
        [strategy1]
    ).df()
    
    strat2 = conn.execute(
        "SELECT ticker, total_return, sharpe_ratio, win_rate, num_trades FROM backtest_results WHERE strategy_name = ? ORDER BY ticker",
        [strategy2]
    ).df()
    
    # Merge on ticker
    comparison = strat1.merge(strat2, on='ticker', suffixes=(f'_{strategy1[:5]}', f'_{strategy2[:5]}'), how='inner')
    
    # Add winner column (by return)
    comparison['winner'] = comparison.apply(
        lambda row: strategy1 if row[f'total_return_{strategy1[:5]}'] > row[f'total_return_{strategy2[:5]}'] else strategy2,
        axis=1
    )
    
    sort_col = {
        'return': f'total_return_{strategy1[:5]}',
        'sharpe': f'sharpe_ratio_{strategy1[:5]}',
        'win_rate': f'win_rate_{strategy1[:5]}'
    }.get(sort_by, f'total_return_{strategy1[:5]}')
    
    comparison = comparison.sort_values(sort_col, ascending=False)
    conn.close()
    
    return comparison

def top_strategies(n: int = 10, metric: str = 'sharpe') -> pd.DataFrame:
    """
    Get top N strategies by metric.
    
    Args:
        n: Number of strategies to return
        metric: Metric to rank by (sharpe, return, win_rate)
    
    Returns:
        DataFrame with top N strategies
    """
    summary = strategy_summary(sort_by=metric)
    return summary.head(n)

def worst_strategies(n: int = 10, metric: str = 'sharpe') -> pd.DataFrame:
    """
    Get bottom N strategies by metric.
    
    Args:
        n: Number of strategies to return
        metric: Metric to rank by (sharpe, return, win_rate)
    
    Returns:
        DataFrame with bottom N strategies
    """
    summary = strategy_summary(sort_by=metric)
    return summary.tail(n)

def get_stats(strategy: Optional[str] = None, ticker: Optional[str] = None) -> Dict:
    """
    Get detailed statistics for a strategy or ticker.
    
    Args:
        strategy: Strategy name (must specify one of strategy or ticker)
        ticker: Ticker name (must specify one of strategy or ticker)
    
    Returns:
        Dictionary with detailed statistics
    """
    if not strategy and not ticker:
        raise ValueError("Must specify either strategy or ticker")
    
    conn = duckdb.connect(str(DB_PATH))
    
    if strategy:
        results = conn.execute(
            "SELECT * FROM backtest_results WHERE strategy_name = ?",
            [strategy]
        ).df()
        label = f"Strategy: {strategy}"
    else:
        results = conn.execute(
            "SELECT * FROM backtest_results WHERE ticker = ?",
            [ticker]
        ).df()
        label = f"Ticker: {ticker}"
    
    if results.empty:
        conn.close()
        return {"error": f"No results found for {label}"}
    
    stats = {
        'label': label,
        'count': len(results),
        'avg_return': f"{results['total_return'].mean()*100:.2f}%",
        'median_return': f"{results['total_return'].median()*100:.2f}%",
        'min_return': f"{results['total_return'].min()*100:.2f}%",
        'max_return': f"{results['total_return'].max()*100:.2f}%",
        'avg_sharpe': f"{results['sharpe_ratio'].mean():.2f}",
        'avg_win_rate': f"{results['win_rate'].mean()*100:.1f}%",
        'avg_trades': f"{results['num_trades'].mean():.0f}",
        'positive_outcomes': f"{(results['total_return'] > 0).sum()}/{len(results)}",
        'beats_buy_hold': f"{(results['total_return'] > results['buy_hold_return']).sum()}/{len(results)}",
    }
    
    conn.close()
    return stats

# =========================================================
# REPORTING FUNCTIONS
# =========================================================

def print_strategy_report(strategy: str = None):
    """Print detailed report for all strategies or specific strategy."""
    if strategy:
        print(f"\n{'='*100}")
        print(f"STRATEGY REPORT: {strategy}")
        print(f"{'='*100}")
        results = query_results(strategy=strategy, sort_by='sharpe')
        print(results[['ticker', 'total_return', 'buy_hold_return', 'sharpe_ratio', 'win_rate', 'num_trades']].to_string())
        
        print(f"\n{'-'*100}")
        stats = get_stats(strategy=strategy)
        for key, value in stats.items():
            print(f"{key:20}: {value}")
    else:
        summary = strategy_summary()
        print(f"\n{'='*100}")
        print("STRATEGY RANKINGS (by Sharpe Ratio)")
        print(f"{'='*100}\n")
        print(summary[['strategy', 'count', 'avg_return', 'avg_sharpe', 'avg_win_rate', 'positive_tickers', 'beats_buy_hold']].to_string())

def print_ticker_report(ticker: str = None):
    """Print detailed report for all tickers or specific ticker."""
    if ticker:
        print(f"\n{'='*100}")
        print(f"TICKER REPORT: {ticker}")
        print(f"{'='*100}")
        results = query_results(ticker=ticker, sort_by='sharpe')
        print(results[['strategy_name', 'total_return', 'buy_hold_return', 'sharpe_ratio', 'win_rate', 'num_trades']].to_string())
        
        print(f"\n{'-'*100}")
        stats = get_stats(ticker=ticker)
        for key, value in stats.items():
            print(f"{key:20}: {value}")
    else:
        summary = ticker_summary()
        print(f"\n{'='*100}")
        print("TICKER RANKINGS (by Average Return)")
        print(f"{'='*100}\n")
        print(summary[['ticker', 'count', 'avg_return', 'avg_sharpe', 'best_strategy', 'best_sharpe']].to_string())

def print_comparison(strategy1: str, strategy2: str):
    """Print head-to-head comparison of two strategies."""
    comparison = strategy_vs_strategy(strategy1, strategy2)
    
    print(f"\n{'='*100}")
    print(f"HEAD-TO-HEAD: {strategy1} vs {strategy2}")
    print(f"{'='*100}\n")
    print(comparison.to_string())
    
    # Summary
    s1_wins = (comparison['winner'] == strategy1).sum()
    s2_wins = (comparison['winner'] == strategy2).sum()
    total = len(comparison)
    
    print(f"\n{'-'*100}")
    print(f"{strategy1:20}: {s1_wins}/{total} wins ({s1_wins/total*100:.1f}%)")
    print(f"{strategy2:20}: {s2_wins}/{total} wins ({s2_wins/total*100:.1f}%)")

# =========================================================
# EXAMPLE USAGE
# =========================================================

if __name__ == "__main__":
    print("Backtest Results Analysis")
    print("="*100)
    
    # Overall strategy rankings
    print_strategy_report()
    
    # Overall ticker rankings
    print("\n")
    print_ticker_report()
    
    # Top 5 strategies
    print(f"\n{'='*100}")
    print("TOP 5 STRATEGIES (by Sharpe Ratio)")
    print(f"{'='*100}\n")
    top_5 = top_strategies(n=5, metric='sharpe')
    print(top_5[['strategy', 'count', 'avg_return', 'avg_sharpe', 'positive_tickers', 'beats_buy_hold']].to_string())
    
    # Example: Compare two strategies
    try:
        top_strats = top_5['strategy'].tolist()
        if len(top_strats) >= 2:
            print_comparison(top_strats[0], top_strats[1])
    except:
        pass
    
    print(f"\n{'='*100}")
    print("Analysis complete!")
    print(f"{'='*100}\n")
