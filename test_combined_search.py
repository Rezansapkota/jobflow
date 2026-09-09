import unittest
from unittest.mock import Mock, patch
from discovery import discover


class CombinedSearchTests(unittest.TestCase):
    def test_both_sites_contribute_before_limit(self):
        agent = Mock()
        agent.stopped.return_value = False
        closed = []
        def source_stream(agent, profile, config, seen):
            source = config['sources'][0]
            try:
                for index in range(10):
                    yield {'source': source, 'index': index}
            finally:
                closed.append(source)
        with patch('discovery.discover_site', side_effect=source_stream):
            jobs = list(discover(agent, {}, {'sources': ['LinkedIn', 'SEEK'], 'max_jobs': 4}, set()))
        self.assertEqual([j['source'] for j in jobs], ['LinkedIn', 'SEEK', 'LinkedIn', 'SEEK'])
        self.assertCountEqual(closed, ['LinkedIn', 'SEEK'])

    def test_empty_site_does_not_block_other_site(self):
        agent = Mock()
        agent.stopped.return_value = False
        def source_stream(agent, profile, config, seen):
            if config['sources'] == ['SEEK']:
                yield {'source': 'SEEK'}
        with patch('discovery.discover_site', side_effect=source_stream):
            jobs = list(discover(agent, {}, {'sources': ['LinkedIn', 'SEEK'], 'max_jobs': 4}, set()))
        self.assertEqual(jobs, [{'source': 'SEEK'}])
