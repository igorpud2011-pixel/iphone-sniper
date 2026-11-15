import unittest
import bot

class CandidateTests(unittest.TestCase):
    def test_bundles_and_accessories(self):
        cfg = {"exclude_title_words": ["etui", "kabel", "kupię", "na części"]}
        for title in ["iPhone 13 z etui", "iPhone 12 + kabel", "iPhone13Pro 128GB", "iPhone-12 mini"]:
            self.assertTrue(bot.is_flip_candidate(bot.Listing("1", title, ""), cfg))
        for title in ["Etui do iPhone 13", "Sprzedam etui do iPhone 13", "Kabel do iPhone 12", "Kupię iPhone 13", "iPhone 13 na części"]:
            self.assertFalse(bot.is_flip_candidate(bot.Listing("1", title, ""), cfg))
