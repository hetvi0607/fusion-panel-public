"""Consistent Word layout for new invoices and previously generated invoices."""
from io import BytesIO

from docx.shared import Cm, Pt
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.text.paragraph import Paragraph


def _move_paragraph(paragraph, target):
    # Images belong to a document part. Recreate their relationships when moving
    # the logo from the body into the header part.
    for image in paragraph._p.xpath('.//a:blip'):
        rid = image.get(qn('r:embed'))
        if rid:
            blob = paragraph.part.related_parts[rid].blob
            new_rid, _ = target.part.get_or_add_image(BytesIO(blob))
            image.set(qn('r:embed'), new_rid)
    target._element.append(paragraph._p)


def _format_table(table, widths):
    table.autofit = False
    table._tbl.tblPr.find(qn('w:tblW')).set(qn('w:type'), 'dxa')
    table._tbl.tblPr.find(qn('w:tblW')).set(qn('w:w'), str(sum(widths)))
    for column, width in zip(table.columns, widths):
        column.width = width * 635
    # Replace duplicate tcW elements, and respect merged totals cells.
    for row in table.rows:
        row_properties = row._tr.get_or_add_trPr()
        if row_properties.find(qn('w:cantSplit')) is None:
            row_properties.append(OxmlElement('w:cantSplit'))
        column_index = 0
        for cell in row._tr.tc_lst:
            properties = cell.get_or_add_tcPr()
            span = properties.grid_span
            for existing in list(properties.findall(qn('w:tcW'))):
                properties.remove(existing)
            properties.get_or_add_tcW().set(qn('w:w'), str(sum(widths[column_index:column_index + span])))
            properties.tcW.set(qn('w:type'), 'dxa')
            column_index += span
        for cell in row.cells:
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            for paragraph in cell.paragraphs:
                fmt = paragraph.paragraph_format
                fmt.space_before = Pt(0)
                fmt.space_after = Pt(2 if paragraph.style.name == 'List Bullet' else 0)
                fmt.line_spacing = 1.1
                if paragraph.style.name == 'List Bullet':
                    fmt.left_indent = Cm(0.4)
                    fmt.first_line_indent = Cm(-0.2)
    props = table._tbl.tblPr
    old = props.find(qn('w:tblCellMar'))
    if old is not None:
        props.remove(old)
    margins = OxmlElement('w:tblCellMar')
    for side, width in [('top', 90), ('bottom', 90), ('left', 110), ('right', 110)]:
        element = OxmlElement('w:' + side)
        element.set(qn('w:w'), str(width))
        element.set(qn('w:type'), 'dxa')
        margins.append(element)
    props.append(margins)


def normalize_invoice_layout(document):
    """Move legacy branding into repeating regions and fix invoice geometry.

    Only the application's invoice structure is accepted; client text and
    amounts are preserved. Calling this again leaves the same layout.
    """
    paragraphs = document.paragraphs
    if not any(p.text == 'INVOICE CUM RECEIPT' for p in paragraphs):
        raise ValueError('Unrecognized invoice document layout.')
    section = document.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(3)
    section.bottom_margin = Cm(2)
    section.left_margin = section.right_margin = Cm(2)
    section.header_distance = Cm(0.7)
    section.footer_distance = Cm(0.7)
    section.different_first_page_header_footer = False

    title_index = next(i for i, p in enumerate(paragraphs) if p.text == 'INVOICE CUM RECEIPT')
    if title_index:
        for p in list(section.header.paragraphs):
            section.header._element.remove(p._p)
        for p in paragraphs[:title_index]:
            _move_paragraph(p, section.header)
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(2)

    # The legacy generator ends with a rule followed by the two contact lines.
    paragraphs = document.paragraphs
    if len(paragraphs) >= 3 and '  |  ' in paragraphs[-1].text:
        for p in list(section.footer.paragraphs):
            section.footer._element.remove(p._p)
        for p in paragraphs[-3:]:
            _move_paragraph(p, section.footer)
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(1)
            p.paragraph_format.line_spacing = 1

    # Empty body paragraphs previously accumulated default line-height and
    # spacing between tables. Use explicit spacing on the following table.
    for p in list(document.paragraphs):
        if not p.text and not p._p.xpath('.//w:drawing'):
            p._p.getparent().remove(p._p)
    for table in document.tables:
        available = int((section.page_width - section.left_margin - section.right_margin) / 635)
        if len(table.columns) == 2:
            widths = [available // 2, available - available // 2]
        else:
            # 10% serial number, 68% description, 22% amount/hours.
            widths = [round(available * 0.10), round(available * 0.68)]
            widths.append(available - sum(widths))
            header = table.rows[0]._tr.get_or_add_trPr()
            if header.find(qn('w:tblHeader')) is None:
                header.append(OxmlElement('w:tblHeader'))
        _format_table(table, widths)
        # Word requires a paragraph between adjacent tables to keep them apart.
        spacer = OxmlElement('w:p')
        table._tbl.addprevious(spacer)
        fmt = Paragraph(spacer, document).paragraph_format
        fmt.space_before = fmt.space_after = Pt(0)
        fmt.line_spacing = Pt(8)
    return document
