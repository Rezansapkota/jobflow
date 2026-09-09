import unittest
from unittest.mock import Mock, patch
import accounts


class AccountTests(unittest.TestCase):
    def tearDown(self):
        accounts.PENDING = None
        accounts.CONFIRMED.clear()

    def test_links_only_open_expected_site(self):
        for value in ('http://www.linkedin.com/in/test', 'https://linkedin.com.evil.test/', 'https://user:secret@linkedin.com/', 'https://www.seek.com.au/profile/me', 'file:///tmp/test'):
            with self.assertRaises(ValueError):
                accounts.account_url({'linkedin_url': value}, 'LinkedIn')
        self.assertEqual(accounts.account_url({}, 'SEEK'), 'https://www.seek.com.au/profile/me')

    def test_confirmation_cannot_cross_profiles_or_requests(self):
        accounts.PENDING = {'id': 'request', 'profile_id': 'default', 'source': 'SEEK'}
        for token, pid in [('old', 'default'), ('request', 'another')]:
            with self.assertRaises(ValueError):
                accounts.confirm(token, pid)
        self.assertFalse(accounts.CONFIRMED.is_set())
        accounts.confirm('request', 'default')
        self.assertTrue(accounts.CONFIRMED.is_set())

    def test_confirmation_waits_for_login_then_cleans_up(self):
        agent = Mock()
        agent.stopped.return_value = False
        page = agent.context.new_page.return_value
        page.is_closed.return_value = False
        page.url = 'https://www.seek.com.au/profile/me'
        def confirm_in_ui(*args):
            pending = accounts.pending()
            accounts.confirm(pending['id'], pending['profile_id'])
        page.wait_for_timeout.side_effect = confirm_in_ui
        with patch('discovery.challenged', side_effect=[True, False]) as challenge:
            accounts.prepare(agent, {'id': 'default'}, ['SEEK'])
        self.assertEqual(challenge.call_count, 2)
        page.close.assert_called_once()
        self.assertIsNone(accounts.pending())

    def test_stop_never_opens_site(self):
        agent = Mock()
        agent.stopped.return_value = True
        with self.assertRaises(ValueError):
            accounts.prepare(agent, {}, ['SEEK'])
        agent.context.new_page.assert_not_called()
