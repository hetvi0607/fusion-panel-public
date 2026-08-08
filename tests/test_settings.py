import os
import re
import tempfile
import unittest
from unittest.mock import patch

import gui.app as app_module
from src.core.repository_db import RepositoryDB


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.original_settings = app_module._runtime_setting_defaults()
        app_module.app.config.update(TESTING=True)

    def tearDown(self):
        app_module._apply_runtime_settings(self.original_settings)

    def test_settings_save_applies_and_persists_typed_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db = RepositoryDB(os.path.join(temp_dir, "settings.db"))
            form = {
                "github_token": "github-secret-value",
                "claude_api_key": "claude-secret-value",
                "claude_model": "claude-test-model",
                "ai_enabled": "on",
                "ai_budget_limit": "75.50",
                "ai_max_tokens": "6000",
                "parallel_processing": "on",
                "max_workers": "4",
                "batch_size": "80",
                "log_level": "WARNING",
            }
            with (
                patch.object(app_module, "get_db", return_value=db),
                app_module.app.test_client() as client,
            ):
                response = client.post("/settings", data=form)
                self.assertEqual(response.status_code, 302)

                stored = db.get_runtime_settings()
                self.assertEqual(stored["CLAUDE_MODEL"], "claude-test-model")
                self.assertEqual(stored["AI_BUDGET_LIMIT"], 75.5)
                self.assertEqual(stored["AI_MAX_TOKENS"], 6000)
                self.assertEqual(stored["MAX_WORKERS"], 4)
                self.assertEqual(stored["BATCH_SIZE"], 80)
                self.assertTrue(stored["AI_ENABLED"])
                self.assertTrue(stored["PARALLEL_PROCESSING"])

                self.assertEqual(
                    app_module.app_config.CLAUDE_MODEL,
                    "claude-test-model",
                )
                self.assertEqual(app_module.app_config.MAX_WORKERS, 4)

                page = client.get("/settings")
                html = page.get_data(as_text=True)
                self.assertEqual(page.status_code, 200)
                self.assertIn("claude-test-model", html)
                self.assertIn("alue", html)
                self.assertNotIn("github-secret-value", html)
                self.assertNotIn("claude-secret-value", html)
                self.assertNotIn("WhatsApp delivery", html)
                self.assertNotIn("Environment", html)
                self.assertNotIn(">Live<", html)

    def test_blank_secret_fields_keep_existing_credentials(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db = RepositoryDB(os.path.join(temp_dir, "settings.db"))
            defaults = dict(self.original_settings)
            defaults["GITHUB_TOKEN"] = "existing-github"
            defaults["CLAUDE_API_KEY"] = "existing-claude"
            db.save_runtime_settings(defaults)
            form = {
                "github_token": "",
                "claude_api_key": "",
                "claude_model": "claude-test-model",
                "ai_enabled": "on",
                "ai_budget_limit": "50",
                "ai_max_tokens": "5000",
                "max_workers": "2",
                "batch_size": "50",
                "log_level": "INFO",
            }
            with (
                patch.object(app_module, "get_db", return_value=db),
                app_module.app.test_client() as client,
            ):
                response = client.post("/settings", data=form)
                self.assertEqual(response.status_code, 302)

            stored = db.get_runtime_settings()
            self.assertEqual(stored["GITHUB_TOKEN"], "existing-github")
            self.assertEqual(stored["CLAUDE_API_KEY"], "existing-claude")

    def test_monthly_budget_blocks_new_ai_jobs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db = RepositoryDB(os.path.join(temp_dir, "settings.db"))
            app_module._apply_runtime_settings({
                **self.original_settings,
                "AI_ENABLED": True,
                "CLAUDE_API_KEY": "configured",
                "AI_BUDGET_LIMIT": 1.0,
            })
            db.record_ai_usage("test", estimated_cost=1.25)
            allowed, reason = app_module._ai_availability(db)
            self.assertFalse(allowed)
            self.assertIn("has been reached", reason)

    def test_parallel_repository_setting_drives_fetch_path(self):
        class FakeGitHubClient:
            def fetch_commits(
                self,
                repo_name,
                start_date,
                end_date,
                branch=None,
            ):
                return [{"repo_name": repo_name, "branch": branch}]

        app_module._apply_runtime_settings({
            **self.original_settings,
            "PARALLEL_PROCESSING": True,
            "MAX_WORKERS": 2,
        })
        job = {"progress": "", "log": []}
        commits = app_module._fetch_selected_commits(
            job=job,
            github_client=FakeGitHubClient(),
            selected_repos=[
                {"repo": "example/one", "branch": "main"},
                {"repo": "example/two", "branch": "develop"},
            ],
            start_date="2026-07-01",
            end_date="2026-07-31",
        )
        self.assertEqual(len(commits), 2)
        self.assertIn("Parallel repository fetching: 2 workers", job["log"])

    def test_settings_admin_routes_and_legacy_redirects(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db = RepositoryDB(os.path.join(temp_dir, "settings.db"))
            with (
                patch.object(app_module, "get_db", return_value=db),
                app_module.app.test_client() as client,
            ):
                for path, heading in (
                    ("/settings", "App Config"),
                    ("/settings/repositories", "Repositories"),
                    ("/settings/clients", "Clients"),
                    ("/settings/company", "My Company Details"),
                ):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(heading, response.get_data(as_text=True))

                repos_redirect = client.get("/repos")
                clients_redirect = client.get("/clients")
                self.assertEqual(repos_redirect.status_code, 302)
                self.assertTrue(
                    repos_redirect.location.endswith(
                        "/settings/repositories"
                    )
                )
                self.assertEqual(clients_redirect.status_code, 302)
                self.assertTrue(
                    clients_redirect.location.endswith("/settings/clients")
                )

                page = client.get("/settings").get_data(as_text=True)
                top_nav = re.search(
                    r'<nav class="bg-gray-900.*?</nav>',
                    page,
                    flags=re.DOTALL,
                ).group(0)
                self.assertNotIn('href="/repos"', top_nav)
                self.assertNotIn('href="/clients"', top_nav)

    def test_company_and_amc_settings_save_without_resetting_each_other(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db = RepositoryDB(os.path.join(temp_dir, "settings.db"))
            db.save_amc_settings({
                "term_months": "18",
                "payment_schedule": "Quarterly",
            })
            company_form = {
                "provider_name": "Example Studio",
                "provider_owner_name": "Alex Example",
                "provider_signatory_title": "Founder",
                "provider_address": "Example Address",
                "provider_email": "hello@example.com",
                "provider_phone": "+91 12345 67890",
                "provider_website": "https://example.com",
                "include_bank_details": "on",
                "bank_details": "Bank Name: Example Bank",
            }
            with (
                patch.object(app_module, "get_db", return_value=db),
                app_module.app.test_client() as client,
            ):
                company_response = client.post(
                    "/settings/company",
                    data=company_form,
                )
                self.assertEqual(company_response.status_code, 302)
                saved = db.get_amc_settings()
                self.assertEqual(saved["provider_name"], "Example Studio")
                self.assertEqual(saved["term_months"], "18")
                self.assertTrue(saved["include_bank_details"])

                amc_response = client.post(
                    "/amc/settings",
                    data={
                        "term_months": "24",
                        "notice_period_days": "45",
                        "payment_schedule": "Annual in advance",
                        "default_response_time": "One business day",
                        "renewal_policy": "Written renewal",
                        "jurisdiction": "Ahmedabad",
                    },
                )
                self.assertEqual(amc_response.status_code, 302)
                saved = db.get_amc_settings()
                self.assertEqual(saved["term_months"], "24")
                self.assertEqual(saved["provider_name"], "Example Studio")
                self.assertEqual(
                    saved["bank_details"],
                    "Bank Name: Example Bank",
                )

                company_page = client.get("/settings/company")
                amc_page = client.get("/amc/settings")
                self.assertIn(
                    b"Service Provider",
                    company_page.data,
                )
                self.assertIn(b"Bank Details", company_page.data)
                self.assertNotIn(b">Service Provider<", amc_page.data)
                self.assertNotIn(b">Bank Details<", amc_page.data)


if __name__ == "__main__":
    unittest.main()
