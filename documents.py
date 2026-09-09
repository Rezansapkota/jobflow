"""Readable, single-column Word documents built from real text paragraphs."""
import html
import io
import zipfile

NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
HEADINGS = {
    'PROFILE': 'PROFESSIONAL SUMMARY',
    'PROFESSIONAL SUMMARY': 'PROFESSIONAL SUMMARY',
    'SKILLS': 'SKILLS',
    'EXPERIENCE': 'WORK EXPERIENCE',
    'WORK EXPERIENCE': 'WORK EXPERIENCE',
    'EDUCATION & CERTIFICATIONS': 'EDUCATION AND CERTIFICATIONS',
    'EDUCATION AND CERTIFICATIONS': 'EDUCATION AND CERTIFICATIONS',
    'EDUCATION': 'EDUCATION',
    'CERTIFICATIONS': 'CERTIFICATIONS',
}


def clean_text(text):
    # XML 1.0 excludes these control characters and invalid Unicode code points.
    return ''.join(c for c in text if c in '\t\n\r' or 0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF)


def plain_text(text):
    return '\n'.join(HEADINGS.get(line, line) for line in clean_text(text).splitlines())


STYLES = f'''<?xml version="1.0" encoding="UTF-8"?>
<w:styles xmlns:w="{NS}">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:eastAsia="Arial" w:cs="Arial"/><w:sz w:val="22"/><w:szCs w:val="22"/><w:color w:val="000000"/></w:rPr></w:rPrDefault>
    <w:pPrDefault><w:pPr><w:spacing w:after="100" w:line="276" w:lineRule="auto"/><w:widowControl/><w:jc w:val="left"/></w:pPr></w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>
    <w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:eastAsia="Arial" w:cs="Arial"/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Name"><w:name w:val="Applicant Name"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>
    <w:pPr><w:keepNext/><w:spacing w:after="120"/></w:pPr><w:rPr><w:b/><w:sz w:val="36"/><w:szCs w:val="36"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
    <w:pPr><w:keepNext/><w:keepLines/><w:spacing w:before="160" w:after="100"/><w:outlineLvl w:val="0"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="22"/><w:szCs w:val="22"/><w:color w:val="000000"/></w:rPr>
  </w:style>
</w:styles>'''


def docx(text, kind='resume'):
    """No tables, graphics, text boxes, columns, headers, or footers."""
    if kind not in ('resume', 'cover_letter'):
        raise ValueError('Unknown document kind.')
    paragraphs = []
    for index, line in enumerate(clean_text(text).splitlines()):
        style = 'Normal'
        if kind == 'resume':
            if index == 0:
                style = 'Name'
            elif line in HEADINGS:
                style = 'Heading1'
                line = HEADINGS[line]
        paragraphs.append(f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr><w:r><w:t xml:space="preserve">{html.escape(line)}</w:t></w:r></w:p>')
    document = f'''<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="{NS}"><w:body>{''.join(paragraphs)}
<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/><w:cols w:num="1"/></w:sectPr>
</w:body></w:document>'''
    content_types = '''<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>'''
    relations = '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
    document_relations = '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, contents in {'[Content_Types].xml': content_types, '_rels/.rels': relations, 'word/document.xml': document, 'word/styles.xml': STYLES, 'word/_rels/document.xml.rels': document_relations}.items():
            archive.writestr(name, contents)
    return output.getvalue()
