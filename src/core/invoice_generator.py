"""
Invoice DOCX generator for creating professional invoices from commit data.

Uses AI to categorize commits into work categories and generates a
formatted DOCX document matching the Example Company invoice template.
"""
import os
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml
import anthropic

from src.core.config import app_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default invoice metadata
# ---------------------------------------------------------------------------
DEFAULT_FROM = {
    "name": "Example Owner",
    "title": "Proprietor Example Company",
    "phone": "+1 202-555-0100",
    "email": "owner@example.com",
}

DEFAULT_FOOTER = {
    "address": "123 Example Street, Example City",
    "website": "example.com",
    "phone": "+1-202-555-0100",
    "email": "billing@example.com",
}


class InvoiceGenerator:
    """Generates DOCX invoices from GitHub commit data with AI categorization."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=app_config.CLAUDE_API_KEY)
        self.model = app_config.CLAUDE_MODEL
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        logger.info("InvoiceGenerator initialized")

    # ------------------------------------------------------------------
    # AI: categorize commits into work-detail rows
    # ------------------------------------------------------------------
    def categorize_commits(
        self,
        commits: List[Dict[str, Any]],
        repo_labels: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Use Claude to group commits into invoice work-detail categories.

        Args:
            commits: list of commit dicts (keys: repo_name, branch, message, username, date_time, sha)
            repo_labels: optional mapping of repo_name -> display label
                         e.g. {"example-org/sample-android": "Android Development"}

        Returns:
            List of dicts with keys:
                category  – e.g. "Android Development"
                hours     – estimated hours (int)
                items     – list of bullet-point strings
        """
        # Build a concise commit listing grouped by repo
        repo_commits: Dict[str, list] = {}
        for c in commits:
            repo = c.get("repo_name", c.get("Repository", "unknown"))
            msg = c.get("message", c.get("Commit Message", ""))
            repo_commits.setdefault(repo, []).append(msg)

        listing = ""
        for repo, msgs in repo_commits.items():
            label = (repo_labels or {}).get(repo, repo)
            listing += f"\n## {label} ({repo})\n"
            for m in msgs[:80]:  # cap per repo
                listing += f"- {m}\n"

        prompt = f"""You are an invoice assistant. Given the following GitHub commit messages grouped by repository, produce a JSON array of work categories for an invoice.

Each element must have:
- "category": a short human-readable title (e.g. "Android Development", "Backend/API Development", "Web Application", "DevOps / Infrastructure", etc.)
- "hours": an integer estimate of hours spent (use your best judgement based on commit volume and complexity)
- "items": an array of concise bullet-point strings summarising the work done in that category. Each bullet should be a clear, non-technical description suitable for a client invoice. Combine related commits into single bullets. Aim for 4-8 bullets per category.

IMPORTANT: Return ONLY the raw JSON array, no markdown fences, no explanation.

Commits:
{listing}
"""
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            self.total_input_tokens += message.usage.input_tokens
            self.total_output_tokens += message.usage.output_tokens

            raw = message.content[0].text.strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                if raw.endswith("```"):
                    raw = raw[: raw.rfind("```")]
            categories = json.loads(raw)
            logger.info(f"AI returned {len(categories)} work categories")
            return categories
        except Exception as e:
            logger.error(f"AI categorization failed: {e}")
            # Fallback: one category per repo
            fallback = []
            for repo, msgs in repo_commits.items():
                label = (repo_labels or {}).get(repo, repo)
                fallback.append({
                    "category": label,
                    "hours": max(1, len(msgs) // 5),
                    "items": msgs[:8],
                })
            return fallback

    # ------------------------------------------------------------------
    # DOCX generation
    # ------------------------------------------------------------------
    def generate_invoice(
        self,
        work_details: List[Dict[str, Any]],
        bill_to: Dict[str, str],
        invoice_meta: Dict[str, str],
        output_path: str,
        from_info: Optional[Dict[str, str]] = None,
        footer_info: Optional[Dict[str, str]] = None,
    ) -> str:
        """Create the DOCX invoice file.

        Args:
            work_details: list of {"category", "hours", "items"} dicts
            bill_to: {"name", "address_line1", "address_line2"} for recipient
            invoice_meta: {"invoice_no", "po_number", "invoice_for", "date_submitted"}
            output_path: where to save the .docx
            from_info: override sender info (defaults to DEFAULT_FROM)
            footer_info: override footer info (defaults to DEFAULT_FOOTER)

        Returns:
            Absolute path to the generated DOCX file.
        """
        sender = from_info or DEFAULT_FROM
        footer = footer_info or DEFAULT_FOOTER

        doc = Document()

        # -- Page margins --
        for section in doc.sections:
            section.top_margin = Cm(1.5)
            section.bottom_margin = Cm(1.5)
            section.left_margin = Cm(2)
            section.right_margin = Cm(2)

        # -- Default font --
        style = doc.styles["Normal"]
        font = style.font
        font.name = "Calibri"
        font.size = Pt(10)
        font.color.rgb = RGBColor(0x33, 0x33, 0x33)

        # ===== HEADER =====
        self._add_header(doc, sender)

        # ===== HORIZONTAL LINE =====
        self._add_horizontal_line(doc)

        # ===== TITLE BLOCK =====
        self._add_title_block(doc, sender)

        # ===== BILLING SECTION =====
        self._add_billing_section(doc, bill_to, invoice_meta)

        # ===== WORK DETAILS TABLE =====
        self._add_work_details_table(doc, work_details)

        # ===== FOOTER =====
        self._add_footer(doc, footer)

        # Save
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        doc.save(output_path)
        logger.info(f"Invoice saved to {output_path}")
        return output_path

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _add_header(self, doc: Document, sender: Dict[str, str]):
        """Add the Example Company header at top-right."""
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run = p.add_run("Example Company")
        run.bold = True
        run.font.size = Pt(20)
        run.font.color.rgb = RGBColor(0xE8, 0x6C, 0x00)  # Orange

    def _add_horizontal_line(self, doc: Document):
        """Add a thin horizontal rule."""
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(6)
        # Use a bottom border on the paragraph
        pPr = p._p.get_or_add_pPr()
        pBdr = parse_xml(
            f'<w:pBdr {nsdecls("w")}>'
            '  <w:bottom w:val="single" w:sz="6" w:space="1" w:color="CCCCCC"/>'
            '</w:pBdr>'
        )
        pPr.append(pBdr)

    def _add_title_block(self, doc: Document, sender: Dict[str, str]):
        """Centered title: INVOICE CUM RECEIPT, name, phone, email."""
        for text, size, bold in [
            ("INVOICE CUM RECEIPT", 14, True),
            (f"{sender['name']} ({sender['title']})", 11, False),
            (sender["phone"], 10, False),
            (sender["email"], 10, False),
        ]:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(1)
            run = p.add_run(text)
            run.bold = bold
            run.font.size = Pt(size)
            if bold:
                run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x1A)

        # Small spacer
        doc.add_paragraph().paragraph_format.space_after = Pt(4)

    def _add_billing_section(self, doc: Document, bill_to: Dict[str, str], meta: Dict[str, str]):
        """Two-column billing box: recipient on left, invoice details on right."""
        table = doc.add_table(rows=1, cols=2)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER

        # Set table borders
        self._set_table_borders(table)

        # Left cell – bill to
        left = table.cell(0, 0)
        left.width = Inches(3.2)
        lp = left.paragraphs[0]
        lp.paragraph_format.space_after = Pt(2)
        run = lp.add_run("To: ")
        run.bold = True
        run.font.size = Pt(10)
        run = lp.add_run(bill_to.get("name", ""))
        run.font.size = Pt(10)
        run.bold = True

        for line in [bill_to.get("address_line1", ""), bill_to.get("address_line2", "")]:
            if line:
                p2 = left.add_paragraph()
                p2.paragraph_format.space_before = Pt(0)
                p2.paragraph_format.space_after = Pt(1)
                r = p2.add_run(line)
                r.font.size = Pt(9)

        # Right cell – invoice meta
        right = table.cell(0, 1)
        right.width = Inches(3.2)
        rp = right.paragraphs[0]
        rp.paragraph_format.space_after = Pt(2)

        fields = [
            ("Invoice No: ", meta.get("invoice_no", "")),
            ("PO #: ", meta.get("po_number", "")),
            ("Invoice For: ", meta.get("invoice_for", "")),
            ("Date Submitted: ", meta.get("date_submitted", "")),
        ]
        first = True
        for label, value in fields:
            if first:
                p3 = rp
                first = False
            else:
                p3 = right.add_paragraph()
            p3.paragraph_format.space_before = Pt(0)
            p3.paragraph_format.space_after = Pt(1)
            rl = p3.add_run(label)
            rl.bold = True
            rl.font.size = Pt(10)
            rv = p3.add_run(value)
            rv.font.size = Pt(10)

        doc.add_paragraph().paragraph_format.space_after = Pt(4)

    def _add_work_details_table(self, doc: Document, work_details: List[Dict[str, Any]]):
        """Build the SR. NO. | ON ACCOUNT OF | HOURS table."""
        # Heading
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run = p.add_run("Work Details")
        run.bold = True
        run.font.size = Pt(12)
        run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x1A)
        p.paragraph_format.space_after = Pt(4)

        # Table: header + one row per category
        num_rows = 1 + len(work_details)
        table = doc.add_table(rows=num_rows, cols=3)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        self._set_table_borders(table)

        # Column widths
        for row in table.rows:
            row.cells[0].width = Inches(0.7)
            row.cells[1].width = Inches(5.0)
            row.cells[2].width = Inches(0.8)

        # Header row
        hdr = table.rows[0]
        for idx, text in enumerate(["SR. NO.", "ON ACCOUNT OF", "HOURS"]):
            cell = hdr.cells[idx]
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(text)
            run.bold = True
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            # Dark background
            shading = parse_xml(
                f'<w:shd {nsdecls("w")} w:fill="2D3748" w:val="clear"/>'
            )
            cell._tc.get_or_add_tcPr().append(shading)

        # Data rows
        total_hours = 0
        for i, detail in enumerate(work_details):
            row = table.rows[i + 1]

            # SR. NO.
            c0 = row.cells[0]
            p0 = c0.paragraphs[0]
            p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r0 = p0.add_run(str(i + 1))
            r0.font.size = Pt(10)

            # ON ACCOUNT OF
            c1 = row.cells[1]
            # Category title
            pt = c1.paragraphs[0]
            rt = pt.add_run(detail["category"])
            rt.bold = True
            rt.font.size = Pt(10)
            rt.font.color.rgb = RGBColor(0x1A, 0x1A, 0x1A)

            hours = detail.get("hours", 0)
            total_hours += hours
            pt_hours = c1.add_paragraph()
            pt_hours.paragraph_format.space_before = Pt(1)
            pt_hours.paragraph_format.space_after = Pt(2)
            rh = pt_hours.add_run(f"({hours} hours)")
            rh.italic = True
            rh.font.size = Pt(9)
            rh.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

            # Bullet items
            for item_text in detail.get("items", []):
                bp = c1.add_paragraph(style="List Bullet")
                bp.paragraph_format.space_before = Pt(0)
                bp.paragraph_format.space_after = Pt(1)
                bp.paragraph_format.left_indent = Cm(0.6)
                br = bp.add_run(item_text)
                br.font.size = Pt(9)

            # HOURS
            c2 = row.cells[2]
            p2 = c2.paragraphs[0]
            p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r2 = p2.add_run(str(hours))
            r2.font.size = Pt(10)
            r2.bold = True

        # Total row
        total_row = table.add_row()
        total_row.cells[0].merge(total_row.cells[1])
        merged = total_row.cells[0]
        pm = merged.paragraphs[0]
        pm.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        rm = pm.add_run("Total Hours: ")
        rm.bold = True
        rm.font.size = Pt(10)

        tc = total_row.cells[2]
        pt = tc.paragraphs[0]
        pt.alignment = WD_ALIGN_PARAGRAPH.CENTER
        rt = pt.add_run(str(total_hours))
        rt.bold = True
        rt.font.size = Pt(11)
        rt.font.color.rgb = RGBColor(0xE8, 0x6C, 0x00)

        doc.add_paragraph().paragraph_format.space_after = Pt(8)

    def _add_footer(self, doc: Document, footer: Dict[str, str]):
        """Add footer with address, website, phone, email."""
        self._add_horizontal_line(doc)
        for text in [
            footer.get("address", ""),
            f"{footer.get('website', '')}  |  {footer.get('phone', '')}  |  {footer.get('email', '')}",
        ]:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(1)
            run = p.add_run(text)
            run.font.size = Pt(8)
            run.font.color.rgb = RGBColor(0x88, 0x88, 0x88)

    def _set_table_borders(self, table):
        """Apply thin borders to all cells in a table."""
        tbl = table._tbl
        tblPr = tbl.tblPr if tbl.tblPr is not None else parse_xml(f'<w:tblPr {nsdecls("w")}/>')
        borders = parse_xml(
            f'<w:tblBorders {nsdecls("w")}>'
            '  <w:top w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/>'
            '  <w:left w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/>'
            '  <w:bottom w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/>'
            '  <w:right w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/>'
            '  <w:insideH w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/>'
            '  <w:insideV w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/>'
            '</w:tblBorders>'
        )
        tblPr.append(borders)

    def get_usage_stats(self) -> Dict[str, Any]:
        """Return token usage statistics."""
        input_cost_per_1k = 0.003
        output_cost_per_1k = 0.015
        estimated_cost = (
            (self.total_input_tokens / 1000) * input_cost_per_1k
            + (self.total_output_tokens / 1000) * output_cost_per_1k
        )
        return {
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "estimated_cost": estimated_cost,
        }
