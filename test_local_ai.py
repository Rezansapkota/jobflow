import json
import unittest
from unittest.mock import patch
import app
import local_ai


class LocalAITests(unittest.TestCase):
    def setUp(self):
        self.profile = {**app.DEFAULT_PROFILE, 'name': 'Example', 'summary': 'Service assistant.',
                        'skills': 'Excel, Customer service', 'experience': 'Customer Service Assistant | Example Co | 2022–2024', 'education': 'Certificate II'}
        self.job = {'title': 'Service officer', 'description': 'Customer service and team communication.'}

    def response(self, summary='Service assistant with customer service experience.', skills=None):
        return {'message': {'content': json.dumps({'priorities': [self.job['description']], 'summary': summary, 'skills': skills if skills is not None else ['Customer service'],
                                                  'selection': {'headline': False, 'education': [0], 'certifications': [], 'experience': [0]}})}}

    def test_local_draft_preserves_source_history(self):
        with patch.object(local_ai, 'request', return_value=self.response()) as request:
            draft = local_ai.rewrite(self.profile, self.job)
        result = app.tailor(self.profile, self.job, draft)
        self.assertIn(self.profile['experience'], result['text'])
        self.assertNotIn(self.profile['education'], result['text'])
        self.assertIn('Customer service', result['text'])
        self.assertNotIn('Excel', result['text'])
        self.assertEqual(result['engine'], 'qwen3:8b')
        body = request.call_args_list[1].args[1]
        self.assertEqual(body['format']['properties']['skills']['items']['enum'], ['Excel', 'Customer service'])
        self.assertFalse(body['stream'])
        self.assertFalse(body['think'])
        self.assertNotIn('email', json.loads(body['messages'][1]['content'])['candidate_facts'])

    def test_invented_skills_are_rejected(self):
        with patch.object(local_ai, 'request', return_value=self.response(skills=['Surgery'])):
            with self.assertRaisesRegex(ValueError, 'outside your profile'):
                local_ai.rewrite(self.profile, self.job)

    def test_resume_preferences_reach_writing_prompts_and_enforce_skill_limit(self):
        skills = ['Excel', 'Customer service', 'Data entry', 'Payroll', 'Recruitment', 'Scheduling', 'Bookkeeping']
        self.profile['skills'] = ', '.join(skills)
        self.profile['_application_context'] = {'constraints': 'Weekdays only'}
        self.job['description'] = 'Required skills: ' + ', '.join(skills) + '.'
        preferences = {'length': 'concise', 'tone': 'formal', 'emphasis': 'achievements', 'max_skills': 6}
        with patch.object(local_ai, 'request', return_value=self.response(skills=skills)) as request:
            draft = local_ai.rewrite(self.profile, self.job, preferences=preferences)
        self.assertEqual(len(draft['skills']), 6)
        writing = request.call_args_list[1].args[1]['messages']
        self.assertIn('20-35 word summary', writing[0]['content'])
        self.assertIn('formal tone', writing[0]['content'])
        self.assertIn('never invent numbers', writing[0]['content'])
        facts = json.loads(writing[1]['content'])['candidate_facts']
        self.assertEqual(facts['writing_preferences'], preferences)
        self.assertEqual(facts['application_context_for_review_only']['constraints'], 'Weekdays only')
        summary_request = request.call_args_list[-2].args[1]['messages']
        self.assertEqual(json.loads(summary_request[1]['content'])['writing_preferences'], preferences)

    def test_unrelated_model_selections_are_removed_before_summary(self):
        profile = {**self.profile, 'skills': 'Python, Customer service',
                   'education': 'Software Development Diploma', 'certifications': 'Cloud Computing Certificate'}
        response = self.response(skills=['Python', 'Customer service'])
        payload = json.loads(response['message']['content'])
        payload['selection']['certifications'] = [0]
        response['message']['content'] = json.dumps(payload)
        with patch.object(local_ai, 'request', return_value=response) as request:
            draft = local_ai.rewrite(profile, self.job)
        self.assertEqual(draft['skills'], ['Customer service'])
        self.assertEqual(draft['selection']['education'], [])
        self.assertEqual(draft['selection']['certifications'], [])
        facts = json.loads(request.call_args_list[-1].args[1]['messages'][1]['content'])['candidate']
        self.assertEqual(facts['skills'], 'Customer service')
        self.assertEqual(facts['education'], '')
        self.assertEqual(facts['certifications'], '')

    def test_boilerplate_does_not_make_an_unrelated_skill_relevant(self):
        response = self.response(skills=['Python', 'Customer service'])
        profile = {**self.profile, 'skills': 'Python, Customer service'}
        job = {**self.job, 'description': self.job['description'] + ' Our company builds Python websites.'}
        with patch.object(local_ai, 'request', return_value=response):
            draft = local_ai.rewrite(profile, job)
        self.assertEqual(draft['skills'], ['Customer service'])

    def test_duplicate_and_conditional_credentials_are_removed(self):
        self.job['description'] = 'Customer service and First Aid required. Driver licence preferred.'
        profile = {**self.profile, 'education': 'First Aid\nCloud Computing Certificate',
                   'certifications': 'First Aid\nDriver licence, if applicable'}
        response = self.response()
        data = json.loads(response['message']['content'])
        data['selection'].update(education=[0, 1], certifications=[0, 1])
        response['message']['content'] = json.dumps(data)
        with patch.object(local_ai, 'request', return_value=response):
            draft = local_ai.rewrite(profile, self.job)
        from tailoring import focused_profile
        focused = focused_profile(profile, draft)
        self.assertEqual(focused['education'], 'First Aid')
        self.assertEqual(focused['certifications'], '')

    def test_job_priorities_must_be_quoted_from_description(self):
        for priorities in ([], ['Invented requirement not in the description.'], [False]):
            with self.subTest(priorities=priorities), patch.object(local_ai, 'structured', return_value={'priorities': priorities}), self.assertRaises(ValueError):
                local_ai.job_priorities(self.job)

    def test_unsupported_cover_letter_claims_use_factual_fallback(self):
        profile = {**self.profile, 'name': 'Example', 'skills': 'Cleaning, Customer service',
                   'experience': 'Cleaner | Example Co | 2025\nMaintained clean shared areas.\nFollowed safety procedures.'}
        job = {'title': 'Kitchen Steward', 'company': 'Example Hotel', 'description': 'Clean kitchen equipment. Food Safety Certificate preferred.'}
        with patch.object(local_ai, 'structured', side_effect=[{'body': 'I have extensive commercial kitchen experience and am willing to obtain a Food Safety Certificate for your hotel.'},
                                                              {'unsupported_claims': ['commercial kitchen experience', 'willing to obtain']} ]):
            letter = local_ai.cover_letter(profile, job)
        self.assertIn('I maintained clean shared areas.', letter)
        self.assertNotIn('commercial kitchen experience', letter)
        self.assertNotIn('willing to obtain', letter)

    def test_invalid_model_output_is_rejected(self):
        for result in ({'message': {'content': 'not JSON'}}, self.response(summary=''), {'done_reason': 'length'}):
            with patch.object(local_ai, 'request', return_value=result):
                with self.assertRaises(ValueError):
                    local_ai.rewrite(self.profile, self.job)

    def test_unavailable_model_is_reported(self):
        with patch.object(local_ai, 'request', side_effect=ValueError('Offline')):
            self.assertFalse(local_ai.status()['available'])

    def test_role_evidence_must_identify_a_target_and_quote_the_job(self):
        profile = {**self.profile, 'roles': 'Customer Service Officer'}
        result = {'score': 90, 'reason': 'Matching duties.', 'missing_requirements': [], 'unknown_requirements': [],
                  'role_match': True, 'location_match': True, 'matched_target_role': 'Customer Service Officer',
                  'role_evidence': 'Customer service and team communication.'}
        for target, evidence, expected in [('Customer Service Officer', result['role_evidence'], True),
                                           ('Kitchen Steward', result['role_evidence'], False),
                                           ('Customer Service Officer', 'Invented duties from the profile', False),
                                           ('Customer Service Officer', '', False)]:
            with self.subTest(target=target, evidence=evidence), patch.object(local_ai, 'structured', return_value={**result, 'matched_target_role': target, 'role_evidence': evidence}):
                assessment = local_ai.assess(profile, self.job)
                self.assertEqual(assessment['role_match'], expected)
                if not expected:
                    self.assertEqual(assessment['score'], 0)

    def test_assessment_does_not_reuse_previous_score(self):
        result = {'score': 0, 'reason': 'Different occupation.', 'missing_requirements': [], 'unknown_requirements': [],
                  'role_match': False, 'location_match': True, 'matched_target_role': '', 'role_evidence': ''}
        with patch.object(local_ai, 'structured', return_value=result) as structured:
            local_ai.assess(self.profile, {**self.job, 'assessment': {'score': 100}, 'note': 'Great match'})
        supplied_job = structured.call_args.args[1]['job']
        self.assertNotIn('assessment', supplied_job)
        self.assertNotIn('note', supplied_job)

    def test_ai_cannot_approve_a_different_location(self):
        result = {'score': 95, 'reason': 'Good match.', 'missing_requirements': [], 'unknown_requirements': [],
                  'role_match': True, 'location_match': True, 'matched_target_role': 'Service officer',
                  'role_evidence': 'Service officer'}
        profile = {**self.profile, 'roles': 'Service officer', 'location': 'Darwin NT', 'search_location': 'Sydney NSW'}
        with patch.object(local_ai, 'structured', return_value=result) as structured:
            assessment = local_ai.assess(profile, {**self.job, 'location': 'Sydney NSW'})
        self.assertFalse(assessment['location_match'])
        self.assertEqual(structured.call_args.args[1]['candidate']['search_location'], 'Darwin NT')


if __name__ == '__main__':
    unittest.main()
