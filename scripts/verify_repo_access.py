# -*- coding: utf-8 -*-
"""Verify repository access and list available branches."""
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

# All your rutvik106 repos
repos_to_check = [
    ('example-user/sample-admin', 'test'),  # Working one
    ('example-user/sample-chat', 'test'),
    ('example-user/sample-backend', 'test'),
    ('example-user/sample-web', 'testing'),
]

print('Verifying repository access and branches...\n')
print('=' * 80)

for repo_name, expected_branch in repos_to_check:
    print('\nRepository: {}'.format(repo_name))
    print('Expected branch: {}'.format(expected_branch))
    print('-' * 80)
    
    # Check if repo exists
    repo_url = 'https://api.github.com/repos/{}'.format(repo_name)
    time.sleep(0.5)  # Rate limiting
    
    try:
        repo_response = requests.get(repo_url, headers=headers)
        
        if repo_response.status_code == 200:
            repo_data = repo_response.json()
            print('[OK] Repository exists')
            print('    Default branch: {}'.format(repo_data.get('default_branch')))
            print('    Private: {}'.format(repo_data.get('private', False)))
            
            # Get all branches
            branches_url = 'https://api.github.com/repos/{}/branches'.format(repo_name)
            time.sleep(0.5)
            branches_response = requests.get(branches_url, headers=headers)
            
            if branches_response.status_code == 200:
                branches = branches_response.json()
                branch_names = [b['name'] for b in branches]
                print('    Available branches ({} total): {}'.format(
                    len(branch_names),
                    ', '.join(branch_names)
                ))
                
                # Check if expected branch exists
                if expected_branch in branch_names:
                    print('    [OK] Expected branch "{}" EXISTS'.format(expected_branch))
                else:
                    print('    [ERROR] Expected branch "{}" NOT FOUND!'.format(expected_branch))
                    if branch_names:
                        print('    Suggestion: Use one of these branches instead: {}'.format(
                            ', '.join(branch_names)
                        ))
            else:
                print('    [ERROR] Could not fetch branches: HTTP {}'.format(
                    branches_response.status_code
                ))
                
        elif repo_response.status_code == 404:
            print('[ERROR] Repository NOT FOUND (404)')
            print('        Check if repository name is correct')
            print('        Repository might be: private & no access, deleted, or renamed')
            
        elif repo_response.status_code == 401:
            print('[ERROR] Authentication failed (401)')
            print('        Check your GitHub token')
            
        elif repo_response.status_code == 403:
            print('[ERROR] Access forbidden (403)')
            print('        Token might not have required permissions')
            
        else:
            print('[ERROR] Unexpected error: HTTP {}'.format(repo_response.status_code))
            error_msg = repo_response.json().get('message', 'Unknown error')
            print('        Message: {}'.format(error_msg))
            
    except Exception as e:
        print('[ERROR] Exception occurred: {}'.format(str(e)))

print('\n' + '=' * 80)
print('\nDiagnostic complete!')
