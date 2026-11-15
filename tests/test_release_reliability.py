import json
import os
import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch
import bot

class ReleaseReliabilityTests(unittest.TestCase):
    def test_corrupt_history_never_becomes_silent_baseline(self):
        for content in ('{broken', '[]', '{"seen_ids":[123]}', '{"seen_ids":[],"rejected_ids":null}'):
            with self.subTest(content=content),tempfile.TemporaryDirectory() as tmp,patch.object(bot,'STATE_PATH',Path(tmp)/'seen.json'),patch.object(bot,'load_config',return_value={'searches':[{'url':'https://www.olx.pl/search'}]}),patch.object(bot,'fetch_search') as fetch,patch.object(bot,'publish_status'):
                bot.STATE_PATH.write_text(content)
                self.assertEqual(bot.run_once(),2)
                self.assertEqual(bot.STATE_PATH.read_text(),content)
                fetch.assert_not_called()

    def test_successful_delivery_is_durable_before_slow_source_finishes(self):
        persisted=Event()
        observed=[]
        ad=bot.Listing('DURABLE','iPhone 13','https://www.olx.pl/d/oferta/test-IDdurable.html')
        cfg={'searches':[{'url':'https://www.olx.pl/fast'},{'url':'https://www.olx.pl/slow'}],'model_ids':['13']}
        original_save=bot.save_state
        def save(state,*args):
            original_save(state,*args)
            if 'DURABLE' in state.get('notified_ids',[]):persisted.set()
        def fetch(session,search,timeout):
            if search['url'].endswith('slow'):
                if persisted.wait(2):observed.append(json.loads(bot.STATE_PATH.read_text())['notified_ids'])
                return []
            return [ad]
        with tempfile.TemporaryDirectory() as tmp,patch.object(bot,'STATE_PATH',Path(tmp)/'seen.json'),patch.object(bot,'load_config',return_value=cfg),patch.object(bot,'fetch_search',side_effect=fetch),patch.object(bot,'send_alert',return_value=True) as send,patch.object(bot,'publish_status'):
            original_save({'initialized':True,'seen_ids':[]})
            with patch.object(bot,'save_state',side_effect=save):self.assertEqual(bot.run_once(),0)
            self.assertEqual(observed,[['DURABLE']])
            self.assertEqual(bot.run_once(),0)
            self.assertEqual(send.call_count,1)

    def test_compact_capacity_and_accessory_after_model(self):
        cfg={'model_ids':['13 pro max','13','12 pro'],'exclude_title_words':['etui','case']}
        for title,model in [('iPhone13ProMax256GB','13 pro max'),('iPhone13128GB','13')]:
            self.assertEqual(bot.detect_model(title),model)
            self.assertTrue(bot.is_flip_candidate(bot.Listing('x',title,''),cfg))
        for title in ['iPhone 13 etui czarne','iPhone 12 Pro etiu ze smyczą','iPhone 13 wyświetlacz LCD']:
            self.assertFalse(bot.is_flip_candidate(bot.Listing('x',title,''),cfg))
        for title in ['iPhone 13 z etui','iPhone 13 128GB + etui','iPhone 13 wymieniony ekran','iPhone 13 ekran pęknięty','iPhone 13 obudowa porysowana']:
            self.assertTrue(bot.is_flip_candidate(bot.Listing('x',title,''),cfg))

    def test_malformed_private_prices_do_not_block_alert_rendering(self):
        for table in ([],{'date':'test','rows':None},{'date':'test','rows':[{'model':'13'}]}):
            with self.subTest(table=table),patch.dict(os.environ,{'RESALE_PRICES_JSON':json.dumps(table)}),patch.object(bot.requests,'post') as post:
                bot.resale_table.cache_clear()
                bot.send_discord('https://example.com/webhook',bot.Listing('x','iPhone 13','https://www.olx.pl/',price='500 zł'),20)
                self.assertIn('Cennik niedostępny',post.call_args.kwargs['json']['embeds'][0]['description'])
        bot.resale_table.cache_clear()

    def test_compact_phone_title_preserves_exact_storage_valuation(self):
        table={'date':'test','rows':[{'model':'13','storage_gb':128,'sale_price':500,'suspect':False},{'model':'13','storage_gb':256,'sale_price':700,'suspect':False}]}
        with patch.object(bot,'resale_table',return_value=table):
            result=bot.resale_estimate(bot.Listing('x','iPhone13128GB','',price='200 zł'))
        self.assertIn('**500 zł**',result)
        self.assertIn('**300 zł**',result)
        self.assertNotIn('Nieznana pamięć',result)
