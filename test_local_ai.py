import json
import unittest
from unittest.mock import patch
import app
import local_ai


class LocalAITests(unittest.TestCase):
    def setUp(self):
        self.profile = {**app.DEFAULT_PROFILE, 'name': 'Example', 'summary': 'Service assistant.',
                        'skills': 'Excel, Customer service', 'experience': 'Assistant | Example Co | 2022–2024', 'education': 'Certificate II'}
        self.job = {'title': 'Service officer', 'description': 'Customer service and team communication.'}

    def response(self, summary='Service assistant with customer service experience.', skills=None):
        return {'message': {'content': json.dumps({'summary': summary, 'skills': skills if skills is not None else ['Customer service']})}}

    def test_local_draft_preserves_source_history(self):
        with patch.object(local_ai, 'request', return_value=self.response()) as request:
            draft = local_ai.rewrite(self.profile, self.job)
        result = app.tailor(self.profile, self.job, draft)
        self.assertIn(self.profile['experience'], result['text'])
        self.assertIn(self.profile['education'], result['text'])
        self.assertIn('Customer service, Excel', result['text'])
        self.assertEqual(result['engine'], 'qwen3:8b')
        body = request.call_args.args[1]
        self.assertFalse(body['stream'])
        self.assertFalse(body['think'])
        self.assertNotIn('email', json.loads(body['messages'][1]['content'])['candidate_facts'])

    def test_invented_skills_are_rejected(self):
        with patch.object(local_ai, 'request', return_value=self.response(skills=['Surgery'])):
            with self.assertRaisesRegex(ValueError, 'outside your profile'):
                local_ai.rewrite(self.profile, self.job)

    def test_invalid_model_output_is_rejected(self):
        for result in ({'message': {'content': 'not JSON'}}, self.response(summary=''), {'done_reason': 'length'}):
            with patch.object(local_ai, 'request', return_value=result):
                with self.assertRaises(ValueError):
                    local_ai.rewrite(self.profile, self.job)

    def test_unavailable_model_is_reported(self):
        with patch.object(local_ai, 'request', side_effect=ValueError('Offline')):
            self.assertFalse(local_ai.status()['available'])


if __name__ == '__main__':
    unittest.main()
