"""AI-first AMC drafting and revision using structured Claude responses."""

import json
from typing import Any, Dict, List, Optional

from src.core.claude_service import ClaudeService

PROMPT_VERSION = "amc-v1"

REQUIRED_CLAUSE_TOPICS = [
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


class AmcAiGenerator:
    """Generate, review, and revise AMC drafts while preserving business facts."""

    def __init__(self, claude: Optional[ClaudeService] = None):
        self.claude = claude or ClaudeService()

    def generate_draft(
        self,
        *,
        facts: Dict[str, Any],
        client: Dict[str, Any],
        defaults: Dict[str, Any],
        project_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        immutable = self._immutable_context(facts, client, defaults, project_context)
        prompt = f"""
Create a professional Annual Maintenance Contract for Example Company.

IMMUTABLE BUSINESS FACTS
{json.dumps(immutable, ensure_ascii=False, indent=2)}

REQUIRED CLAUSE TOPICS
{json.dumps(REQUIRED_CLAUSE_TOPICS, indent=2)}

Return ONLY one JSON object with exactly this structure:
{{
  "title": "string",
  "opening": "string",
  "overview": "string",
  "scope_included": ["string"],
  "scope_excluded": ["string"],
  "service_levels": [
    {{"service": "string", "commitment": "string"}}
  ],
  "clauses": [
    {{"heading": "string", "body": "string"}}
  ],
  "assumptions": ["string"],
  "needs_confirmation": ["string"],
  "risk_flags": ["string"]
}}

Draft every required clause topic. Keep the language clear, balanced, and
commercially practical. Use the supplied amount, currency, parties, dates, and
term exactly. When "maintenance_items" contains multiple entries, cover every
item in the overview, scope, and relevant obligations without merging or
silently dropping any item. Do not invent registration numbers, tax treatment, addresses,
service limits, governing law, bank details, or signatures. When a material
fact is missing, use neutral wording and list the issue under
"needs_confirmation". Do not include markdown or commentary outside the JSON.
"""
        draft = self.claude.generate_json(
            system=(
                "You draft business maintenance agreements from supplied facts. "
                "You never fabricate material facts and you return strict JSON."
            ),
            prompt=prompt,
            max_tokens=7000,
        )
        draft = validate_amc_draft(draft)
        review = self.review_draft(draft=draft, immutable=immutable)
        draft["risk_flags"] = _unique(
            draft["risk_flags"] + review.get("risk_flags", [])
        )
        draft["needs_confirmation"] = _unique(
            draft["needs_confirmation"] + review.get("needs_confirmation", [])
        )
        draft["consistency_notes"] = _string_list(
            review.get("consistency_notes", [])
        )
        return draft

    def review_draft(
        self,
        *,
        draft: Dict[str, Any],
        immutable: Dict[str, Any],
    ) -> Dict[str, Any]:
        prompt = f"""
Audit this AMC draft against the immutable facts.

IMMUTABLE FACTS
{json.dumps(immutable, ensure_ascii=False, indent=2)}

DRAFT
{json.dumps(draft, ensure_ascii=False, indent=2)}

Return ONLY:
{{
  "risk_flags": ["material legal or commercial concern"],
  "needs_confirmation": ["missing fact that requires human confirmation"],
  "consistency_notes": ["contradiction, ambiguity, or duplicated obligation"]
}}

Do not rewrite the contract. Flag unsupported assumptions and any mismatch in
party names, maintenance items, amount, currency, term, dates, scope, or
payment schedule.
"""
        review = self.claude.generate_json(
            system="You are a meticulous contract consistency reviewer.",
            prompt=prompt,
            max_tokens=1800,
        )
        return {
            "risk_flags": _string_list(review.get("risk_flags", [])),
            "needs_confirmation": _string_list(
                review.get("needs_confirmation", [])
            ),
            "consistency_notes": _string_list(
                review.get("consistency_notes", [])
            ),
        }

    def revise_draft(
        self,
        *,
        draft: Dict[str, Any],
        instruction: str,
        facts: Dict[str, Any],
        client: Dict[str, Any],
        defaults: Dict[str, Any],
        project_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        immutable = self._immutable_context(facts, client, defaults, project_context)
        prompt = f"""
Revise the AMC draft according to the user's instruction.

USER INSTRUCTION
{instruction}

IMMUTABLE BUSINESS FACTS - these must not change
{json.dumps(immutable, ensure_ascii=False, indent=2)}

CURRENT DRAFT
{json.dumps(draft, ensure_ascii=False, indent=2)}

Return ONLY the complete revised JSON object using the identical schema as the
current draft. Preserve sections that the instruction does not affect. Never
change parties, amount, currency, dates, or term. If the instruction conflicts
with immutable facts, leave the facts unchanged and add a risk flag explaining
the conflict.
"""
        revised = self.claude.generate_json(
            system=(
                "You revise structured business contracts precisely while "
                "preserving immutable commercial facts."
            ),
            prompt=prompt,
            max_tokens=7000,
        )
        return validate_amc_draft(revised)

    @staticmethod
    def _immutable_context(
        facts: Dict[str, Any],
        client: Dict[str, Any],
        defaults: Dict[str, Any],
        project_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "service_provider": {
                "name": defaults.get("provider_name", "Example Company"),
                "owner_name": defaults.get("provider_owner_name", "Example Owner"),
                "address": defaults.get("provider_address", ""),
                "email": defaults.get("provider_email", ""),
                "phone": defaults.get("provider_phone", ""),
                "website": defaults.get("provider_website", ""),
            },
            "counterparty": {
                "name": client.get("name", ""),
                "address": " ".join(
                    part
                    for part in [
                        client.get("address_line1", ""),
                        client.get("address_line2", ""),
                    ]
                    if part
                ),
                "contact_person": client.get("contact_person", ""),
                "email": client.get("email", "") or client.get("contact", ""),
                "website": client.get("website", ""),
                "signatory_name": client.get("signatory_name", ""),
                "signatory_title": client.get("signatory_title", ""),
            },
            "contract": facts,
            "business_defaults": {
                "payment_schedule": defaults.get("payment_schedule", ""),
                "jurisdiction": defaults.get("jurisdiction", ""),
                "default_response_time": defaults.get(
                    "default_response_time", ""
                ),
                "renewal_policy": defaults.get("renewal_policy", ""),
                "notice_period_days": defaults.get("notice_period_days", ""),
            },
            "project_context": project_context or {},
        }

    def get_usage_stats(self) -> Dict[str, Any]:
        return self.claude.get_usage_stats()


def validate_amc_draft(value: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize the JSON structure used by the UI and DOCX layer."""
    if not isinstance(value, dict):
        raise ValueError("AMC draft must be an object")

    normalized = {
        "title": _required_string(value.get("title"), "title"),
        "opening": _required_string(value.get("opening"), "opening"),
        "overview": _required_string(value.get("overview"), "overview"),
        "scope_included": _string_list(value.get("scope_included", [])),
        "scope_excluded": _string_list(value.get("scope_excluded", [])),
        "service_levels": [],
        "clauses": [],
        "assumptions": _string_list(value.get("assumptions", [])),
        "needs_confirmation": _string_list(
            value.get("needs_confirmation", [])
        ),
        "risk_flags": _string_list(value.get("risk_flags", [])),
        "consistency_notes": _string_list(
            value.get("consistency_notes", [])
        ),
    }

    for item in value.get("service_levels", []):
        if isinstance(item, dict):
            service = str(item.get("service", "")).strip()
            commitment = str(item.get("commitment", "")).strip()
            if service and commitment:
                normalized["service_levels"].append(
                    {"service": service, "commitment": commitment}
                )

    for item in value.get("clauses", []):
        if isinstance(item, dict):
            heading = str(item.get("heading", "")).strip()
            body = str(item.get("body", "")).strip()
            if heading and body:
                normalized["clauses"].append(
                    {"heading": heading, "body": body}
                )

    if not normalized["scope_included"]:
        raise ValueError("AMC draft must include at least one included service")
    if not normalized["clauses"]:
        raise ValueError("AMC draft must include contract clauses")
    return normalized


def _required_string(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"AMC draft is missing {field}")
    return text


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _unique(items: List[str]) -> List[str]:
    return list(dict.fromkeys(item for item in items if item))
