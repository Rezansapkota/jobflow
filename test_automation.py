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

    def __init__(self, *args):
        pass

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
            app.save_job({**JOB, 'url': JOB['url'] + jid, 'id': jid, 'profile_id': 'default', 'status': status, 'resume': {'text': 'Reviewed resume'}, 'cover_letter': 'Reviewed letter'})
        with patch('discovery.discover', return_value=iter([])), patch('local_ai.rewrite') as rewrite:
            self.run_pipeline(False)
        rewrite.assert_not_called()
        self.assertEqual(app.get_job('uncertain-job')['status'], 'uncertain')

    def test_prepare_mode_does_not_apply(self):
        self.run_pipeline(False)
        self.assertEqual(app.jobs()[0]['status'], 'ready')
        self.assertEqual(FakeBrowser.attempts, [])

    def test_unknown_eligibility_blocks_submission_even_with_high_score(self):
        with patch('local_ai.assess', return_value={**MATCH, 'score': 100, 'unknown_requirements': ['Required licence not evidenced']}):
            self.run_pipeline(True)
        self.assertEqual(app.jobs()[0]['status'], 'needs_input')
        self.assertEqual(FakeBrowser.attempts, [])

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


if __name__ == '__main__':
    unittest.main()
