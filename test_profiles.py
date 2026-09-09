import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch
import app
import local_ai


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.override = patch.object(app, 'DB', Path(self.temp.name) / 'profiles.db')
        self.override.start()
        app.init()
        self.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.override.stop()
        self.temp.cleanup()

    def post(self, route, data):
        request = urllib.request.Request(self.base + route, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json', 'X-Session-Token': app.TOKEN})
        with urllib.request.urlopen(request) as response:
            return json.load(response)

    def test_profiles_keep_certifications_and_jobs_separate(self):
        it = {**app.profile(), 'title': 'Alex IT', 'name': 'Alex', 'email': 'alex@example.invalid', 'experience': 'IT support technician', 'certifications': 'IT Support Certificate | Example Institute | 2025'}
        self.post('/api/profile', it)
        self.post('/api/jobs', {'url': 'https://www.seek.com.au/job/12345678', 'title': 'Support technician', 'company': 'Fictional Co', 'description': 'Support users and maintain their computers and software.'})
        it_job = app.jobs()[0]
        self.post('/api/prepare', {'ids': [it_job['id']]})
        self.post('/api/profiles/create', {'title': 'Alex Aged Care'})
        care_id = app.profile()['id']
        care = {**app.profile(), 'name': 'Alex', 'email': 'alex@example.invalid', 'experience': 'Care assistant', 'certifications': 'First Aid | Example Training | Expires 2027-06-01'}
        self.post('/api/profile', care)
        with urllib.request.urlopen(self.base + '/api/state') as response:
            self.assertEqual(json.load(response)['jobs'], [])
        self.assertEqual(app.get_job(it_job['id'])['status'], 'ready')
        self.assertIn('IT Support Certificate', app.get_job(it_job['id'])['profile_snapshot']['certifications'])
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post('/api/run', {'ids': [it_job['id']]})
        self.assertEqual(error.exception.code, 400)
        error.exception.close()
        self.post('/api/profiles/select', {'id': 'default'})
        self.assertEqual(app.profile()['title'], 'Alex IT')
        self.assertNotIn('First Aid', app.tailor(app.profile(), {'description': 'IT Support'})['text'])
        self.assertIn('First Aid', app.profile(care_id)['certifications'])

    def test_unchanged_profile_and_account_links_preserve_documents(self):
        p = app.profile()
        app.save_job({'id': 'draft', 'url': 'https://www.seek.com.au/job/98765432', 'profile_id': p['id'], 'status': 'ready', 'resume': {'text': 'Existing draft'}, 'cover_letter': 'Existing letter'})
        self.post('/api/profile', p)
        self.assertEqual(app.get_job('draft')['status'], 'ready')
        self.post('/api/profile', {**p, 'title': 'New title', 'linkedin_url': 'https://www.linkedin.com/in/example/'})
        self.assertEqual(app.get_job('draft')['cover_letter'], 'Existing letter')
        self.post('/api/profile', {**app.profile(), 'skills': 'Updated skill'})
        self.assertIsNone(app.get_job('draft')['resume'])

    def test_submission_requires_current_document_approval(self):
        from review import fingerprint, approved
        job = {'id': 'review', 'url': 'https://www.seek.com.au/job/98765432', 'profile_id': app.profile()['id'], 'status': 'ready', 'resume': {'text': 'Resume'}, 'cover_letter': 'Letter'}
        app.save_job(job)
        with self.assertRaises(urllib.error.HTTPError) as err:
            self.post('/api/run', {'ids': ['review'], 'submit': True})
        self.assertEqual(err.exception.code, 400)
        err.exception.close()
        self.assertFalse(app.RUN_LOCK.locked())
        self.post('/api/review/approve', {'id': 'review', 'review_token': fingerprint(job)})
        self.assertTrue(approved(app.get_job('review')))
        old_token = fingerprint(job)
        job = app.get_job('review')
        job['cover_letter'] = 'Revised letter'
        app.save_job(job)
        self.assertFalse(approved(job))
        with self.assertRaises(urllib.error.HTTPError) as err:
            self.post('/api/review/approve', {'id': 'review', 'review_token': old_token})
        self.assertEqual(err.exception.code, 400)
        err.exception.close()

    def test_legacy_profile_is_migrated_once(self):
        with app.connect() as c:
            c.execute('DELETE FROM profiles')
            c.execute("INSERT OR REPLACE INTO settings VALUES ('profile', ?)", (json.dumps({'name': 'Legacy Applicant', 'education': 'Existing qualification'}),))
        app.init()
        self.assertEqual(app.profile()['name'], 'Legacy Applicant')
        self.assertEqual(app.profile()['education'], 'Existing qualification')
        self.post('/api/profile', {**app.profile(), 'title': 'Renamed'})
        app.init()
        self.assertEqual(app.profile()['title'], 'Renamed')

    def test_certifications_reach_model_and_resume(self):
        p = {**app.profile(), 'certifications': 'First Aid | Expires 2027-06-01'}
        response = {'message': {'content': json.dumps({'summary': 'Profile summary.', 'skills': []})}}
        with patch.object(local_ai, 'request', return_value=response) as request:
            draft = local_ai.rewrite(p, {'title': 'Care assistant', 'description': 'First Aid required.'})
        data = json.loads(request.call_args.args[1]['messages'][1]['content'])
        self.assertEqual(data['candidate_facts']['certifications'], p['certifications'])
        self.assertIn('CERTIFICATIONS\nFirst Aid', app.tailor(p, {'description': 'First Aid required'}, draft)['text'])


if __name__ == '__main__':
    unittest.main()
