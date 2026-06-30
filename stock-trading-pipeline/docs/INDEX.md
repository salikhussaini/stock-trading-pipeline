# Documentation Index

All documentation files for the stock trading pipeline project.

## Quick Navigation

### Getting Started
- **[QUICKSTART.md](QUICKSTART.md)** - Get up and running in 5 minutes
- **[../README.md](../README.md)** - Project overview and architecture

### Setup & Usage
- **[LICENSE](LICENSE)** - MIT License and disclaimer
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - How to contribute code
- **[GIT_SETUP.md](GIT_SETUP.md)** - Git workflow and best practices

### Reference
- **[CHANGELOG.md](CHANGELOG.md)** - Version history and features
- **[LOGGER_INTEGRATION_GUIDE.md](LOGGER_INTEGRATION_GUIDE.md)** - Logging system details
- **[REPOSITORY_CHECKLIST.md](REPOSITORY_CHECKLIST.md)** - Pre-commit verification
- **[GIT_PREPARATION_SUMMARY.md](GIT_PREPARATION_SUMMARY.md)** - Git setup summary

---

## Project Structure

```
stock-trading-pipeline/
├── README.md                    (root, main overview)
├── .gitignore                   (root, git configuration)
├── .gitattributes               (root, line ending rules)
├── .github/                     (root, GitHub templates)
│   ├── ISSUE_TEMPLATE.md
│   └── PULL_REQUEST_TEMPLATE.md
│
├── docs/                        (all documentation)
│   ├── INDEX.md                 (this file)
│   ├── QUICKSTART.md            (5-minute setup)
│   ├── CHANGELOG.md             (version history)
│   ├── CONTRIBUTING.md          (contribution guide)
│   ├── LICENSE                  (MIT license)
│   ├── GIT_SETUP.md             (git workflow)
│   ├── LOGGER_INTEGRATION_GUIDE.md
│   ├── REPOSITORY_CHECKLIST.md
│   └── GIT_PREPARATION_SUMMARY.md
│
├── backtester.py                (core scripts)
├── feature_engine.py
├── incremental_collector.py
├── logger_config.py
├── query_backtest_results.py
│
├── requirements.txt
├── tickers.csv
└── database/                    (git-ignored, auto-created)
    ├── stock_data.duckdb
    └── stock_features.parquet
```

## File Descriptions

### Essential for New Users
1. Start with **[../README.md](../README.md)** - Understand what the project does
2. Read **[QUICKSTART.md](QUICKSTART.md)** - Set up and run locally
3. Check **[CONTRIBUTING.md](CONTRIBUTING.md)** - If you want to contribute

### For Developers
- **[GIT_SETUP.md](GIT_SETUP.md)** - Git workflow, branch naming, commit format
- **[LOGGER_INTEGRATION_GUIDE.md](LOGGER_INTEGRATION_GUIDE.md)** - Using the logging system
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Code style, testing, PR process

### Reference & Tracking
- **[CHANGELOG.md](CHANGELOG.md)** - What's new, known issues, roadmap
- **[REPOSITORY_CHECKLIST.md](REPOSITORY_CHECKLIST.md)** - Pre-commit checklist
- **[GIT_PREPARATION_SUMMARY.md](GIT_PREPARATION_SUMMARY.md)** - Git initialization summary
- **[LICENSE](LICENSE)** - Legal terms and disclaimer

---

## Quick Reference

**Setup:**
```bash
pip install -r requirements.txt
python incremental_collector.py --test
```

**Run Pipeline:**
```bash
python incremental_collector.py    # Download data
python feature_engine.py            # Compute features
python backtester.py                # Evaluate strategies
```

**Check Results:**
```bash
python query_backtest_results.py
```

---

**For more information, start with [QUICKSTART.md](QUICKSTART.md) or [../README.md](../README.md)**
