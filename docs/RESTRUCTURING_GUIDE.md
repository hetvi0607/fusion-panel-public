# Project Restructuring Guide

## Overview

The project has been reorganized into a cleaner, more maintainable structure. This document outlines the changes and how to adapt.

## What Changed?

### Directory Structure

**Before:**
```
task-sheet-automation/
├── *.py (all Python files in root)
├── *.csv (reports in root)
├── *.md (docs in root)
├── repositories.db (in root)
└── commit_tracker.log (in root)
```

**After:**
```
task-sheet-automation/
├── main.py (entry point only)
├── src/
│   ├── core/ (business logic)
│   └── integrations/ (external services)
├── scripts/ (utility scripts)
├── tests/ (test files)
├── docs/ (documentation)
├── data/ (database & reports)
└── logs/ (log files)
```

### File Relocations

| Old Location | New Location | Type |
|-------------|--------------|------|
| `config.py` | `src/core/config.py` | Core |
| `github_client.py` | `src/core/github_client.py` | Core |
| `csv_reporter.py` | `src/core/csv_reporter.py` | Core |
| `repository_db.py` | `src/core/repository_db.py` | Core |
| `ai_analyzer.py` | `src/core/ai/analyzer.py` | AI |
| `ai_analyzer_simple.py` | `src/core/ai/analyzer_simple.py` | AI |
| `ai_csv_summarizer.py` | `src/core/ai/csv_summarizer.py` | AI |
| `email_sender.py` | `src/integrations/email_sender.py` | Integration |
| `whatsapp_sender.py` | `src/integrations/whatsapp_sender.py` | Integration |
| `google_sheets.py` | `src/integrations/google_sheets.py` | Integration |
| `manage_repos.py` | `scripts/manage_repos.py` | Script |
| `migrate_to_db.py` | `scripts/migrate_to_db.py` | Script |
| `verify_all_repos.py` | `scripts/verify_all_repos.py` | Script |
| `verify_repo_access.py` | `scripts/verify_repo_access.py` | Script |
| `check_branches.py` | `scripts/check_branches.py` | Script |
| `fix_repository_names.py` | `scripts/fix_repository_names.py` | Script |
| `find_example_repos.py` | `scripts/find_example_repos.py` | Script |
| `list_accessible_repos.py` | `scripts/list_accessible_repos.py` | Script |
| `test_commit_fetch.py` | `tests/test_commit_fetch.py` | Test |
| `PROJECT_README.md` | `docs/PROJECT_README.md` | Doc |
| `WHATSAPP_SETUP.md` | `docs/WHATSAPP_SETUP.md` | Doc |
| `DATABASE_MIGRATION.md` | `docs/DATABASE_MIGRATION.md` | Doc |
| `MIGRATION_COMPLETE.md` | `docs/MIGRATION_COMPLETE.md` | Doc |
| `readme.md` | `docs/REQUIREMENTS.md` | Doc |
| `repositories.db` | `data/repositories.db` | Data |
| `*.csv` | `data/reports/*.csv` | Data |
| `commit_tracker.log` | `logs/commit_tracker.log` | Log |

### Import Changes

All imports have been updated to reflect the new structure:

**Old:**
```python
from config import app_config
from github_client import GitHubClient
from csv_reporter import CSVReporter
```

**New:**
```python
from src.core.config import app_config
from src.core.github_client import GitHubClient
from src.core.csv_reporter import CSVReporter
```

### Path Changes

Default paths have been updated:

- **Database**: `data/repositories.db` (was `repositories.db`)
- **Reports**: `data/reports/` (was root directory)
- **Logs**: `logs/commit_tracker.log` (was `commit_tracker.log`)

## Python Version Requirement

**Important**: This project requires Python 3.8+. Always use `python3`:

```bash
# ✓ Correct
python3 main.py

# ✗ Incorrect (Python 2.7 doesn't support f-strings)
python main.py
```

## Migration Steps

If you have existing code that imports these modules:

### 1. Update Your Imports

Replace all old-style imports with new package-based imports:

```python
# Old
from config import app_config

# New
from src.core.config import app_config
```

### 2. Update File Paths

If you reference files directly:

```python
# Old
db_path = "repositories.db"

# New
db_path = "data/repositories.db"
```

### 3. Use Python 3

Ensure all commands use `python3`:

```bash
python3 main.py
python3 scripts/manage_repos.py list
```

## Benefits

### 1. **Better Organization**
- Clear separation between core logic, integrations, and utilities
- Easy to locate files by purpose
- Reduced root directory clutter

### 2. **Improved Maintainability**
- Logical grouping makes code easier to understand
- Clear dependencies between modules
- Better support for future growth

### 3. **Enhanced Scalability**
- Easy to add new integrations or core modules
- Clear structure for adding tests
- Organized documentation

### 4. **Professional Structure**
- Follows Python best practices
- Standard project layout
- Better for collaboration

## Common Issues & Solutions

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'config'`

**Solution**: Update imports to use new paths:
```python
from src.core.config import app_config
```

### Database Not Found

**Problem**: `sqlite3.OperationalError: unable to open database file`

**Solution**: Database moved to `data/repositories.db`. The code automatically uses the new path, but if you're accessing it directly:
```python
db_path = "data/repositories.db"
```

### Python Version Error

**Problem**: `SyntaxError: invalid syntax` on f-strings

**Solution**: Use Python 3:
```bash
python3 main.py  # Instead of: python main.py
```

### Reports Not Found

**Problem**: Generated CSV reports not in expected location

**Solution**: Reports are now in `data/reports/` directory. The CSVReporter automatically saves there.

## Testing the New Structure

Verify everything works:

```bash
# Test configuration loading
python3 -c "from src.core.config import app_config; print('✓ Config OK')"

# Test repository management
python3 scripts/manage_repos.py list

# Run a test report (with AI disabled for speed)
python3 main.py --no-ai --verbose
```

## Rollback (If Needed)

If you need to revert to the old structure (not recommended):

```bash
# Move files back to root (example)
mv src/core/*.py .
mv src/core/ai/*.py .
mv src/integrations/*.py .
mv scripts/*.py .
mv data/repositories.db .
# etc...
```

However, **this is not recommended** as the new structure provides significant benefits.

## Questions?

If you encounter issues with the new structure:

1. Check this guide for common solutions
2. Verify you're using Python 3
3. Ensure imports use the new `src.core.*` or `src.integrations.*` paths
4. Check that paths point to `data/` and `logs/` directories

## Summary

The restructuring provides:
- ✅ Clear, logical organization
- ✅ Scalable architecture
- ✅ Professional project layout
- ✅ Better maintainability
- ✅ Easier collaboration
- ✅ Cleaner root directory

All functionality remains the same - only the organization has improved!
