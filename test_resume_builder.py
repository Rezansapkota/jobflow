import copy
import threading
import time
import unittest
from unittest.mock import patch

import app
import local_ai
import resume_builder as builder


PROFILE = {**app.DEFAULT_PROFILE, 'id': 'builder-test', 'name': 'Alex Example', 'email': 'alex@example.test',
           'skills': 'Customer service, Microsoft Excel, Python',
           'experience': 'Service Assistant | Example Co | 2022-2024\n- Provided customer service and resolved enquiries.\n'
                         '- Used Microsoft Excel to track requests.\nDeveloper | Tech Co | 2020-2021\n- Built Python websites.',
           'education': 'Software Development Diploma', 'certifications': 'Forklift licence, not yet obtained'}
JOB = {'title': 'Customer Service Officer', 'description':
       'Responsibilities:\nProvide customer service and use Microsoft Excel.\nRequirements:\nCurrent forklift licence required.'}


class ResumeBuilderTests(unittest.TestCase):
    def setUp(self):
        self.ai_lock = threading.Lock()
        self.lock_patch = patch.object(app, 'AI_LOCK', self.ai_lock)
        self.lock_patch.start()
        self.addCleanup(self.lock_patch.stop)
        self.profile = copy.deepcopy(PROFILE)
        self.body = {'profile_id': self.profile['id'], 'candidate': self.profile, 'engine': 'basic', **JOB}

    def completed_task(self, task_id):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = builder.get(task_id, self.profile['id'])
            if result['status'] != 'running' and not self.ai_lock.locked():
                return result
            time.sleep(.01)
        self.fail('Background task did not finish.')

    def test_basic_tailoring_retains_employment_attribution_without_inventing_requirements(self):
        original = copy.deepcopy(self.profile)
        result = builder.generate(self.profile, JOB, 'basic')
        self.assertIn('Service Assistant | Example Co | 2022-2024', result['text'])
        self.assertIn('Microsoft Excel', result['text'])
        for unrelated in ('Python', 'Tech Co', 'Software Development', 'Forklift'):
            self.assertNotIn(unrelated, result['text'])
        self.assertTrue(any('forklift' in row['requirement'] for row in result['requirements']))
        self.assertTrue(all(row['status'] == 'review' for row in result['requirements']))
        self.assertEqual(self.profile, original)

    def test_extractive_summary_keeps_compound_verbs_grammatical(self):
        summary = builder.basic_draft(self.profile, JOB)['summary']
        self.assertTrue(summary.startswith('Provided customer service and resolved enquiries.'))

    def test_quoted_evidence_is_checked_before_display(self):
        result = {'requirements': [{'requirement': 'Current forklift licence required.', 'evidence': ['Current forklift licence'],
                                    'status': 'evidenced', 'note': 'Meets requirement.'}]}
        with patch.object(local_ai, 'structured', return_value=result):
            rows = builder.analysis(self.profile, JOB, 'ollama')
        self.assertEqual(rows[0]['status'], 'not_found')
        self.assertEqual(rows[0]['evidence'], [])
        self.assertNotIn('Meets requirement', rows[0]['note'])

    def test_model_cannot_invent_requirements(self):
        result = {'requirements': [{'requirement': 'Must have a doctorate.', 'evidence': [], 'status': 'not_found', 'note': ''}]}
        with patch.object(local_ai, 'structured', return_value=result), self.assertRaisesRegex(ValueError, 'traced'):
            builder.analysis(self.profile, JOB, 'ollama')

    def test_short_quote_cannot_hide_an_unconfirmed_credential(self):
        result = {'requirements': [{'requirement': 'Current forklift licence required.', 'evidence': ['Forklift licence'],
                                    'status': 'evidenced', 'note': 'Meets requirement.'}]}
        with patch.object(local_ai, 'structured', return_value=result):
            rows = builder.analysis(self.profile, JOB, 'ollama')
        self.assertEqual(rows[0]['status'], 'not_found')
        basic = builder.analysis(self.profile, JOB, 'basic')
        licence = next(row for row in basic if 'forklift' in row['requirement'])
        self.assertEqual(licence['evidence'], [])

    def test_ai_generation_uses_existing_verified_rewrite_and_preserves_source(self):
        draft = builder.basic_draft(self.profile, JOB)
        draft['summary'] = 'Customer service experience with Microsoft Excel.'
        original = copy.deepcopy(self.profile)
        with patch.object(builder, 'analysis', return_value=[]), patch.object(local_ai, 'rewrite', return_value=draft) as rewrite:
            result = builder.generate(self.profile, JOB, 'ollama')
        rewrite.assert_called_once_with(self.profile, JOB, preferences=local_ai.RESUME_DEFAULTS)
        self.assertIn(draft['summary'], result['text'])
        self.assertEqual(result['engine'], 'ollama')
        self.assertEqual(self.profile, original)

    def test_tasks_are_profile_scoped_and_release_busy_lock(self):
        task = builder.start(self.body, self.profile)
        result = self.completed_task(task['id'])
        self.assertEqual(result['status'], 'complete')
        self.assertIn('Customer service', result['result']['text'])
        with self.assertRaisesRegex(ValueError, 'not found'):
            builder.get(task['id'], 'other-profile')

    def test_local_ai_failure_is_visible_without_fabricated_fallback(self):
        with patch.object(builder, 'generate', side_effect=ValueError('Ollama is unavailable.')):
            task = builder.start(self.body, self.profile)
            result = self.completed_task(task['id'])
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['message'], 'Ollama is unavailable.')
        self.assertNotIn('result', result)

    def test_invalid_requests_never_start_work(self):
        for changes in ({'profile_id': 'other'}, {'description': 'Short'}, {'engine': 'cloud'},
                        {'candidate': {'name': 12}}, {'candidate': {}}, {'description': 'A' * 16001}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                builder.start({**self.body, **changes}, self.profile)
            self.assertFalse(self.ai_lock.locked())

    def test_concurrent_analysis_is_rejected(self):
        self.ai_lock.acquire()
        try:
            with self.assertRaisesRegex(ValueError, 'Another analysis'):
                builder.start(self.body, self.profile)
        finally:
            self.ai_lock.release()

    def test_profile_context_and_preferences_reach_the_local_worker(self):
        self.profile.update(work_rights='Australian citizen', constraints='Available weekdays only',
                            roles='Customer Service Officer', search_location='Darwin',
                            answers={'Expected salary': '$65,000'})
        preferences = {'length': 'concise', 'tone': 'formal', 'emphasis': 'achievements', 'max_skills': 6}
        with patch.object(builder, 'generate', return_value={'text': 'Test resume'}) as generate:
            task = builder.start({**self.body, 'preferences': preferences}, self.profile)
            self.completed_task(task['id'])
        candidate = generate.call_args.args[0]
        self.assertEqual(candidate['_application_context']['work_rights'], 'Australian citizen')
        self.assertEqual(candidate['_application_context']['constraints'], 'Available weekdays only')
        self.assertIn('$65,000', candidate['_application_context']['saved_application_answers'])
        self.assertEqual(generate.call_args.kwargs['preferences'], preferences)

    def test_context_evidence_is_used_for_analysis_but_not_copied_into_resume(self):
        p = {**self.profile, '_application_context': {'work_rights': 'Australian citizen'}}
        job = {**JOB, 'description': JOB['description'] + '\nAustralian citizenship required.'}
        result = {'requirements': [{'requirement': 'Australian citizenship required.', 'evidence': ['Australian citizen'],
                                    'status': 'evidenced', 'note': 'Check requirements.'}]}
        with patch.object(local_ai, 'structured', return_value=result) as model:
            rows = builder.analysis(p, job, 'ollama')
        self.assertEqual(rows[0]['evidence'], ['Australian citizen'])
        self.assertEqual(model.call_args.args[1]['candidate']['work_rights'], 'Australian citizen')
        resume = builder.generate(p, job, 'basic')['text']
        self.assertNotIn('Australian citizen', resume)

    def test_unknown_preferences_and_boolean_skill_limit_are_rejected(self):
        for preferences in ({'max_skills': True}, {'tone': 'invent credentials'}, {'model': 'cloud'}, []):
            with self.subTest(preferences=preferences), self.assertRaises(ValueError):
                builder.start({**self.body, 'preferences': preferences}, self.profile)
        self.assertFalse(self.ai_lock.locked())


if __name__ == '__main__':
    unittest.main()
