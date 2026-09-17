import unittest
from job_location import matches, profile_location


class LocationTests(unittest.TestCase):
    def test_profile_location_takes_priority(self):
        self.assertEqual(profile_location({'location': 'Darwin, NT', 'search_location': 'Sydney'}), 'Darwin, NT')

    def test_street_address_uses_explicit_search_area(self):
        profile = {'location': '12 Example Crescent, Coconut Grove NT', 'search_location': 'Darwin NT'}
        self.assertEqual(profile_location(profile), 'Darwin NT')
        self.assertTrue(matches(profile, {'location': 'Darwin, Northern Territory'}))
        self.assertFalse(matches(profile, {'location': 'Sydney NSW'}))
        self.assertEqual(profile_location({**profile, 'search_location': ''}), '')

    def test_locality_and_region_variants(self):
        profile = {'location': 'Darwin, NT 0800'}
        for location in ('Darwin', 'Darwin, Northern Territory, Australia', 'Darwin NT (Hybrid)',
                         '{"addressLocality":"Darwin","addressRegion":"NT","postalCode":"0800"}',
                         'Sydney NSW; Darwin NT'):
            with self.subTest(location=location):
                self.assertTrue(matches(profile, {'location': location}))

    def test_different_or_unknown_locations_are_excluded(self):
        profile = {'location': 'Darwin, NT', 'search_location': 'Sydney'}
        for location in ('Sydney NSW', 'Alice Springs NT', 'Darwin NSW', 'Remote Australia', '', 'Northern Territory', 'Darwinville NT'):
            with self.subTest(location=location):
                self.assertFalse(matches(profile, {'location': location, 'description': 'Our company has an office in Darwin.'}))

    def test_legacy_search_location_and_postcode_only(self):
        self.assertTrue(matches({'search_location': 'Darwin'}, {'location': 'Darwin NT'}))
        self.assertTrue(matches({'location': '0800'}, {'location': 'Darwin NT 0800'}))
        self.assertFalse(matches({'location': '0800'}, {'location': 'Sydney 2000'}))
