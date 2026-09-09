import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree
import app


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.override = patch.object(app, 'DB', Path(self.tmp.name) / 'test.db')
        self.override.start()
        app.init()

    def tearDown(self):
        self.override.stop()
        self.tmp.cleanup()

    def test_links_are_canonical_and_restricted(self):
        self.assertEqual(app.validate_url('https://au.linkedin.com/jobs/view/service-agent-123?tracking=abc')[0], 'https://www.linkedin.com/jobs/view/123/')
        self.assertEqual(app.validate_url('https://www.linkedin.com/jobs/view/engineer-123/?trackingId=abc')[0], 'https://www.linkedin.com/jobs/view/123/')
        self.assertEqual(app.validate_url('https://seek.com.au/job/123?ref=search')[0], 'https://www.seek.com.au/job/123')
        for url in ['http://www.seek.com.au/job/123', 'https://www.seek.com.au.evil.com/job/123', 'https://localhost/job/123', 'https://www.linkedin.com/feed/', 'https://user@www.seek.com.au/job/123']:
            with self.assertRaises(ValueError):
                app.validate_url(url)

    def test_tailoring_does_not_invent_experience(self):
        p = {**app.DEFAULT_PROFILE, 'name': 'Example Person', 'skills': 'Java, Python, Excel', 'experience': 'Shop assistant, 2020–2024\nManaged stock.', 'education': 'Certificate II'}
        result = app.tailor(p, {'description': 'Python and JavaScript expert with a PhD wanted'})
        self.assertEqual(result['matched'], ['Python'])
        self.assertIn('Python, Java, Excel', result['text'])
        self.assertIn(p['experience'], result['text'])
        self.assertNotIn('PhD', result['text'])

    def test_docx_handles_unicode_and_xml(self):
        text = 'Zoë & 李\n<Experience>\nActual facts'
        with zipfile.ZipFile(io.BytesIO(app.docx(text))) as archive:
            root = ElementTree.fromstring(archive.read('word/document.xml'))
            actual = '\n'.join(n.text or '' for n in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'))
            self.assertEqual(text, actual)

    def test_interrupted_submission_is_not_retried(self):
        app.save_job({'id': 'abc', 'url': 'https://www.seek.com.au/job/123', 'status': 'running'})
        app.init()
        self.assertEqual(app.get_job('abc')['status'], 'uncertain')

    def test_jobs_persist_without_duplicates(self):
        app.save_job({'id': 'abc', 'url': 'https://www.seek.com.au/job/123', 'status': 'saved'})
        app.set_status('abc', 'submitted', 'Confirmed')
        self.assertEqual(len(app.jobs()), 1)
        self.assertEqual(app.get_job('abc')['status'], 'submitted')


if __name__ == '__main__':
    unittest.main()
