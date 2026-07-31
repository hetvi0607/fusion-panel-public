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

# Path to logo image (place your logo at gui/static/logo.png)
LOGO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "gui", "static", "logo.png",
)


# ---------------------------------------------------------------------------
# Number to Indian Rupees words
# ---------------------------------------------------------------------------
def _number_to_words(n: int) -> str:
    """Convert an integer to English words (Indian style)."""
    if n == 0:
        return "Zero"

    ones = [
        "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
        "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
        "Seventeen", "Eighteen", "Nineteen",
    ]
    tens = [
        "", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety",
    ]

    def _two_digits(num):
        if num < 20:
            return ones[num]
        return (tens[num // 10] + " " + ones[num % 10]).strip()

    def _three_digits(num):
        if num >= 100:
            return ones[num // 100] + " Hundred" + (" and " + _two_digits(num % 100) if num % 100 else "")
        return _two_digits(num)

    if n < 0:
        return "Minus " + _number_to_words(-n)

    # Indian numbering: Crore, Lakh, Thousand, Hundred
    parts = []
    if n >= 10_000_000:
        parts.append(_three_digits(n // 10_000_000) + " Crore")
        n %= 10_000_000
    if n >= 100_000:
        parts.append(_two_digits(n // 100_000) + " Lakh")
        n %= 100_000
    if n >= 1_000:
        parts.append(_two_digits(n // 1_000) + " Thousand")
        n %= 1_000
    if n > 0:
        parts.append(_three_digits(n))

    return " ".join(parts)


def amount_in_words_inr(amount: float) -> str:
    """Convert amount to Indian Rupees in words.

    Example: 52000.50 -> 'Indian Rupees Fifty Two Thousand and Fifty Paise Only'
    """
    rupees = int(amount)
    paise = round((amount - rupees) * 100)

    result = "Indian Rupees " + _number_to_words(rupees)
    if paise:
        result += " and " + _number_to_words(paise) + " Paise"
    result += " Only"
    return result


def _number_to_words_western(n: int) -> str:
    """Convert an integer to English words (Western/US style)."""
    if n == 0:
        return "Zero"

    ones = [
        "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
        "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
        "Seventeen", "Eighteen", "Nineteen",
    ]
    tens = [
        "", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety",
    ]

    def _two(num):
        if num < 20:
            return ones[num]
        return (tens[num // 10] + " " + ones[num % 10]).strip()

    def _three(num):
        if num >= 100:
            return ones[num // 100] + " Hundred" + (" and " + _two(num % 100) if num % 100 else "")
        return _two(num)

    if n < 0:
        return "Minus " + _number_to_words_western(-n)

    parts = []
    if n >= 1_000_000_000:
        parts.append(_three(n // 1_000_000_000) + " Billion")
        n %= 1_000_000_000
    if n >= 1_000_000:
        parts.append(_three(n // 1_000_000) + " Million")
        n %= 1_000_000
    if n >= 1_000:
        parts.append(_three(n // 1_000) + " Thousand")
        n %= 1_000
    if n > 0:
        parts.append(_three(n))

    return " ".join(parts)


def amount_in_words_usd(amount: float) -> str:
    """Convert amount to US Dollars in words.

    Example: 5200.50 -> 'US Dollars Five Thousand Two Hundred and Fifty Cents Only'
    """
    dollars = int(amount)
    cents = round((amount - dollars) * 100)

    result = "US Dollars " + _number_to_words_western(dollars)
    if cents:
        result += " and " + _number_to_words_western(cents) + " Cents"
    result += " Only"
    return result


def amount_in_words(amount: float, currency: str = "INR") -> str:
    """Convert amount to words in the given currency."""
    if currency == "USD":
        return amount_in_words_usd(amount)
    return amount_in_words_inr(amount)


CURRENCY_SYMBOLS = {
    "INR": "\u20b9",  # ₹
    "USD": "$",
}


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

    def __init__(self, enable_ai: bool = True):
        self.client = None
        if enable_ai:
            if not app_config.CLAUDE_API_KEY:
                raise ValueError("Claude API key is required for AI categorization")
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
                     Each commit may also have a 'stats' dict with:
                         additions, deletions, files_changed, file_types
            repo_labels: optional mapping of repo_name -> display label
                         e.g. {"example-org/sample-android": "Android Development"}

        Returns:
            List of dicts with keys:
                category  – e.g. "Android Development"
                hours     – estimated hours (int)
                items     – list of bullet-point strings
        """
        if self.client is None:
            raise RuntimeError("AI categorization is disabled")

        # Build a detailed commit listing grouped by repo, including code stats
        repo_commits: Dict[str, list] = {}
        repo_totals: Dict[str, Dict] = {}
        for c in commits:
            repo = c.get("repo_name", c.get("Repository", "unknown"))
            msg = c.get("message", c.get("Commit Message", ""))
            stats = c.get("stats", {})
            repo_commits.setdefault(repo, []).append({
                "msg": msg,
                "add": stats.get("additions", 0),
                "del": stats.get("deletions", 0),
                "files": stats.get("files_changed", 0),
                "types": stats.get("file_types", []),
            })
            totals = repo_totals.setdefault(repo, {"add": 0, "del": 0, "files": 0, "commits": 0})
            totals["add"] += stats.get("additions", 0)
            totals["del"] += stats.get("deletions", 0)
            totals["files"] += stats.get("files_changed", 0)
            totals["commits"] += 1

        listing = ""
        for repo, entries in repo_commits.items():
            label = (repo_labels or {}).get(repo, repo)
            t = repo_totals[repo]
            listing += f"\n## {label} ({repo})\n"
            listing += f"Summary: {t['commits']} commits, +{t['add']} additions, -{t['del']} deletions, {t['files']} file changes\n"
            for e in entries[:app_config.BATCH_SIZE]:
                stat_str = f" [+{e['add']} -{e['del']}, {e['files']} files]" if e['add'] or e['del'] else ""
                listing += f"- {e['msg']}{stat_str}\n"

        prompt = f"""You are an invoice assistant. Given the following GitHub commit data grouped by repository (including lines of code added/deleted and files changed per commit), produce a JSON array of work categories for an invoice.

HOUR ESTIMATION RULES — estimate hours based on the ACTUAL CODE written:
- Use the lines added/deleted and number of files changed as the PRIMARY signal for effort.
- Assume a mixed workflow: some code is AI-assisted (faster to write) and some is written manually by a human developer.
- Factor in that EVERY piece of code is reviewed and tested by a human, which takes additional time.
- As a rough guide: ~100-150 lines of meaningful code additions (not config/generated files) ≈ 1 hour of combined writing + review + testing effort.
- Large deletions or refactors also take significant review time.
- Config files, lock files, migrations, and auto-generated code take less time per line.
- Use file types to judge complexity (e.g. .py, .java, .kt, .swift = higher effort; .json, .xml, .yml, .lock = lower effort).

Each element must have:
- "category": a short human-readable title (e.g. "Android Development", "Backend/API Development", "Web Application", "DevOps / Infrastructure", etc.)
- "hours": an integer estimate of hours spent based on the code analysis above
- "items": an array of concise bullet-point strings summarising the work done in that category. Each bullet should be a clear, non-technical description suitable for a client invoice. Combine related commits into single bullets. Aim for 4-8 bullets per category.

IMPORTANT: Return ONLY the raw JSON array, no markdown fences, no explanation.

Commits:
{listing}
"""
        message = self.client.messages.create(
            model=self.model,
            max_tokens=min(2000, app_config.AI_MAX_TOKENS),
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

    # ------------------------------------------------------------------
    # DOCX generation
    # ------------------------------------------------------------------
    def generate_invoice(
        self,
        work_details: List[Dict[str, Any]],
        bill_to: Dict[str, str],
        invoice_meta: Dict[str, str],
        output_path: str,
        per_hour_rate: float = 0,
        currency: str = "INR",
        pricing_mode: str = "hourly",
        from_info: Optional[Dict[str, str]] = None,
        footer_info: Optional[Dict[str, str]] = None,
        logo_path: Optional[str] = None,
    ) -> str:
        """Create the DOCX invoice file.

        Args:
            work_details: list of {"category", "hours", "items"} dicts for
                hourly invoices, or {"category", "amount", "items"} dicts for
                fixed-rate invoices
            bill_to: {"name", "address_line1", "address_line2"} for recipient
            invoice_meta: {"invoice_no", "po_number", "invoice_for", "date_submitted"}
            output_path: where to save the .docx
            per_hour_rate: rate per hour for total amount calculation
            currency: "INR" or "USD"
            pricing_mode: "hourly" or "fixed"
            from_info: override sender info (defaults to DEFAULT_FROM)
            footer_info: override footer info (defaults to DEFAULT_FOOTER)
            logo_path: path to company logo image (defaults to gui/static/logo.png)

        Returns:
            Absolute path to the generated DOCX file.
        """
        sender = from_info or DEFAULT_FROM
        footer = footer_info or DEFAULT_FOOTER
        logo = logo_path or LOGO_PATH

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
        self._add_header(doc, sender, logo)

        # ===== HORIZONTAL LINE =====
        self._add_horizontal_line(doc)

        # ===== TITLE BLOCK =====
        self._add_title_block(doc, sender)

        # ===== BILLING SECTION =====
        self._add_billing_section(doc, bill_to, invoice_meta)

        # ===== WORK DETAILS TABLE =====
        self._add_work_details_table(
            doc,
            work_details,
            per_hour_rate,
            currency,
            pricing_mode,
        )

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
    def _add_header(self, doc: Document, sender: Dict[str, str], logo_path: str = None):
        """Add company logo (if available) or text header at top-right."""
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if logo_path and os.path.isfile(logo_path):
            run = p.add_run()
            run.add_picture(logo_path, width=Inches(1.8))
            logger.info(f"Logo added from {logo_path}")
        else:
            run = p.add_run("Example Company")
            run.bold = True
            run.font.size = Pt(20)
            run.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
            if logo_path:
                logger.warning(f"Logo not found at {logo_path}, using text fallback")

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

        gstin = bill_to.get("gstin", "").strip()
        if gstin:
            pg = left.add_paragraph()
            pg.paragraph_format.space_before = Pt(2)
            pg.paragraph_format.space_after = Pt(1)
            rl = pg.add_run("GSTIN: ")
            rl.bold = True
            rl.font.size = Pt(9)
            rv = pg.add_run(gstin)
            rv.font.size = Pt(9)

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

    def _add_work_details_table(
        self,
        doc: Document,
        work_details: List[Dict[str, Any]],
        per_hour_rate: float = 0,
        currency: str = "INR",
        pricing_mode: str = "hourly",
    ):
        """Build the invoice line-items table and its totals."""
        is_fixed = pricing_mode == "fixed"
        value_heading = "AMOUNT" if is_fixed else "HOURS"
        # Heading
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        # run = p.add_run("Work Details")
        # run.bold = True
        # run.font.size = Pt(12)
        # run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x1A)
        p.paragraph_format.space_after = Pt(4)

        # Table: header + one row per category
        num_rows = 1 + len(work_details)
        table = doc.add_table(rows=num_rows, cols=3)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        self._set_table_borders(table)

        # Column widths
        # for row in table.rows:
        #     row.cells[0].width = Inches(0.7)
        #     row.cells[1].width = Inches(5.0)
        #     row.cells[2].width = Inches(0.8)

        # Column widths — disable auto-fit and force widths via XML
        tbl = table._tbl
        tblPr = tbl.tblPr
        tblPr.append(parse_xml(
            f'<w:tblLayout {nsdecls("w")} w:type="fixed"/>'
        ))
        col_widths = (
            [Inches(0.6), Inches(4.6), Inches(1.3)]
            if is_fixed
            else [Inches(0.4), Inches(5.5), Inches(0.6)]
        )
        for row in table.rows:
            for i, width in enumerate(col_widths):
                tc = row.cells[i]._tc
                tcPr = tc.get_or_add_tcPr()
                tcW = parse_xml(
                    f'<w:tcW {nsdecls("w")} w:w="{int(width.emu / 635)}" w:type="dxa"/>'
                )
                tcPr.append(tcW)

        # Header row
        hdr = table.rows[0]
        for idx, text in enumerate(["SR. NO.", "ON ACCOUNT OF", value_heading]):
            cell = hdr.cells[idx]
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(text)
            run.bold = True
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0x00, 0x00, 0x00)

        # Data rows
        total_hours = 0
        total_amount = 0.0
        sym = CURRENCY_SYMBOLS.get(currency, "\u20b9")
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

            hours = detail.get("hours", 0)
            total_hours += hours
            amount = float(detail.get("amount", 0) or 0)
            total_amount += amount

            # Bullet items
            for item_text in detail.get("items", []):
                bp = c1.add_paragraph(style="List Bullet")
                bp.paragraph_format.space_before = Pt(0)
                bp.paragraph_format.space_after = Pt(1)
                bp.paragraph_format.left_indent = Cm(0.6)
                br = bp.add_run(item_text)
                br.font.size = Pt(9)

            # HOURS / AMOUNT
            c2 = row.cells[2]
            p2 = c2.paragraphs[0]
            p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
            value = f"{sym}{amount:,.2f}" if is_fixed else str(hours)
            r2 = p2.add_run(value)
            r2.font.size = Pt(10)
            r2.bold = True

        if is_fixed:
            # Total Amount row
            amt_row = table.add_row()
            amt_row.cells[0].merge(amt_row.cells[1])
            am_cell = amt_row.cells[0]
            pam = am_cell.paragraphs[0]
            pam.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            ram = pam.add_run("Total Amount: ")
            ram.bold = True
            ram.font.size = Pt(11)

            av_cell = amt_row.cells[2]
            pav = av_cell.paragraphs[0]
            pav.alignment = WD_ALIGN_PARAGRAPH.CENTER
            rav = pav.add_run(f"{sym}{total_amount:,.2f}")
            rav.bold = True
            rav.font.size = Pt(12)

            self._add_amount_in_words(doc, total_amount, currency)
            doc.add_paragraph().paragraph_format.space_after = Pt(8)
            return

        # Total Hours row
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

        # Per Hour Rate and Total Amount (if rate provided)
        if per_hour_rate and per_hour_rate > 0:
            total_amount = total_hours * per_hour_rate

            # Rate row
            rate_row = table.add_row()
            rate_row.cells[0].merge(rate_row.cells[1])
            rm_cell = rate_row.cells[0]
            prm = rm_cell.paragraphs[0]
            prm.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            rr = prm.add_run("Per Hour Rate: ")
            rr.bold = True
            rr.font.size = Pt(10)

            rv_cell = rate_row.cells[2]
            prv = rv_cell.paragraphs[0]
            prv.alignment = WD_ALIGN_PARAGRAPH.CENTER
            rrv = prv.add_run(f"{sym}{per_hour_rate:,.0f}")
            rrv.font.size = Pt(10)
            rrv.bold = True

            # Total Amount row
            amt_row = table.add_row()
            amt_row.cells[0].merge(amt_row.cells[1])
            am_cell = amt_row.cells[0]
            pam = am_cell.paragraphs[0]
            pam.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            ram = pam.add_run("Total Amount: ")
            ram.bold = True
            ram.font.size = Pt(11)

            av_cell = amt_row.cells[2]
            pav = av_cell.paragraphs[0]
            pav.alignment = WD_ALIGN_PARAGRAPH.CENTER
            rav = pav.add_run(f"{sym}{total_amount:,.2f}")
            rav.bold = True
            rav.font.size = Pt(12)

            self._add_amount_in_words(doc, total_amount, currency)

        doc.add_paragraph().paragraph_format.space_after = Pt(8)

    def _add_amount_in_words(
        self,
        doc: Document,
        total_amount: float,
        currency: str,
    ):
        """Add the invoice total as words below the line-items table."""
        words_p = doc.add_paragraph()
        words_p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        words_p.paragraph_format.space_before = Pt(6)
        words_p.paragraph_format.space_after = Pt(2)
        wr = words_p.add_run("Amount in Words: ")
        wr.bold = True
        wr.font.size = Pt(9)
        wv = words_p.add_run(amount_in_words(total_amount, currency))
        wv.italic = True
        wv.font.size = Pt(9)

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
        estimated_cost = (
            (self.total_input_tokens / 1_000_000)
            * app_config.CLAUDE_INPUT_COST_PER_MILLION
            + (self.total_output_tokens / 1_000_000)
            * app_config.CLAUDE_OUTPUT_COST_PER_MILLION
        )
        return {
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "estimated_cost": estimated_cost,
        }
