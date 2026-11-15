import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import bot

class BaselineChangeTests(unittest.TestCase):
    def test_changed_search_does_not_silently_consume_new_offer(self):
        ad=bot.Listing('NEW','iPhone 13 128GB','https://www.olx.pl/a')
        cfg={'searches':[{'url':'https://www.olx.pl/new-filter'}]}
        with tempfile.TemporaryDirectory() as tmp, patch.object(bot,'STATE_PATH',Path(tmp)/'seen.json'),patch.object(bot,'load_config',return_value=cfg),patch.object(bot,'fetch_search',return_value=[ad]),patch.object(bot,'publish_status'),patch.object(bot,'send_alert',return_value=True) as send:
            bot.save_state({'initialized':True,'seen_ids':['OLD'],'initialized_searches':['https://www.olx.pl/old-filter']})
            self.assertEqual(bot.run_once(),0)
            send.assert_called_once()
            state=bot.load_state()
            self.assertIn('NEW',state['notified_ids'])
            self.assertEqual(bot.run_once(),0)
            self.assertEqual(send.call_count,1)
