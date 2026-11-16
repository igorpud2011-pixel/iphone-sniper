import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import bot

class SecondaryRecheckTests(unittest.TestCase):
    def test_known_main_offer_is_enriched_and_secondary_sent_once(self):
        ad=bot.Listing('KNOWN','iPhone 13 128GB','https://www.olx.pl/d/oferta/test-IDknown.html',price='200 zł',description='Nie działa Face ID')
        cfg={'searches':[{'url':'https://www.olx.pl/search'}],'model_ids':['13']}
        with tempfile.TemporaryDirectory() as tmp,patch.object(bot,'STATE_PATH',Path(tmp)/'seen.json'),patch.object(bot,'load_config',return_value=cfg),patch.object(bot,'fetch_search',return_value=[ad]),patch.object(bot,'publish_status') as status,patch.dict('os.environ',{'DISCORD_DAMAGED_WEBHOOK_URL':'https://example.com/damaged'}),patch.object(bot,'send_alert') as main,patch.object(bot,'send_discord') as extra:
            bot.save_state({'initialized':True,'seen_ids':['KNOWN'],'notified_ids':['KNOWN']})
            self.assertEqual(bot.run_once(),0)
            self.assertEqual(status.call_args.args[0]['alerts'],1)
            self.assertEqual(bot.run_once(),0)
            self.assertEqual(status.call_args.args[0]['alerts'],0)
            main.assert_not_called()
            extra.assert_called_once()
            self.assertIn('KNOWN',bot.load_state()['secondary_delivered'])
    def test_whole_damaged_phone_for_parts_is_allowed_but_accessory_is_not(self):
        cfg={'model_ids':['13'],'include_damaged':True,'exclude_title_words':['na części','etui']}
        self.assertTrue(bot.is_flip_candidate(bot.Listing('a','iPhone 13 na części',''),cfg))
        self.assertTrue(bot.is_damaged(bot.Listing('a','iPhone 13 na części','')))
        self.assertFalse(bot.is_flip_candidate(bot.Listing('b','Etui iPhone 13 uszkodzone',''),cfg))

    def test_corrupt_secondary_history_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(bot,'STATE_PATH',Path(tmp)/'seen.json'):
            raw='{"seen_ids":[],"secondary_delivered":{"x":null}}'
            bot.STATE_PATH.write_text(raw)
            with self.assertRaises(RuntimeError):bot.load_state()
            self.assertEqual(bot.STATE_PATH.read_text(),raw)
