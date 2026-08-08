"""Unit tests for the AI-first AMC workflow (no network calls)."""

import os
import tempfile
import unittest
from unittest.mock import patch

from docx import Document

from src.core.amc_ai_generator import AmcAiGenerator, validate_amc_draft
from src.core.amc_document_generator import AmcDocumentGenerator
from src.core.repository_db import RepositoryDB


def sample_draft():
    return {
        "title": "Annual Website Maintenance Contract",
        "opening": (
            "This Annual Maintenance Contract is entered into between Example Company "
            "and Example Foundation for maintenance of the Example Foundation website."
        ),
        "overview": (
            "Example Company will provide routine technical maintenance and support "
            "for the maintained website during the contract period."
        ),
        "scope_included": [
            "Routine software and dependency updates",
            "Scheduled website backups",
            "Correction of reproducible website defects",
        ],
        "scope_excluded": [
            "New modules, redesigns, and major feature development",
            "Third-party licence, hosting, and domain charges",
        ],
        "service_levels": [
            {
                "service": "Support requests",
                "commitment": "Initial response within two business days",
            }
        ],
        "clauses": [
            {
                "heading": heading,
                "body": (
                    f"{heading} will be governed by the supplied commercial facts "
                    "and the responsibilities stated in this agreement."
                ),
            }
            for heading in [
                "Term and Renewal",
                "Access and Cooperation",
                "Maintenance Services",
                "Changes and Additional Work",
                "Fees and Payment",
                "Third-Party Costs",
                "Taxes",
                "Confidentiality and Data Protection",
                "Intellectual Property",
                "Warranties and Responsibilities",
                "Termination",
                "Default and Remedies",
                "Notices",
                "Governing Law and Entire Agreement",
                "Acceptance",
            ]
        ],
        "assumptions": ["Support is provided during normal business days."],
        "needs_confirmation": [],
        "risk_flags": [],
        "consistency_notes": [],
    }


def sample_facts():
    return {
        "service_type": "Website Maintenance",
        "asset_name": "Example Foundation Website",
        "asset_url": "https://example.org",
        "effective_date": "2026-08-01",
        "effective_date_display": "1 August 2026",
        "end_date": "2027-07-31",
        "end_date_display": "31 July 2027",
        "term_months": 12,
        "annual_fee": 15000,
        "currency": "INR",
        "tax_note": "Taxes as applicable",
        "scope_hint": "",
        "contract_reference": "FB/AMC/2026/0001",
    }


def sample_client():
    return {
        "name": "Example Foundation",
        "address_line1": "100 Example Road",
        "address_line2": "Ahmedabad, Gujarat",
        "contact": "",
        "contact_person": "Manjula Example",
        "email": "contact@example.org",
        "phone": "",
        "website": "https://example.org",
        "signatory_name": "Manjula Example",
        "signatory_title": "Trustee",
    }


def sample_draft_form():
    draft = sample_draft()
    data = {
        "title": draft["title"],
        "opening": draft["opening"],
        "overview": draft["overview"],
        "scope_included": "\n".join(draft["scope_included"]),
        "scope_excluded": "\n".join(draft["scope_excluded"]),
        "assumptions": "\n".join(draft["assumptions"]),
        "needs_confirmation": "",
        "risk_flags": "",
        "consistency_notes": "",
        "service_level_count": str(len(draft["service_levels"])),
        "clause_count": str(len(draft["clauses"])),
    }
    for index, item in enumerate(draft["service_levels"]):
        data[f"service_{index}"] = item["service"]
        data[f"commitment_{index}"] = item["commitment"]
    for index, clause in enumerate(draft["clauses"]):
        data[f"clause_heading_{index}"] = clause["heading"]
        data[f"clause_body_{index}"] = clause["body"]
    return data


class FakeClaude:
    model = "test-model"

    def __init__(self):
        self.calls = 0

    def generate_json(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return sample_draft()
        return {
            "risk_flags": [],
            "needs_confirmation": [],
            "consistency_notes": [],
        }

    def get_usage_stats(self):
        return {
            "input_tokens": 100,
            "output_tokens": 200,
            "total_tokens": 300,
            "estimated_cost": 0.01,
        }


class AmcTests(unittest.TestCase):
    def test_validate_draft(self):
        validated = validate_amc_draft(sample_draft())
        self.assertEqual(validated["title"], sample_draft()["title"])
        self.assertEqual(len(validated["clauses"]), 15)

    def test_ai_generator_uses_structured_review(self):
        fake = FakeClaude()
        generator = AmcAiGenerator(claude=fake)
        draft = generator.generate_draft(
            facts=sample_facts(),
            client=sample_client(),
            defaults={"provider_name": "Example Company"},
        )
        self.assertEqual(fake.calls, 2)
        self.assertEqual(draft["scope_included"][0], "Routine software and dependency updates")

    def test_database_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db = RepositoryDB(os.path.join(temp_dir, "test.db"))
            client_id = db.add_client(
                name="Example Foundation",
                email="contact@example.org",
                signatory_name="Manjula Example",
            )
            contract_id = db.create_amc_contract(
                client_id,
                {"facts": sample_facts(), "project_context": {}},
                model="test-model",
                prompt_version="amc-v1",
            )
            db.update_amc_contract(
                contract_id,
                status="review",
                draft_json=sample_draft(),
            )
            db.add_amc_revision(contract_id, sample_draft(), "Initial AI draft")

            contract = db.get_amc_contract(contract_id)
            self.assertEqual(contract["client_name"], "Example Foundation")
            self.assertEqual(contract["draft"]["title"], sample_draft()["title"])
            self.assertEqual(len(db.get_amc_revisions(contract_id)), 1)

    def test_generate_route_accepts_multiple_maintenance_items(self):
        import gui.app as app_module

        with tempfile.TemporaryDirectory() as temp_dir:
            db = RepositoryDB(os.path.join(temp_dir, "test.db"))
            client_id = db.add_client(name="Example Foundation")
            captured = {}

            def fake_queue(queue_db, queued_client_id, input_data):
                captured["client_id"] = queued_client_id
                captured["input_data"] = input_data
                return "amc_test_job", 1

            app_module.app.config.update(TESTING=True)
            with (
                patch.object(app_module, "get_db", return_value=db),
                patch.object(
                    app_module,
                    "_queue_amc_job",
                    side_effect=fake_queue,
                ),
                app_module.app.test_client() as client,
            ):
                page = client.get("/amc")
                self.assertIn(b"Add item", page.data)
                response = client.post(
                    "/amc/generate",
                    data={
                        "client_id": str(client_id),
                        "maintenance_item_count": "2",
                        "maintenance_type_0": "Website Maintenance",
                        "maintenance_name_0": "Public Website",
                        "maintenance_url_0": "https://example.org",
                        "maintenance_type_1": "Mobile Application Maintenance",
                        "maintenance_name_1": "Member Mobile App",
                        "maintenance_url_1": "",
                        "effective_date": "2026-08-01",
                        "annual_fee": "25000",
                        "currency": "INR",
                    },
                )
                self.assertEqual(response.status_code, 302)

            facts = captured["input_data"]["facts"]
            self.assertEqual(len(facts["maintenance_items"]), 2)
            self.assertEqual(
                facts["maintenance_items"][1]["asset_name"],
                "Member Mobile App",
            )
            self.assertEqual(facts["asset_name"], "Public Website")

    def test_docx_generation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "amc.docx")
            settings = {
                "provider_name": "Example Company",
                "provider_owner_name": "Example Owner",
                "provider_signatory_title": "Proprietor",
                "provider_address": (
                    "123 Example Street, Example City"
                ),
                "provider_email": "billing@example.com",
                "provider_phone": "+1-202-555-0100",
                "provider_website": "https://example.com/",
                "payment_schedule": "Annual payment due within 15 days of invoice",
                "include_bank_details": False,
                "bank_details": "",
            }
            AmcDocumentGenerator().generate(
                draft=sample_draft(),
                facts=sample_facts(),
                client=sample_client(),
                settings=settings,
                output_path=output_path,
                logo_path="",
            )
            self.assertTrue(os.path.isfile(output_path))
            doc = Document(output_path)
            text = "\n".join(p.text for p in doc.paragraphs)
            self.assertIn("Annual Website Maintenance Contract", text)
            self.assertIn("Services Included", text)
            self.assertGreaterEqual(len(doc.tables), 5)
            footer_text = "\n".join(
                paragraph.text
                for paragraph in doc.sections[0].footer.paragraphs
            )
            self.assertIn(
                "123 Example Street, Example City",
                footer_text,
            )
            self.assertIn(
                (
                    "AMC  |  example.com  |  +1-202-555-0100  |  "
                    "billing@example.com"
                ),
                footer_text,
            )

    def test_docx_lists_multiple_maintenance_items(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "multi-item-amc.docx")
            facts = {
                **sample_facts(),
                "maintenance_items": [
                    {
                        "service_type": "Website Maintenance",
                        "asset_name": "Public Website",
                        "asset_url": "https://example.org",
                    },
                    {
                        "service_type": "Mobile Application Maintenance",
                        "asset_name": "Member Mobile App",
                        "asset_url": "",
                    },
                ],
            }
            AmcDocumentGenerator().generate(
                draft=sample_draft(),
                facts=facts,
                client=sample_client(),
                settings={
                    "provider_name": "Example Company",
                    "provider_owner_name": "Example Owner",
                    "provider_signatory_title": "Proprietor",
                    "provider_address": "Ahmedabad, Gujarat, India",
                    "payment_schedule": "Annual in advance",
                    "include_bank_details": False,
                    "bank_details": "",
                },
                output_path=output_path,
                logo_path="",
            )
            doc = Document(output_path)
            table_text = "\n".join(
                cell.text
                for table in doc.tables
                for row in table.rows
                for cell in row.cells
            )
            self.assertIn("Maintenance Item 1", table_text)
            self.assertIn("Public Website", table_text)
            self.assertIn("Maintenance Item 2", table_text)
            self.assertIn("Member Mobile App", table_text)

    def test_review_save_and_export_routes(self):
        import gui.app as app_module

        with tempfile.TemporaryDirectory() as temp_dir:
            db = RepositoryDB(os.path.join(temp_dir, "test.db"))
            client_id = db.add_client(
                name=sample_client()["name"],
                address_line1=sample_client()["address_line1"],
                address_line2=sample_client()["address_line2"],
                email=sample_client()["email"],
                signatory_name=sample_client()["signatory_name"],
                signatory_title=sample_client()["signatory_title"],
            )
            contract_id = db.create_amc_contract(
                client_id,
                {"facts": sample_facts(), "project_context": {}},
                model="test-model",
                prompt_version="amc-v1",
            )
            db.update_amc_contract(
                contract_id,
                status="review",
                draft_json=sample_draft(),
            )

            app_module.app.config.update(TESTING=True)
            with (
                patch.object(app_module, "get_db", return_value=db),
                patch.object(
                    app_module,
                    "get_amc_contracts_dir",
                    return_value=temp_dir,
                ),
                app_module.app.test_client() as client,
            ):
                review = client.get(f"/amc/{contract_id}")
                self.assertEqual(review.status_code, 200)
                self.assertIn(b"Review AMC Draft", review.data)
                self.assertIn(b"Needs Your Decision", review.data)
                self.assertIn(
                    b"never included in the exported DOCX",
                    review.data,
                )

                saved = client.post(
                    f"/amc/{contract_id}/save",
                    data=sample_draft_form(),
                )
                self.assertEqual(saved.status_code, 302)

                export_form = sample_draft_form()
                export_form["confirm_review"] = "on"
                exported = client.post(
                    f"/amc/{contract_id}/export",
                    data=export_form,
                )
                self.assertEqual(exported.status_code, 200)
                self.assertIn(
                    "application/vnd.openxmlformats",
                    exported.content_type,
                )
                self.assertTrue(db.get_amc_contract(contract_id)["output_filename"])
                exported.close()


if __name__ == "__main__":
    unittest.main()
