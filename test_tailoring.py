import copy
import unittest
import app
from tailoring import focused_profile


class TailoringTests(unittest.TestCase):
    def setUp(self):
        self.profile = {**app.DEFAULT_PROFILE, 'name': 'Example', 'headline': 'Software developer',
                        'skills': 'Python, Personal care', 'education': 'Certificate III Individual Support\nDiploma of Software Development',
                        'certifications': 'First Aid | Valid to 2028\nCloud Computing Certificate',
                        'experience': 'Care placement | Example Home | 2025\n- Assisted residents under supervision.\n- Updated the staff website.'}
        self.draft = {'summary': 'Care placement experience with supervised resident support.', 'skills': ['Personal care'],
                      'selection': {'headline': False, 'education': [0], 'certifications': [0], 'experience': [1]}}

    def test_irrelevant_facts_are_removed_without_modifying_profile(self):
        original = copy.deepcopy(self.profile)
        text = app.tailor(self.profile, {'description': 'Personal care and First Aid.'}, self.draft)['text']
        for removed in ('Python', 'Software', 'software', 'Cloud Computing', 'staff website'):
            self.assertNotIn(removed, text)
        for kept in ('Care placement | Example Home | 2025', 'under supervision', 'First Aid | Valid to 2028', 'Certificate III Individual Support'):
            self.assertIn(kept, text)
        self.assertEqual(self.profile, original)

    def test_cover_letter_facts_use_the_same_selection(self):
        focused = focused_profile(self.profile, self.draft)
        self.assertEqual(focused['certifications'], 'First Aid | Valid to 2028')
        self.assertEqual(focused['skills'], 'Personal care')
        self.assertNotIn('staff website', focused['experience'])

    def test_out_of_range_and_boolean_indexes_are_rejected(self):
        for index in (-1, 99, True, '0'):
            with self.subTest(index=index), self.assertRaises(ValueError):
                focused_profile(self.profile, {**self.draft, 'selection': {**self.draft['selection'], 'education': [index]}})

    def test_unrelated_employment_is_omitted_with_its_headings(self):
        profile = {**self.profile, 'experience': self.profile['experience'] + '\n\nDeveloper | Software Co | 2022\n- Built Python websites.'}
        focused = focused_profile(profile, self.draft)
        self.assertNotIn('Software Co', focused['experience'])
        self.assertNotIn('Developer', focused['experience'])
        self.assertIn('Care placement | Example Home | 2025', focused['experience'])

    def test_company_background_is_excluded_but_later_duties_remain(self):
        from tailoring import requirements_text
        text = 'About us: We run Python websites.\nResponsibilities:\nProvide personal care.\nBenefits:\nFree cloud courses.\nRequirements:\nFirst Aid required.'
        result = requirements_text(text)
        self.assertNotIn('Python', result)
        self.assertNotIn('cloud', result)
        self.assertIn('Provide personal care.', result)
        self.assertIn('First Aid required.', result)

    def test_relevant_wording_variants_are_retained(self):
        from tailoring import relevant_fact
        self.assertTrue(relevant_fact('Respectful communication', {'description': 'Communicate respectfully with residents.'}))
        self.assertTrue(relevant_fact('Teamwork', {'description': 'Work collaboratively with colleagues.'}))
        self.assertFalse(relevant_fact('Python development', {'description': 'Provide personal care and communicate with residents.'}))

    def test_kitchen_excludes_care_placement_even_when_hygiene_overlaps(self):
        profile = {**self.profile, 'experience': 'Aged Care Placement | Care Home | 2025\n- Followed hygiene and workplace safety procedures.\nCleaner | Cleaning Co | 2024\n- Used cleaning equipment safely.'}
        draft = {**self.draft, 'target_job': {'title': 'Kitchen Steward'}, 'selection': {**self.draft['selection'], 'experience': [1, 3]}}
        focused = focused_profile(profile, draft)
        self.assertNotIn('Care Home', focused['experience'])
        self.assertIn('Cleaning Co', focused['experience'])

    def test_actual_kitchen_advert_section_names(self):
        from tailoring import requirements_text
        text = 'Kitchen steward opportunity.\nWhat We Offer\nFree parking.\nWhat will you do?\nClean kitchen equipment.\nMore About You\nFood Safety Certificate.\nWho We Are\nResort entertainment.'
        result = requirements_text(text)
        self.assertIn('Clean kitchen equipment.', result)
        self.assertIn('Food Safety Certificate.', result)
        self.assertNotIn('Free parking', result)
        self.assertNotIn('Resort entertainment', result)

    def test_plain_text_duties_keep_their_own_employer_and_scope(self):
        profile = {**self.profile, 'experience': 'Example Care Home\n\nPlacement Student\n120-hour placement\n\nAssisted residents under supervision.\nUpdated the company website.\n\nSoftware Co\nDeveloper\n2022\nBuilt websites using Python.'}
        draft = {**self.draft, 'selection': {**self.draft['selection'], 'experience': [5]}}
        focused = focused_profile(profile, draft)
        self.assertIn('Example Care Home', focused['experience'])
        self.assertIn('Placement Student', focused['experience'])
        self.assertIn('120-hour placement', focused['experience'])
        self.assertIn('under supervision', focused['experience'])
        self.assertNotIn('website', focused['experience'])
        self.assertNotIn('Software Co', focused['experience'])
