import os
import tempfile
import unittest
from unittest.mock import patch

from docx import Document

import gui.app as app_module
from src.core.invoice_generator import InvoiceGenerator


class _ImmediateThread:
    def __init__(self, target, args, daemon):
        self.target = target
        self.args = args
        self.daemon = daemon

    def start(self):
        self.target(*self.args)


class InvoiceTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True)
        app_module.jobs.clear()

    def test_fixed_rate_invoice_document_lists_amounts_and_total(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "fixed-invoice.docx")
            InvoiceGenerator(enable_ai=False).generate_invoice(
                work_details=[
                    {
                        "category": "Brand identity design",
                        "items": ["Logo, colours, and brand guidelines"],
                        "amount": 25000,
                    },
                    {
                        "category": "Website maintenance",
                        "items": [],
                        "amount": 7500.50,
                    },
                ],
                bill_to={"name": "Example Client"},
                invoice_meta={"invoice_no": "INV-100"},
                output_path=output_path,
                currency="INR",
                pricing_mode="fixed",
            )

            document = Document(output_path)
            text = "\n".join(
                paragraph.text for paragraph in document.paragraphs
            )
            table_text = "\n".join(
                cell.text
                for table in document.tables
                for row in table.rows
                for cell in row.cells
            )

            self.assertIn("AMOUNT", table_text)
            self.assertNotIn("Total Hours", table_text)
            self.assertIn("Brand identity design", table_text)
            self.assertIn("₹25,000.00", table_text)
            self.assertIn("₹32,500.50", table_text)
            self.assertIn(
                "Indian Rupees Thirty Two Thousand Five Hundred "
                "and Fifty Paise Only",
                text,
            )

    def test_fixed_rate_route_does_not_require_repositories_or_ai(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(
                    app_module,
                    "get_invoices_dir",
                    return_value=temp_dir,
                ),
                patch.object(
                    app_module.threading,
                    "Thread",
                    _ImmediateThread,
                ),
                patch.object(
                    app_module,
                    "get_db",
                    side_effect=AssertionError(
                        "fixed invoices should not access repository settings"
                    ),
                ),
                app_module.app.test_client() as client,
            ):
                response = client.post(
                    "/invoice",
                    data={
                        "invoice_type": "fixed",
                        "invoice_no": "FIXED-42",
                        "invoice_for": "Consulting services",
                        "date_submitted": "31/07/2026",
                        "currency": "USD",
                        "bill_to_name": "Example Client",
                        "service_name[]": [
                            "Architecture workshop",
                            "Implementation plan",
                        ],
                        "service_description[]": [
                            "One-day discovery workshop",
                            "",
                        ],
                        "service_amount[]": ["1200", "800"],
                    },
                )

            self.assertEqual(response.status_code, 302)
            job_id = response.location.rsplit("/", 1)[-1]
            job = app_module.jobs[job_id]
            self.assertEqual(job["status"], "done")
            self.assertEqual(job["result"]["service_count"], 2)
            self.assertEqual(job["result"]["total_amount"], 2000)
            self.assertTrue(
                os.path.exists(
                    os.path.join(
                        temp_dir,
                        job["result"]["invoice_filename"],
                    )
                )
            )

    def test_fixed_rate_route_rejects_empty_service_items(self):
        with app_module.app.test_client() as client:
            response = client.post(
                "/invoice",
                data={
                    "invoice_type": "fixed",
                    "service_name[]": "",
                    "service_description[]": "",
                    "service_amount[]": "",
                },
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/invoice"))

    def test_development_invoice_fails_when_commit_fetch_fails(self):
        job_id = "invoice-fetch-error"
        app_module.jobs[job_id] = {
            "status": "queued",
            "progress": "Queued",
            "log": [],
        }

        class FailedGitHubClient:
            def fetch_commits(self, *args, **kwargs):
                raise RuntimeError(
                    "GitHub API error (403): API rate limit exceeded"
                )

        with (
            patch.object(app_module, "get_db", return_value=object()),
            patch.object(
                app_module,
                "GitHubClient",
                return_value=FailedGitHubClient(),
            ),
            patch.object(
                app_module,
                "_ai_availability",
                return_value=(False, "AI disabled for test"),
            ),
        ):
            app_module.run_invoice_job(
                job_id=job_id,
                start_date="2026-09-01",
                end_date="2026-09-28",
                selected_repos=[{"repo": "example/private", "branch": "main"}],
                repo_labels={},
                bill_to={},
                invoice_meta={},
                per_hour_rate=100,
                currency="USD",
            )

        job = app_module.jobs[job_id]
        self.assertEqual(job["status"], "error")
        self.assertIn("API rate limit exceeded", job["progress"])


if __name__ == "__main__":
    unittest.main()
