# Repository Configuration Database Migration

## Overview

Repository configurations (`GITHUB_REPOS` and `GITHUB_REPOS_BRANCHES`) have been migrated from environment variables to a SQLite database for better management and flexibility.

## Why This Change?

- **Easier Management**: Add/update/delete repositories without editing `.env` file
- **Dynamic Configuration**: Enable/disable repositories without restarting
- **Better Organization**: Support for per-repository settings (AI enabled, etc.)
- **Version Control**: Both the runtime database and `.env` remain local and ignored

## Migration Steps

### 1. Install Dependencies

First, ensure you have the latest dependencies:

```bash
pip install -r requirements.txt
```

### 2. Run the Migration Script

The migration script will read your current `.env` file and populate the database:

```bash
# Dry run (see what would be migrated without actually doing it)
python migrate_to_db.py --dry-run

# Actual migration
python migrate_to_db.py

# Clear existing database and migrate fresh (use with caution!)
python migrate_to_db.py --clear
```

Expected output:
```
============================================================
Repository Migration Tool
============================================================

Found 6 repository configurations in .env:

1. example-org/sample-api (branch: develop)
2. example-org/sample-android (branch: jetpack-compose)
3. example-org/sample-android (branch: code-cleanup)
4. example-org/sample-web (branch: test)
5. example-org/sample-admin (branch: test)
6. example-org/example-website (branch: master)

📥 Importing repositories to database...

============================================================
Migration Complete!
============================================================
✓ Added: 6 repositories
```

### 3. Verify the Migration

List all repositories in the database:

```bash
python manage_repos.py list
```

Expected output:
```
Found 6 repositories:

╒═════════╤══════════════════════════════════╤═══════════════════╤═══════╕
│ Enabled │ Repository                       │ Branch            │ AI    │
╞═════════╪══════════════════════════════════╪═══════════════════╪═══════╡
│ ✓       │ example-org/sample-api             │ develop           │ ✓     │
├─────────┼──────────────────────────────────┼───────────────────┼───────┤
│ ✓       │ example-org/sample-android          │ jetpack-compose   │ ✓     │
├─────────┼──────────────────────────────────┼───────────────────┼───────┤
│ ✓       │ example-org/sample-android          │ code-cleanup      │ ✓     │
├─────────┼──────────────────────────────────┼───────────────────┼───────┤
│ ✓       │ example-org/sample-web          │ test              │ ✓     │
├─────────┼──────────────────────────────────┼───────────────────┼───────┤
│ ✓       │ example-org/sample-admin     │ test              │ ✓     │
├─────────┼──────────────────────────────────┼───────────────────┼───────┤
│ ✓       │ example-org/example-website    │ master            │ ✓     │
╘═════════╧══════════════════════════════════╧═══════════════════╧═══════╛
```

### 4. Test Your Application

Run your main application to ensure it works with the database:

```bash
python main.py --verbose
```

The application will automatically load repositories from the database.

### 5. Clean Up .env File (Optional)

Once you've verified everything works, you can remove the commented repository lines from `.env`:

1. Open `.env`
2. Remove lines 13-15 (the old GITHUB_REPOS and GITHUB_REPOS_BRANCHES)
3. Keep line 18 for now as a backup

## Managing Repositories

### List All Repositories

```bash
# Show enabled repositories only
python manage_repos.py list

# Show all repositories (including disabled)
python manage_repos.py list --all
```

### Add a New Repository

```bash
# Add repository with default settings (enabled, AI enabled)
python manage_repos.py add example-org/new-repo main

# Add repository but disable AI analysis
python manage_repos.py add example-org/new-repo develop --no-ai

# Add repository as disabled
python manage_repos.py add example-org/new-repo feature-branch --disabled
```

### Update a Repository

```bash
# Disable a repository
python manage_repos.py update example-org/sample-api develop --disable

# Enable a repository
python manage_repos.py update example-org/sample-api develop --enable

# Disable AI analysis for a specific repository
python manage_repos.py update example-org/sample-api develop --no-ai

# Enable AI analysis
python manage_repos.py update example-org/sample-api develop --ai
```

### Delete a Repository

```bash
python manage_repos.py delete example-org/old-repo main
```

You'll be prompted to confirm the deletion.

## Database File

The database file is stored as `repositories.db` in your project root.

**Important**: 
- Add `repositories.db` to your `.gitignore` if you don't want to commit it
- Keep databases and backups private; never commit them.
- The database file is portable and can be copied between environments

## Fallback Behavior

If the database is empty or cannot be loaded, the system will automatically fall back to reading from environment variables (`GITHUB_REPOS` and `GITHUB_REPOS_BRANCHES`).

This ensures backward compatibility and allows for gradual migration.

## Troubleshooting

### "No repositories found"

If you see this error after migration:

1. Check if `repositories.db` exists in your project directory
2. Run `python manage_repos.py list` to verify the database
3. If empty, run the migration again: `python migrate_to_db.py`

### "Error loading repositories from database"

Check the log file (`commit_tracker.log`) for detailed error messages. Common issues:

- Database file permissions
- Corrupted database file (delete and re-migrate)
- Missing dependencies (run `pip install -r requirements.txt`)

### Migration Doesn't Find Repositories

Ensure your `.env` file still has `GITHUB_REPOS_BRANCHES` or `GITHUB_REPOS` defined. The migration script reads from these variables.

## Database Schema

For reference, here's the database schema:

```sql
CREATE TABLE repositories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_name TEXT NOT NULL,
    branch TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    ai_enabled INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(repo_name, branch)
);
```

## Benefits of Database Configuration

1. **No Code Restarts**: Enable/disable repositories without restarting your application
2. **Audit Trail**: Track when repositories were added/modified (created_at, updated_at)
3. **Flexible Filtering**: Easily query repositories by various criteria
4. **Scalability**: Better performance with many repositories
5. **Repository-specific Settings**: Configure AI, notifications, etc. per repository
6. **Easy Backup**: Single file to backup/restore all configurations
