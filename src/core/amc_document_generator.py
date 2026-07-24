"""Deterministic DOCX renderer for approved AMC drafts."""

import os
from datetime import datetime
from typing import Any, Dict, Iterable, List
from urllib.parse import urlparse

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches, Pt, RGBColor


LOGO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "gui",
    "static",
    "logo.png",
)

BLUE = RGBColor(0x2E, 0x74, 0xB5)
DARK_BLUE = RGBColor(0x1F, 0x4D, 0x78)
INK = RGBColor(0x22, 0x22, 0x22)
MUTED = RGBColor(0x66, 0x66, 0x66)
LIGHT_FILL = "F4F6F9"
TABLE_FILL = "E8EEF5"
CONTENT_WIDTH_DXA = 9360
TABLE_INDENT_DXA = 120


def _maintenance_items(facts: Dict[str, Any]) -> List[Dict[str, str]]:
    items = facts.get("maintenance_items")
    if isinstance(items, list):
        normalized = [
            {
                "service_type": str(item.get("service_type", "")).strip(),
                "asset_name": str(item.get("asset_name", "")).strip(),
                "asset_url": str(item.get("asset_url", "")).strip(),
            }
            for item in items
            if isinstance(item, dict) and item.get("asset_name")
        ]
        if normalized:
            return normalized
    return [{
        "service_type": str(facts.get("service_type", "")).strip(),
        "asset_name": str(
            facts.get("asset_name", "Maintenance Services")
        ).strip(),
        "asset_url": str(facts.get("asset_url", "")).strip(),
    }]


def _asset_summary(facts: Dict[str, Any], compact: bool = False) -> str:
    names = [item["asset_name"] for item in _maintenance_items(facts)]
    if compact and len(names) > 2:
        return f"{names[0]} + {len(names) - 1} more"
    return " • ".join(names)


class AmcDocumentGenerator:
    """Render an AI-created AMC JSON draft into a polished Word document."""

    def generate(
        self,
        *,
        draft: Dict[str, Any],
        facts: Dict[str, Any],
        client: Dict[str, Any],
        settings: Dict[str, Any],
        output_path: str,
        logo_path: str = None,
    ) -> str:
        doc = Document()
        self._configure_document(doc)
        self._add_running_furniture(
            doc,
            asset_name=_asset_summary(facts, compact=True),
            settings=settings,
        )

        self._add_cover(
            doc,
            draft=draft,
            facts=facts,
            client=client,
            settings=settings,
            logo_path=logo_path or LOGO_PATH,
        )
        doc.add_page_break()

        self._add_contract_header(doc, draft["title"], facts)
        self._add_body_paragraph(doc, draft["opening"])
        self._add_body_paragraph(doc, draft["overview"])

        self._add_heading(doc, "Contract Details", level=1)
        self._add_contract_details_table(doc, facts, client, settings)

        self._add_heading(doc, "Services Included", level=1)
        for item in draft.get("scope_included", []):
            self._add_bullet(doc, item)

        excluded = draft.get("scope_excluded", [])
        if excluded:
            self._add_heading(doc, "Services Excluded", level=1)
            for item in excluded:
                self._add_bullet(doc, item)

        service_levels = draft.get("service_levels", [])
        if service_levels:
            self._add_heading(doc, "Service Levels", level=1)
            self._add_service_levels_table(doc, service_levels)

        self._add_heading(doc, "Commercial Terms", level=1)
        self._add_commercial_table(doc, facts, settings)

        for clause in draft.get("clauses", []):
            self._add_heading(doc, clause["heading"], level=1)
            self._add_body_paragraph(doc, clause["body"])

        if settings.get("include_bank_details") and settings.get("bank_details"):
            self._add_heading(doc, "Bank Details", level=1)
            self._add_bank_details(doc, settings["bank_details"])

        self._add_heading(doc, "Signatures", level=1)
        self._add_signature_table(doc, client, settings)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        doc.core_properties.title = draft["title"]
        doc.core_properties.subject = "Annual Maintenance Contract"
        doc.core_properties.author = settings.get("provider_name", "Example Company")
        doc.core_properties.keywords = "AMC, annual maintenance contract"
        doc.core_properties.created = datetime.now()
        doc.save(output_path)
        return output_path

    def _configure_document(self, doc: Document) -> None:
        section = doc.sections[0]
        section.page_width = Inches(8.5)
        section.page_height = Inches(11)
        section.top_margin = Inches(1)
        section.right_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.header_distance = Inches(0.492)
        section.footer_distance = Inches(0.492)
        section.start_type = WD_SECTION.NEW_PAGE

        normal = doc.styles["Normal"]
        self._set_style_font(normal, "Calibri", 11, INK)
        normal.paragraph_format.space_before = Pt(0)
        normal.paragraph_format.space_after = Pt(8)
        normal.paragraph_format.line_spacing = 1.333
        normal.paragraph_format.widow_control = True

        heading_tokens = {
            "Heading 1": (16, BLUE, 18, 10),
            "Heading 2": (13, BLUE, 12, 6),
            "Heading 3": (12, DARK_BLUE, 8, 4),
        }
        for name, (size, color, before, after) in heading_tokens.items():
            style = doc.styles[name]
            self._set_style_font(style, "Calibri", size, color, bold=True)
            style.paragraph_format.space_before = Pt(before)
            style.paragraph_format.space_after = Pt(after)
            style.paragraph_format.keep_with_next = True

        bullet = doc.styles["List Bullet"]
        self._set_style_font(bullet, "Calibri", 11, INK)
        bullet.paragraph_format.left_indent = Inches(0.375)
        bullet.paragraph_format.first_line_indent = Inches(-0.188)
        bullet.paragraph_format.space_after = Pt(4)
        bullet.paragraph_format.line_spacing = 1.208

    @staticmethod
    def _set_style_font(style, name, size, color, bold=None):
        style.font.name = name
        style._element.rPr.rFonts.set(qn("w:ascii"), name)
        style._element.rPr.rFonts.set(qn("w:hAnsi"), name)
        style.font.size = Pt(size)
        style.font.color.rgb = color
        if bold is not None:
            style.font.bold = bold

    def _add_running_furniture(
        self,
        doc: Document,
        asset_name: str,
        settings: Dict[str, Any],
    ) -> None:
        section = doc.sections[0]
        header = section.header
        p = header.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(f"ANNUAL MAINTENANCE CONTRACT | {asset_name}")
        self._format_run(run, size=8, color=MUTED, bold=True)

        footer = section.footer
        address = str(settings.get("provider_address", "")).strip()
        contact_parts = [
            "AMC",
            self._display_website(settings.get("provider_website", "")),
            str(settings.get("provider_phone", "")).strip(),
            str(settings.get("provider_email", "")).strip(),
        ]
        contact_line = "  |  ".join(part for part in contact_parts if part)

        address_paragraph = footer.paragraphs[0]
        address_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        address_paragraph.paragraph_format.space_before = Pt(0)
        address_paragraph.paragraph_format.space_after = Pt(1)
        address_paragraph.paragraph_format.line_spacing = 1
        self._set_paragraph_top_border(address_paragraph, color="B7C9DC")
        address_run = address_paragraph.add_run(address)
        self._format_run(
            address_run,
            size=8,
            color=DARK_BLUE,
            bold=True,
        )

        contact_paragraph = footer.add_paragraph()
        contact_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        contact_paragraph.paragraph_format.space_before = Pt(0)
        contact_paragraph.paragraph_format.space_after = Pt(0)
        contact_paragraph.paragraph_format.line_spacing = 1
        contact_run = contact_paragraph.add_run(contact_line)
        self._format_run(
            contact_run,
            size=8,
            color=DARK_BLUE,
            bold=True,
        )

    @staticmethod
    def _display_website(value: Any) -> str:
        website = str(value or "").strip()
        if not website:
            return ""
        parsed = urlparse(
            website if "://" in website else f"https://{website}"
        )
        display = parsed.netloc or parsed.path
        if display.lower().startswith("www."):
            display = display[4:]
        return display.rstrip("/")

    @staticmethod
    def _set_paragraph_top_border(paragraph, color: str) -> None:
        paragraph_properties = paragraph._p.get_or_add_pPr()
        borders = paragraph_properties.find(qn("w:pBdr"))
        if borders is None:
            borders = OxmlElement("w:pBdr")
            paragraph_properties.append(borders)
        top = borders.find(qn("w:top"))
        if top is None:
            top = OxmlElement("w:top")
            borders.append(top)
        top.set(qn("w:val"), "single")
        top.set(qn("w:sz"), "6")
        top.set(qn("w:space"), "5")
        top.set(qn("w:color"), color)

    def _add_cover(
        self,
        doc: Document,
        *,
        draft: Dict[str, Any],
        facts: Dict[str, Any],
        client: Dict[str, Any],
        settings: Dict[str, Any],
        logo_path: str,
    ) -> None:
        if logo_path and os.path.isfile(logo_path):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(30)
            p.add_run().add_picture(logo_path, width=Inches(1.8))
        else:
            self._add_centered_text(
                doc,
                settings.get("provider_name", "EXAMPLE COMPANY").upper(),
                size=13,
                color=MUTED,
                bold=True,
                after=30,
            )

        self._add_centered_text(
            doc,
            draft["title"],
            size=26,
            color=INK,
            bold=True,
            after=10,
        )
        self._add_centered_text(
            doc,
            _asset_summary(facts),
            size=15,
            color=DARK_BLUE,
            after=6,
        )
        maintenance_items = _maintenance_items(facts)
        if len(maintenance_items) == 1 and maintenance_items[0]["asset_url"]:
            self._add_centered_text(
                doc,
                maintenance_items[0]["asset_url"],
                size=10,
                color=MUTED,
                after=42,
            )
        else:
            self._add_spacer(doc, 36)

        table = doc.add_table(rows=4, cols=2)
        self._set_table_geometry(table, [4680, 4680])
        table.style = "Table Grid"
        rows = [
            ("Prepared for", client.get("name", "")),
            (
                "Prepared by",
                f"{settings.get('provider_owner_name', '')}, "
                f"{settings.get('provider_name', 'Example Company')}",
            ),
            ("Effective date", facts.get("effective_date_display", "")),
            ("Contract reference", facts.get("contract_reference", "")),
        ]
        for row, (label, value) in zip(table.rows, rows):
            self._set_cell_text(row.cells[0], label, bold=True, fill=LIGHT_FILL)
            self._set_cell_text(row.cells[1], value)

        self._add_spacer(doc, 36)
        self._add_centered_text(
            doc,
            "Confidential business document",
            size=9,
            color=MUTED,
            after=0,
        )

    def _add_contract_header(
        self, doc: Document, title: str, facts: Dict[str, Any]
    ) -> None:
        self._add_centered_text(
            doc,
            title.upper(),
            size=17,
            color=INK,
            bold=True,
            after=5,
        )
        ref = facts.get("contract_reference", "")
        if ref:
            self._add_centered_text(
                doc,
                f"Reference: {ref}",
                size=9,
                color=MUTED,
                after=18,
            )

    def _add_contract_details_table(
        self,
        doc: Document,
        facts: Dict[str, Any],
        client: Dict[str, Any],
        settings: Dict[str, Any],
    ) -> None:
        client_address = ", ".join(
            part
            for part in [
                client.get("address_line1", ""),
                client.get("address_line2", ""),
            ]
            if part
        )
        rows = [
            ("Service Provider", settings.get("provider_name", "Example Company")),
            ("Service Provider Address", settings.get("provider_address", "")),
            ("Client / Website Owner", client.get("name", "")),
            ("Client Address", client_address or "As communicated in writing"),
        ]
        maintenance_items = _maintenance_items(facts)
        for index, item in enumerate(maintenance_items, 1):
            label = (
                "Maintenance Item"
                if len(maintenance_items) == 1
                else f"Maintenance Item {index}"
            )
            value = f"{item['service_type']} — {item['asset_name']}"
            if item["asset_url"]:
                value += f"\n{item['asset_url']}"
            rows.append((label, value))
        rows.append((
                "Contract Period",
                f"{facts.get('effective_date_display', '')} to "
                f"{facts.get('end_date_display', '')}",
        ))
        table = doc.add_table(rows=len(rows), cols=2)
        self._set_table_geometry(table, [3000, 6360])
        table.style = "Table Grid"
        for row, (label, value) in zip(table.rows, rows):
            self._set_cell_text(row.cells[0], label, bold=True, fill=LIGHT_FILL)
            self._set_cell_text(row.cells[1], value)

    def _add_service_levels_table(
        self, doc: Document, service_levels: List[Dict[str, str]]
    ) -> None:
        table = doc.add_table(rows=1 + len(service_levels), cols=2)
        self._set_table_geometry(table, [3600, 5760])
        table.style = "Table Grid"
        self._set_cell_text(
            table.rows[0].cells[0], "Service", bold=True, fill=TABLE_FILL
        )
        self._set_cell_text(
            table.rows[0].cells[1], "Commitment", bold=True, fill=TABLE_FILL
        )
        self._mark_header_row(table.rows[0])
        for row, item in zip(table.rows[1:], service_levels):
            self._set_cell_text(row.cells[0], item.get("service", ""))
            self._set_cell_text(row.cells[1], item.get("commitment", ""))

    def _add_commercial_table(
        self,
        doc: Document,
        facts: Dict[str, Any],
        settings: Dict[str, Any],
    ) -> None:
        amount = facts.get("annual_fee", "0")
        currency = facts.get("currency", "INR")
        display_amount = self._format_amount(amount, currency)
        rows = [
            ("Annual maintenance fee", display_amount),
            ("Payment schedule", settings.get("payment_schedule", "")),
            ("Taxes", facts.get("tax_note") or "As applicable"),
        ]
        table = doc.add_table(rows=1 + len(rows), cols=2)
        self._set_table_geometry(table, [6200, 3160])
        table.style = "Table Grid"
        self._set_cell_text(
            table.rows[0].cells[0], "Description", bold=True, fill=TABLE_FILL
        )
        self._set_cell_text(
            table.rows[0].cells[1], "Terms", bold=True, fill=TABLE_FILL
        )
        self._mark_header_row(table.rows[0])
        for row, (label, value) in zip(table.rows[1:], rows):
            self._set_cell_text(row.cells[0], label)
            self._set_cell_text(
                row.cells[1],
                value,
                bold=label == "Annual maintenance fee",
            )

    def _add_bank_details(self, doc: Document, bank_details: str) -> None:
        pairs = []
        for line in bank_details.splitlines():
            clean = line.strip()
            if not clean:
                continue
            if ":" in clean:
                label, value = clean.split(":", 1)
                pairs.append((label.strip(), value.strip()))
            else:
                pairs.append(("Details", clean))
        if not pairs:
            return
        table = doc.add_table(rows=len(pairs), cols=2)
        self._set_table_geometry(table, [2700, 6660])
        table.style = "Table Grid"
        for row, (label, value) in zip(table.rows, pairs):
            self._set_cell_text(row.cells[0], label, bold=True, fill=LIGHT_FILL)
            self._set_cell_text(row.cells[1], value)

    def _add_signature_table(
        self,
        doc: Document,
        client: Dict[str, Any],
        settings: Dict[str, Any],
    ) -> None:
        table = doc.add_table(rows=5, cols=2)
        self._set_table_geometry(table, [4680, 4680])
        table.style = "Table Grid"
        left = [
            settings.get("provider_name", "Example Company"),
            "Signature",
            settings.get("provider_owner_name", "Example Owner"),
            settings.get("provider_signatory_title", "Proprietor"),
            "Date:",
        ]
        right = [
            client.get("name", ""),
            "Signature",
            client.get("signatory_name") or "Authorized Signatory",
            client.get("signatory_title", ""),
            "Date:",
        ]
        for index, row in enumerate(table.rows):
            row_properties = row._tr.get_or_add_trPr()
            row_properties.append(OxmlElement("w:cantSplit"))
            self._set_cell_text(
                row.cells[0],
                left[index],
                bold=index in {0, 2},
                fill=LIGHT_FILL if index == 0 else None,
            )
            self._set_cell_text(
                row.cells[1],
                right[index],
                bold=index in {0, 2},
                fill=LIGHT_FILL if index == 0 else None,
            )
            if index == 1:
                row.cells[0].paragraphs[0].paragraph_format.space_before = Pt(36)
                row.cells[1].paragraphs[0].paragraph_format.space_before = Pt(36)
            if index < len(table.rows) - 1:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        paragraph.paragraph_format.keep_with_next = True

    def _add_heading(self, doc: Document, text: str, level: int = 1) -> None:
        paragraph = doc.add_paragraph(style=f"Heading {level}")
        paragraph.add_run(text)

    def _add_body_paragraph(self, doc: Document, text: str) -> None:
        paragraph = doc.add_paragraph(style="Normal")
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        paragraph.add_run(text)

    def _add_bullet(self, doc: Document, text: str) -> None:
        paragraph = doc.add_paragraph(style="List Bullet")
        paragraph.add_run(f" {text}")

    def _add_centered_text(
        self,
        doc: Document,
        text: str,
        *,
        size: float,
        color: RGBColor,
        bold: bool = False,
        after: float = 0,
    ) -> None:
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(after)
        run = paragraph.add_run(text)
        self._format_run(run, size=size, color=color, bold=bold)

    @staticmethod
    def _add_spacer(doc: Document, points: float) -> None:
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(points)

    @staticmethod
    def _format_run(run, *, size, color, bold=False):
        run.font.name = "Calibri"
        run._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
        run._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
        run.font.size = Pt(size)
        run.font.color.rgb = color
        run.bold = bold

    @staticmethod
    def _add_field(run, instruction: str) -> None:
        begin = OxmlElement("w:fldChar")
        begin.set(qn("w:fldCharType"), "begin")
        instr = OxmlElement("w:instrText")
        instr.set(qn("xml:space"), "preserve")
        instr.text = instruction
        separate = OxmlElement("w:fldChar")
        separate.set(qn("w:fldCharType"), "separate")
        text = OxmlElement("w:t")
        text.text = "1"
        end = OxmlElement("w:fldChar")
        end.set(qn("w:fldCharType"), "end")
        run._r.extend([begin, instr, separate, text, end])

    def _set_cell_text(
        self,
        cell,
        text: Any,
        *,
        bold: bool = False,
        fill: str = None,
    ) -> None:
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        paragraph = cell.paragraphs[0]
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.line_spacing = 1.15
        run = paragraph.add_run(str(text or ""))
        self._format_run(run, size=10, color=INK, bold=bold)
        if fill:
            shading = parse_xml(
                f'<w:shd {nsdecls("w")} w:fill="{fill}"/>'
            )
            cell._tc.get_or_add_tcPr().append(shading)

    def _set_table_geometry(self, table, widths_dxa: Iterable[int]) -> None:
        widths = list(widths_dxa)
        if sum(widths) != CONTENT_WIDTH_DXA:
            raise ValueError("AMC table widths must total 9360 DXA")
        table.autofit = False

        tbl_pr = table._tbl.tblPr
        tbl_w = tbl_pr.find(qn("w:tblW"))
        if tbl_w is None:
            tbl_w = OxmlElement("w:tblW")
            tbl_pr.append(tbl_w)
        tbl_w.set(qn("w:w"), str(CONTENT_WIDTH_DXA))
        tbl_w.set(qn("w:type"), "dxa")

        tbl_ind = tbl_pr.find(qn("w:tblInd"))
        if tbl_ind is None:
            tbl_ind = OxmlElement("w:tblInd")
            tbl_pr.append(tbl_ind)
        tbl_ind.set(qn("w:w"), str(TABLE_INDENT_DXA))
        tbl_ind.set(qn("w:type"), "dxa")

        grid = table._tbl.tblGrid
        for grid_col, width in zip(grid.gridCol_lst, widths):
            grid_col.set(qn("w:w"), str(width))

        for row in table.rows:
            for cell, width in zip(row.cells, widths):
                cell.width = Inches(width / 1440)
                tc_pr = cell._tc.get_or_add_tcPr()
                tc_w = tc_pr.find(qn("w:tcW"))
                if tc_w is None:
                    tc_w = OxmlElement("w:tcW")
                    tc_pr.append(tc_w)
                tc_w.set(qn("w:w"), str(width))
                tc_w.set(qn("w:type"), "dxa")
                self._set_cell_margins(cell, top=80, bottom=80, start=120, end=120)

    @staticmethod
    def _set_cell_margins(cell, **margins) -> None:
        tc_pr = cell._tc.get_or_add_tcPr()
        tc_mar = tc_pr.first_child_found_in("w:tcMar")
        if tc_mar is None:
            tc_mar = OxmlElement("w:tcMar")
            tc_pr.append(tc_mar)
        for margin in ("top", "start", "bottom", "end"):
            node = tc_mar.find(qn(f"w:{margin}"))
            if node is None:
                node = OxmlElement(f"w:{margin}")
                tc_mar.append(node)
            node.set(qn("w:w"), str(margins.get(margin, 80)))
            node.set(qn("w:type"), "dxa")

    @staticmethod
    def _mark_header_row(row) -> None:
        tr_pr = row._tr.get_or_add_trPr()
        tbl_header = OxmlElement("w:tblHeader")
        tbl_header.set(qn("w:val"), "true")
        tr_pr.append(tbl_header)

    @staticmethod
    def _format_amount(amount: Any, currency: str) -> str:
        try:
            numeric = float(amount)
            number = f"{numeric:,.2f}".rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            number = str(amount)
        symbol = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}.get(
            currency, f"{currency} "
        )
        return f"{symbol}{number}"
