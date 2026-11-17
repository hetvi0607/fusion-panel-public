"""Check tracked content for private files and recognizable credential formats.

Run from the repository root. --all-history checks every reachable commit as
well. This complements Gitleaks and a manual review; it is not a certification.
Only file paths and rule names are printed, never credential values.
"""
import argparse
from pathlib import PurePosixPath
import re
import subprocess
import sys


def git(*args):
    return subprocess.check_output(['git', *args])


def private_path(name):
    path = PurePosixPath(name)
    parts = path.parts
    base = path.name
    return (
        any(p in {'data', 'output', 'backups', '__pycache__'} for p in parts)
        or (parts and parts[0] == 'logs' and name != 'logs/.gitkeep')
        or (base == '.env' or base.startswith('.env.')) and base != '.env.example'
        or base in {'.DS_Store', '.flask_secret_key', '.db_key', 'credentials.json', 'token.json'}
        or base.startswith('credentials-') and base.endswith('.json')
        or bool(re.search(r'\.(?:db|sqlite3?)(?:[.-].*)?$', base, re.I))
        or bool(re.search(r'\.(?:backup.*|bak|log|docx|pdf|pem|key|pyc)$', base, re.I))
        or base.startswith('github_commits') and base.endswith('.csv')
        or name in {'docs/MIGRATION_COMPLETE.md', 'docs/CLIENT_EMAIL_VERIFICATION.md', 'gui/static/logo.png'}
    )


RULES = {
    'GitHub token': re.compile(rb'(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})'),
    'Anthropic key': re.compile(rb'sk-ant-[A-Za-z0-9_-]{20,}'),
    'private key': re.compile(rb'-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----'),
    'Google API key': re.compile(rb'AIza[0-9A-Za-z_-]{35}'),
    'AWS access key ID': re.compile(rb'(?:AKIA|ASIA)[A-Z0-9]{16}'),
}


def entries(tree=None):
    if tree:
        for record in git('ls-tree', '-rz', '--full-tree', tree).split(b'\0'):
            if not record:
                continue
            metadata, name = record.split(b'\t', 1)
            mode, kind, oid = metadata.split()
            if kind == b'blob':
                yield name.decode('utf-8', 'surrogateescape'), oid.decode(), mode
    else:
        for record in git('ls-files', '--stage', '-z').split(b'\0'):
            if not record:
                continue
            metadata, name = record.split(b'\t', 1)
            mode, oid, stage = metadata.split()
            if stage != b'0':
                raise RuntimeError('Resolve merge conflicts before checking publication.')
            yield name.decode('utf-8', 'surrogateescape'), oid.decode(), mode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all-history', action='store_true')
    args = parser.parse_args()
    seen = set()
    blobs = {}
    findings = set()
    trees = git('rev-list', '--all').decode().splitlines() if args.all_history else [None]
    for tree in trees:
        for name, oid, mode in entries(tree):
            if (name, oid) in seen:
                continue
            seen.add((name, oid))
            if private_path(name):
                findings.add((name, 'private/generated file'))
                continue
            if mode == b'120000':
                findings.add((name, 'symlink requires manual review'))
            if oid not in blobs:
                data = git('cat-file', 'blob', oid)
                blobs[oid] = [label for label, pattern in RULES.items() if pattern.search(data)]
            for label in blobs[oid]:
                findings.add((name, label))
    for name, label in sorted(findings):
        print(f'{name}: {label}')
    print(f'Checked {len(seen)} file revisions; {len(findings)} findings.')
    return bool(findings)


if __name__ == '__main__':
    sys.exit(main())
