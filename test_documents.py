import io
import unittest
import zipfile
from xml.etree import ElementTree

import documents


WORD_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': WORD_NS}


def attr(name):
    return f'{{{WORD_NS}}}{name}'


def paragraph_text(paragraph):
    return ''.join(node.text or '' for node in paragraph.iter(attr('t')))


class ATSDocumentTests(unittest.TestCase):
    def open_document(self, text, kind='resume'):
        archive = zipfile.ZipFile(io.BytesIO(documents.docx(text, kind=kind)))
        self.addCleanup(archive.close)
        return archive, ElementTree.fromstring(archive.read('word/document.xml'))

    def test_unicode_resume_text_keeps_its_reading_order(self):
        lines = [
            'Zoë 李',
            'zoe@example.test | Darwin, NT | +61 400 000 000',
            'PROFESSIONAL SUMMARY',
            'Support specialist with café, retail & customer service experience.',
            'SKILLS',
            'Python, customer service, Français',
            'WORK EXPERIENCE',
            'Customer Support Officer — Example Company | Jan 2022 – Present',
            '• Resolved requests using <internal> tools & documented outcomes.',
            'EDUCATION AND CERTIFICATIONS',
            'Diplôme in Business, 2021',
        ]
        _, root = self.open_document('\n'.join(lines))
        body = root.find('w:body', NS)
        self.assertIsNotNone(body)
        paragraphs = body.findall('w:p', NS)
        self.assertEqual([paragraph_text(p) for p in paragraphs], lines)
        self.assertEqual(list(root.iter(attr('t'))), list(body.iter(attr('t'))))

    def test_resume_layout_has_one_column_and_no_objects_that_hide_text(self):
        archive, root = self.open_document(
            'Example Person\nexample@example.test\nSKILLS\nPython, Excel'
        )
        sections = root.findall('.//w:sectPr', NS)
        self.assertTrue(sections, 'The document must explicitly define its layout.')
        for section in sections:
            columns = section.find('w:cols', NS)
            self.assertIsNotNone(columns, 'Use an explicit single-column layout.')
            self.assertEqual(columns.get(attr('num')), '1')
        forbidden = {
            'tbl', 'drawing', 'pict', 'txbxContent', 'textbox',
            'headerReference', 'footerReference',
        }
        self.assertFalse(
            forbidden.intersection(node.tag.rsplit('}', 1)[-1] for node in root.iter())
        )
        self.assertFalse(
            any(name.startswith(('word/header', 'word/footer')) for name in archive.namelist())
        )

    def test_normal_text_uses_an_attached_arial_eleven_point_style(self):
        archive, _ = self.open_document('Example Person\nProfessional experience')
        styles = ElementTree.fromstring(archive.read('word/styles.xml'))
        normal = styles.find("w:style[@w:styleId='Normal']", NS)
        self.assertIsNotNone(normal)
        fonts = normal.find('w:rPr/w:rFonts', NS)
        self.assertIsNotNone(fonts)
        self.assertEqual(fonts.get(attr('ascii')), 'Arial')
        self.assertEqual(fonts.get(attr('hAnsi')), 'Arial')
        size = normal.find('w:rPr/w:sz', NS)
        self.assertIsNotNone(size)
        self.assertEqual(size.get(attr('val')), '22')

        relationships = ElementTree.fromstring(archive.read('word/_rels/document.xml.rels'))
        self.assertTrue(any(
            relationship.get('Type', '').endswith('/styles')
            and relationship.get('Target') in ('styles.xml', '/word/styles.xml')
            for relationship in relationships
        ), 'The document must reference its styles so Word applies them.')

    def test_standard_resume_sections_use_heading_paragraphs(self):
        headings = [
            'PROFESSIONAL SUMMARY', 'SKILLS', 'WORK EXPERIENCE',
            'EDUCATION AND CERTIFICATIONS',
        ]
        lines = ['Example Person']
        for heading in headings:
            lines.extend([heading, 'Verified profile content'])
        archive, root = self.open_document('\n'.join(lines))
        for paragraph in root.findall('w:body/w:p', NS):
            if paragraph_text(paragraph) in headings:
                style = paragraph.find('w:pPr/w:pStyle', NS)
                self.assertIsNotNone(style)
                self.assertEqual(style.get(attr('val')), 'Heading1')
        styles = ElementTree.fromstring(archive.read('word/styles.xml'))
        self.assertIsNotNone(styles.find("w:style[@w:styleId='Heading1']", NS))

    def test_cover_letter_greeting_is_not_formatted_as_a_candidate_name(self):
        lines = ['Dear Hiring Manager,', 'I am applying for the advertised role.', 'Kind regards,', 'Zoë 李']
        _, root = self.open_document('\n'.join(lines), kind='cover_letter')
        paragraphs = root.findall('w:body/w:p', NS)
        self.assertEqual([paragraph_text(p) for p in paragraphs], lines)
        for paragraph in paragraphs:
            style = paragraph.find('w:pPr/w:pStyle', NS)
            self.assertNotEqual(style.get(attr('val')) if style is not None else None, 'Name')

    def test_xml_forbidden_characters_are_removed_without_losing_unicode(self):
        text = 'Zoë\x00\x01 李\nRésumé\x08\x0b\x0c & café\x1f\ufffe\uffff\n技能: Python — Excel'
        _, root = self.open_document(text)
        actual = '\n'.join(paragraph_text(p) for p in root.findall('w:body/w:p', NS))
        self.assertEqual(actual, 'Zoë 李\nRésumé & café\n技能: Python — Excel')


if __name__ == '__main__':
    unittest.main()
