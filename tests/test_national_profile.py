import unittest,os
from unittest.mock import patch
from urllib.parse import urlsplit,parse_qs
import bot
from run_profiles import national_env
class NationalTests(unittest.TestCase):
 def test_country_searches_have_no_city_or_radius_and_keep_private(self):
  remote={'models':['13','14 pro'],'city':'Cała Polska','radius':0,'min':100,'max':900,'enabled':True,'nationwide':True}
  with patch.dict(os.environ,{'SETTINGS_URL':'https://example.com/settings?profile=polska','SETTINGS_KEY':'test'}),patch.object(bot.requests,'get') as get:
   get.return_value.json.return_value=remote;cfg=bot.load_config()
  self.assertIsNone(cfg['area_city'])
  for search in cfg['searches']:
   p=urlsplit(search['url']);q=parse_qs(p.query)
   self.assertNotIn('cala-polska',p.path);self.assertNotIn('search[dist]',q);self.assertEqual(q['search[private_business]'],['private'])
 def test_profile_env_does_not_send_to_local_destinations(self):
  result=national_env({'SETTINGS_URL':'https://example.com/settings','SETTINGS_KEY':'test','DISCORD_WEBHOOK_URL':'private','DISCORD_DEALS_WEBHOOK_URL':'deal','TELEGRAM_BOT_TOKEN':'telegram'})
  self.assertEqual(result['ALERT_PROFILE'],'polska');self.assertTrue(result['SETTINGS_URL'].endswith('profile=polska'));self.assertTrue(result['DISCORD_WEBHOOK_URL'].endswith('/relay/polska'));self.assertNotIn('TELEGRAM_BOT_TOKEN',result);self.assertNotIn('DISCORD_DEALS_WEBHOOK_URL',result)
