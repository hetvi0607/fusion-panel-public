# -*- coding: utf-8 -*-
"""Find all accessible repositories with 'sample' in the name."""
import requests
import os
from dotenv import load_dotenv
import time

load_dotenv()
token = os.getenv('GITHUB_TOKEN')

headers = {
    'Authorization': 'token {}'.format(token),
    'Accept': 'application/vnd.github.v3+json'
}

print('Searching for all accessible repositories with "sample" in the name...\n')
print('=' * 80)

# Get user info first
user_url = 'https://api.github.com/user'
user_response = requests.get(user_url, headers=headers)

if user_response.status_code == 200:
    user_data = user_response.json()
    username = user_data.get('login')
    print('Authenticated as: {}\n'.format(username))
else:
    print('Could not authenticate. Check your token.\n')
    exit(1)

# Search through all accessible repositories
found_sample_repos = []
page = 1
per_page = 100

while True:
    repos_url = 'https://api.github.com/user/repos?page={}&per_page={}&affiliation=owner,collaborator,organization_member'.format(page, per_page)
    time.sleep(0.5)  # Rate limiting
    
    repos_response = requests.get(repos_url, headers=headers)
    
    if repos_response.status_code != 200:
        print('Error fetching repositories: HTTP {}'.format(repos_response.status_code))
        break
    
    repos = repos_response.json()
    
    if not repos:
        break  # No more repos
    
    # Filter for sample repos
    for repo in repos:
        full_name = repo.get('full_name', '')
        if 'sample' in full_name.lower():
            found_sample_repos.append({
                'full_name': full_name,
                'default_branch': repo.get('default_branch', 'unknown'),
                'private': repo.get('private', False),
                'description': repo.get('description', 'No description'),
                'owner': repo.get('owner', {}).get('login', 'unknown')
            })
    
    page += 1
    
    # Safety limit
    if page > 10:
        break

print('Found {} repositories with "sample" in the name:\n'.format(len(found_sample_repos)))

if found_sample_repos:
    for i, repo in enumerate(found_sample_repos, 1):
        print('{}. {}'.format(i, repo['full_name']))
        print('   Default branch: {}'.format(repo['default_branch']))
        print('   Private: {}'.format(repo['private']))
        print('   Owner: {}'.format(repo['owner']))
        if repo['description']:
            print('   Description: {}'.format(repo['description']))
        print()
else:
    print('No repositories with "sample" found.')
    print('\nThis could mean:')
    print('- Repository names are completely different')
    print('- Your token does not have access to these repos')
    print('- Repositories are under a different account')

print('=' * 80)
print('\nNext steps:')
print('1. Compare the found repository names with your database')
print('2. Update incorrect repository names using: python3 manage_repos.py')
print('3. If repos are missing, check:')
print('   - Repository privacy settings')
print('   - GitHub token permissions (needs "repo" scope for private repos)')
