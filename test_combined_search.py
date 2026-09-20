import unittest
from unittest.mock import Mock, patch
from discovery import discover


class CombinedSearchTests(unittest.TestCase):
    def test_seek_listing_date_is_attached_to_the_correct_job(self):
        from discovery import discover_site
        agent = Mock()
        agent.stopped.return_value = False
        agent.source_issues = []
        search, detail = Mock(), Mock()
        agent.context.new_page.side_effect = [search, detail]
        links, cards = Mock(), Mock()
        links.evaluate_all.return_value = ['https://www.seek.com.au/job/12345678']
        cards.evaluate_all.return_value = [{'url': 'https://au.seek.com/job/12345678?ref=search', 'posted': '2h ago'}]
        search.locator.side_effect = lambda selector: cards if selector == 'article' else links
        config = {'sources': ['SEEK'], 'roles': ['Care worker'], 'pages': 1, 'max_jobs': 1}
        with patch('discovery.challenged', return_value=False), patch('discovery.wait_for_job'), patch('discovery.extract_job', return_value={'title': 'Care worker'}):
            jobs = list(discover_site(agent, {'search_location': 'Darwin'}, config, set()))
        self.assertEqual(jobs[0]['posted_label'], '2h ago')

    def test_visible_search_waits_for_verification_and_resumes(self):
        from discovery import discover_site
        agent = Mock()
        agent.headless = False
        agent.stopped.return_value = False
        agent.source_issues = []
        search, detail = Mock(), Mock()
        agent.context.new_page.side_effect = [search, detail]
        search.locator.return_value.evaluate_all.return_value = ['https://www.seek.com.au/job/12345678']
        config = {'sources': ['SEEK'], 'roles': ['Care worker'], 'pages': 1, 'max_jobs': 1}
        with patch('discovery.challenged', side_effect=[True, False, False]), patch('discovery.wait_for_access') as wait, patch('discovery.wait_for_job'), patch('discovery.extract_job', return_value={'title': 'Care worker'}):
            jobs = list(discover_site(agent, {'search_location': 'Darwin'}, config, set()))
        wait.assert_called_once()
        self.assertEqual(jobs[0]['title'], 'Care worker')
        self.assertFalse(agent.source_issues)

    def test_posting_date_and_sort_parameters_for_both_sites(self):
        from discovery import search_url
        from urllib.parse import parse_qs, urlparse
        linkedin = parse_qs(urlparse(search_url('LinkedIn', 'Care worker', 'Darwin', 1, 1, 'newest')).query)
        seek = parse_qs(urlparse(search_url('SEEK', 'Care worker', 'Darwin', 1, 7, 'newest')).query)
        self.assertEqual(linkedin['f_TPR'], ['r86400'])
        self.assertEqual(linkedin['sortBy'], ['DD'])
        self.assertEqual(linkedin['start'], ['25'])
        self.assertEqual(seek['daterange'], ['7'])
        self.assertEqual(seek['sortmode'], ['ListedDate'])
        self.assertEqual(seek['page'], ['2'])
        self.assertNotIn('daterange', search_url('SEEK', 'Care', 'Darwin'))

    def test_delayed_detail_verification_stops_site_after_one_job(self):
        from discovery import discover_site
        agent = Mock()
        agent.stopped.return_value = False
        agent.source_issues = []
        search, detail = Mock(), Mock()
        agent.context.new_page.side_effect = [search, detail]
        search.locator.return_value.evaluate_all.return_value = ['https://www.seek.com.au/job/12345678', 'https://www.seek.com.au/job/12345679']
        config = {'sources': ['SEEK'], 'roles': ['Cleaner'], 'pages': 1, 'max_jobs': 10}
        with patch('discovery.challenged', side_effect=[False, False, True]), patch('discovery.wait_for_job') as wait, patch('discovery.extract_job') as extract:
            self.assertEqual(list(discover_site(agent, {'search_location': 'Darwin'}, config, set())), [])
        wait.assert_called_once_with(detail)
        extract.assert_not_called()
        detail.close.assert_called_once()
        self.assertEqual(len(agent.source_issues), 1)
        self.assertIn('verification or sign-in required', agent.source_issues[0])

    def test_network_denial_stops_repeated_queries_and_reports_fix(self):
        from discovery import discover_site
        agent = Mock()
        agent.stopped.return_value = False
        agent.source_issues = []
        page = agent.context.new_page.return_value
        page.goto.side_effect = RuntimeError('net::ERR_NETWORK_ACCESS_DENIED')
        config = {'sources': ['SEEK'], 'roles': ['Cleaner', 'Kitchen hand'], 'pages': 3, 'max_jobs': 10}
        self.assertEqual(list(discover_site(agent, {'search_location': 'Darwin'}, config, set())), [])
        self.assertEqual(page.goto.call_count, 1)
        page.close.assert_called_once()
        self.assertIn('Chrome cannot access the internet', agent.source_issues[0])

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
