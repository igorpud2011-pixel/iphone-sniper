import unittest,os
from unittest.mock import patch
from urllib.parse import urlsplit,parse_qs
import bot
class PrivateTests(unittest.TestCase):
 def test_all_sources_keep_private_filter(self):
  with patch.dict(os.environ,{'SETTINGS_URL':''}):
   config=bot.load_config()
  self.assertTrue(config['private_only'])
  self.assertTrue(any(s.get('source')=='rss_bridge' for s in config['searches']))
  for search in config['searches']:self.assertEqual(parse_qs(urlsplit(search['url']).query)['search[private_business]'],['private'])
 def test_business_and_buying_ads_rejected_but_private_invoice_allowed(self):
  cfg={'model_ids':['13']}
  ad=bot.Listing('test','iPhone 13 128GB faktura zakupu','https://www.olx.pl/d/oferta/test-IDT.html',seller_type='private')
  self.assertTrue(bot.is_flip_candidate(ad,cfg))
  ad.seller_type='business';self.assertFalse(bot.is_flip_candidate(ad,cfg))
  ad.seller_type='unknown';ad.title='iPhone 13 skup telefonów gotówka';self.assertFalse(bot.is_flip_candidate(ad,cfg))
 def test_rss_explicit_business_label(self):
  feed='<rss><channel><item><title>iPhone 13 128GB</title><link>https://www.olx.pl/d/oferta/test-IDT.html</link><description>&lt;p&gt;Firmowe&lt;/p&gt;</description></item></channel></rss>'
  ad=bot.parse_rss(feed)[0];self.assertEqual(ad.seller_type,'business')
