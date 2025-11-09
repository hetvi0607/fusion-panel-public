# GitHub Commit Tracking Automation

An automated system for collecting, analyzing, and reporting GitHub commits across multiple repositories with AI-powered analysis.

## Features

✨ **Automated Data Collection** - Fetch commits from multiple GitHub repositories  
🤖 **AI-Powered Analysis** - Claude AI generates human-readable summaries  
📊 **Report Generation** - Creates detailed CSV reports and AI summaries  
💬 **WhatsApp Integration** - Send reports to WhatsApp Business groups  
📧 **Email Notifications** - Automated email delivery (optional)  
🗄️ **Repository Management** - Database-backed repository configuration

## Quick Start

### Prerequisites

- Python 3.8+
- GitHub Personal Access Token
- Claude API key (Anthropic)

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd task-sheet-automation

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your credentials
```

### Basic Usage

**Note**: This project requires Python 3.8+. Use `python3` command:

```bash
# Generate report for current month
python3 main.py

# Specify custom month
python3 main.py --month 2024-11

# Custom date range
python3 main.py --start-date 2024-11-01 --end-date 2024-11-30

# Disable AI analysis
python3 main.py --no-ai

# Verbose output
python3 main.py --verbose
```

## Project Structure

```
task-sheet-automation/
│
├── main.py                      # Entry point - orchestrates the workflow
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment variables template
├── .gitignore                   # Git ignore rules
│
├── src/                         # Source code
│   ├── core/                    # Core business logic
│   │   ├── config.py           # Configuration management
│   │   ├── github_client.py    # GitHub API integration
│   │   ├── csv_reporter.py     # CSV report generation
│   │   ├── repository_db.py    # Repository database management
│   │   └── ai/                 # AI analysis modules
│   │       ├── analyzer.py     # Detailed commit analysis
│   │       ├── analyzer_simple.py  # Simplified analyzer
│   │       └── csv_summarizer.py   # CSV-based summarization
│   │
│   └── integrations/            # External service integrations
│       ├── email_sender.py     # Email notifications
│       ├── whatsapp_sender.py  # WhatsApp Business API
│       └── google_sheets.py    # Google Sheets integration
│
├── scripts/                     # Utility and maintenance scripts
│   ├── manage_repos.py         # Manage repository configurations
│   ├── migrate_to_db.py        # Migrate repos from env to DB
│   ├── verify_all_repos.py     # Verify repository access
│   ├── verify_repo_access.py   # Verify individual repo access
│   ├── check_branches.py       # Check branch information
│   ├── fix_repository_names.py # Fix repository name issues
│   ├── find_example_repos.py     # Find specific repositories
│   └── list_accessible_repos.py # List accessible repositories
│
├── tests/                       # Test files
│   └── test_commit_fetch.py    # Test commit fetching
│
├── docs/                        # Documentation
│   ├── PROJECT_README.md       # Detailed project documentation
│   ├── WHATSAPP_SETUP.md       # WhatsApp setup guide
│   ├── DATABASE_MIGRATION.md   # Database migration guide
│   ├── MIGRATION_COMPLETE.md   # Migration completion notes
│   └── REQUIREMENTS.md         # Original requirements document
│
├── data/                        # Data storage
│   ├── repositories.db         # SQLite database for repositories
│   └── reports/                # Generated CSV reports
│
└── logs/                        # Log files
    └── commit_tracker.log      # Application logs
```

## Configuration

Configuration is managed through environment variables in the `.env` file:

### Essential Settings

```bash
# GitHub API
GITHUB_TOKEN=your_github_token_here

# Claude API
CLAUDE_API_KEY=your_claude_api_key
CLAUDE_MODEL=claude-3-5-sonnet-20241022

# AI Analysis
AI_ENABLED=True
AI_BUDGET_LIMIT=50.0  # Monthly budget in USD
```

### Optional Settings

```bash
# WhatsApp Business API
WHATSAPP_ENABLED=False
WHATSAPP_ACCESS_TOKEN=your_access_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_id
WHATSAPP_GROUP_IDS=group_id_1,group_id_2

# Email Notifications
EMAIL_SENDER=sender@example.com
EMAIL_PASSWORD=your_app_password
EMAIL_RECIPIENT=recipient@example.com

# Performance
PARALLEL_PROCESSING=True
MAX_WORKERS=5
BATCH_SIZE=100

# Logging
LOG_LEVEL=INFO
```

See `.env.example` for all available options.

## Repository Management

Repositories are managed in a SQLite database for better organization:

### List Repositories

```bash
python3 scripts/manage_repos.py list
python3 scripts/manage_repos.py list --all  # Include disabled repos
```

### Add Repository

```bash
python3 scripts/manage_repos.py add owner/repo-name branch-name
```

### Update Repository

```bash
# Disable a repository
python3 scripts/manage_repos.py update owner/repo-name branch-name --disable

# Enable a repository
python3 scripts/manage_repos.py update owner/repo-name branch-name --enable

# Disable AI for a specific repo
python3 scripts/manage_repos.py update owner/repo-name branch-name --disable-ai
```

### Delete Repository

```bash
python3 scripts/manage_repos.py delete owner/repo-name branch-name
```

### Verify Access

```bash
# Verify all repositories
python3 scripts/verify_all_repos.py

# Verify specific repository
python3 scripts/verify_repo_access.py owner/repo-name
```

## AI Analysis

The system uses Claude AI to analyze commit diffs and generate:

- **Human-readable summaries** - Plain language explanations of technical changes
- **Change categorization** - Automatic classification (Feature, Bug Fix, Refactor, etc.)
- **Impact assessment** - Understanding the scope of changes

### Change Categories

- Feature - New functionality
- Bug Fix - Fixing issues
- Refactor - Code restructuring
- Performance - Optimizations
- Security - Security improvements
- Documentation - Doc updates
- Configuration - Config changes
- Dependencies - Package updates
- Database - Schema changes
- UI/UX - Interface improvements
- Test - Testing changes
- Build/Deploy - Build system changes
- Other - Miscellaneous

## Output

The system generates:

1. **Main CSV Report** - All commits from all repositories
2. **Individual Repository Reports** - Separate CSV per repository/branch
3. **AI Summary Report** - Point-wise summaries and overall analysis (if AI enabled)

Reports are saved in `data/reports/` directory.

## Troubleshooting

### Common Issues

**Rate Limiting**
```bash
# Reduce parallel workers or increase delays
# In .env: MAX_WORKERS=3
```

**Authentication Failures**
```bash
# Verify API keys in .env file
# Check token permissions on GitHub/Claude
```

**Database Issues**
```bash
# Check database location: data/repositories.db
# Verify with: python scripts/manage_repos.py list
```

**Import Errors**
```bash
# Ensure you're running from project root
cd /path/to/task-sheet-automation
python main.py
```

### Logs

Application logs are stored in `logs/commit_tracker.log`. Use `--verbose` flag to see logs in console.

## Development

### Adding New Features

1. Core logic goes in `src/core/`
2. External integrations go in `src/integrations/`
3. Utility scripts go in `scripts/`
4. Tests go in `tests/`

### Code Style

- Follow PEP 8 guidelines
- Keep files under 300 lines
- Add docstrings to functions and classes
- Update imports when moving files

## Documentation

- **[docs/PROJECT_README.md](docs/PROJECT_README.md)** - Comprehensive project documentation
- **[docs/WHATSAPP_SETUP.md](docs/WHATSAPP_SETUP.md)** - WhatsApp integration setup
- **[docs/DATABASE_MIGRATION.md](docs/DATABASE_MIGRATION.md)** - Database migration guide
- **[docs/REQUIREMENTS.md](docs/REQUIREMENTS.md)** - Original requirements document

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

---

**Note**: This project was recently restructured for better organization. If you encounter any issues with imports or paths, please open an issue.
