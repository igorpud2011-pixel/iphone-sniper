import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import bot

class RoutingAuditTests(unittest.TestCase):
    def test_negations_and_separate_actual_fault(self):
        for title in ['iPhone 13 nie uszkodzony','iPhone 13 nie jest zalany','iPhone 13 bez uszkodzeń']:
            self.assertFalse(bot.is_damaged(bot.Listing('x',title,'')))
        ad=bot.Listing('x','iPhone 13 nie zalany','',description='Nie działa Face ID.')
        self.assertTrue(bot.is_damaged(ad))
    def test_description_fault_excludes_deals(self):
        table={'date':'test','rows':[{'model':'13','storage_gb':128,'sale_price':700,'suspect':False}]}
        ad=bot.Listing('x','iPhone 13 128GB','',price='200 zł',description='Telefon nie ładuje się, do naprawy.')
        with patch.object(bot,'resale_table',return_value=table):self.assertIsNone(bot.deal_discount(ad))
    def test_description_is_read_from_existing_feed(self):
        feed='''<rss><channel><item><title>iPhone 13 128GB</title><link>https://www.olx.pl/d/oferta/iphone-IDabc.html</link><description>&lt;table&gt;&lt;tr&gt;&lt;td&gt;&lt;p&gt;Bielsko-Biała&lt;/p&gt;&lt;p&gt;&lt;span&gt;500 zł&lt;/span&gt;&lt;/p&gt;&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Opis Telefon nie działa&lt;/td&gt;&lt;/tr&gt;&lt;/table&gt;</description></item></channel></rss>'''
        ad=bot.parse_rss(feed)[0]
        self.assertEqual(ad.description,'Telefon nie działa')
        self.assertTrue(bot.is_damaged(ad))
    def test_exact_money_boundary(self):
        table={'date':'test','rows':[{'model':'13','storage_gb':128,'sale_price':300.15,'suspect':False}]}
        with patch.object(bot,'resale_table',return_value=table):
            self.assertEqual(bot.deal_discount(bot.Listing('x','iPhone 13 128GB','',price='200,15 zł')),100)
            self.assertEqual(bot.deal_discount(bot.Listing('x','iPhone 13 128GB','',price='200,16 zł')),99.99)
    def test_corrupt_receipt_history_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(bot,'STATE_PATH',Path(tmp)/'seen.json'):
            bot.STATE_PATH.write_text('{"seen_ids":[],"route_receipts":{"x":null}}')
            with self.assertRaises(RuntimeError):bot.load_state()
            self.assertIn('null',bot.STATE_PATH.read_text())
