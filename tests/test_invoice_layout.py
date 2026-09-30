import os
import tempfile
import unittest
from io import BytesIO

from docx import Document
from docx.oxml.ns import qn

from src.core.invoice_generator import InvoiceGenerator
from src.core.invoice_layout import normalize_invoice_layout


class InvoiceLayoutTests(unittest.TestCase):
    def _invoice(self, path, mode='fixed'):
        InvoiceGenerator(enable_ai=False).generate_invoice(
            work_details=[{'category': 'Annual maintenance', 'items': ['Support and updates'],
                           'amount': 12500, 'hours': 25}],
            bill_to={'name': 'Example Client'},
            invoice_meta={'invoice_no': 'INV-1'},
            output_path=path, pricing_mode=mode, per_hour_rate=500,
        )
        return Document(path)

    def test_branding_is_in_repeating_regions_and_widths_include_totals(self):
        with tempfile.TemporaryDirectory() as directory:
            for mode in ['fixed', 'hourly']:
                with self.subTest(mode=mode):
                    document = self._invoice(os.path.join(directory, mode + '.docx'), mode)
                    section = document.sections[0]
                    self.assertTrue(section.header._element.xpath('.//w:drawing'))
                    self.assertIn('example.com', '\n'.join(p.text for p in section.footer.paragraphs))
                    self.assertNotIn('billing@example.com', '\n'.join(p.text for p in document.paragraphs))
                    table = document.tables[1]
                    widths = [column.width.twips for column in table.columns]
                    self.assertLess(widths[0], widths[2])
                    self.assertLess(widths[2], widths[1])
                    self.assertAlmostEqual(sum(widths), (section.page_width - section.left_margin - section.right_margin) / 635, delta=1)
                    for row in table.rows:
                        self.assertEqual(sum(int(cell.tcPr.tcW.w) for cell in row._tr.tc_lst), sum(widths))
                        for cell in row._tr.tc_lst:
                            self.assertEqual(len(cell.tcPr.findall(qn('w:tcW'))), 1)

    def test_legacy_body_branding_migrates_without_changing_invoice_content(self):
        with tempfile.TemporaryDirectory() as directory:
            document = self._invoice(os.path.join(directory, 'invoice.docx'))
            section = document.sections[0]
            # Recreate the old body-based header/footer structure.
            for p in reversed(list(section.header.paragraphs)):
                document._element.body.insert(0, p._p)
                for blip in p._p.xpath('.//a:blip'):
                    rid = blip.get(qn('r:embed'))
                    new_rid, _ = document.part.get_or_add_image(BytesIO(section.header.part.related_parts[rid].blob))
                    blip.set(qn('r:embed'), new_rid)
            for p in list(section.footer.paragraphs):
                document._element.body.insert(-1, p._p)
            before = [[cell.text for cell in row.cells] for table in document.tables for row in table.rows]
            normalize_invoice_layout(document)
            first_xml = document._element.xml
            normalize_invoice_layout(document)
            self.assertEqual(first_xml, document._element.xml)
            self.assertTrue(section.header._element.xpath('.//w:drawing'))
            self.assertEqual(before, [[cell.text for cell in row.cells] for table in document.tables for row in table.rows])


if __name__ == '__main__':
    unittest.main()
