# -*- coding: utf-8 -*-
"""Quick script to check branch names for repositories."""
import requests
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv('GITHUB_TOKEN')

repos = [
    'example-user/sample-chat',
    'example-user/sample-backend',
    'example-user/sample-web'
]

headers = {
    'Authorization': 'token {}'.format(token),
    'Accept': 'application/vnd.github.v3+json'
}

for repo_name in repos:
    print('\n{}'.format(repo_name))
    print('-' * 50)
    
    # Get repo info
    repo_url = 'https://api.github.com/repos/{}'.format(repo_name)
    repo_response = requests.get(repo_url, headers=headers)
    
    if repo_response.status_code == 200:
        repo_data = repo_response.json()
        default_branch = repo_data.get('default_branch', 'N/A')
        print('  Default branch: {}'.format(default_branch))
        
        # Get branches
        branches_url = 'https://api.github.com/repos/{}/branches'.format(repo_name)
        branches_response = requests.get(branches_url, headers=headers)
        
        if branches_response.status_code == 200:
            branches = branches_response.json()
            branch_names = [b['name'] for b in branches]
            print('  All branches: {}'.format(', '.join(branch_names)))
        else:
            print('  Could not fetch branches: {}'.format(branches_response.status_code))
    else:
        print('  ERROR: {} - {}'.format(repo_response.status_code, repo_response.json().get('message', 'Unknown error')))
