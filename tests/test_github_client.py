import unittest
from unittest.mock import patch

import requests

from src.core.github_client import GitHubClient


class GitHubClientTests(unittest.TestCase):
    def test_initialization_does_not_require_user_endpoint(self):
        with patch("src.core.github_client.requests.Session") as session_factory:
            client = GitHubClient(token="test-token")

        session_factory.return_value.get.assert_not_called()
        self.assertIsNone(client.authenticated_user)
        self.assertEqual(
            session_factory.return_value.headers.update.call_args.args[0][
                "Authorization"
            ],
            "Bearer test-token",
        )

    def test_fetch_commits_raises_github_error_message(self):
        response = requests.Response()
        response.status_code = 403
        response.url = "https://api.github.com/repos/example/private/commits"
        response._content = b'{"message": "API rate limit exceeded"}'

        with patch("src.core.github_client.requests.Session") as session_factory:
            session = session_factory.return_value
            session.get.return_value.raise_for_status.side_effect = (
                requests.HTTPError(response=response)
            )
            client = GitHubClient(token="test-token")

            with self.assertRaisesRegex(
                RuntimeError,
                r"GitHub API error \(403\): API rate limit exceeded",
            ):
                client.fetch_commits("example/private", "2026-09-01", "2026-09-28")

    def test_fetch_commit_authors_stops_at_max_pages(self):
        commit = {
            "sha": "commit-sha",
            "author": {"login": "contributor"},
            "commit": {
                "author": {
                    "name": "Contributor",
                    "date": "2026-09-28T00:00:00Z",
                }
            },
        }
        with patch("src.core.github_client.requests.Session") as session_factory:
            session = session_factory.return_value
            session.get.return_value.json.return_value = [commit] * 100
            client = GitHubClient(token="test-token")

            commits = client.fetch_commit_authors_since(
                "example/project",
                "main",
                "2026-09-01",
                max_pages=1,
            )

        self.assertEqual(len(commits), 100)
        session.get.assert_called_once()


if __name__ == "__main__":
    unittest.main()