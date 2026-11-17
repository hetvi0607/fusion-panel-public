"""Exercise accidental staging and reintroduced historical data in isolated Git repos."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CHECKER = Path(__file__).resolve().parents[1] / 'scripts' / 'check_publication.py'


class PublicationGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Test Author')
        self.git('config', 'user.email', 'author@example.com')

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True)

    def stage(self, path, text):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)
        self.git('add', '--', path)

    def check(self, *args):
        return subprocess.run([sys.executable, str(CHECKER), *args], cwd=self.root,
                              capture_output=True, text=True)

    def test_dummy_example_allowed(self):
        self.stage('.env.example', 'GITHUB_TOKEN=your_github_token\n')
        self.assertEqual(self.check().returncode, 0)

    def test_private_paths_blocked(self):
        for name in ['.env.local', 'data/.db_key', 'data/reports/nested/report.csv',
                     'output/screenshot.png', 'old.db.backup_1', 'secret.pem']:
            self.stage(name, 'private fixture')
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn('data/.db_key: private/generated file', result.stdout)
        self.assertNotIn('private fixture', result.stdout)

    def test_credential_value_redacted(self):
        value = 'gh' + 'p_' + 'aB7Z' * 10
        self.stage('config.py', 'TOKEN = ' + repr(value))
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn('GitHub token', result.stdout)
        self.assertNotIn(value, result.stdout)

    def test_deleted_secret_still_detected_in_history(self):
        self.stage('data/private.csv', 'private fixture')
        self.git('commit', '-qm', 'Add fixture')
        self.git('rm', 'data/private.csv')
        self.git('commit', '-qm', 'Delete fixture')
        self.assertEqual(self.check().returncode, 0)
        self.assertEqual(self.check('--all-history').returncode, 1)


if __name__ == '__main__':
    unittest.main()
