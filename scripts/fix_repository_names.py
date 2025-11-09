# -*- coding: utf-8 -*-
"""Fix repository names - change from rutvik106 to example-org organization."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.core.repository_db import RepositoryDB

# Repositories to fix: (old_name, branch, new_name)
repos_to_fix = [
    ('example-user/sample-admin', 'test', 'example-org/sample-admin', 'prod'),
    ('example-user/sample-chat', 'test', 'example-org/sample-chat', 'prod'),
    ('example-user/sample-backend', 'test', 'example-org/sample-backend', 'prod'),
    ('example-user/sample-web', 'testing', 'example-org/sample-web', 'master'),
]

db = RepositoryDB()

print('Fixing repository names and branches...\n')
print('=' * 80)

for old_repo, old_branch, new_repo, new_branch in repos_to_fix:
    print('\nProcessing: {}'.format(old_repo))
    print('  Old: {} (branch: {})'.format(old_repo, old_branch))
    print('  New: {} (branch: {})'.format(new_repo, new_branch))
    
    # Delete old entry
    deleted = db.delete_repository(old_repo, old_branch)
    if deleted:
        print('  [OK] Deleted old entry')
    else:
        print('  [WARNING] Old entry not found (maybe already deleted)')
    
    # Add new entry
    added = db.add_repository(new_repo, new_branch, enabled=True, ai_enabled=True)
    if added:
        print('  [OK] Added new entry')
    else:
        print('  [WARNING] New entry already exists')

print('\n' + '=' * 80)
print('\nFix complete! Verifying...\n')

# List all repositories
all_repos = db.get_repositories(enabled_only=False)
print('Total repositories in database: {}\n'.format(len(all_repos)))

print('Example repositories:')
for repo in all_repos:
    if 'sample' in repo['repo'].lower():
        print('  {} (branch: {})'.format(repo['repo'], repo['branch']))

print('\nRun the following to verify:')
print('  python3 manage_repos.py list')
