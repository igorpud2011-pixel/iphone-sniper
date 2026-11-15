import json,os,unittest
from unittest.mock import patch
import bot

class ResaleTests(unittest.TestCase):
    def tearDown(self):
        bot.resale_table.cache_clear()
    def test_secret_loading_and_profit(self):
        table={"date":"test", "rows":[{"model":"11","storage_gb":64,"sale_price":500,"suspect":False}]}
        with patch.dict(os.environ,{"RESALE_PRICES_JSON":json.dumps(table)}):
            bot.resale_table.cache_clear()
            result=bot.resale_estimate(bot.Listing('id','iPhone 11 64GB','',price='200 zł'))
        self.assertIn('500 zł',result)
        self.assertIn('300 zł',result)
    def test_unknown_memory_and_suspect_price(self):
        table={"date":"test","rows":[{"model":"11","storage_gb":64,"sale_price":500,"suspect":False},{"model":"11","storage_gb":128,"sale_price":700,"suspect":False}]}
        with patch.object(bot,'resale_table',return_value=table):
            text=bot.resale_estimate(bot.Listing('id','iPhone 11','',price='200 zł'))
            self.assertIn('500–700 zł',text)
            self.assertIn('Nieznana pamięć',text)
            table['rows'][0]['suspect']=True
            self.assertIn('Podejrzana',bot.resale_estimate(bot.Listing('id','iPhone 11 64GB','',price='200 zł')))

    def test_discord_is_one_compact_card(self):
        ad=bot.Listing('pricing-test','iPhone 11 64GB','https://www.olx.pl/',price='200 zł (przykład)')
        with patch.object(bot,'resale_estimate',return_value='Twoja cena sprzedaży: **500 zł**\nZysk przed kosztami: **300 zł**'), patch.object(bot.requests,'post') as post:
            bot.send_discord('https://example.com',ad,20)
        payload=post.call_args.kwargs['json']
        self.assertEqual(payload['content'],'')
        self.assertEqual(len(payload['embeds']),1)
        card=payload['embeds'][0]
        self.assertIn('**Zakup:** **200 zł**',card['description'])
        self.assertIn('**Sprzedaż:** **500 zł**',card['description'])
        self.assertFalse(card.get('fields'))
