import unittest
from unittest.mock import patch

import gui.app as app_module


class _FakeGitHubClient:
    def __init__(self):
        self.calls = []

    def list_branches(self, repo_name):
        raise AssertionError("activity should not enumerate remote branches")

    def fetch_commit_authors_since(
        self,
        repo_name,
        branch,
        since_date,
        max_pages=None,
    ):
        self.calls.append((repo_name, branch, max_pages))
        return [{
            "sha": "shared-commit",
            "author_login": "contributor",
            "author_name": "Contributor",
        }]

    def close(self):
        pass


class DashboardActivityTests(unittest.TestCase):
    def test_snapshot_uses_configured_branches_and_deduplicates_commits(self):
        client = _FakeGitHubClient()
        repo_configs = [
            {"repo": "example/project", "branch": "main"},
            {"repo": "example/project", "branch": "release"},
        ]

        with patch.object(app_module, "GitHubClient", return_value=client):
            active_repos, users = app_module._compute_activity_snapshot(
                repo_configs
            )

        self.assertCountEqual(
            client.calls,
            [
                ("example/project", "main", 1),
                ("example/project", "release", 1),
            ],
        )
        self.assertEqual(active_repos, {"example/project"})
        self.assertEqual(users[0]["total"], 1)

    def test_worker_records_repo_key_when_snapshot_fails(self):
        repo_configs = [{"repo": "example/project", "branch": "main"}]
        previous_state = dict(app_module._active_repos_state)

        try:
            with patch.object(
                app_module,
                "_compute_activity_snapshot",
                side_effect=RuntimeError("test failure"),
            ):
                app_module._active_repos_worker(repo_configs)

            self.assertEqual(app_module._active_repos_state["status"], "error")
            self.assertEqual(
                app_module._active_repos_state["repos_key"],
                frozenset({("example/project", "main")}),
            )
        finally:
            app_module._active_repos_state.clear()
            app_module._active_repos_state.update(previous_state)


if __name__ == "__main__":
    unittest.main()