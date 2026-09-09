import base64
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import app
import certificates as cert
from browser_agent import BrowserAgent

DETAILS = dict(name='First Aid Certificate', issuer='Example Training', holder='Alex Example', issued_on='2025-01-01', expires_on='2099-01-01', keywords='First Aid, HLTAID011')
TEXT = '\n'.join(DETAILS.values())


class CertificateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app, 'DB', Path(self.temp.name) / 'test.db'), patch.object(app, 'DATA', Path(self.temp.name))]
        for item in self.patches:
            item.start()
        app.init()
        self.profile = {**app.profile(), 'name': 'Alex Example'}
        with app.connect() as c:
            c.execute('UPDATE profiles SET payload=? WHERE id=?', (json.dumps(self.profile), self.profile['id']))

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def receive(self):
        content = app.docx(TEXT)
        return cert.receive('default', '../../certificate.docx', base64.b64encode(content).decode())

    def ready(self):
        record = self.receive()
        record.update(DETAILS, status='ready')
        cert.store(record)
        return record

    def test_upload_path_and_profile_scoping(self):
        record = self.receive()
        self.assertEqual(record['filename'], 'certificate.docx')
        self.assertEqual(cert.file_path(record).parent, app.DATA / 'certificates')
        with self.assertRaises(ValueError):
            cert.get(record['id'], 'other-profile')
        with self.assertRaisesRegex(ValueError, 'already uploaded'):
            self.receive()

    def test_invalid_files_are_rejected(self):
        for filename, content in [('evil.exe', b'MZ'), ('fake.pdf', b'not pdf'), ('fake.png', b'%PDF-')]:
            with self.assertRaises(ValueError):
                cert.receive('default', filename, base64.b64encode(content).decode())

    def test_extraction_fills_combined_section_without_overwriting_manual_text(self):
        record = self.receive()
        app.AI_LOCK.acquire()
        with patch.object(cert, 'parse_details', return_value=DETAILS.copy()):
            cert.read_worker(record)
        self.assertFalse(app.AI_LOCK.locked())
        effective = cert.effective_profile({**self.profile, 'certifications': 'Manual qualification'})
        self.assertIn('Manual qualification', effective['certifications'])
        self.assertIn('First Aid Certificate', effective['certifications'])
        self.assertEqual(effective['certificate_ids'], [record['id']])

    def test_holder_and_expiry_control_usage(self):
        record = self.ready()
        for changes in ({'holder': 'Someone Else'}, {'expires_on': '2001-01-01'}, {'expires_on': 'unreadable date'}):
            changed = {**record, **changes}
            self.assertEqual(cert.validate_record(changed, self.profile)[0], 'needs_review')
            cert.store(changed)
            self.assertEqual(cert.effective_profile(self.profile)['certificate_ids'], [])

    def test_relevance_attachment_integrity_and_format_limits(self):
        record = self.ready()
        effective = cert.effective_profile(self.profile)
        job = {'description': 'First Aid required for this care role.'}
        selected = cert.select_for_job(effective, job)
        self.assertEqual(selected, [record['id']])
        self.assertEqual(cert.select_for_job(effective, {'description': 'Python developer required.'}), [])
        files = cert.attachments({**job, 'certificate_ids': selected}, effective)
        self.assertEqual(len(files), 1)
        self.assertTrue(cert.field_files(files, 'First Aid certificate', '.docx')[0])
        self.assertFalse(cert.field_files(files, 'First Aid certificate', '.pdf')[0])
        self.assertFalse(cert.field_files(files * 2, 'certificates', '', False)[0])
        cert.file_path(record).write_bytes(b'changed')
        self.assertEqual(cert.attachments({**job, 'certificate_ids': selected}, effective), [])

    def test_unsupported_model_claims_are_rejected(self):
        with patch('local_ai.structured', return_value={**DETAILS, 'issuer': 'Invented Institute'}):
            with self.assertRaisesRegex(ValueError, 'not supported'):
                cert.parse_details(TEXT)

    def test_browser_upload_and_automatic_profile_fill(self):
        from playwright.sync_api import sync_playwright, expect
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(cert, 'parse_details', return_value=DETAILS.copy()), sync_playwright() as pw:
                browser = pw.chromium.launch(channel=os.environ.get('BROWSER_CHANNEL') or None)
                page = browser.new_page()
                page.goto(f'http://127.0.0.1:{server.server_port}')
                page.get_by_role('button', name='My profile', exact=False).first.click()
                page.get_by_label('Certificate file', exact=True).set_input_files({'name': 'first-aid.docx', 'mimeType': cert.ALLOWED['.docx'], 'buffer': app.docx(TEXT)})
                page.get_by_role('button', name='Upload and read certificate').click()
                expect(page.get_by_label('Certification section used in applications')).to_have_value(__import__('re').compile('First Aid Certificate'), timeout=15000)
                record = cert.rows('default')[0]
                job = {'description': 'First Aid required.', 'certificate_ids': [record['id']]}
                files = cert.attachments(job, cert.effective_profile(self.profile))
                form = browser.new_page()
                form.set_content('<main><label>First Aid certificate<input type="file" accept=".docx"></label></main>')
                missing = BrowserAgent.fill(form.locator('main'), self.profile, Path('unused.docx'), certificate_files=files)
                self.assertEqual(missing, [])
                self.assertEqual(form.get_by_label('First Aid certificate').evaluate('(el) => el.files.length'), 1)
                self.assertEqual(form.get_by_label('First Aid certificate').evaluate('(el) => el.files[0].name'), cert.file_path(record).name)
                browser.close()
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
