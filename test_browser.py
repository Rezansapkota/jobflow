"""Local browser tests; no job sites or real submissions are contacted."""
import tempfile
import os
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import app
from browser_agent import BrowserAgent


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.temp = tempfile.TemporaryDirectory()
        cls.override = patch.object(app, 'DB', Path(cls.temp.name) / 'test.db')
        cls.override.start()
        app.init()
        cls.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(channel=os.environ.get('BROWSER_CHANNEL') or None)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.override.stop()
        cls.temp.cleanup()

    def test_account_confirmation_banner(self):
        import accounts
        page = self.browser.new_page()
        with patch.object(accounts, 'PENDING', {'id': 'test-request', 'profile_id': app.profile()['id'], 'source': 'SEEK'}):
            accounts.CONFIRMED.clear()
            page.goto(f'http://127.0.0.1:{self.server.server_port}')
            page.locator('#account-continue').click()
            page.get_by_text('Account confirmation sent.', exact=False).wait_for()
            self.assertTrue(accounts.CONFIRMED.is_set())
        accounts.CONFIRMED.clear()
        page.close()

    def test_review_previews_both_documents_and_records_approval(self):
        from review import approved
        job = {'id': 'review-ui', 'profile_id': app.profile()['id'], 'url': 'https://www.seek.com.au/job/98765431', 'title': 'Review test role', 'company': 'Fictional', 'source': 'SEEK', 'description': 'Fictional job description', 'status': 'ready', 'note': 'Review required', 'resume': {'text': 'Resume preview example', 'note': 'Test draft', 'matched': []}, 'cover_letter': 'Cover letter preview example'}
        app.save_job(job)
        page = self.browser.new_page()
        page.goto(f'http://127.0.0.1:{self.server.server_port}')
        page.get_by_role('button', name='Review test role', exact=True).click()
        page.get_by_text('Resume preview example', exact=True).wait_for()
        page.get_by_text('Cover letter preview example', exact=True).wait_for()
        page.get_by_role('button', name='I reviewed both documents - approve').click()
        page.get_by_role('button', name='Documents approved', exact=True).wait_for()
        self.assertTrue(approved(app.get_job(job['id'])))
        page.close()

    def test_profile_to_resume_workflow(self):
        page = self.browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda err: errors.append(str(err)))
        page.goto(f'http://127.0.0.1:{self.server.server_port}')
        page.get_by_text('Good things start with a first step.').wait_for()
        page.screenshot(path=str(app.DATA / 'dashboard.png'), full_page=True)
        page.get_by_role('button', name='My profile', exact=False).click()
        page.get_by_label('Full name', exact=True).fill('Test Applicant')
        page.get_by_label('Email', exact=True).fill('test@example.com')
        page.locator('[name=skills]').fill('Excel, Customer service')
        page.locator('[name=experience]').fill('Service assistant | Example Co | 2022–2024\nHelped customers and maintained records.')
        page.get_by_role('button', name='Save profile', exact=True).click()
        page.locator('#profile-saved').get_by_text('Saved', exact=True).wait_for()
        page.get_by_role('button', name='Applications', exact=False).first.click()
        page.get_by_role('button', name='Add a job', exact=False).click()
        page.get_by_label('Job link').fill('https://www.seek.com.au/job/12345678?ref=search')
        page.get_by_label('Job title', exact=True).fill('Customer Service Officer')
        page.get_by_label('Company', exact=True).fill('Example Company')
        page.get_by_label('Job description', exact=True).fill('We are looking for excellent customer service skills and reliable communication with customers.')
        page.get_by_role('button', name='Add to pipeline').click()
        page.get_by_role('checkbox', name='Select Customer Service Officer').check()
        page.get_by_label('Resume tailoring engine').select_option('basic')
        page.get_by_role('button', name='Prepare selected').click()
        page.locator('.badge.ready').wait_for()
        page.get_by_role('button', name='Customer Service Officer', exact=True).click()
        page.get_by_text('Customer service, Excel', exact=False).wait_for()
        with page.expect_download() as download:
            page.get_by_role('link', name='Download resume (.docx)').click()
        self.assertEqual(download.value.suggested_filename, 'resume.docx')
        with page.expect_download() as text_download:
            page.get_by_role('link', name='Download plain text (.txt)').click()
        self.assertEqual(text_download.value.suggested_filename, 'resume.txt')
        plain = Path(text_download.value.path()).read_text(encoding='utf-8')
        self.assertIn('WORK EXPERIENCE', plain)
        self.assertIn('Test Applicant\ntest@example.com', plain)
        page.get_by_role('button', name='Close', exact=True).last.click()
        page.screenshot(path=str(app.DATA / 'pipeline.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        self.assertEqual(errors, [])
        page.close()

    def test_agent_screen_validates_profile_and_is_responsive(self):
        page = self.browser.new_page(viewport={'width': 1280, 'height': 950})
        page.goto(f'http://127.0.0.1:{self.server.server_port}')
        page.get_by_role('button', name='Job agent', exact=False).click()
        page.get_by_role('button', name='Start job agent', exact=False).click()
        page.locator('#toast').get_by_text('Complete name in My profile', exact=False).wait_for()
        page.screenshot(path=str(app.DATA / 'job-agent.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        page.close()

    def test_unknown_questions_are_not_guessed(self):
        page = self.browser.new_page()
        page.set_content('<main><label>Full name<input></label><label>Years of experience<input></label><label>Consent<input type="checkbox"></label></main>')
        missing = BrowserAgent.fill(page.locator('main'), {**app.DEFAULT_PROFILE, 'name': 'Actual Name'}, Path('unused.docx'))
        self.assertEqual(page.get_by_label('Full name').input_value(), 'Actual Name')
        self.assertEqual(page.get_by_label('Years of experience').input_value(), '')
        self.assertIn('Years of experience', missing)
        self.assertIn('Consent', missing)
        page.close()

    def test_job_description_is_not_confirmation(self):
        page = self.browser.new_page()
        page.set_content('<main><p>Your application has been submitted is what our email will say.</p></main>')
        self.assertFalse(BrowserAgent.confirmed(page))
        page.set_content('<h1>Application submitted</h1>')
        self.assertTrue(BrowserAgent.confirmed(page))
        page.close()

    def test_profile_switching_preserves_named_certifications(self):
        from playwright.sync_api import expect
        page = self.browser.new_page()
        page.goto(f'http://127.0.0.1:{self.server.server_port}')
        page.get_by_role('button', name='My profile', exact=False).first.click()
        page.get_by_label('Profile title', exact=True).fill('Alex IT profile')
        page.get_by_label('Certifications and licences').fill('IT Support Certificate | Example Institute | 2025')
        page.get_by_role('button', name='New profile', exact=False).click()
        page.get_by_label('New profile title', exact=True).fill('Alex Aged Care profile')
        page.get_by_role('button', name='Create profile', exact=True).click()
        page.get_by_label('Profile title', exact=True).wait_for()
        expect(page.get_by_label('Profile title', exact=True)).to_have_value('Alex Aged Care profile')
        self.assertEqual(page.get_by_label('Certifications and licences').input_value(), '')
        page.get_by_label('Certifications and licences').fill('First Aid | Expires 2027-06-01')
        page.get_by_label('Active career profile').select_option(label='Alex IT profile')
        expect(page.get_by_label('Profile title', exact=True)).to_have_value('Alex IT profile')
        self.assertIn('IT Support Certificate', page.get_by_label('Certifications and licences').input_value())
        page.get_by_label('Active career profile').select_option(label='Alex Aged Care profile')
        expect(page.get_by_label('Profile title', exact=True)).to_have_value('Alex Aged Care profile')
        self.assertIn('First Aid', page.get_by_label('Certifications and licences').input_value())
        page.screenshot(path=str(app.DATA / 'named-profiles.png'), full_page=True)
        page.close()

    def test_discovery_extracts_jobposting_data(self):
        import json
        from discovery import extract_job
        page = self.browser.new_page()
        posting = {'@type': 'JobPosting', 'title': 'Service Officer', 'hiringOrganization': {'name': 'Fictional Store'}, 'description': '<p>' + 'Assist customers and maintain accurate inventory records. ' * 3 + '</p>', 'jobLocation': {'address': {'addressLocality': 'Darwin'}}}
        page.set_content('<script type="application/ld+json">' + json.dumps({'@graph': [posting]}) + '</script>')
        result = extract_job(page, 'SEEK', 'https://www.seek.com.au/job/12345678')
        self.assertEqual(result['company'], 'Fictional Store')
        self.assertNotIn('<p>', result['description'])
        self.assertIn('Darwin', result['location'])
        page.close()

    def test_browser_submits_resume_and_cover_letter_to_intercepted_fixture(self):
        # Every request is intercepted locally: the fictional application never reaches SEEK.
        context = self.browser.new_context()
        fixture = '''<main><a href="#" onclick="document.querySelector('form').hidden=false">Apply now</a>
        <form hidden><label>Full name<input></label><label>Email<input type="email"></label>
        <label>Resume<input type="file" id="resume"></label><label>Cover letter<input type="file" id="letter"></label>
        <button type="button" onclick="if(document.querySelector('#resume').files.length && document.querySelector('#letter').files.length) document.querySelector('main').innerHTML='<h1>Application submitted</h1>'">Submit application</button></form></main>'''
        context.route('**/*', lambda route: route.fulfill(status=200, content_type='text/html', body=fixture))
        agent = BrowserAgent(app.DATA)
        agent.context = context
        with tempfile.TemporaryDirectory() as directory:
            resume, letter = Path(directory) / 'resume.docx', Path(directory) / 'letter.docx'
            resume.write_bytes(app.docx('Fictional resume'))
            letter.write_bytes(app.docx('Fictional cover letter'))
            status, note = agent.apply({'url': 'https://www.seek.com.au/job/12345678', 'source': 'SEEK', 'cover_letter': 'Fictional cover letter'}, {**app.DEFAULT_PROFILE, 'name': 'Alex Example', 'email': 'alex@example.invalid'}, resume, True, letter)
            self.assertEqual(status, 'submitted')
        context.close()


if __name__ == '__main__':
    unittest.main()
