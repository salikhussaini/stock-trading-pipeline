#!/usr/bin/env python3
"""
Query and analyze backtest results from DuckDB.
Rank strategies, compare performance, and generate reports.
Supports both standard backtests and walk-forward analysis.
"""

import duckdb
import pandas as pd
from pathlib import Path
from typing import List, Optional, Dict
import numpy as np

# =========================================================
# CONFIGURATION
# =========================================================

DB_PATH = Path(__file__).parent.parent / "database" / "stock_data.duckdb"
WALK_FORWARD_CSV = Path(__file__).parent.parent / "walk_forward_results.csv"

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
# WALK-FORWARD ANALYSIS QUERIES
# =========================================================

def load_walk_forward_results() -> pd.DataFrame:
    """
    Load walk-forward analysis results from CSV.
    
    Returns:
        DataFrame with walk-forward results, or empty DataFrame if file doesn't exist
    """
    if not WALK_FORWARD_CSV.exists():
        print(f"⚠️  Walk-forward results not found at {WALK_FORWARD_CSV}")
        print("   Run: python backtester.py --walk-forward --limit 20")
        return pd.DataFrame()
    
    return pd.read_csv(WALK_FORWARD_CSV)

def query_walk_forward(
    sort_by: str = 'composite_score',
    min_consistency: float = 0.0,
    min_return: float = None,
    min_sharpe: float = None,
    only_buy_candidates: bool = False,
    strategy: str = None
) -> pd.DataFrame:
    """
    Query walk-forward analysis results with filtering.
    
    Args:
        sort_by: Column to sort by (composite_score, total_return, consistency, avg_sharpe)
        min_consistency: Minimum consistency threshold (0.0-1.0)
        min_return: Minimum total return threshold
        min_sharpe: Minimum average Sharpe ratio
        only_buy_candidates: Filter for stocks meeting buy criteria
        strategy: Filter by strategy name (None = all strategies)
    
    Returns:
        Filtered and sorted DataFrame
    """
    df = load_walk_forward_results()
    
    if df.empty:
        return df
    
    # Apply strategy filter
    if strategy and 'strategy' in df.columns:
        df = df[df['strategy'] == strategy]
    
    # Apply filters
    if min_consistency > 0:
        df = df[df['consistency'] >= min_consistency]
    
    if min_return is not None:
        df = df[df['total_return'] >= min_return]
    
    if min_sharpe is not None:
        df = df[df['avg_sharpe'] >= min_sharpe]
    
    if only_buy_candidates:
        df = df[
            (df['consistency'] >= 0.5) &
            (df['total_return'] > 0) &
            (df['avg_sharpe'] > 0.5)
        ]
    
    # Sort
    if sort_by in df.columns:
        df = df.sort_values(sort_by, ascending=False)
    
    return df

def get_buy_recommendations(min_composite_score: float = 0.0) -> pd.DataFrame:
    """
    Get stocks that meet all buy criteria from walk-forward analysis.
    
    Args:
        min_composite_score: Minimum composite score (0 = no filter)
    
    Returns:
        DataFrame with buy recommendations sorted by composite score
    """
    df = query_walk_forward(only_buy_candidates=True)
    
    if not df.empty and min_composite_score > 0:
        df = df[df['composite_score'] >= min_composite_score]
    
    return df

def compare_wf_to_standard(ticker: str) -> Dict:
    """
    Compare walk-forward performance to standard backtest for a ticker.
    
    Args:
        ticker: Stock ticker symbol
    
    Returns:
        Dictionary with comparison metrics
    """
    # Get walk-forward results
    wf_df = load_walk_forward_results()
    if wf_df.empty or ticker not in wf_df['ticker'].values:
        return {'error': f'No walk-forward results for {ticker}'}
    
    wf_result = wf_df[wf_df['ticker'] == ticker].iloc[0]
    
    # Get standard backtest results
    conn = duckdb.connect(str(DB_PATH))
    std_results = conn.execute(
        "SELECT * FROM backtest_results WHERE ticker = ? ORDER BY sharpe_ratio DESC",
        [ticker]
    ).df()
    conn.close()
    
    if std_results.empty:
        return {
            'ticker': ticker,
            'walk_forward': {
                'return': wf_result['total_return'],
                'consistency': wf_result['consistency'],
                'sharpe': wf_result['avg_sharpe']
            },
            'standard_backtest': 'No results'
        }
    
    # Best standard strategy for this ticker
    best_std = std_results.iloc[0]
    
    return {
        'ticker': ticker,
        'walk_forward': {
            'return': wf_result['total_return'],
            'consistency': wf_result['consistency'],
            'sharpe': wf_result['avg_sharpe'],
            'composite_score': wf_result['composite_score'],
            'num_windows': wf_result['num_windows']
        },
        'standard_backtest': {
            'best_strategy': best_std['strategy_name'],
            'return': best_std['total_return'],
            'sharpe': best_std['sharpe_ratio'],
            'win_rate': best_std['win_rate'],
            'num_trades': best_std['num_trades']
        },
        'recommendation': 'BUY' if (
            wf_result['consistency'] >= 0.5 and
            wf_result['total_return'] > 0 and
            wf_result['avg_sharpe'] > 0.5
        ) else 'HOLD/SKIP'
    }

def rank_stocks_by_robustness(top_n: int = 20) -> pd.DataFrame:
    """
    Rank stocks by walk-forward robustness (composite score).
    
    Args:
        top_n: Number of top stocks to return
    
    Returns:
        DataFrame with top N most robust stocks
    """
    df = load_walk_forward_results()
    
    if df.empty:
        return df
    
    # Add robustness grade
    def grade_stock(row):
        score = row['composite_score']
        consistency = row['consistency']
        
        if score > 0.6 and consistency >= 0.6:
            return 'A - Excellent'
        elif score > 0.4 and consistency >= 0.5:
            return 'B - Good'
        elif score > 0.2 and consistency >= 0.4:
            return 'C - Fair'
        else:
            return 'D - Poor'
    
    df['robustness_grade'] = df.apply(grade_stock, axis=1)
    
    return df.nlargest(top_n, 'composite_score')[
        ['ticker', 'total_return', 'consistency', 'avg_sharpe', 
         'composite_score', 'robustness_grade', 'beats_buy_hold']
    ]

def portfolio_from_walk_forward(
    num_stocks: int = 10,
    min_consistency: float = 0.5,
    allocation_method: str = 'equal',
    strategy: str = None
) -> pd.DataFrame:
    """
    Generate portfolio allocation from walk-forward results.
    
    Args:
        num_stocks: Number of stocks in portfolio
        min_consistency: Minimum consistency requirement
        allocation_method: 'equal' or 'score_weighted'
        strategy: Filter by strategy name (None = all strategies)
    
    Returns:
        DataFrame with portfolio allocations
    """
    # Get buy candidates with strategy filter
    df = query_walk_forward(only_buy_candidates=True, strategy=strategy)
    
    if df.empty:
        print("⚠️  No stocks meet buy criteria")
        return pd.DataFrame()
    
    # Filter by consistency
    df = df[df['consistency'] >= min_consistency]
    
    # Top N by composite score
    portfolio = df.nlargest(num_stocks, 'composite_score').copy()
    
    # Calculate allocation
    if allocation_method == 'equal':
        portfolio['allocation'] = 1.0 / len(portfolio)
    elif allocation_method == 'score_weighted':
        total_score = portfolio['composite_score'].sum()
        portfolio['allocation'] = portfolio['composite_score'] / total_score
    
    portfolio['allocation_pct'] = portfolio['allocation'] * 100
    
    cols = ['ticker', 'total_return', 'consistency', 'avg_sharpe', 
             'composite_score', 'allocation_pct']
    if 'strategy' in portfolio.columns:
        cols.insert(1, 'strategy')
    
    return portfolio[cols]

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

def print_walk_forward_report(strategy: str = None):
    """
    Print detailed walk-forward analysis report.
    
    Args:
        strategy: Filter by strategy name (None = all strategies)
    """
    df = query_walk_forward(strategy=strategy) if strategy else load_walk_forward_results()
    
    if df.empty:
        return
    
    strategy_label = f" ({strategy})" if strategy else ""
    print(f"\n{'='*100}")
    print(f"WALK-FORWARD ANALYSIS REPORT{strategy_label}")
    print(f"{'='*100}\n")
    
    # Show unique strategies if multiple exist
    if 'strategy' in df.columns and not strategy:
        strategies = df['strategy'].unique()
        print(f"Strategies: {', '.join(strategies)}")
    
    print(f"Total Stocks Analyzed: {len(df)}")
    
    # Get buy recommendations with strategy filter
    buy_recs = df[
        (df['consistency'] >= 0.5) &
        (df['total_return'] > 0) &
        (df['avg_sharpe'] > 0.5)
    ]
    print(f"Buy Candidates: {len(buy_recs)}")
    print(f"Avg Consistency: {df['consistency'].mean()*100:.1f}%")
    print(f"Median Return: {df['total_return'].median()*100:+.2f}%")
    
    # Top 10
    print(f"\n{'-'*100}")
    print("TOP 10 STOCKS (by Composite Score)")
    print(f"{'-'*100}\n")
    top_10 = df.nlargest(10, 'composite_score').copy()
    top_10['total_return'] = top_10['total_return'].apply(lambda x: f"{x*100:+6.2f}%")
    top_10['consistency'] = top_10['consistency'].apply(lambda x: f"{x*100:.1f}%")
    top_10['avg_sharpe'] = top_10['avg_sharpe'].apply(lambda x: f"{x:.2f}")
    top_10['composite_score'] = top_10['composite_score'].apply(lambda x: f"{x:.3f}")
    
    display_cols = ['ticker', 'total_return', 'consistency', 'avg_sharpe', 'composite_score']
    if 'strategy' in top_10.columns:
        display_cols.insert(1, 'strategy')
    print(top_10[display_cols].to_string(index=False))
    
    # Buy recommendations
    if not buy_recs.empty:
        print(f"\n{'-'*100}")
        print(f"BUY RECOMMENDATIONS ({len(buy_recs)} stocks)")
        print(f"{'-'*100}\n")
        
        buy_display = buy_recs.head(15).copy()
        buy_display['total_return'] = buy_display['total_return'].apply(lambda x: f"{x*100:+6.2f}%")
        buy_display['consistency'] = buy_display['consistency'].apply(lambda x: f"{x*100:.1f}%")
        buy_display['avg_sharpe'] = buy_display['avg_sharpe'].apply(lambda x: f"{x:.2f}")
        buy_display['composite_score'] = buy_display['composite_score'].apply(lambda x: f"{x:.3f}")
        
        display_cols = ['ticker', 'total_return', 'consistency', 'avg_sharpe', 'composite_score']
        if 'strategy' in buy_display.columns:
            display_cols.insert(1, 'strategy')
        print(buy_display[display_cols].to_string(index=False))

def print_portfolio_report(num_stocks: int = 10, strategy: str = None):
    """
    Print portfolio allocation based on walk-forward results.
    
    Args:
        num_stocks: Number of stocks in portfolio
        strategy: Filter by strategy name (None = all strategies)
    """
    portfolio = portfolio_from_walk_forward(num_stocks=num_stocks, allocation_method='score_weighted', strategy=strategy)
    
    if portfolio.empty:
        return
    
    strategy_label = f" ({strategy})" if strategy else ""
    print(f"\n{'='*100}")
    print(f"RECOMMENDED PORTFOLIO ({num_stocks} stocks, score-weighted){strategy_label}")
    print(f"{'='*100}\n")
    
    portfolio_display = portfolio.copy()
    portfolio_display['total_return'] = portfolio_display['total_return'].apply(lambda x: f"{x*100:+6.2f}%")
    portfolio_display['consistency'] = portfolio_display['consistency'].apply(lambda x: f"{x*100:.1f}%")
    portfolio_display['avg_sharpe'] = portfolio_display['avg_sharpe'].apply(lambda x: f"{x:.2f}")
    portfolio_display['composite_score'] = portfolio_display['composite_score'].apply(lambda x: f"{x:.3f}")
    portfolio_display['allocation_pct'] = portfolio_display['allocation_pct'].apply(lambda x: f"{x:.1f}%")
    
    print(portfolio_display.to_string(index=False))
    
    # Portfolio statistics
    print(f"\n{'-'*100}")
    print("Portfolio Statistics:")
    print(f"{'-'*100}")
    weighted_return = (portfolio['total_return'] * portfolio['allocation']).sum()
    avg_consistency = portfolio['consistency'].mean()
    avg_sharpe = portfolio['avg_sharpe'].mean()
    
    print(f"Expected Return: {weighted_return*100:+.2f}%")
    print(f"Avg Consistency: {avg_consistency*100:.1f}%")
    print(f"Avg Sharpe: {avg_sharpe:.2f}")

def print_ticker_comparison(ticker: str):
    """Compare walk-forward vs standard backtest for a ticker."""
    comparison = compare_wf_to_standard(ticker)
    
    if 'error' in comparison:
        print(f"\n⚠️  {comparison['error']}")
        return
    
    print(f"\n{'='*100}")
    print(f"COMPARISON: {ticker} (Walk-Forward vs Standard Backtest)")
    print(f"{'='*100}\n")
    
    wf = comparison['walk_forward']
    std = comparison['standard_backtest']
    
    print(f"{'Walk-Forward Analysis:':30}")
    print(f"  Return:                     {wf['return']*100:+6.2f}%")
    print(f"  Consistency:                {wf['consistency']*100:5.1f}%")
    print(f"  Avg Sharpe:                 {wf['sharpe']:5.2f}")
    print(f"  Composite Score:            {wf['composite_score']:5.3f}")
    print(f"  Test Windows:               {wf['num_windows']}")
    
    print(f"\n{'Standard Backtest (Best):':30}")
    if std == 'No results':
        print(f"  No standard backtest results")
    else:
        print(f"  Strategy:                   {std['best_strategy']}")
        print(f"  Return:                     {std['return']*100:+6.2f}%")
        print(f"  Sharpe:                     {std['sharpe']:5.2f}")
        print(f"  Win Rate:                   {std['win_rate']*100:5.1f}%")
        print(f"  Trades:                     {std['num_trades']}")
    
    print(f"\n{'Recommendation:':30} {comparison['recommendation']}")
    print(f"{'='*100}")

# =========================================================
# EXAMPLE USAGE
# =========================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Query and analyze backtest results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # View all reports (standard + walk-forward)
  python query_backtest_results.py
  
  # Standard backtest reports only
  python query_backtest_results.py --standard
  
  # Walk-forward analysis only
  python query_backtest_results.py --walk-forward
  
  # Compare specific ticker (walk-forward vs standard)
  python query_backtest_results.py --compare AAPL
  
  # Generate portfolio from walk-forward (top 10 stocks)
  python query_backtest_results.py --portfolio 10
  
  # Specific strategy report
  python query_backtest_results.py --strategy rsi_classic
  
  # Specific ticker report (all strategies)
  python query_backtest_results.py --ticker MSFT
        """
    )
    
    parser.add_argument('--standard', action='store_true', help='Show standard backtest reports only')
    parser.add_argument('--walk-forward', action='store_true', help='Show walk-forward analysis only')
    parser.add_argument('--compare', type=str, help='Compare walk-forward vs standard for ticker')
    parser.add_argument('--portfolio', type=int, help='Generate portfolio with N stocks from walk-forward')
    parser.add_argument('--wf-strategy', type=str, help='Filter walk-forward results by strategy (rsi_classic, macd_only, bollinger_bands, etc.)')
    parser.add_argument('--strategy', type=str, help='Show report for specific strategy (standard backtest)')
    parser.add_argument('--ticker', type=str, help='Show report for specific ticker')
    
    args = parser.parse_args()
    
    # Specific queries
    if args.compare:
        print_ticker_comparison(args.compare)
        exit(0)
    
    if args.portfolio:
        print_portfolio_report(num_stocks=args.portfolio, strategy=args.wf_strategy)
        exit(0)
    
    if args.strategy:
        print_strategy_report(strategy=args.strategy)
        exit(0)
    
    if args.ticker:
        print_ticker_report(ticker=args.ticker)
        exit(0)
    
    # Full reports
    print("Backtest Results Analysis")
    print("="*100)
    
    # Standard backtest reports (if --walk-forward not specified)
    if not args.walk_forward:
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
    
    # Walk-forward reports (if --standard not specified)
    if not args.standard:
        print_walk_forward_report(strategy=args.wf_strategy)
        print_portfolio_report(num_stocks=10, strategy=args.wf_strategy)
    
    print(f"\n{'='*100}")
    print("Analysis complete!")
    print(f"{'='*100}\n")
    
    # Helpful tips
    if not args.standard and not args.walk_forward:
        print("\n💡 Tip: Use --walk-forward to see only walk-forward analysis")
        print("💡 Tip: Use --standard to see only standard backtest results")
        print("💡 Tip: Use --compare AAPL to compare both methods for a ticker")
        print("💡 Tip: Use --portfolio 15 to generate a 15-stock portfolio\n")
