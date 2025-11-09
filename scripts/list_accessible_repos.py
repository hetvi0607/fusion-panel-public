# -*- coding: utf-8 -*-
"""List repositories accessible with the current GitHub token."""
import requests
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv('GITHUB_TOKEN')

headers = {
    'Authorization': 'token {}'.format(token),
    'Accept': 'application/vnd.github.v3+json'
}

# Get authenticated user
user_url = 'https://api.github.com/user'
user_response = requests.get(user_url, headers=headers)

if user_response.status_code == 200:
    user_data = user_response.json()
    username = user_data.get('login')
    print('Authenticated as: {}'.format(username))
    print('\nSearching for example-user/sample* repositories...\n')
    
    # Search for repositories
    search_url = 'https://api.github.com/user/repos?per_page=100&affiliation=owner,collaborator,organization_member'
    repos_response = requests.get(search_url, headers=headers)
    
    if repos_response.status_code == 200:
        repos = repos_response.json()
        sample_repos = [r for r in repos if 'sample' in r['full_name'].lower()]
        
        if sample_repos:
            print('Found {} sample-related repositories:'.format(len(sample_repos)))
            print('-' * 70)
            for repo in sample_repos:
                print('  {} (default branch: {})'.format(
                    repo['full_name'], 
                    repo['default_branch']
                ))
        else:
            print('No sample-related repositories found.')
            print('\nShowing all repositories under rutvik106:')
            print('-' * 70)
            rutvik_repos = [r for r in repos if r['full_name'].startswith('example-user/')]
            for repo in rutvik_repos[:20]:  # Show first 20
                print('  {} (default branch: {})'.format(
                    repo['full_name'],
                    repo['default_branch']
                ))
    else:
        print('Could not fetch repositories: {}'.format(repos_response.status_code))
else:
    print('Authentication failed: {}'.format(user_response.status_code))
