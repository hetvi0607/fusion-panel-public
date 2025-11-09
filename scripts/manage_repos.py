# -*- coding: utf-8 -*-
"""
Repository management utility for adding, updating, and listing repositories.

Usage:
    python manage_repos.py list
    python manage_repos.py add <repo_name> <branch> [--disabled] [--no-ai]
    python manage_repos.py update <repo_name> <branch> [--enable|--disable] [--ai|--no-ai]
    python manage_repos.py delete <repo_name> <branch>
    
Examples:
    python manage_repos.py list
    python manage_repos.py add example-org/sample-api develop
    python manage_repos.py update example-org/sample-api develop --disable
    python manage_repos.py delete example-org/sample-api develop
"""
import argparse
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.core.repository_db import RepositoryDB
from tabulate import tabulate


def list_repositories(db: RepositoryDB, all_repos: bool = False):
    """List all repositories in the database."""
    repositories = db.get_repositories(enabled_only=not all_repos)
    
    if not repositories:
        print("No repositories found in the database.")
        return
    
    # Prepare table data
    table_data = []
    for repo in repositories:
        status = "[Y]" if repo['enabled'] else "[N]"
        ai_status = "[Y]" if repo['ai_enabled'] else "[N]"
        table_data.append([
            status,
            repo['repo'],
            repo['branch'],
            ai_status
        ])
    
    headers = ["Enabled", "Repository", "Branch", "AI"]
    print("\nFound {} repositories:\n".format(len(repositories)))
    print(tabulate(table_data, headers=headers, tablefmt="grid"))


def add_repository(db: RepositoryDB, repo_name: str, branch: str, 
                  enabled: bool = True, ai_enabled: bool = True):
    """Add a new repository to the database."""
    success = db.add_repository(repo_name, branch, enabled, ai_enabled)
    
    if success:
        print("[OK] Added: {} (branch: {})".format(repo_name, branch))
    else:
        print("[ERROR] Failed: Repository already exists: {} (branch: {})".format(repo_name, branch))
        return 1
    
    return 0


def update_repository(db: RepositoryDB, repo_name: str, branch: str,
                     enabled: bool = None, ai_enabled: bool = None):
    """Update a repository in the database."""
    if enabled is None and ai_enabled is None:
        print("[ERROR] Nothing to update. Use --enable/--disable or --ai/--no-ai")
        return 1
    
    success = db.update_repository(repo_name, branch, enabled, ai_enabled)
    
    if success:
        print("[OK] Updated: {} (branch: {})".format(repo_name, branch))
    else:
        print("[ERROR] Failed: Repository not found: {} (branch: {})".format(repo_name, branch))
        return 1
    
    return 0


def delete_repository(db: RepositoryDB, repo_name: str, branch: str):
    """Delete a repository from the database."""
    # Confirm deletion
    response = input("Are you sure you want to delete {} (branch: {})? [y/N]: ".format(repo_name, branch))
    if response.lower() != 'y':
        print("Cancelled.")
        return 0
    
    success = db.delete_repository(repo_name, branch)
    
    if success:
        print("[OK] Deleted: {} (branch: {})".format(repo_name, branch))
    else:
        print("[ERROR] Failed: Repository not found: {} (branch: {})".format(repo_name, branch))
        return 1
    
    return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Manage repository configurations',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List all repositories')
    list_parser.add_argument('--all', action='store_true', help='Show disabled repositories too')
    
    # Add command
    add_parser = subparsers.add_parser('add', help='Add a new repository')
    add_parser.add_argument('repo_name', help='Repository name (e.g., owner/repo)')
    add_parser.add_argument('branch', help='Branch name')
    add_parser.add_argument('--disabled', action='store_true', help='Add as disabled')
    add_parser.add_argument('--no-ai', action='store_true', help='Disable AI analysis')
    
    # Update command
    update_parser = subparsers.add_parser('update', help='Update a repository')
    update_parser.add_argument('repo_name', help='Repository name (e.g., owner/repo)')
    update_parser.add_argument('branch', help='Branch name')
    update_group = update_parser.add_mutually_exclusive_group()
    update_group.add_argument('--enable', action='store_true', help='Enable repository')
    update_group.add_argument('--disable', action='store_true', help='Disable repository')
    ai_group = update_parser.add_mutually_exclusive_group()
    ai_group.add_argument('--ai', action='store_true', help='Enable AI analysis')
    ai_group.add_argument('--no-ai', action='store_true', help='Disable AI analysis')
    
    # Delete command
    delete_parser = subparsers.add_parser('delete', help='Delete a repository')
    delete_parser.add_argument('repo_name', help='Repository name (e.g., owner/repo)')
    delete_parser.add_argument('branch', help='Branch name')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Initialize database
    db = RepositoryDB()
    
    # Execute command
    if args.command == 'list':
        list_repositories(db, all_repos=args.all)
        return 0
    
    elif args.command == 'add':
        return add_repository(
            db, 
            args.repo_name, 
            args.branch,
            enabled=not args.disabled,
            ai_enabled=not args.no_ai
        )
    
    elif args.command == 'update':
        enabled = None
        if args.enable:
            enabled = True
        elif args.disable:
            enabled = False
        
        ai_enabled = None
        if args.ai:
            ai_enabled = True
        elif args.no_ai:
            ai_enabled = False
        
        return update_repository(db, args.repo_name, args.branch, enabled, ai_enabled)
    
    elif args.command == 'delete':
        return delete_repository(db, args.repo_name, args.branch)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
