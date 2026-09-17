"""Readable, single-column Word and PDF documents built from real text paragraphs."""
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
    'PROJECTS': 'PROJECTS',
    'LANGUAGES': 'LANGUAGES',
    'REFERENCES': 'REFERENCES',
}

# Every design shares the same reading order and body paragraphs. Styling never
# moves contact details into headers, tables or floating elements.
TEMPLATES = {
    'professional': dict(font='Arial', color='172B4D', body=11, name=18, margin=22, rule=False),
    'modern': dict(font='Arial', color='2563EB', body=11, name=23, margin=20, rule=True),
    'minimal': dict(font='Arial', color='172033', body=10.5, name=19, margin=23, rule=False),
    'creative': dict(font='Trebuchet MS', color='1D4ED8', body=11, name=24, margin=21, rule=True),
    'executive': dict(font='Georgia', color='172B4D', body=11, name=22, margin=24, rule=True),
}


def template_settings(template='professional'):
    if not isinstance(template, str) or template not in TEMPLATES:
        raise ValueError('Choose a supported resume template.')
    return TEMPLATES[template]


def clean_text(text):
    # XML 1.0 excludes these control characters and invalid Unicode code points.
    return ''.join(c for c in text if c in '\t\n\r' or 0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF)


def plain_text(text):
    return '\n'.join(HEADINGS.get(line, line) for line in clean_text(text).splitlines())


def pdf_markup(text, template='professional'):
    theme = template_settings(template)
    paragraphs = []
    for index, line in enumerate(clean_text(text).splitlines()):
        tag = 'h1' if index == 0 else 'h2' if line in HEADINGS else 'p'
        content = html.escape(HEADINGS.get(line, line)) or '&#160;'
        paragraphs.append(f'<{tag}>{content}</{tag}>')
    rule = f'border-bottom: 1pt solid #{theme["color"]}; padding-bottom: 4pt;' if theme['rule'] else ''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Resume</title><style>
@page {{ size: A4; margin: {theme['margin']}mm; }}
body {{ font-family: "{theme['font']}", sans-serif; font-size: {theme['body']}pt; line-height: 1.4; color: #172033; }}
p, h1, h2 {{ white-space: pre-wrap; overflow-wrap: anywhere; margin: 0 0 7pt; }}
p {{ orphans: 2; widows: 2; }}
h1 {{ font-size: {theme['name']}pt; color: #{theme['color']}; {rule} }}
h2 {{ font-size: {theme['body']}pt; margin-top: 12pt; color: #{theme['color']}; }}
h1, h2 {{ break-after: avoid; }}
</style></head><body>''' + ''.join(paragraphs) + '</body></html>'


def pdf(text, template='professional'):
    """Print escaped resume text locally using the app's existing Chrome dependency."""
    from playwright.sync_api import sync_playwright, Error
    from chrome_browser import executable

    markup = pdf_markup(text, template)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=executable(), headless=True)
            try:
                page = browser.new_page(java_script_enabled=False)
                page.route('**/*', lambda route: route.abort())
                page.set_content(markup, wait_until='load')
                return page.pdf(prefer_css_page_size=True, print_background=False)
            finally:
                browser.close()
    except Error as exc:
        raise ValueError('Could not create the PDF. Check that Google Chrome is available and try again.') from exc


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


def docx(text, kind='resume', template='professional'):
    """No tables, graphics, text boxes, columns, headers, or footers."""
    if kind not in ('resume', 'cover_letter'):
        raise ValueError('Unknown document kind.')
    theme = template_settings(template)
    styles = STYLES.replace('Arial', theme['font']).replace('w:val="000000"', f'w:val="{theme["color"]}"')
    styles = styles.replace('w:val="22"', f'w:val="{int(theme["body"] * 2)}"')
    styles = styles.replace('w:val="36"', f'w:val="{int(theme["name"] * 2)}"')
    if theme['rule']:
        styles = styles.replace('<w:spacing w:after="120"/>', '<w:spacing w:after="120"/>'
                                f'<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="5" w:color="{theme["color"]}"/></w:pBdr>')
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
    margin = round(theme['margin'] / 25.4 * 1440)
    document = f'''<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="{NS}"><w:body>{''.join(paragraphs)}
<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="{margin}" w:right="{margin}" w:bottom="{margin}" w:left="{margin}"/><w:cols w:num="1"/></w:sectPr>
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
        for name, contents in {'[Content_Types].xml': content_types, '_rels/.rels': relations, 'word/document.xml': document, 'word/styles.xml': styles, 'word/_rels/document.xml.rels': document_relations}.items():
            archive.writestr(name, contents)
    return output.getvalue()
