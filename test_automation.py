import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app
import automation


PROFILE = {**app.DEFAULT_PROFILE, 'name': 'Alex Example', 'email': 'alex@example.invalid',
           'skills': 'Excel, Customer service', 'experience': 'Service assistant at Fictional Store, 2021–2025. Assisted customers and maintained records.',
           'roles': 'Customer Service Officer', 'search_location': 'Darwin', 'work_rights': 'Unrestricted work rights in Australia'}
JOB = {'url': 'https://www.seek.com.au/job/12345678', 'source': 'SEEK', 'title': 'Customer Service Officer',
       'company': 'Fictional Employer', 'location': 'Darwin', 'description': 'Assist customers and maintain records in Excel. Customer service experience required. Darwin office.'}
MATCH = {'score': 90, 'reason': 'Relevant customer service experience.', 'missing_requirements': [], 'unknown_requirements': [], 'role_match': True, 'location_match': True}


class FakeBrowser:
    attempts = []

    def __init__(self, *args, **kwargs):
        self.headless = kwargs.get('headless', False)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def apply(self, job, profile, resume, submit, letter):
        assert resume.exists() and letter.exists()
        self.attempts.append(job['id'])
        return 'submitted', 'Local test confirmation.'


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app, 'DB', Path(self.temp.name) / 'test.db'), patch.object(app, 'DATA', Path(self.temp.name)),
                        patch('browser_agent.BrowserAgent', FakeBrowser), patch('accounts.prepare'), patch('discovery.discover', return_value=iter([JOB])),
                        patch('local_ai.assess', return_value=MATCH.copy()),
                        patch('local_ai.rewrite', return_value={'summary': 'Service assistant with customer service experience.', 'skills': ['Customer service', 'Excel']}),
                        patch('local_ai.cover_letter', return_value='Dear Hiring Manager,\nFictional test letter.\nAlex Example')]
        for item in self.patches:
            item.start()
        app.init()
        app.STOP.clear()
        FakeBrowser.attempts = []

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def run_pipeline(self, submit):
        config = automation.validate_config(PROFILE, {'submit': submit})
        app.RUN_LOCK.acquire()
        automation.run(PROFILE, config)
        self.assertFalse(app.RUN_LOCK.locked())

    def test_complete_pipeline_requires_review_even_when_submit_requested(self):
        self.run_pipeline(True)
        job = app.jobs()[0]
        self.assertEqual(job['status'], 'ready')
        self.assertEqual(len(FakeBrowser.attempts), 0)
        self.assertEqual(automation.current()['submitted'], 0)
        self.assertIn('cover_letter', job)

    def test_search_does_not_require_account_confirmation(self):
        with patch('accounts.prepare', side_effect=ValueError('Sign in first')) as prepare:
            self.run_pipeline(False)
        prepare.assert_not_called()
        self.assertEqual(app.jobs()[0]['status'], 'ready')

    def test_search_uses_background_browser(self):
        with patch('browser_agent.BrowserAgent', wraps=FakeBrowser) as browser:
            self.run_pipeline(False)
        self.assertTrue(browser.call_args.kwargs['headless'])

    def test_documents_are_created_automatically_after_search_finishes(self):
        finished = []
        def listings(*args):
            try:
                yield JOB
                yield {**JOB, 'url': 'https://www.seek.com.au/job/12345679', 'title': 'Second service role'}
            finally:
                finished.append(True)
        def draft(*args):
            self.assertTrue(finished)
            self.assertEqual(len(app.jobs()), 2)
            return {'summary': 'Customer service experience.', 'skills': ['Customer service']}
        with patch('discovery.discover', side_effect=listings), patch('local_ai.rewrite', side_effect=draft) as rewrite:
            self.run_pipeline(False)
        self.assertEqual(rewrite.call_count, 2)
        self.assertTrue(all(job['resume'] and job['cover_letter'] for job in app.jobs()))
        self.assertEqual(automation.current()['queued'], 2)
        self.assertEqual(automation.current()['prepared'], 2)

    def test_stop_after_discovery_preserves_jobs_without_starting_drafts(self):
        def listings(*args):
            yield JOB
            app.STOP.set()
        with patch('discovery.discover', side_effect=listings), patch('local_ai.rewrite') as rewrite:
            self.run_pipeline(False)
        rewrite.assert_not_called()
        self.assertEqual(len(app.jobs()), 1)
        self.assertEqual(automation.current()['status'], 'stopped')

    def test_single_site_excludes_saved_jobs_from_other_site(self):
        app.save_job({**JOB, 'id': 'seek-saved', 'profile_id': 'default', 'status': 'saved', 'resume': None})
        config = automation.validate_config(PROFILE, {'sources': ['LinkedIn']})
        with patch('discovery.discover', return_value=iter([])) as discover:
            app.RUN_LOCK.acquire()
            automation.run(PROFILE, config)
        self.assertEqual(discover.call_args.args[2]['sources'], ['LinkedIn'])
        self.assertEqual(automation.current()['revisited'], 0)
        self.assertIsNone(app.get_job('seek-saved')['resume'])

    def test_saved_unfinished_job_is_retried_without_new_results(self):
        app.save_job({**JOB, 'id': 'saved-job', 'profile_id': 'default', 'status': 'saved', 'resume': None})
        with patch('discovery.discover', return_value=iter([])):
            self.run_pipeline(False)
        self.assertEqual(app.get_job('saved-job')['status'], 'ready')
        self.assertEqual(automation.current()['revisited'], 1)
        self.assertEqual(automation.current()['prepared'], 1)

    def test_no_results_is_not_reported_as_success(self):
        with patch('discovery.discover', return_value=iter([])):
            self.run_pipeline(False)
        self.assertEqual(automation.current()['status'], 'no_results')

    def test_prepared_and_uncertain_jobs_are_not_regenerated(self):
        for jid, status in [('ready-job', 'ready'), ('uncertain-job', 'uncertain')]:
            app.save_job({**JOB, 'url': JOB['url'] + jid, 'id': jid, 'profile_id': 'default', 'status': status, 'resume': {'text': 'Reviewed resume', 'tailoring_version': __import__('tailoring').VERSION}, 'cover_letter': 'Reviewed letter'})
        with patch('discovery.discover', return_value=iter([])), patch('local_ai.rewrite') as rewrite:
            self.run_pipeline(False)
        rewrite.assert_not_called()
        self.assertEqual(app.get_job('uncertain-job')['status'], 'uncertain')

    def test_outdated_unapproved_documents_refresh_on_next_search(self):
        app.save_job({**JOB, 'id': 'outdated', 'profile_id': 'default', 'status': 'ready', 'resume': {'text': 'Old generic resume'}, 'cover_letter': 'Old letter'})
        with patch('discovery.discover', return_value=iter([])):
            self.run_pipeline(False)
        job = app.get_job('outdated')
        self.assertEqual(job['resume']['tailoring_version'], __import__('tailoring').VERSION)
        self.assertNotEqual(job['cover_letter'], 'Old letter')
        self.assertEqual(automation.current()['prepared'], 1)

    def test_outdated_approved_documents_are_preserved(self):
        from review import fingerprint
        job = {**JOB, 'id': 'approved-old', 'profile_id': 'default', 'status': 'ready', 'resume': {'text': 'Approved resume'}, 'cover_letter': 'Approved letter'}
        job['approved_documents'] = fingerprint(job)
        app.save_job(job)
        with patch('discovery.discover', return_value=iter([])), patch('local_ai.rewrite') as rewrite:
            self.run_pipeline(False)
        rewrite.assert_not_called()
        self.assertEqual(app.get_job(job['id'])['approved_documents'], job['approved_documents'])

    def test_prepare_mode_does_not_apply(self):
        self.run_pipeline(False)
        self.assertEqual(app.jobs()[0]['status'], 'ready')
        self.assertEqual(FakeBrowser.attempts, [])

    def test_unknown_eligibility_blocks_submission_even_with_high_score(self):
        with patch('local_ai.assess', return_value={**MATCH, 'score': 100, 'unknown_requirements': ['Required licence not evidenced']}):
            self.run_pipeline(True)
        self.assertEqual(app.jobs()[0]['status'], 'needs_input')
        self.assertEqual(FakeBrowser.attempts, [])
        self.assertTrue(app.jobs()[0]['resume'])
        self.assertTrue(app.jobs()[0]['cover_letter'])
        self.assertIn('Required licence not evidenced', app.jobs()[0]['note'])

    def test_letter_generation_failure_does_not_apply(self):
        with patch('local_ai.cover_letter', side_effect=ValueError('Model unavailable')):
            self.run_pipeline(True)
        self.assertEqual(FakeBrowser.attempts, [])
        self.assertEqual(app.jobs()[0]['status'], 'needs_input')

    def test_blank_profile_and_invalid_limits_are_rejected(self):
        for profile, body in [(app.DEFAULT_PROFILE, {}), (PROFILE, {'max_jobs': 100}), (PROFILE, {'pages': True}), (PROFILE, {'sources': ['unknown']}), ({**PROFILE, 'work_rights': ''}, {'submit': True})]:
            with self.assertRaises(ValueError):
                automation.validate_config(profile, body)

    def test_stop_prevents_submission(self):
        app.STOP.set()
        self.run_pipeline(True)
        self.assertEqual(FakeBrowser.attempts, [])
        self.assertEqual(automation.current()['status'], 'stopped')

    def test_location_and_role_must_match(self):
        for key in ('role_match', 'location_match'):
            self.assertFalse(automation.suitable({**MATCH, key: False}, 80))

    def test_location_mismatch_cannot_be_overridden_by_ai(self):
        profile = {**PROFILE, 'location': 'Sydney NSW'}
        config = automation.validate_config(profile, {})
        self.assertEqual(config['location'], 'Sydney NSW')
        with patch('local_ai.assess', return_value=MATCH.copy()) as assess, patch('discovery.discover', return_value=iter([JOB])) as discover:
            app.RUN_LOCK.acquire()
            automation.run(profile, config)
        assess.assert_not_called()
        self.assertEqual(app.jobs(), [])
        self.assertEqual(discover.call_args.args[1]['search_location'], 'Sydney NSW')

    def test_unrelated_new_listings_are_not_saved_or_prepared(self):
        for key in ('role_match', 'location_match'):
            with self.subTest(key=key), patch('local_ai.assess', return_value={**MATCH, key: False}), patch('discovery.discover', return_value=iter([JOB])), patch('local_ai.rewrite') as rewrite:
                self.run_pipeline(False)
                self.assertEqual(app.jobs(), [])
                self.assertEqual(automation.current()['found'], 0)
                self.assertEqual(automation.current()['skipped'], 1)
                rewrite.assert_not_called()


if __name__ == '__main__':
    unittest.main()
