"""
Offer Letter DOCX generator for creating internship offer letters.

Generates a professionally formatted DOCX offer letter using the
Example Company company template.
"""
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import nsdecls
from docx.oxml import parse_xml

logger = logging.getLogger(__name__)

# Path to logo image (same as invoice module)
LOGO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "gui", "static", "logo.png",
)

COMPANY_INFO = {
    "name": "EXAMPLE COMPANY",
    "reg_no": "EXAMPLE-REGISTRATION",
    "tax_no": "EXAMPLE-TAX-ID",
    "email": "billing@example.com",
    "phone": "+1 202-555-0100",
    "address": "123 Example Street, Example City",
    "signatory_name": "Example Owner",
    "signatory_title": "Founder",
}

DEFAULT_KEY_RESPONSIBILITIES = [
    "Understand existing project architecture and workflows",
    "Participate in project discussions and weekly review meetings",
    "Contribute to software development, testing, documentation, research, and feature implementation",
    "Collaborate with team members using GitHub and other project tools",
    "Follow project guidelines, coding standards, and security practices",
]


class OfferLetterGenerator:
    """Generates DOCX internship offer letters from provided details."""

    def generate_offer_letter(
        self,
        data: Dict[str, Any],
        output_path: str,
        logo_path: Optional[str] = None,
    ) -> str:
        """Create the DOCX offer letter file.

        Args:
            data: Dictionary with offer letter fields:
                - candidate_name (str)
                - candidate_email (str, optional)
                - candidate_phone (str, optional)
                - candidate_college (str, optional)
                - issue_date (str) – formatted date string e.g. "3 June 2026"
                - letter_ref (str, optional) – reference/letter number
                - position (str) – e.g. "Software Development Intern"
                - department (str, optional)
                - start_date (str) – e.g. "1 June 2026"
                - duration (str) – e.g. "3 Months"
                - mode (str) – e.g. "Remote"
                - reporting_manager (str)
                - working_hours (str) – e.g. "Flexible"
                - stipend (str) – e.g. "Unpaid Internship (Learning & Project Experience Based)"
                - project_description (str) – custom paragraph about project/work
                - extra_terms (str, optional) – any additional terms/conditions
            output_path: where to save the .docx
            logo_path: optional override for logo image path

        Returns:
            Absolute path to the generated DOCX file.
        """
        logo = logo_path or LOGO_PATH

        doc = Document()

        # -- Page margins --
        for section in doc.sections:
            section.top_margin = Cm(1.5)
            section.bottom_margin = Cm(2.0)
            section.left_margin = Cm(2.5)
            section.right_margin = Cm(2.5)

        # -- Default font --
        style = doc.styles["Normal"]
        font = style.font
        font.name = "Calibri"
        font.size = Pt(10.5)
        font.color.rgb = RGBColor(0x22, 0x22, 0x22)

        # ===== HEADER =====
        self._add_header(doc, logo)

        # ===== HORIZONTAL LINE =====
        self._add_horizontal_line(doc)

        # ===== TITLE =====
        self._add_centered_bold(doc, "INTERNSHIP OFFER LETTER", size=14, space_before=10, space_after=6)

        # ===== DATE & REFERENCE =====
        issue_date = data.get("issue_date", datetime.now().strftime("%d %B %Y"))
        letter_ref = data.get("letter_ref", "")
        date_line = f"Date: {issue_date}"
        if letter_ref:
            date_line += f"     Ref: {letter_ref}"
        self._add_paragraph(doc, date_line, space_before=4, space_after=10)

        # ===== ADDRESSEE =====
        candidate_name = data.get("candidate_name", "").strip()
        self._add_paragraph(doc, "To,", space_after=2)
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(2)
        run = p.add_run(candidate_name)
        run.bold = True
        run.font.size = Pt(10.5)

        if data.get("candidate_email"):
            self._add_paragraph(doc, data["candidate_email"], space_before=0, space_after=1)
        if data.get("candidate_phone"):
            self._add_paragraph(doc, data["candidate_phone"], space_before=0, space_after=1)
        if data.get("candidate_college"):
            self._add_paragraph(doc, data["candidate_college"], space_before=0, space_after=1)

        # ===== SUBJECT =====
        position = data.get("position", "Software Development Intern")
        doc.add_paragraph().paragraph_format.space_after = Pt(6)
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(8)
        r1 = p.add_run("Subject: ")
        r1.bold = True
        r1.font.size = Pt(10.5)
        r2 = p.add_run(f"Offer for {position}")
        r2.font.size = Pt(10.5)

        # ===== SALUTATION =====
        self._add_paragraph(doc, f"Dear {candidate_name},", space_before=0, space_after=8)

        # ===== OPENING =====
        self._add_paragraph(
            doc,
            f"We are pleased to offer you the position of {position} at Example Company.",
            space_before=0,
            space_after=8,
        )

        # ===== PROJECT DESCRIPTION =====
        project_desc = data.get("project_description", "").strip()
        if project_desc:
            self._add_paragraph(doc, project_desc, space_before=0, space_after=10)

        # ===== INTERNSHIP DETAILS =====
        self._add_section_heading(doc, "Internship Details")

        details = [
            ("Position", position),
            ("Start Date", data.get("start_date", "")),
            ("Duration", data.get("duration", "")),
            ("Mode", data.get("mode", "")),
            ("Reporting Manager", data.get("reporting_manager", "")),
            ("Working Hours", data.get("working_hours", "")),
            ("Stipend", data.get("stipend", "")),
        ]
        if data.get("department"):
            details.insert(1, ("Department", data["department"]))

        for label, value in details:
            if value:
                self._add_detail_row(doc, label, value)

        # ===== KEY RESPONSIBILITIES =====
        doc.add_paragraph().paragraph_format.space_after = Pt(6)
        self._add_section_heading(doc, "Key Responsibilities")
        for item in DEFAULT_KEY_RESPONSIBILITIES:
            self._add_bullet(doc, item)

        # ===== CONFIDENTIALITY =====
        doc.add_paragraph().paragraph_format.space_after = Pt(6)
        self._add_section_heading(doc, "Confidentiality")
        self._add_paragraph(
            doc,
            "During the internship, you may receive access to confidential information, source code, "
            "project documentation, business processes, client-related information, and proprietary "
            "intellectual property belonging to Example Company and its clients. Such information must be "
            "treated as strictly confidential and must not be disclosed, copied, distributed, or shared "
            "with any third party without prior written approval from Example Company.",
            space_before=0,
            space_after=8,
        )

        # ===== NATURE OF INTERNSHIP =====
        self._add_section_heading(doc, "Nature of Internship")
        self._add_paragraph(
            doc,
            "This internship is intended to provide practical industry exposure and learning opportunities. "
            "It does not constitute employment and does not create an employer-employee relationship between "
            "Example Company and the intern. Example Company reserves the right to conclude the internship at any time "
            "if deemed necessary.",
            space_before=0,
            space_after=8,
        )

        # ===== EXTRA TERMS =====
        extra_terms = data.get("extra_terms", "").strip()
        if extra_terms:
            self._add_section_heading(doc, "Additional Terms")
            self._add_paragraph(doc, extra_terms, space_before=0, space_after=8)

        # ===== CERTIFICATE OF COMPLETION =====
        self._add_section_heading(doc, "Certificate of Completion")
        self._add_paragraph(
            doc,
            "Upon successful completion of the internship, Example Company will issue an Internship Completion "
            "Certificate outlining the duration of the internship and the areas of contribution.",
            space_before=0,
            space_after=8,
        )

        # ===== ACCEPTANCE =====
        self._add_section_heading(doc, "Acceptance")
        self._add_paragraph(
            doc,
            "Please confirm your acceptance of this internship opportunity by replying to this email.",
            space_before=0,
            space_after=12,
        )

        # ===== CLOSING =====
        self._add_paragraph(
            doc,
            "We look forward to working with you and wish you a successful learning journey with Example Company.",
            space_before=0,
            space_after=16,
        )
        self._add_paragraph(doc, "Sincerely,", space_before=0, space_after=20)

        # ===== SIGNATORY =====
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(COMPANY_INFO["signatory_name"])
        r.bold = True
        r.font.size = Pt(10.5)
        self._add_paragraph(doc, COMPANY_INFO["signatory_title"], space_before=0, space_after=1)
        self._add_paragraph(doc, COMPANY_INFO["name"], space_before=0, space_after=1)
        self._add_paragraph(doc, f"Email: {COMPANY_INFO['email']}", space_before=0, space_after=1)
        self._add_paragraph(doc, f"Phone: {COMPANY_INFO['phone']}", space_before=0, space_after=4)

        # ===== FOOTER LINE =====
        self._add_horizontal_line(doc)
        self._add_footer_line(
            doc,
            f"Firm Reg. No.: {COMPANY_INFO['reg_no']}  |  Professional Tax No.: {COMPANY_INFO['tax_no']}",
        )
        self._add_footer_line(
            doc,
            f"{COMPANY_INFO['address']}  |  {COMPANY_INFO['email']}  |  {COMPANY_INFO['phone']}",
        )

        # Save
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        doc.save(output_path)
        logger.info(f"Offer letter saved to {output_path}")
        return output_path

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _add_header(self, doc: Document, logo_path: str = None):
        """Add company logo (if available) or bold company name header."""
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p.paragraph_format.space_after = Pt(4)
        if logo_path and os.path.isfile(logo_path):
            run = p.add_run()
            run.add_picture(logo_path, width=Inches(1.8))
        else:
            run = p.add_run(COMPANY_INFO["name"])
            run.bold = True
            run.font.size = Pt(20)
            run.font.color.rgb = RGBColor(0x00, 0x00, 0x00)

        # Sub-header with reg details
        sub = doc.add_paragraph()
        sub.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        sub.paragraph_format.space_before = Pt(0)
        sub.paragraph_format.space_after = Pt(2)
        r = sub.add_run(
            f"Firm Reg. No.: {COMPANY_INFO['reg_no']}  |  Professional Tax No.: {COMPANY_INFO['tax_no']}"
        )
        r.font.size = Pt(7.5)
        r.font.color.rgb = RGBColor(0x77, 0x77, 0x77)

        sub2 = doc.add_paragraph()
        sub2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        sub2.paragraph_format.space_before = Pt(0)
        sub2.paragraph_format.space_after = Pt(2)
        r2 = sub2.add_run(f"{COMPANY_INFO['email']}  |  {COMPANY_INFO['phone']}")
        r2.font.size = Pt(7.5)
        r2.font.color.rgb = RGBColor(0x77, 0x77, 0x77)

    def _add_horizontal_line(self, doc: Document):
        """Add a thin horizontal rule."""
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(6)
        pPr = p._p.get_or_add_pPr()
        pBdr = parse_xml(
            f'<w:pBdr {nsdecls("w")}>'
            '  <w:bottom w:val="single" w:sz="6" w:space="1" w:color="AAAAAA"/>'
            '</w:pBdr>'
        )
        pPr.append(pBdr)

    def _add_centered_bold(self, doc: Document, text: str, size: int = 12,
                           space_before: int = 4, space_after: int = 4):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(space_before)
        p.paragraph_format.space_after = Pt(space_after)
        run = p.add_run(text)
        run.bold = True
        run.font.size = Pt(size)
        run.font.color.rgb = RGBColor(0x11, 0x11, 0x11)

    def _add_paragraph(self, doc: Document, text: str, bold: bool = False,
                       size: int = 10, space_before: int = 0, space_after: int = 6):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(space_before)
        p.paragraph_format.space_after = Pt(space_after)
        run = p.add_run(text)
        run.bold = bold
        run.font.size = Pt(size if size != 10 else 10.5)

    def _add_section_heading(self, doc: Document, text: str):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(text)
        run.bold = True
        run.font.size = Pt(11)
        run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x1A)
        # Underline section headings subtly
        run.underline = True

    def _add_detail_row(self, doc: Document, label: str, value: str):
        """Add a bold label: value line for internship details."""
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(3)
        r1 = p.add_run(f"{label}: ")
        r1.bold = True
        r1.font.size = Pt(10.5)
        r2 = p.add_run(value)
        r2.font.size = Pt(10.5)

    def _add_bullet(self, doc: Document, text: str):
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.left_indent = Cm(0.6)
        run = p.add_run(text)
        run.font.size = Pt(10.5)

    def _add_footer_line(self, doc: Document, text: str):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(1)
        run = p.add_run(text)
        run.font.size = Pt(7.5)
        run.font.color.rgb = RGBColor(0x88, 0x88, 0x88)
