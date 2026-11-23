import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs
import bot

class OfferButtonTests(unittest.TestCase):
    def table(self, price=500, suspect=False):
        return {'date':'test','rows':[{'model':'11','storage_gb':64,'sale_price':price,'suspect':suspect}]}
    def test_price_uses_resale_minus_200_not_asking(self):
        with patch.object(bot,'resale_table',return_value=self.table()):
            ad=bot.Listing('id','iPhone 11 64GB','https://www.olx.pl/d/oferta/test-ID123.html',price='100 zł')
            self.assertEqual(bot.suggested_offer(ad),'300')
            link=bot.offer_components(ad)[0]['components'][0]['url']
            self.assertEqual(urlsplit(link).query,'')
            self.assertEqual(parse_qs(urlsplit(link).fragment)['price'],['300'])
    def test_unknown_suspect_and_negative_are_manual(self):
        for price,suspect,title in [(500,False,'iPhone 11'),(500,True,'iPhone 11 64GB'),(100,False,'iPhone 11 64GB')]:
            with self.subTest(title=title,price=price,suspect=suspect),patch.object(bot,'resale_table',return_value=self.table(price,suspect)):
                self.assertEqual(bot.suggested_offer(bot.Listing('id',title,'')),'')
    def test_lowest_duplicate_and_compact_tb(self):
        table={'rows':[{'model':'15 pro','storage_gb':1024,'sale_price':p,'suspect':False} for p in (1500,1700)]}
        with patch.object(bot,'resale_table',return_value=table):
            self.assertEqual(bot.suggested_offer(bot.Listing('id','iPhone15Pro1TB','')),'1300')
    def test_only_olx_listing_links_and_discord_components_enabled(self):
        for url in ['https://evil.test/d/oferta/x','javascript:alert(1)','https://www.olx.pl/']:
            self.assertEqual(bot.offer_components(bot.Listing('id','iPhone 11',url)),[])
        ad=bot.Listing('id','iPhone 11 64GB','https://www.olx.pl/d/oferta/test-ID123.html?tracking=1')
        with patch.object(bot,'resale_table',return_value=self.table()),patch.object(bot.requests,'post') as post:
            bot.send_discord('https://example.com',ad,20)
        self.assertEqual(post.call_args.kwargs['params'],{'with_components':'true','wait':'true'})
        payload=post.call_args.kwargs['json']
        self.assertEqual(len(payload['embeds']),1)
        self.assertTrue(all(c['style']==5 for c in payload['components'][0]['components']))


        purchase = payload['components'][0]['components'][1]
        self.assertEqual(purchase['label'], 'Otwórz zakup na OLX')
        self.assertEqual(purchase['url'], 'https://www.olx.pl/d/oferta/test-ID123.html')
