import unittest
import bot

class CandidateTests(unittest.TestCase):
    def test_bundles_and_accessories(self):
        cfg = {"exclude_title_words": ["etui", "kabel", "kupię", "na części"]}
        for title in ["iPhone 13 z etui", "iPhone 12 + kabel", "iPhone13Pro 128GB", "iPhone-12 mini"]:
            self.assertTrue(bot.is_flip_candidate(bot.Listing("1", title, ""), cfg))
        for title in ["Etui do iPhone 13", "Sprzedam etui do iPhone 13", "Kabel do iPhone 12", "Kupię iPhone 13", "iPhone 13 na części"]:
            self.assertFalse(bot.is_flip_candidate(bot.Listing("1", title, ""), cfg))

    def test_parts_and_complete_damaged_phones(self):
        cfg = {"model_ids": ["13", "13 pro"], "include_damaged": True}
        for title in ("Płyta główna iPhone 13", "iPhone 13 płyta główna",
                      "iPhone 13 Pro 128GB — obudowa", "iPhone 13 części",
                      "iPhone 13 ekran OLED", "iPhone 13 oryginalna bateria"):
            self.assertFalse(bot.is_flip_candidate(bot.Listing("1", title, ""), cfg), title)
        for title in ("iPhone 13 128GB z etui", "iPhone 13 bateria 82%",
                      "iPhone 13 ekran pęknięty", "iPhone 13 uszkodzony na części"):
            self.assertTrue(bot.is_flip_candidate(bot.Listing("1", title, ""), cfg), title)
