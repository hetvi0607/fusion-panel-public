# -*- coding: utf-8 -*-
"""
Migration script to move repository configurations from .env to SQLite database.

Usage:
    python migrate_to_db.py [--clear] [--dry-run]
    
Options:
    --clear: Clear existing database before importing
    --dry-run: Show what would be imported without actually importing
"""
import os
import argparse
from dotenv import load_dotenv
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.core.repository_db import RepositoryDB

# Load environment variables
load_dotenv()


def parse_repositories_from_env():
    """
    Parse repository configurations from environment variables.
    
    Returns:
        List of repository dictionaries
    """
    repositories = []
    
    # Parse repository-branch mappings (prioritize this)
    if os.getenv("GITHUB_REPOS_BRANCHES", ""):
        for repo_branch in os.getenv("GITHUB_REPOS_BRANCHES", "").split(","):
            if ":" in repo_branch:
                repo, branch = repo_branch.split(":", 1)
                repo = repo.strip()
                branch = branch.strip()
                if repo:
                    repositories.append({
                        "repo": repo,
                        "branch": branch,
                        "enabled": True,
                        "ai_enabled": True
                    })
    else:
        # Fallback to standard repository list without branches
        for repo in os.getenv("GITHUB_REPOS", "").split(","):
            if repo.strip():
                repositories.append({
                    "repo": repo.strip(),
                    "branch": "main",  # Default branch if not specified
                    "enabled": True,
                    "ai_enabled": True
                })
    
    return repositories


def main():
    """Main migration function."""
    parser = argparse.ArgumentParser(description='Migrate repository configs from .env to database')
    parser.add_argument('--clear', action='store_true', help='Clear existing database before importing')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be imported without importing')
    args = parser.parse_args()
    
    # Parse repositories from environment
    repositories = parse_repositories_from_env()
    
    if not repositories:
        print("[ERROR] No repositories found in environment variables.")
        print("        Make sure GITHUB_REPOS or GITHUB_REPOS_BRANCHES is set in .env file")
        return 1
    
    print("=" * 60)
    print("Repository Migration Tool")
    print("=" * 60)
    print("\nFound {} repository configurations in .env:\n".format(len(repositories)))
    
    for i, repo in enumerate(repositories, 1):
        print("{}. {} (branch: {})".format(i, repo['repo'], repo['branch']))
    
    if args.dry_run:
        print("\n[OK] Dry run complete. No changes made.")
        return 0
    
    # Initialize database
    db = RepositoryDB()
    
    if args.clear:
        print("\n[WARNING] Clearing existing database...")
        deleted = db.clear_all()
        print("           Cleared {} existing repositories".format(deleted))
    
    # Import repositories
    print("\n[INFO] Importing repositories to database...")
    added, skipped = db.bulk_import(repositories)
    
    print("\n" + "=" * 60)
    print("Migration Complete!")
    print("=" * 60)
    print("[OK] Added: {} repositories".format(added))
    if skipped > 0:
        print("[WARNING] Skipped: {} repositories (already existed)".format(skipped))
    
    print("\n[INFO] Next steps:")
    print("1. Verify the database by running: python manage_repos.py list")
    print("2. Comment out or remove GITHUB_REPOS and GITHUB_REPOS_BRANCHES from .env")
    print("3. Test your application to ensure it works with the database")
    
    return 0


if __name__ == "__main__":
    exit(main())
