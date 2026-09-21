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
    def test_missing_details_can_be_saved_and_retried_without_inventing_an_answer(self):
        import json
        from playwright.sync_api import expect
        previous = app.profile()['id']
        profile = {**app.DEFAULT_PROFILE, 'id': 'missing-details', 'title': 'Missing details fixture',
                   'name': 'Alex Example', 'email': 'alex@example.invalid'}
        question = 'Do you hold a current police check?'
        with app.connect() as connection:
            connection.execute('INSERT INTO profiles VALUES (?, ?)', (profile['id'], json.dumps(profile)))
            connection.execute("UPDATE settings SET value=? WHERE key='active_profile'", (profile['id'],))
        job = {'id': 'missing-details-job', 'profile_id': profile['id'], 'url': 'https://www.seek.com.au/job/55500095',
               'title': 'Missing details role', 'company': 'Fictional', 'source': 'SEEK', 'status': 'needs_input',
               'description': 'Fictional care role requiring a police check.', 'note': 'Confirm your details.',
               'input_kind': 'profile_information', 'input_questions': [question], 'resume': None}
        app.save_job(job)
        page = self.browser.new_page()
        prepared = []
        try:
            def prepare_request(route):
                prepared.append(route.request.post_data_json)
                route.fulfill(content_type='application/json', body='{"ok": true}')
            page.route('**/api/prepare', prepare_request)
            page.goto(f'http://127.0.0.1:{self.server.server_port}')
            page.get_by_role('button', name='Review issues Missing details role', exact=True).click()
            expect(page.get_by_label(question, exact=True)).to_have_value('')
            page.get_by_label(question, exact=True).fill('No')
            page.get_by_role('button', name='Save answers & retry', exact=True).click()
            expect(page.locator('#detail-dialog')).not_to_be_visible()
            self.assertEqual(app.profile()['answers'][question], 'No')
            self.assertEqual(prepared, [{'ids': [job['id']], 'engine': 'ollama'}])
            self.assertFalse(app.get_job(job['id']).get('submission_requested'))
        finally:
            page.close()
            with app.connect() as connection:
                connection.execute("UPDATE settings SET value=? WHERE key='active_profile'", (previous,))
                connection.execute('DELETE FROM jobs WHERE id=?', (job['id'],))
                connection.execute('DELETE FROM profiles WHERE id=?', (profile['id'],))

    def test_approve_click_runs_automatic_submission_without_mode_selection(self):
        from playwright.sync_api import expect
        from review import approved
        job = {'id': 'automatic-click', 'profile_id': app.profile()['id'],
               'url': 'https://www.seek.com.au/job/55500094', 'title': 'Automatic click fixture',
               'company': 'Fictional', 'source': 'SEEK', 'status': 'ready',
               'description': 'Fictional role for isolated submission testing.', 'note': 'Ready',
               'resume': {'text': 'Fixture resume', 'matched': [], 'note': 'Test'}, 'cover_letter': 'Fixture letter'}
        calls = []
        class FixtureAgent:
            def __init__(self, *args, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def apply(self, current, profile, resume, submit, letter):
                if not approved(current) or not resume.exists() or not letter.exists():
                    raise AssertionError('Submission started without approved document files')
                calls.append((current['id'], submit))
                return 'submitted', 'Confirmed by isolated fixture.'
        app.save_job(job)
        app.STOP.clear()
        page = self.browser.new_page()
        try:
            with tempfile.TemporaryDirectory() as directory, patch.object(app, 'DATA', Path(directory)), patch('browser_agent.BrowserAgent', FixtureAgent):
                page.goto(f'http://127.0.0.1:{self.server.server_port}')
                expect(page.locator('#mode')).to_have_count(0)
                page.get_by_role('button', name='Approve & apply Automatic click fixture', exact=True).click()
                card = page.locator('.job').filter(has_text='Automatic click fixture')
                expect(card.locator('.badge')).to_have_text('Submitted', timeout=10000)
                self.assertEqual(calls, [(job['id'], True)])
                self.assertFalse(app.RUN_LOCK.locked())
                page.reload()
                expect(page.locator('.job').filter(has_text='Automatic click fixture').locator('.badge')).to_have_text('Submitted')
                self.assertEqual(len(calls), 1)
        finally:
            page.close()
            with app.connect() as connection:
                connection.execute('DELETE FROM jobs WHERE id=?', (job['id'],))

    def test_approval_pending_survives_refresh_and_finishes_in_both_views(self):
        from playwright.sync_api import expect
        job = {'id': 'approval-loading', 'profile_id': app.profile()['id'],
               'url': 'https://www.seek.com.au/job/55500091', 'title': 'Approval loading fixture',
               'company': 'Fictional', 'source': 'SEEK', 'status': 'ready',
               'description': 'Fictional customer service role for testing.', 'note': 'Ready',
               'resume': {'text': 'Fixture resume', 'matched': [], 'note': 'Test'}, 'cover_letter': 'Fixture letter'}
        app.save_job(job)
        page = self.browser.new_page()
        held = []
        worker_patch = patch('submission_queue.submit_when_idle')
        worker = worker_patch.start()
        self.addCleanup(worker_patch.stop)
        try:
            page.route('**/api/review/approve', lambda route: held.append(route))
            page.goto(f'http://127.0.0.1:{self.server.server_port}')
            page.get_by_role('button', name='Review Approval loading fixture', exact=True).click()
            review = page.locator('[data-review-approve]')
            review.click()
            expect(review).to_have_text('Approving...')
            expect(review).to_be_disabled()
            page.evaluate('refresh()')
            expect(review).to_have_attribute('aria-busy', 'true')
            board = page.locator('[data-approve="approval-loading"]')
            expect(board).to_be_disabled()
            expect(board).to_have_text('Approving...')
            self.assertEqual(len(held), 1)
            held[0].continue_()
            expect(review).to_have_text('Queued')
            expect(review).to_have_attribute('aria-busy', 'false')
            expect(board).to_have_text('Queued')
            expect(board).to_be_disabled()
            self.assertEqual(board.evaluate('el => getComputedStyle(el).cursor'), 'not-allowed')
            self.assertTrue(held[0].request.post_data_json['submit'])
            self.assertTrue(app.get_job(job['id'])['submission_requested'])
            worker.assert_called_once()
        finally:
            page.close()
            with app.connect() as connection:
                connection.execute('DELETE FROM jobs WHERE id=?', (job['id'],))

    def test_needs_input_job_has_a_working_review_and_prepare_action(self):
        from playwright.sync_api import expect
        job = {'id': 'approval-review', 'profile_id': app.profile()['id'],
               'url': 'https://www.seek.com.au/job/55500093', 'title': 'Review fixture',
               'company': 'Fictional', 'source': 'SEEK', 'status': 'needs_input',
               'description': 'Fictional care role requiring review before preparation.',
               'note': 'The job match needs review.', 'resume': None, 'cover_letter': None}
        app.save_job(job)
        page = self.browser.new_page()
        prepared = []
        try:
            def prepare_request(route):
                prepared.append(route.request.post_data_json)
                route.fulfill(content_type='application/json', body='{"ok": true}')
            page.route('**/api/prepare', prepare_request)
            page.goto(f'http://127.0.0.1:{self.server.server_port}')
            expect(page.locator('[data-approve="approval-review"]')).to_have_count(0)
            page.get_by_role('button', name='Review issues Review fixture', exact=True).click()
            expect(page.locator('#detail-content')).to_contain_text('The job match needs review.')
            page.get_by_role('button', name='Prepare documents after review', exact=True).click()
            expect(page.locator('#detail-dialog')).not_to_be_visible()
            self.assertEqual(prepared, [{'ids': [job['id']], 'engine': 'ollama'}])
            self.assertFalse(app.get_job(job['id']).get('approved_documents'))
            self.assertFalse(app.get_job(job['id']).get('submission_requested'))
        finally:
            page.close()
            with app.connect() as connection:
                connection.execute('DELETE FROM jobs WHERE id=?', (job['id'],))

    def test_approval_timeout_releases_button_without_retrying_submission(self):
        from playwright.sync_api import expect
        job = {'id': 'approval-timeout', 'profile_id': app.profile()['id'],
               'url': 'https://www.seek.com.au/job/55500092', 'title': 'Approval timeout fixture',
               'company': 'Fictional', 'source': 'SEEK', 'status': 'ready',
               'description': 'Fictional customer service role for testing.', 'note': 'Ready',
               'resume': {'text': 'Fixture resume', 'matched': [], 'note': 'Test'}, 'cover_letter': 'Fixture letter'}
        app.save_job(job)
        page = self.browser.new_page()
        requests = []
        try:
            page.route('**/api/review/approve', lambda route: requests.append(route))
            page.goto(f'http://127.0.0.1:{self.server.server_port}')
            button = page.locator('[data-approve="approval-timeout"]')
            button.click()
            expect(button).to_have_attribute('aria-busy', 'true')
            expect(page.locator('#toast')).to_contain_text('Approval response timed out', timeout=16000)
            expect(button).to_be_enabled()
            expect(button).to_have_attribute('aria-busy', 'false')
            self.assertEqual(len(requests), 1)
            requests[0].abort()
            self.assertFalse(app.get_job(job['id']).get('approved_documents'))
        finally:
            page.close()
            with app.connect() as connection:
                connection.execute('DELETE FROM jobs WHERE id=?', (job['id'],))

    def test_favicon_loads_without_content_security_errors(self):
        page = self.browser.new_page()
        errors = []
        page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
        try:
            for path in ('/', '/resume-builder'):
                page.goto(f'http://127.0.0.1:{self.server.server_port}{path}')
                icon = page.locator('link[rel=icon]').get_attribute('href')
                self.assertEqual(icon, '/favicon.svg')
                response = page.request.get(f'http://127.0.0.1:{self.server.server_port}{icon}')
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers['content-type'], 'image/svg+xml')
                page.wait_for_load_state('networkidle')
            self.assertEqual(errors, [])
        finally:
            page.close()

    def test_login_fills_only_selected_site(self):
        from accounts import fill_login
        context = self.browser.new_context()
        context.route('**/*', lambda route: route.fulfill(content_type='text/html', body='<input type="email"><input type="password"><button onclick="window.loginClicked=true">Sign in</button>'))
        page = context.new_page()
        try:
            page.goto('https://www.linkedin.com/login')
            credentials = {'username': 'example@example.invalid', 'password': 'fictional-test-password'}
            self.assertTrue(fill_login(page, 'LinkedIn', credentials))
            self.assertEqual(page.locator('input[type=password]').input_value(), credentials['password'])
            self.assertTrue(page.evaluate('window.loginClicked'))
            page.goto('https://untrusted.example/login')
            self.assertFalse(fill_login(page, 'LinkedIn', credentials))
            self.assertEqual(page.locator('input[type=password]').input_value(), '')
        finally:
            context.close()

    def test_delayed_seek_verification_is_detected_before_extraction(self):
        from discovery import wait_for_job, challenged
        page = self.browser.new_page()
        try:
            page.set_content('''<title>SEEK</title><p>Loading</p><script>
                setTimeout(() => document.body.innerHTML = '<p>Help us keep SEEK secure, confirm you are human.</p>', 150);
            </script>''')
            wait_for_job(page)
            self.assertTrue(challenged(page))
        finally:
            page.close()

    def test_delayed_seek_description_can_be_extracted(self):
        from discovery import wait_for_job, extract_job
        page = self.browser.new_page()
        try:
            page.set_content('''<h1 data-automation="job-detail-title">Care worker</h1>
                <span data-automation="advertiser-name">Fictional Care</span>
                <span data-automation="job-detail-location">Darwin NT</span>
                <div data-automation="jobAdDetails"></div><script>
                setTimeout(() => document.querySelector('[data-automation="jobAdDetails"]').textContent = 'Support residents with daily activities and follow documented care plans. Communicate with the care team and keep accurate records.', 150);
            </script>''')
            wait_for_job(page)
            result = extract_job(page, 'SEEK', 'https://www.seek.com.au/job/12345678')
            self.assertEqual(result['title'], 'Care worker')
            self.assertGreater(len(result['description']), 100)
        finally:
            page.close()

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
        cls.browser = cls.pw.chromium.launch(channel='chrome')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.override.stop()
        cls.temp.cleanup()

    def test_separate_resume_builder_prefill_drafts_and_download(self):
        from playwright.sync_api import expect
        import io
        import json
        import zipfile
        first = {**app.DEFAULT_PROFILE, 'id': 'builder-first', 'title': 'Builder IT', 'name': 'Alex Example', 'email': 'alex@example.invalid', 'experience': 'IT support', 'certifications': 'First Aid'}
        second = {**app.DEFAULT_PROFILE, 'id': 'builder-second', 'title': 'Builder Care', 'name': 'Casey Example', 'experience': 'Care assistant'}
        with app.connect() as c:
            for p in (first, second):
                c.execute('INSERT INTO profiles VALUES (?, ?)', (p['id'], json.dumps(p)))
            c.execute("INSERT OR REPLACE INTO settings VALUES ('active_profile', ?)", (first['id'],))
        page = self.browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            page.goto(f'http://127.0.0.1:{self.server.server_port}')
            page.get_by_role('link', name='Resume Builder', exact=True).click()
            expect(page.locator('[name=name]')).to_have_value('Alex Example')
            self.assertEqual(page.locator('[name=certifications]').input_value(), 'First Aid')
            page.locator('[name=summary]').fill('A resume-only summary <safe>')
            self.assertIn('A resume-only summary <safe>', page.locator('#resume-preview').inner_text())
            page.reload()
            expect(page.locator('[name=summary]')).to_have_value('A resume-only summary <safe>')
            page.locator('#resume-profile').select_option(second['id'])
            expect(page.locator('[name=name]')).to_have_value('Casey Example')
            self.assertEqual(page.locator('[name=summary]').input_value(), '')
            page.locator('#resume-profile').select_option(first['id'])
            expect(page.locator('[name=summary]')).to_have_value('A resume-only summary <safe>')
            self.assertEqual(app.profile()['summary'], '')
            with page.expect_download() as downloaded:
                page.get_by_role('button', name='Download Word').click()
            contents = Path(downloaded.value.path()).read_bytes()
            with zipfile.ZipFile(io.BytesIO(contents)) as archive:
                document = archive.read('word/document.xml').decode()
                self.assertIn('Alex Example', document)
                self.assertIn('A resume-only summary &lt;safe&gt;', document)
            with page.expect_download() as downloaded:
                page.get_by_role('button', name='Download text').click()
            self.assertEqual(downloaded.value.suggested_filename, 'resume.txt')
            self.assertIn('A resume-only summary <safe>', Path(downloaded.value.path()).read_text(encoding='utf-8'))
            with page.expect_download() as downloaded:
                page.get_by_role('button', name='Download PDF').click()
            self.assertEqual(downloaded.value.suggested_filename, 'resume.pdf')
            import pypdfium2 as pdfium
            with pdfium.PdfDocument(Path(downloaded.value.path()).read_bytes()) as document:
                pdf_page = document[0]
                text_page = pdf_page.get_textpage()
                try:
                    extracted = text_page.get_text_range()
                    self.assertIn('Alex Example', extracted)
                    self.assertIn('A resume-only summary <safe>', extracted)
                finally:
                    text_page.close()
                    pdf_page.close()
            # Long experience must wrap and paginate, preserving the final entry.
            long_text = 'Zoë Example\nWORK EXPERIENCE\n' + '\n'.join(
                f'Position {i}: Customer service & support with <internal> tools. ' * 3
                for i in range(80)) + '\nFinal achievement'
            response = page.request.post(
                f'http://127.0.0.1:{self.server.server_port}/api/resume-builder/download',
                headers={'X-Session-Token': app.TOKEN},
                data={'text': long_text, 'format': 'pdf'})
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers['content-type'], 'application/pdf')
            with pdfium.PdfDocument(response.body()) as document:
                self.assertGreater(len(document), 1)
                pdf_page = document[len(document) - 1]
                text_page = pdf_page.get_textpage()
                try:
                    self.assertIn('Final achievement', text_page.get_text_range())
                finally:
                    text_page.close()
                    pdf_page.close()
            page.on('dialog', lambda dialog: dialog.accept())
            page.get_by_role('button', name='Refill from saved profile').click()
            expect(page.locator('[name=summary]')).to_have_value('')
            page.set_viewport_size({'width': 390, 'height': 844})
            self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
            self.assertEqual(errors, [])
        finally:
            page.close()
            with app.connect() as c:
                c.execute("UPDATE settings SET value='default' WHERE key='active_profile'")
                c.execute("DELETE FROM profiles WHERE id IN ('builder-first', 'builder-second')")

    def test_resume_builder_job_analysis_final_download_and_stale_results(self):
        import json
        from playwright.sync_api import expect
        from test_resume_builder import PROFILE, JOB
        p = {**PROFILE, 'id': 'tailoring-ui', 'title': 'Tailoring test'}
        with app.connect() as c:
            c.execute('INSERT INTO profiles VALUES (?, ?)', (p['id'], json.dumps(p)))
            c.execute("INSERT OR REPLACE INTO settings VALUES ('active_profile', ?)", (p['id'],))
        page = self.browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            page.goto(f'http://127.0.0.1:{self.server.server_port}/resume-builder')
            expect(page.locator('[name=name]')).to_have_value(p['name'])
            page.locator('#target-title').fill(JOB['title'])
            page.locator('#target-description').fill(JOB['description'])
            page.locator('#resume-length').select_option('concise')
            page.locator('#resume-tone').select_option('formal')
            page.locator('#resume-emphasis').select_option('achievements')
            page.locator('#resume-max-skills').select_option('6')
            page.locator('#tailor-engine').select_option('basic')
            page.get_by_role('button', name='Analyze job & tailor resume').click()
            expect(page.locator('#preview-heading')).to_have_text('Final tailored resume', timeout=15000)
            final_text = page.locator('#resume-preview').inner_text()
            self.assertIn('Service Assistant | Example Co | 2022-2024', final_text)
            self.assertNotIn('Python', final_text)
            self.assertNotIn('forklift licence', final_text.lower())
            self.assertIn('forklift licence', page.locator('#analysis-requirements').inner_text())
            self.assertEqual(page.locator('[name=experience]').input_value(), p['experience'])
            with page.expect_download() as downloaded:
                page.get_by_role('button', name='Download text').click()
            self.assertEqual(Path(downloaded.value.path()).read_text(encoding='utf-8'), final_text)
            page.reload()
            expect(page.locator('#preview-heading')).to_have_text('Final tailored resume')
            expect(page.locator('#resume-length')).to_have_value('concise')
            expect(page.locator('#resume-tone')).to_have_value('formal')
            expect(page.locator('#resume-max-skills')).to_have_value('6')
            self.assertEqual(page.locator('#resume-preview').inner_text(), final_text)
            page.get_by_text('Edit final resume text', exact=True).click()
            page.locator('#final-resume-text').fill(final_text + '\nAdditional verified detail')
            with page.expect_download() as downloaded:
                page.get_by_role('button', name='Download text').click()
            self.assertIn('Additional verified detail', Path(downloaded.value.path()).read_text(encoding='utf-8'))
            page.set_viewport_size({'width': 390, 'height': 844})
            self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
            page.locator('#resume-max-skills').select_option('10')
            expect(page.locator('#preview-heading')).to_have_text('Live preview')
            page.locator('#target-description').fill(JOB['description'] + '\nWeekend work required.')
            expect(page.locator('#tailor-results')).to_be_hidden()
            expect(page.locator('#preview-heading')).to_have_text('Live preview')
            self.assertIn('Python', page.locator('#resume-preview').inner_text())
            page.locator('#resume-profile').select_option('default')
            expect(page.locator('#target-description')).to_have_value('')
            page.locator('#resume-profile').select_option(p['id'])
            expect(page.locator('#target-description')).to_have_value(JOB['description'] + '\nWeekend work required.')
            self.assertEqual(app.profile()['experience'], p['experience'])
            self.assertEqual(errors, [])
        finally:
            page.close()
            with app.connect() as c:
                c.execute("UPDATE settings SET value='default' WHERE key='active_profile'")
                c.execute("DELETE FROM profiles WHERE id='tailoring-ui'")

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
        with patch('submission_queue.submit_when_idle') as worker:
            page.get_by_role('button', name='Approve & apply', exact=True).click()
            page.get_by_role('button', name='Queued', exact=True).wait_for()
            self.assertTrue(approved(app.get_job(job['id'])))
            self.assertTrue(app.get_job(job['id'])['submission_requested'])
            worker.assert_called_once()
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
        page.get_by_role('button', name='Add job manually', exact=True).click()
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
        page.get_by_role('button', name='Job search', exact=False).click()
        page.get_by_role('button', name='Search LinkedIn + SEEK', exact=False).click()
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

    def test_confirmation_must_be_visible_and_outside_job_description(self):
        page = self.browser.new_page()
        try:
            page.set_content('<main id="job-details"><h2>Application submitted</h2></main><h2 hidden>Application sent</h2>')
            self.assertFalse(BrowserAgent.confirmed(page))
            page.set_content('<div role="status"><p>Thank you for applying</p></div>')
            self.assertTrue(BrowserAgent.confirmed(page))
        finally:
            page.close()

    def test_submission_recheck_reads_exact_job_without_clicking_apply(self):
        from types import SimpleNamespace
        page_context = self.browser.new_context()
        clicks = []
        page_context.expose_binding('clicked', lambda *args: clicks.append(True))
        url = 'https://www.seek.com.au/job/12345678'
        page_context.route(url, lambda route: route.fulfill(content_type='text/html', body='<div data-automation="job-application-status">You applied on 14 September 2026</div><button onclick="clicked()">Apply</button>'))
        agent = SimpleNamespace(context=page_context, stopped=lambda: False)
        try:
            confirmed, note = BrowserAgent.verify_submission(agent, {'url': url, 'source': 'SEEK'})
            self.assertTrue(confirmed)
            self.assertIn('You applied', note)
            self.assertEqual(clicks, [])
        finally:
            page_context.close()

    def test_job_buttons_review_approve_and_reject_automatic_queue(self):
        job = {'id': 'decision-ui', 'profile_id': app.profile()['id'], 'url': 'https://www.seek.com.au/job/55500011',
               'title': 'Decision fixture job', 'company': 'Fictional', 'source': 'SEEK', 'status': 'ready',
               'description': 'Fixture description', 'note': 'Ready',
               'resume': {'text': 'Decision fixture resume', 'matched': [], 'note': 'Test'}, 'cover_letter': 'Decision fixture letter'}
        app.save_job(job)
        page = self.browser.new_page(viewport={'width': 1200, 'height': 900})
        try:
            with patch('submission_queue.submit_when_idle') as worker:
                page.goto(f'http://127.0.0.1:{self.server.server_port}')
                page.get_by_role('button', name='Review Decision fixture job', exact=True).click()
                page.get_by_text('Decision fixture resume', exact=True).wait_for()
                page.get_by_text('Decision fixture letter', exact=True).wait_for()
                page.locator('[data-close="detail-dialog"]').click()
                page.get_by_role('button', name='Approve & apply Decision fixture job', exact=True).click()
                page.locator('#toast').get_by_text('Approved and queued', exact=False).wait_for()
                worker.assert_called_once()
                self.assertTrue(app.get_job(job['id'])['submission_requested'])
                page.get_by_role('button', name='Reject Decision fixture job', exact=True).click()
                page.locator('#toast').get_by_text('Rejected.', exact=False).wait_for()
                self.assertFalse(app.get_job(job['id'])['submission_requested'])
                self.assertEqual(app.get_job(job['id'])['status'], 'rejected')
        finally:
            page.close()
            with app.connect() as connection:
                connection.execute('DELETE FROM jobs WHERE id=?', (job['id'],))

    def test_unrelated_jobs_can_be_hidden_without_deleting_them(self):
        job = {'id': 'unrelated-ui', 'profile_id': app.profile()['id'], 'url': 'https://www.seek.com.au/job/12344999',
               'title': 'Unrelated fixture role', 'company': 'Fictional', 'source': 'SEEK', 'description': 'Fixture description',
               'status': 'saved', 'resume': None, 'assessment': {'role_match': False, 'location_match': True}}
        app.save_job(job)
        page = self.browser.new_page()
        try:
            page.goto(f'http://127.0.0.1:{self.server.server_port}')
            page.locator('#relevant-only').wait_for()
            self.assertEqual(page.get_by_role('button', name=job['title'], exact=True).count(), 0)
            page.locator('#relevant-only').uncheck()
            page.get_by_role('button', name=job['title'], exact=True).wait_for()
            self.assertIsNotNone(app.get_job(job['id']))
        finally:
            page.close()
            with app.connect() as connection:
                connection.execute('DELETE FROM jobs WHERE id=?', (job['id'],))

    def test_signed_in_linkedin_layout_and_seek_domain(self):
        from discovery import extract_job
        page = self.browser.new_page()
        description = 'Support customers and maintain accurate records. ' * 4
        page.set_content('<title>Service Officer | Fictional Store | LinkedIn</title><main>Fictional Store\nService Officer\nDarwin, Australia\n<div><div><h2>About the job</h2></div><div data-testid="expandable-text-box">' + description + '</div></div></main>')
        result = extract_job(page, 'LinkedIn', 'https://www.linkedin.com/jobs/view/12345678/')
        self.assertEqual(result['title'], 'Service Officer')
        self.assertEqual(result['company'], 'Fictional Store')
        self.assertIn('Support customers', result['description'])
        self.assertEqual(app.validate_url('https://au.seek.com/job/12345678?ref=search'), ('https://www.seek.com.au/job/12345678', 'SEEK'))
        page.close()

    def test_linkedin_multistep_with_hidden_login_and_answered_radio(self):
        context = self.browser.new_context()
        fixture = '''<input type="password" hidden><main><button onclick="document.querySelector('[role=dialog]').hidden=false">Easy Apply</button></main>
        <div role="dialog" hidden><section id="first"><label>Full name<input></label><label>Email<input type="email" required></label>
        <label>Yes<input type="radio" name="answer" checked></label><label>No<input type="radio" name="answer"></label>
        <button onclick="document.querySelector('#first').remove();document.querySelector('#second').hidden=false">Next</button></section>
        <section id="second" hidden><label>Resume<input type="file" id="resume"></label><label>Cover letter<input type="file" id="letter"></label>
        <button onclick="if(document.querySelector('#resume').files.length && document.querySelector('#letter').files.length)document.body.innerHTML='<h1>Application submitted</h1>'">Submit application</button></section></div>'''
        context.route('**/*', lambda route: route.fulfill(status=200, content_type='text/html', body=fixture))
        agent = BrowserAgent(app.DATA)
        agent.context = context
        with tempfile.TemporaryDirectory() as directory:
            resume, letter = Path(directory) / 'resume.docx', Path(directory) / 'letter.docx'
            resume.write_bytes(app.docx('Fictional resume'))
            letter.write_bytes(app.docx('Fictional letter'))
            with patch.object(agent, 'handoff', return_value=('needs_input', 'Unexpected handoff')) as handoff:
                result = agent.apply({'url': 'https://www.linkedin.com/jobs/view/12345678/', 'source': 'LinkedIn'}, {**app.DEFAULT_PROFILE, 'name': 'Alex Example', 'email': 'alex@example.invalid'}, resume, True, letter)
            self.assertEqual(result[0], 'submitted')
            handoff.assert_not_called()
            self.assertTrue(agent.submission_possible)
        context.close()

    def test_invalid_email_blocks_submit(self):
        context = self.browser.new_context()
        fixture = '''<main><button onclick="document.querySelector('form').hidden=false">Apply now</button><form hidden><label>Email<input type="email" required></label><button type="button" onclick="window.clicked=true">Submit application</button></form></main>'''
        context.route('**/*', lambda route: route.fulfill(status=200, content_type='text/html', body=fixture))
        agent = BrowserAgent(app.DATA)
        agent.context = context
        with patch.object(agent, 'handoff', return_value=('needs_input', 'Validation failed')) as handoff:
            result = agent.apply({'url': 'https://www.seek.com.au/job/12345678', 'source': 'SEEK'}, {**app.DEFAULT_PROFILE, 'email': 'invalid-email'}, Path('unused.docx'), True)
        self.assertEqual(result[0], 'needs_input')
        self.assertIn('validation', handoff.call_args.args[1])
        self.assertFalse(agent.submission_possible)
        context.close()

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
