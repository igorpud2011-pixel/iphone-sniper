import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import bot


class StateTests(unittest.TestCase):
    def test_partial_baseline_and_retry_failed_alert(self):
        a = bot.Listing('A', 'iPhone 11', 'https://www.olx.pl/a')
        b = bot.Listing('B', 'iPhone 12', 'https://www.olx.pl/b')
        new = bot.Listing('NEW', 'iPhone 12 Pro', 'https://www.olx.pl/new')
        cfg = {'searches': [{'url': 'https://www.olx.pl/11'}, {'url': 'https://www.olx.pl/12'}], 'delay_between_searches_seconds': 0}
        with tempfile.TemporaryDirectory() as tmp, patch.object(bot, 'STATE_PATH', Path(tmp)/'seen.json'), patch.object(bot, 'load_config', return_value=cfg), patch.object(bot, 'send_alert') as notify:
            with patch.object(bot, 'fetch_search', side_effect=[[a], RuntimeError('403')]):
                self.assertEqual(bot.run_once(), 1)
            notify.assert_not_called()
            with patch.object(bot, 'fetch_search', side_effect=[[a], [b]]):
                self.assertEqual(bot.run_once(), 0)
            notify.assert_not_called()
            with patch.object(bot, 'fetch_search', side_effect=[[a], [b, new]]), patch.object(bot, 'send_alert', return_value=False):
                self.assertEqual(bot.run_once(), 1)
            self.assertNotIn('NEW', bot.load_state()['seen_ids'])
            with patch.object(bot, 'fetch_search', side_effect=[[a], [b, new]]), patch.object(bot, 'send_alert', return_value=True) as success:
                self.assertEqual(bot.run_once(), 0)
                success.assert_called_once()
            self.assertEqual(bot.load_state()['seen_ids'], ['A', 'B', 'NEW'])
            with patch.object(bot, 'fetch_search', side_effect=[[a], [b, new]]):
                self.assertEqual(bot.run_once(), 0)
            notify.assert_not_called()

    def test_total_block_preserves_state(self):
        cfg = {'searches': [{'url': 'https://www.olx.pl/11'}]}
        with tempfile.TemporaryDirectory() as tmp, patch.object(bot, 'STATE_PATH', Path(tmp)/'seen.json'), patch.object(bot, 'load_config', return_value=cfg), patch.object(bot, 'fetch_search', side_effect=RuntimeError('403')):
            bot.save_state({'initialized': True, 'seen_ids': ['OLD'], 'initialized_searches': []})
            before = bot.STATE_PATH.read_bytes()
            self.assertEqual(bot.run_once(), 2)
            self.assertEqual(bot.STATE_PATH.read_bytes(), before)
