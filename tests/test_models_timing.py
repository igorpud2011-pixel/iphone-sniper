import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
import bot

class ModelTimingTests(unittest.TestCase):
    def test_exact_variants(self):
        for title,model in [('iPhone13ProMax 256GB','13 pro max'),('iPhone XS Max','xs max'),('iPhone 16e','16e'),('iPhone SE 2020','se 2020'),('iPhone 6s Plus','6s plus')]:
            self.assertEqual(bot.detect_model(title),model)
        cfg={'model_ids':['13'],'exclude_title_words':[]}
        self.assertFalse(bot.is_flip_candidate(bot.Listing('a','iPhone 13 Pro',''),cfg))
        self.assertTrue(bot.is_flip_candidate(bot.Listing('b','iPhone 13 128GB',''),cfg))
    def test_timing_does_not_invent_unknown_publication(self):
        now=datetime(2026,11,15,14,0,tzinfo=ZoneInfo('Europe/Warsaw'))
        ad=bot.Listing('a','iPhone 13','',location_date='Miejscowość: Bielsko-Biała, Wystawiono: Dzisiaj o 13:57')
        self.assertIn('3 min',bot.capture_timing(ad,now))
        ad.location_date='Wystawiono: Dzisiaj'
        self.assertIn('nie podaje',bot.capture_timing(ad,now))
    def test_no_tracking_loss_on_empty_rss(self):
        self.assertEqual(bot.parse_rss('<rss><channel/></rss>'),[])

    def test_remote_exact_models_build_family_searches(self):
        remote={'models':['13 pro','13 pro max','16e','xs max'],'city':'Bielsko-Biała','radius':30,'min':0,'max':None,'enabled':True}
        with patch.dict('os.environ',{'SETTINGS_URL':'https://example.com/settings','SETTINGS_KEY':'test'}), patch.object(bot.requests,'get') as get:
            get.return_value.json.return_value=remote
            cfg=bot.load_config()
        self.assertEqual(len(cfg['searches']),4)
        self.assertEqual(cfg['model_ids'],remote['models'])
        self.assertFalse(bot.is_flip_candidate(bot.Listing('id','iPhone 13 128 GB',''),cfg))
        self.assertTrue(bot.is_flip_candidate(bot.Listing('id','iPhone13Pro 128GB',''),cfg))

    def test_se_short_names_and_local_price(self):
        self.assertEqual(bot.detect_model('iPhone SE2 64 GB'), 'se 2020')
        self.assertEqual(bot.detect_model('iPhone SE3 128 GB'), 'se 2022')
        cfg={'model_ids':['13'],'price_min':100,'price_max':900}
        for price, expected in [('1 200 zł',False),('899,99 zł do negocjacji',True),('50 zł',False),('Cena niepodana',False)]:
            self.assertEqual(bot.is_flip_candidate(bot.Listing('id','iPhone 13','',price=price),cfg),expected)

    def test_promoted_outside_radius_is_rejected(self):
        cfg={'model_ids':['13'],'area_city':'Bielsko-Biała','area_radius':30}
        self.assertFalse(bot.is_flip_candidate(bot.Listing('1','iPhone 13','',location_name='Żory'),cfg))
        self.assertTrue(bot.is_flip_candidate(bot.Listing('2','iPhone 13','',location_name='Bielsko-Biała'),cfg))
