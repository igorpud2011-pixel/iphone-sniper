import unittest
from unittest.mock import patch
import bot

class RoutingTests(unittest.TestCase):
    table={'date':'test','rows':[{'model':'13','storage_gb':128,'sale_price':700,'suspect':False}]}
    def test_threshold_and_unknown_storage(self):
        with patch.object(bot,'resale_table',return_value=self.table):
            for price,expected in [('600 zł',100),('601 zł',99),('500 zł',200)]:
                self.assertEqual(bot.deal_discount(bot.Listing('x','iPhone 13 128GB','',price=price)),expected)
            self.assertIsNone(bot.deal_discount(bot.Listing('x','iPhone 13','',price='200 zł')))
            self.assertIsNone(bot.deal_discount(bot.Listing('x','iPhone 13 128GB uszkodzony','',price='200 zł')))
    def test_damaged_signals_and_negation(self):
        for title in ['iPhone 13 uszkodzony','iPhone 13 nie działa','iPhone 13 brak Face ID']:
            self.assertTrue(bot.is_damaged(bot.Listing('x',title,'')))
        self.assertFalse(bot.is_damaged(bot.Listing('x','iPhone 13 nieuszkodzony','')))
    def test_partial_failure_retries_only_additional_channel(self):
        ad=bot.Listing('x','iPhone 13 128GB','',price='500 zł');state={}
        env={'DISCORD_WEBHOOK_URL':'https://example.com/main','DISCORD_DEALS_WEBHOOK_URL':'https://example.com/deals','DISCORD_DAMAGED_WEBHOOK_URL':'https://example.com/damaged'}
        with patch.dict('os.environ',env),patch.object(bot,'resale_table',return_value=self.table),patch.object(bot,'send_alert',return_value=True) as base,patch.object(bot,'send_discord',side_effect=[RuntimeError('offline'),None]) as extra:
            self.assertFalse(bot.send_routed_alert(ad,20,state))
            self.assertTrue(bot.send_routed_alert(ad,20,state))
            self.assertEqual(base.call_count,1)
            self.assertEqual(extra.call_count,2)
            self.assertEqual(extra.call_args.args[0],env['DISCORD_DEALS_WEBHOOK_URL'])
            self.assertEqual(state['route_receipts'],{})
    def test_damaged_never_goes_to_deals(self):
        ad=bot.Listing('x','iPhone 13 128GB uszkodzony','',price='100 zł')
        with patch.dict('os.environ',{'DISCORD_DAMAGED_WEBHOOK_URL':'https://example.com/damaged','DISCORD_DEALS_WEBHOOK_URL':'https://example.com/deals'}),patch.object(bot,'send_alert',return_value=True),patch.object(bot,'send_discord') as send:
            self.assertTrue(bot.send_routed_alert(ad,20,{}))
            self.assertEqual(send.call_args.args[0],'https://example.com/damaged')
