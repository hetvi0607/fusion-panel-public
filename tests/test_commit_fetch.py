# -*- coding: utf-8 -*-
"""Test if we can actually fetch commits from the configured branches."""
import requests
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()
token = os.getenv('GITHUB_TOKEN')

headers = {
    'Authorization': 'token {}'.format(token),
    'Accept': 'application/vnd.github.v3+json'
}

# Test the 3 problematic repos
test_repos = [
    ('example-org/sample-chat', 'prod'),
    ('example-org/sample-backend', 'prod'),
    ('example-org/sample-web', 'master'),
]

# Use last month for testing
end_date = datetime.now()
start_date = end_date - timedelta(days=30)

print('Testing if we can fetch commits from these branches...\n')
print('=' * 80)

for repo_name, branch in test_repos:
    print('\n{} (branch: {})'.format(repo_name, branch))
    
    # Try to fetch commits
    commits_url = 'https://api.github.com/repos/{}/commits?sha={}&per_page=5'.format(
        repo_name, branch
    )
    
    commits_response = requests.get(commits_url, headers=headers)
    
    if commits_response.status_code == 200:
        commits = commits_response.json()
        print('  [OK] Can fetch commits! Found {} recent commits'.format(len(commits)))
        if commits:
            latest = commits[0]
            commit_date = latest['commit']['author']['date']
            print('      Latest commit: {} ({})'.format(
                latest['commit']['message'][:50],
                commit_date
            ))
        print('  [CONCLUSION] Branch is accessible - will work in your app!')
    elif commits_response.status_code == 404:
        print('  [ERROR] Branch not found (404)')
        print('  [ACTION] Need to use a different branch')
        
        # Suggest checking default branch
        repo_url = 'https://api.github.com/repos/{}'.format(repo_name)
        repo_response = requests.get(repo_url, headers=headers)
        if repo_response.status_code == 200:
            default_branch = repo_response.json().get('default_branch')
            print('  [SUGGESTION] Try using default branch: {}'.format(default_branch))
    else:
        print('  [ERROR] HTTP {} - {}'.format(
            commits_response.status_code,
            commits_response.json().get('message', 'Unknown error')
        ))

print('\n' + '=' * 80)
print('\nConclusion:')
print('If all branches show [OK], your app will work fine.')
print('If any show [ERROR], update the branch name using manage_repos.py')
