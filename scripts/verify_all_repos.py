# -*- coding: utf-8 -*-
"""Verify all repositories in database are accessible."""
import requests
import os
from dotenv import load_dotenv
import time
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.core.repository_db import RepositoryDB

load_dotenv()
token = os.getenv('GITHUB_TOKEN')

headers = {
    'Authorization': 'token {}'.format(token),
    'Accept': 'application/vnd.github.v3+json'
}

# Get all repos from database
db = RepositoryDB()
repos = db.get_repositories(enabled_only=True)

print('Verifying all {} repositories from database...\n'.format(len(repos)))
print('=' * 80)

accessible = 0
not_accessible = 0
branch_issues = 0

for repo in repos:
    repo_name = repo['repo']
    expected_branch = repo['branch']
    
    print('\n{} (branch: {})'.format(repo_name, expected_branch))
    
    # Check repo access
    repo_url = 'https://api.github.com/repos/{}'.format(repo_name)
    time.sleep(0.3)  # Rate limiting
    
    try:
        repo_response = requests.get(repo_url, headers=headers)
        
        if repo_response.status_code == 200:
            repo_data = repo_response.json()
            default_branch = repo_data.get('default_branch')
            
            # Check branch exists
            branches_url = 'https://api.github.com/repos/{}/branches'.format(repo_name)
            time.sleep(0.3)
            branches_response = requests.get(branches_url, headers=headers)
            
            if branches_response.status_code == 200:
                branches = branches_response.json()
                branch_names = [b['name'] for b in branches]
                
                if expected_branch in branch_names:
                    print('  [OK] Repository accessible, branch exists')
                    accessible += 1
                else:
                    print('  [WARNING] Repository accessible but branch "{}" NOT FOUND'.format(expected_branch))
                    print('            Available branches: {}'.format(', '.join(branch_names[:5])))
                    print('            Default branch: {}'.format(default_branch))
                    branch_issues += 1
            else:
                print('  [WARNING] Repository accessible but could not fetch branches')
                accessible += 1
        else:
            print('  [ERROR] Repository NOT accessible (HTTP {})'.format(repo_response.status_code))
            not_accessible += 1
            
    except Exception as e:
        print('  [ERROR] Exception: {}'.format(str(e)))
        not_accessible += 1

print('\n' + '=' * 80)
print('\nSummary:')
print('  Total repositories: {}'.format(len(repos)))
print('  Accessible: {} [OK]'.format(accessible))
print('  Branch issues: {} [WARNING]'.format(branch_issues))
print('  Not accessible: {} [ERROR]'.format(not_accessible))

if not_accessible == 0 and branch_issues == 0:
    print('\n[SUCCESS] All repositories are accessible with correct branches!')
    print('You should now get CSVs for all {} repositories.'.format(len(repos)))
elif branch_issues > 0:
    print('\n[ACTION NEEDED] Some branches are incorrect.')
    print('Use: python3 manage_repos.py update <repo> <old-branch> --enable')
    print('Then: python3 manage_repos.py delete <repo> <old-branch>')
    print('And: python3 manage_repos.py add <repo> <correct-branch>')
else:
    print('\n[ACTION NEEDED] Some repositories are not accessible.')
    print('Use: python3 manage_repos.py delete <repo> <branch> to remove them')
