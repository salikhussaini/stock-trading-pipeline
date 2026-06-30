# Repository Setup for Git Commit

This document contains the git configuration and commit checklist for this project.

## Pre-Commit Checklist

Before committing code, ensure:

### Code Quality
- [ ] Code follows PEP 8 style guidelines
- [ ] No unused imports or variables
- [ ] All functions have docstrings
- [ ] No hardcoded values (use config instead)
- [ ] Error handling is comprehensive

### Testing
- [ ] Code tested locally
- [ ] No breaking changes to existing functionality
- [ ] Edge cases considered
- [ ] Performance impact assessed

### Documentation
- [ ] Comments explain complex logic
- [ ] README updated if functionality changes
- [ ] CHANGELOG.md updated
- [ ] Docstrings follow Google/NumPy format

### Files
- [ ] .gitignore configured (see .gitignore)
- [ ] No database files committed (stock_data.duckdb in .gitignore)
- [ ] No log files committed (logs/ in .gitignore)
- [ ] No venv/ or __pycache__/ committed
- [ ] No .env files with secrets committed

## Commit Message Guidelines

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

| Type | Description | Example |
|------|-------------|---------|
| `feat` | New feature | `feat(backtester): add RSI divergence strategy` |
| `fix` | Bug fix | `fix(feature_engine): handle missing data gracefully` |
| `docs` | Documentation | `docs(README): add backtester examples` |
| `style` | Code style | `style: format imports alphabetically` |
| `refactor` | Code refactoring | `refactor(backtester): extract strategy logic` |
| `perf` | Performance | `perf(feature_engine): vectorize calculations` |
| `test` | Test updates | `test(backtester): add strategy validation tests` |
| `ci` | CI/CD changes | `ci: add GitHub Actions workflow` |
| `chore` | Maintenance | `chore: update dependencies` |

### Scopes

Main components:
- `backtester` - backtester.py
- `feature_engine` - feature_engine.py
- `collector` - incremental_collector.py / daily_collector.py
- `query` - query_backtest_results.py
- `logger` - logger_config.py
- `repo` - Repository-wide changes
- `deps` - Dependency updates

### Subject Line Rules

- Use imperative mood: "add" not "added" or "adds"
- Don't capitalize first letter
- No period at end
- Max 50 characters
- Should complete: "If applied, this commit will **[subject]**"

✅ Good:
- `add RSI divergence strategy`
- `fix KeyError in feature calculation`
- `optimize database queries`

❌ Bad:
- `Added RSI divergence strategy` (past tense)
- `fix: KeyError in feature calculation` (capitalize)
- `Fix KeyError in feature calculation.` (period)

### Body (Optional but Recommended)

- Explain **what** and **why**, not **how**
- Reference related issues: `Fixes #123`, `Closes #456`
- Separate from subject with blank line
- Wrap at 72 characters
- Use bullet points for multiple changes

Example:
```
feat(backtester): add momentum filter strategy

- Implements ROC (Rate of Change) based trend filtering
- Only takes signals when price above 50-day SMA
- Filters out choppy/sideways markets
- Backtested on 500 tickers with Sharpe ratio 1.973

Outperforms traditional RSI strategy on trending stocks.
Works well combined with mean reversion strategies.

Fixes #42
Closes #123
```

### Footer

- Closes/Fixes issues: `Closes #123`
- Breaking changes: `BREAKING CHANGE: description`
- Co-authored: `Co-authored-by: Name <email>`

Example:
```
Closes #100
BREAKING CHANGE: Changed strategy API return format
Co-authored-by: Jane Smith <jane@example.com>
```

## Repository File Structure

```
stock-trading-pipeline/
├── .git/                              # Git repository metadata
├── .github/
│   ├── ISSUE_TEMPLATE.md             # Issue report template
│   ├── PULL_REQUEST_TEMPLATE.md      # PR template
│   └── workflows/                     # CI/CD workflows (future)
├── .gitignore                         # Git ignore rules
├── .gitattributes                     # Line ending normalization
│
├── database/
│   ├── stock_data.duckdb             # ⚠️ NOT in git (ignore)
│   └── stock_features.parquet        # ⚠️ NOT in git (ignore)
│
├── logs/                              # ⚠️ NOT in git (ignore)
│   ├── pipeline_20260629_110000.log  # ⚠️ NOT in git
│   └── pipeline.log                  # ⚠️ NOT in git
│
├── backtester.py                      # Strategy backtesting
├── feature_engine.py                  # Feature generation
├── incremental_collector.py           # Data collection
├── daily_collector.py                 # Legacy data collector
├── query_backtest_results.py         # Result analysis
├── logger_config.py                   # Centralized logging
│
├── tickers.csv                        # S&P 500 symbols (in git)
├── requirements.txt                   # Python dependencies
│
├── README.md                          # Project overview
├── CHANGELOG.md                       # Version history
├── LICENSE                            # MIT License
├── CONTRIBUTING.md                    # Contribution guidelines
├── GIT_SETUP.md                       # This file
└── LOGGER_INTEGRATION_GUIDE.md       # Logging integration guide
```

## Common Git Commands

### Create Feature Branch
```bash
git checkout -b feature/strategy-name
git checkout -b bugfix/issue-description
git checkout -b docs/update-readme
```

### View Changes Before Commit
```bash
git status                    # See what changed
git diff                      # See exact changes
git diff --staged            # See staged changes
```

### Stage and Commit
```bash
# Stage specific files
git add backtester.py feature_engine.py

# Stage all changes
git add .

# Commit with message
git commit -m "feat(backtester): add new strategy"

# Commit with body (opens editor)
git commit                    # Opens $EDITOR
```

### Review Before Push
```bash
git log --oneline -5         # Last 5 commits
git log -p feature/branch    # Show diffs
git show HEAD                # Show latest commit
```

### Push and Create PR
```bash
git push origin feature/strategy-name
# Then create PR on GitHub interface
```

### Amend Last Commit (if unpushed)
```bash
# Fix commit message
git commit --amend -m "new message"

# Add forgotten files
git add forgotten_file.py
git commit --amend --no-edit

# Push (careful if already pushed!)
git push origin feature/branch -f
```

## Merge and Rebase Strategy

### Local Development
```bash
# Create feature branch from main
git checkout -b feature/xyz main

# Keep up to date with main
git fetch origin
git rebase origin/main
# or merge if you prefer: git merge origin/main

# Final commit before PR
git log main..HEAD          # See your commits
```

### Code Review & Merge
- PR requires 1 maintainer approval
- All checks must pass
- Merge using "Squash and merge" for cleaner history
- Or "Create a merge commit" to preserve branch history

## Branch Protection Rules (Future)

Recommended GitHub settings:
- Require pull request reviews before merging
- Require status checks to pass
- Require branches to be up to date
- Require code reviews from code owners
- Require signed commits (optional)

## Ignore Rules Explanation

### database/
```
database/stock_data.duckdb    # Large, auto-generated
database/stock_features.parquet # Large, auto-generated
```
Rationale: Binary files, 100MB+, regenerated by pipeline

### logs/
```
logs/
*.log
```
Rationale: Temporary files, session-specific, regenerated on each run

### Python Cache
```
__pycache__/
*.pyc
*.pyo
*.egg-info/
```
Rationale: Generated by Python interpreter, platform-specific

### Virtual Environment
```
venv/
env/
.venv
```
Rationale: Local to each developer, large, platform-specific

### IDE/Editor
```
.vscode/
.idea/
*.swp
*.swo
```
Rationale: Personal settings, should not be in shared repo

## Quick Reference Card

```bash
# Setup
git clone <repo>
cd stock-trading-pipeline
git checkout -b feature/xyz

# Work
# ... make changes ...
git add .
git commit -m "feat(scope): description"

# Review
git log -p
git diff origin/main

# Push
git push origin feature/xyz
# Create PR on GitHub

# Sync with main
git fetch origin
git rebase origin/main

# Finish
# Merge via GitHub PR interface
# Delete branch: git branch -d feature/xyz
```

## Troubleshooting

### "File too large" error
```bash
# Check file size
git ls-files -l
# Remove from history (if not yet pushed)
git rm --cached file.duckdb
git commit --amend
```

### "Accidentally committed database file"
```bash
# If not pushed yet
git rm --cached database/stock_data.duckdb
echo "database/stock_data.duckdb" >> .gitignore
git add .gitignore
git commit --amend

# If already pushed (requires force push)
git rm --cached database/stock_data.duckdb
git commit --amend
git push -f  # Careful!
```

### "Need to undo last commit"
```bash
# Keep changes
git reset --soft HEAD~1

# Discard changes
git reset --hard HEAD~1

# Keep files but unstage
git reset HEAD~1
```

## Additional Resources

- [Git Documentation](https://git-scm.com/doc)
- [GitHub Guides](https://guides.github.com/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [Keep a Changelog](https://keepachangelog.com/)

---

**Last Updated:** 2026-06-29  
**Version:** 1.0.0
