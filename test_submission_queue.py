import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import app
import review
import submission_queue as queue


class SubmissionQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = patch.object(app, 'DB', Path(self.temp.name) / 'test.db')
        self.db.start()
        app.init()
        app.STOP.clear()
        self.job = {'id': 'approved-job', 'profile_id': 'default', 'source': 'SEEK',
                    'url': 'https://www.seek.com.au/job/12345678', 'title': 'Fixture job', 'status': 'ready',
                    'resume': {'text': 'Factual resume'}, 'cover_letter': 'Factual letter',
                    'profile_snapshot': app.profile(), 'certificate_ids': []}
        app.save_job(self.job)
        self.token = review.fingerprint(self.job)

    def tearDown(self):
        app.STOP.clear()
        self.db.stop()
        self.temp.cleanup()

    def approve(self, automatic=True):
        with app.MUTATION_LOCK, patch('submission_queue.threading.Thread') as thread:
            queue.decide(self.job['id'], 'approve', self.token, automatic)
        return thread

    def test_automatic_approval_starts_worker_once(self):
        first = self.approve()
        second = self.approve()
        first.return_value.start.assert_called_once()
        second.assert_not_called()
        self.assertEqual(app.get_job(self.job['id'])['submission_requested'], self.token)

    def test_manual_approval_does_not_submit(self):
        thread = self.approve(False)
        thread.assert_not_called()
        self.assertTrue(review.approved(app.get_job(self.job['id'])))
        self.assertFalse(app.get_job(self.job['id']).get('submission_requested'))

    def test_worker_submits_only_approved_job_using_its_profile(self):
        self.approve()
        def run(ids, submit, profile_id):
            self.assertEqual((ids, submit, profile_id), ([self.job['id']], True, 'default'))
            self.assertTrue(app.RUN_LOCK.locked())
            app.set_status(self.job['id'], 'submitted', 'Fixture confirmation')
            app.RUN_LOCK.release()
        with patch.object(app, 'run_queue', side_effect=run) as worker:
            queue.submit_when_idle(self.job['id'], self.token)
            queue.submit_when_idle(self.job['id'], self.token)
        worker.assert_called_once()
        self.assertEqual(app.get_job(self.job['id'])['status'], 'submitted')
        self.assertFalse(app.get_job(self.job['id'])['submission_in_progress'])

    def test_rejection_cancels_waiting_submission(self):
        self.approve()
        with app.MUTATION_LOCK:
            queue.decide(self.job['id'], 'reject')
        with patch.object(app, 'run_queue') as worker:
            queue.submit_when_idle(self.job['id'], self.token)
        worker.assert_not_called()
        self.assertEqual(app.get_job(self.job['id'])['status'], 'rejected')
        self.assertFalse(review.approved(app.get_job(self.job['id'])))

    def test_changed_documents_cancel_submission(self):
        self.approve()
        job = app.get_job(self.job['id'])
        job['cover_letter'] = 'Changed letter'
        app.save_job(job)
        with patch.object(app, 'run_queue') as worker:
            queue.submit_when_idle(self.job['id'], self.token)
        worker.assert_not_called()
        self.assertFalse(app.get_job(self.job['id'])['submission_requested'])

    def test_stale_or_uncertain_approvals_are_rejected(self):
        for status, token in [('ready', 'old-token'), ('uncertain', self.token), ('submitted', self.token)]:
            app.save_job({**self.job, 'status': status})
            with self.subTest(status=status), app.MUTATION_LOCK, self.assertRaises(ValueError):
                queue.decide(self.job['id'], 'approve', token, True)

    def test_stop_cancels_pending_jobs(self):
        self.approve()
        with app.MUTATION_LOCK:
            app.STOP.set()
            queue.cancel_pending()
        self.assertFalse(app.get_job(self.job['id'])['submission_requested'])

    def test_restart_does_not_retry_pending_or_active_jobs(self):
        self.approve()
        app.init()
        self.assertFalse(app.get_job(self.job['id'])['submission_requested'])
        app.save_job({**self.job, 'submission_in_progress': True})
        app.init()
        self.assertEqual(app.get_job(self.job['id'])['status'], 'uncertain')

    def test_worker_waits_for_another_browser_run(self):
        self.approve()
        done = threading.Event()
        def run(*args):
            app.RUN_LOCK.release()
            done.set()
        app.RUN_LOCK.acquire()
        with patch.object(app, 'run_queue', side_effect=run):
            worker = threading.Thread(target=queue.submit_when_idle, args=(self.job['id'], self.token))
            worker.start()
            self.assertFalse(done.wait(0.1))
            app.RUN_LOCK.release()
            self.assertTrue(done.wait(3))
            worker.join(3)
            self.assertFalse(worker.is_alive())

    def test_uncertain_submission_is_reconciled_without_applying_again(self):
        from submission_verification import recheck
        app.save_job({**self.job, 'status': 'uncertain'})
        with patch('browser_agent.BrowserAgent') as browser:
            agent = browser.return_value.__enter__.return_value
            agent.verify_submission.return_value = (True, 'Job page confirms: You applied on 14 September 2026')
            recheck([self.job['id']], app.profile())
            agent.apply.assert_not_called()
        job = app.get_job(self.job['id'])
        self.assertEqual(job['status'], 'submitted')
        self.assertTrue(job['submission_check']['confirmed'])

    def test_missing_confirmation_does_not_become_submitted(self):
        from submission_verification import recheck
        app.save_job({**self.job, 'status': 'uncertain'})
        with patch('browser_agent.BrowserAgent') as browser:
            agent = browser.return_value.__enter__.return_value
            agent.verify_submission.return_value = (False, 'Sign-in required.')
            recheck([self.job['id']], app.profile())
            agent.apply.assert_not_called()
        self.assertEqual(app.get_job(self.job['id'])['status'], 'uncertain')
