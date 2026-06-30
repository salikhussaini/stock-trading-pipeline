# Contributing Guidelines

Thank you for your interest in contributing to the Stock Trading Pipeline project! Here are the guidelines to help you get started.

## Code of Conduct

- Be respectful and constructive
- Maintain professional communication
- Focus on code quality and testing
- Share knowledge and help others

## Getting Started

### Prerequisites

- Python 3.9+
- Virtual environment (venv/conda)
- Git
- Basic understanding of trading strategies and technical analysis

### Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/yourusername/stock-trading-pipeline.git
cd stock-trading-pipeline

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Verify setup
python incremental_collector.py --test
```

## Development Workflow

### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
# or for bug fixes:
git checkout -b bugfix/issue-description
# or for documentation:
git checkout -b docs/update-readme
```

### Branch Naming Convention

- `feature/description` - New features or enhancements
- `bugfix/description` - Bug fixes
- `docs/description` - Documentation updates
- `refactor/description` - Code refactoring
- `perf/description` - Performance improvements
- `test/description` - Test additions/improvements

### 2. Make Your Changes

#### Code Style

- Follow PEP 8 standards
- Use meaningful variable names
- Add docstrings to functions and classes
- Keep functions focused and testable
- Maximum line length: 100 characters (soft limit)

#### Example Function Documentation

```python
def backtest_strategy(df: pd.DataFrame, initial_capital: float = 10000) -> Dict:
    """
    Evaluate a trading strategy on historical data.
    
    Args:
        df: DataFrame with OHLCV data and technical indicators
        initial_capital: Starting capital in dollars (default: 10000)
    
    Returns:
        Dictionary containing:
            - total_return: Percentage return of strategy
            - buy_hold_return: Buy-and-hold benchmark return
            - sharpe_ratio: Risk-adjusted return metric
            - win_rate: Percentage of profitable trades
            - num_trades: Total number of trades executed
            - max_drawdown: Largest peak-to-trough decline
    
    Raises:
        ValueError: If DataFrame is empty or missing required columns
    
    Example:
        >>> df = load_features("AAPL")
        >>> result = backtest_strategy(df, initial_capital=50000)
        >>> print(f"Sharpe: {result['sharpe_ratio']:.2f}")
    """
```

#### Logging

Use the centralized logger instead of print statements:

```python
from logger_config import log_info, log_error, log_warning

# Instead of: print("Processing ticker:", ticker)
log_info(f"Processing ticker: {ticker}")

# For errors:
log_error(f"Failed to process {ticker}: {str(e)}")
```

### 3. Testing

#### Adding Tests

- Write tests for new functionality
- Test edge cases and error conditions
- Ensure tests are reproducible

#### Manual Testing

```bash
# Test with small dataset
python incremental_collector.py --test --limit 5

# Test feature generation
python feature_engine.py

# Test backtesting
python -c "from backtester import run_backtest; run_backtest(limit=10, num_workers=2)"

# Check results
python query_backtest_results.py
```

#### Performance Testing

```bash
# Benchmark before and after changes
import time
start = time.perf_counter()
# Run your code
elapsed = time.perf_counter() - start
print(f"Execution time: {elapsed:.2f}s")
```

### 4. Commit Messages

Use clear, descriptive commit messages:

```bash
# Good commit messages
git commit -m "feat: add support for volume-weighted VWAP strategy"
git commit -m "fix: resolve KeyError when ticker has missing columns"
git commit -m "perf: optimize feature calculation by 10x using vectorization"
git commit -m "docs: add backtester examples to README"
git commit -m "refactor: extract strategy logic into separate module"

# Avoid vague messages
# git commit -m "fix stuff"
# git commit -m "update code"
# git commit -m "WIP"
```

### Commit Message Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type:**
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation
- `style` - Code style (formatting, missing semicolons, etc.)
- `refactor` - Code refactoring
- `perf` - Performance improvement
- `test` - Adding tests
- `ci` - CI/CD configuration
- `chore` - Maintenance tasks

**Scope:** Component affected (backtester, feature_engine, collector, etc.)

**Subject:** 
- Imperative mood ("add" not "added" or "adds")
- Don't capitalize first letter
- No period at end
- Maximum 50 characters

**Body:** (optional)
- Explain the change and why
- Separate from subject with blank line
- Wrap at 72 characters

**Example:**
```
feat(backtester): add RSI divergence strategy

Implements divergence detection between price action and RSI
indicator. Strategy buys when price makes new low but RSI doesn't,
indicating bullish divergence. Sharpe ratio: 0.596

Closes #42
```

### 5. Push and Create Pull Request

```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub:
- Fill out the PR template completely
- Link to related issues
- Describe what changed and why
- Include backtest results if applicable
- Be responsive to code review feedback

## Types of Contributions

### 1. Adding a New Strategy

#### File: `backtester.py`

```python
def your_new_strategy(df: pd.DataFrame) -> pd.DataFrame:
    """
    Brief description of the strategy.
    
    Buy signal: [describe condition]
    Sell signal: [describe condition]
    
    Indicators used: RSI, MACD, Volume, etc.
    """
    df = df.copy()
    df['signal'] = 0
    
    # Buy conditions
    buy_condition = (df['rsi_14'] < 30) & (df['volume'] > df['volume_zscore_20d'])
    df.loc[buy_condition, 'signal'] = 1
    
    # Sell conditions
    sell_condition = (df['rsi_14'] > 70)
    df.loc[sell_condition, 'signal'] = -1
    
    return df

# Register in STRATEGIES dict
STRATEGIES['your_strategy_name'] = your_new_strategy
```

#### Testing Your Strategy

```bash
python -c "
from backtester import run_backtest
run_backtest(strategies=['your_strategy_name'], limit=10, num_workers=2)
"
```

#### Document Results

Include in PR description:
- Strategy logic and inspiration
- Backtest results (Sharpe, return, win rate)
- Comparison to existing strategies
- When to use this strategy

### 2. Improving Data Collection

#### File: `incremental_collector.py`

```python
# Enhance safe_yf_download() or add new data source
def fetch_from_alternative_source(ticker, start, end):
    """Fetch data from alternative provider"""
    pass

# Update rate limiting or retry logic
# Optimize performance
```

### 3. Adding Technical Indicators

#### File: `feature_engine.py`

```python
def compute_ticker_features(ticker_data: pd.DataFrame) -> tuple:
    # Add new indicator calculation
    df['your_indicator'] = ...
    
    # Ensure it's included in the output
```

### 4. Enhancing Analysis Tools

#### File: `query_backtest_results.py`

```python
def new_analysis_function(metric: str = 'sharpe') -> pd.DataFrame:
    """New way to query or analyze results"""
    pass
```

### 5. Documentation

- Update README.md with examples
- Add docstrings to functions
- Create usage guides
- Document strategy parameters
- Add performance benchmarks

## Code Review Process

1. **Automated Checks** (if CI/CD is configured)
   - Linting (PEP 8)
   - Type checking
   - Test coverage

2. **Manual Review**
   - Code quality and readability
   - Algorithm correctness
   - Performance implications
   - Backtest result validity

3. **Approval & Merge**
   - At least 1 maintainer approval required
   - All feedback addressed
   - Tests passing
   - No conflicts with main branch

## Performance Guidelines

### Optimization Priority

1. **Correctness** - Must be accurate
2. **Clarity** - Must be understandable
3. **Performance** - Optimize after above

### Benchmarking

Track performance of changes:

```python
import time
import cProfile

# Simple timing
start = time.perf_counter()
function_to_test()
elapsed = time.perf_counter() - start
print(f"Time: {elapsed:.2f}s")

# Profile
cProfile.run('function_to_test()', sort='cumtime')

# Memory profiling
# pip install memory_profiler
# python -m memory_profiler script.py
```

### Expected Performance

- Feature generation: ~55 seconds for 500 tickers
- Backtester: ~2.5 hours for 28 strategies × 500 tickers
- Per-ticker query: <100ms

## Documentation Requirements

### For New Features

- [ ] Add to README.md usage section
- [ ] Include docstrings in code
- [ ] Update CHANGELOG.md
- [ ] Add examples/usage documentation
- [ ] Document any new parameters

### For Bug Fixes

- [ ] Update CHANGELOG.md
- [ ] Explain root cause in PR description
- [ ] Add test case that catches the bug

### For Performance Improvements

- [ ] Document before/after metrics
- [ ] Update performance benchmarks in README
- [ ] Explain optimization technique

## Questions or Need Help?

- **GitHub Issues** - For bugs and feature requests
- **Discussions** - For questions and discussions
- **PR Comments** - For review feedback

## Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md (if created)
- Credited in commit messages
- Recognized in release notes

## License

By contributing, you agree that your code will be licensed under the same license as the project (specify license).

Thank you for contributing! 🚀
