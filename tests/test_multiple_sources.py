import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import bot

FEED = '''<rss xmlns:media="http://search.yahoo.com/mrss/"><channel><item>
<title>iPhone 13 128 GB</title><link>https://www.olx.pl/d/oferta/iphone-13-IDabc123.html?tracking=x</link>
<description>&lt;table&gt;&lt;tr&gt;&lt;td&gt;&lt;p&gt;Bielsko-Biała&lt;/p&gt;&lt;p&gt;&lt;span&gt;700 zł&lt;/span&gt;&lt;/p&gt;&lt;/td&gt;&lt;/tr&gt;&lt;/table&gt;</description>
<media:content url="https://images.example/phone.jpg#.image"/></item></channel></rss>'''

class MultipleSourcesTests(unittest.TestCase):
    def test_bridge_price_location_image_and_shared_id(self):
        ad=bot.parse_rss(FEED)[0]
        self.assertEqual(ad.price,'700 zł')
        self.assertEqual(ad.location_name,'Bielsko-Biała')
        self.assertEqual(ad.image_url,'https://images.example/phone.jpg')
        self.assertEqual(ad.listing_id,'IDABC123')
        self.assertNotIn('tracking',ad.url)

    def test_duplicate_then_independent_failure(self):
        url='https://www.olx.pl/elektronika/telefony/bielsko-biala/q-iphone/'
        cfg={'searches':[{'url':url,'source':'rss'},{'url':url,'source':'rss_bridge'}],'model_ids':['13']}
        ad=bot.parse_rss(FEED)[0]
        def fetch(session,search,timeout):
            if search['source']=='rss': raise TimeoutError('primary offline')
            return [ad]
        with tempfile.TemporaryDirectory() as tmp, patch.object(bot,'STATE_PATH',Path(tmp)/'seen.json'),patch.object(bot,'load_config',return_value=cfg),patch.object(bot,'publish_status'),patch.object(bot,'send_alert',return_value=True) as send:
            bot.save_state({'initialized':True,'seen_ids':[]})
            with patch.object(bot,'fetch_search',return_value=[ad]):
                self.assertEqual(bot.run_once(),0)
            self.assertEqual(send.call_count,1)
            with patch.object(bot,'fetch_search',side_effect=fetch):
                self.assertEqual(bot.run_once(),1)
            self.assertEqual(send.call_count,1)
            self.assertIn(ad.listing_id,bot.load_state()['notified_ids'])
            # A new matching offer still gets delivered when the primary is down.
            ad.listing_id='SECOND'
            with patch.object(bot,'fetch_search',side_effect=fetch):
                self.assertEqual(bot.run_once(),1)
            self.assertEqual(send.call_count,2)

    def test_first_install_both_sources_share_silent_baseline(self):
        url='https://www.olx.pl/search'
        cfg={'searches':[{'url':url},{'url':url}]}
        ads=[[bot.Listing('A','iPhone 13',url)],[bot.Listing('B','iPhone 13',url)]]
        with tempfile.TemporaryDirectory() as tmp,patch.object(bot,'STATE_PATH',Path(tmp)/'seen.json'),patch.object(bot,'load_config',return_value=cfg),patch.object(bot,'fetch_search',side_effect=ads),patch.object(bot,'send_alert') as send,patch.object(bot,'publish_status'):
            self.assertEqual(bot.run_once(),0)
            send.assert_not_called()
            self.assertEqual(set(bot.load_state()['seen_ids']),{'A','B'})

    def test_alert_is_sent_before_slow_source_finishes(self):
        from threading import Event
        delivered=Event()
        slow_observed=[]
        ad=bot.parse_rss(FEED)[0]
        cfg={'searches':[{'url':'https://www.olx.pl/fast'},{'url':'https://www.olx.pl/slow'}],'model_ids':['13']}
        def fetch(session,search,timeout):
            if search['url'].endswith('/slow'):
                slow_observed.append(delivered.wait(2))
                return []
            return [ad]
        def send(*args):
            delivered.set()
            return True
        with tempfile.TemporaryDirectory() as tmp,patch.object(bot,'STATE_PATH',Path(tmp)/'seen.json'),patch.object(bot,'load_config',return_value=cfg),patch.object(bot,'fetch_search',side_effect=fetch),patch.object(bot,'send_alert',side_effect=send),patch.object(bot,'publish_status'):
            bot.save_state({'initialized':True,'seen_ids':[]})
            self.assertEqual(bot.run_once(),0)
            self.assertEqual(slow_observed,[True])

    def test_incomplete_rejected_copy_does_not_hide_valid_copy(self):
        from threading import Event
        first=Event()
        invalid=bot.parse_rss(FEED)[0]
        invalid.price='Cena niepodana'
        valid=bot.parse_rss(FEED)[0]
        cfg={'searches':[{'url':'https://www.olx.pl/incomplete'},{'url':'https://www.olx.pl/complete'}],'model_ids':['13'],'price_min':100}
        def fetch(session,search,timeout):
            if search['url'].endswith('/incomplete'):
                return [invalid]
            first.wait(2)
            return [valid]
        original_filter=bot.is_flip_candidate
        def check(ad,cfg):
            result=original_filter(ad,cfg)
            if ad is invalid:first.set()
            return result
        with tempfile.TemporaryDirectory() as tmp,patch.object(bot,'STATE_PATH',Path(tmp)/'seen.json'),patch.object(bot,'load_config',return_value=cfg),patch.object(bot,'fetch_search',side_effect=fetch),patch.object(bot,'send_alert',return_value=True) as send,patch.object(bot,'publish_status'),patch.object(bot,'is_flip_candidate',side_effect=check):
            bot.save_state({'initialized':True,'seen_ids':[]})
            self.assertEqual(bot.run_once(),0)
            send.assert_called_once_with(valid,20)
            self.assertNotIn(valid.listing_id,bot.load_state()['rejected_ids'])
