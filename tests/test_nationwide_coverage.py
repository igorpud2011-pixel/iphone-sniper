import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import bot
import vinted_monitor as vinted


def cards(*ids):
    return {str(i): (f"https://www.vinted.pl/items/{i}-iphone-13", "iPhone 13, Stan: Dobry, 500 zł") for i in ids}


class NationwideCoverageTests(unittest.TestCase):
    def test_olx_always_fetches_second_broad_page_only_for_national_profile(self):
        settings = {"models": ["13"], "city": "Bielsko-Biała", "radius": 30, "min": 0, "enabled": True}
        with patch.dict(os.environ, {"SETTINGS_URL": "https://example.test/settings", "SETTINGS_KEY": "test"}, clear=True), patch.object(bot.requests, "get") as get:
            get.return_value.json.return_value = {**settings, "nationwide": False}
            local = bot.load_config()
            get.return_value.json.return_value = {**settings, "nationwide": True}
            national = bot.load_config()
        for config, count in ((local, 0), (national, 1)):
            urls = [urlsplit(s["url"]) for s in config["searches"]]
            self.assertEqual(sum(u.path.endswith("/q-iphone/") and parse_qs(u.query).get("page") == ["2"] for u in urls), count)

    def test_vinted_alerts_for_out_of_order_ids_on_later_pages_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(vinted, "STATE", Path(temp) / "state.json"), patch.object(vinted, "fetch_catalog") as fetch, patch.object(vinted, "urlopen") as post, patch.object(vinted.time, "sleep"):
            vinted.STATE.write_text(json.dumps(["100"]), encoding="utf-8")
            for pages, expected in (([cards(100, 110), cards(100, 90), cards(80)], 1),
                                    ([cards(120, 110), cards(110, 105), cards(90, 80)], 2)):
                fetch.side_effect = pages
                report = dict(fetched=0, matched=0, alerts=0, searches_ok=0, errors=[])
                vinted.scan("https://example.test/webhook", {"models": ["13"], "min": 0, "max": None}, report)
                self.assertEqual(report["alerts"], expected)
                self.assertEqual(report["searches_ok"], 3)
                self.assertEqual(report["errors"], [])
            sent = [json.loads(call.args[0].data)["embeds"][0]["url"] for call in post.call_args_list]
            self.assertEqual([urlsplit(url).path for url in sent], ["/items/110-iphone-13", "/items/120-iphone-13", "/items/105-iphone-13"])

    def test_vinted_respects_rate_limit_and_delivers_from_available_page(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(vinted, "STATE", Path(temp) / "state.json"), patch.object(vinted, "fetch_catalog") as fetch, patch.object(vinted, "urlopen") as post, patch.object(vinted.time, "sleep"):
            vinted.save(["100"])
            fetch.side_effect = [cards(101), HTTPError("https://www.vinted.pl/catalog", 429, "", {}, None)]
            report = dict(fetched=0, matched=0, alerts=0, searches_ok=0, errors=[])
            vinted.scan("https://example.test/webhook", {"models": ["13"], "min": 0, "max": None}, report)
            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(report["alerts"], 1)
            self.assertIn("429", report["errors"][0])
            post.assert_called_once()


    def test_vinted_sends_first_page_before_reading_second(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(vinted, "STATE", Path(temp) / "state.json"), patch.object(vinted, "send_listing") as send, patch.object(vinted.time, "sleep"):
            vinted.save(["100"])
            def fetch(page):
                if page == 1:
                    return cards(101)
                send.assert_called_once()
                return cards(101)
            report = dict(fetched=0, matched=0, alerts=0, searches_ok=0, errors=[])
            with patch.object(vinted, "fetch_catalog", side_effect=fetch):
                vinted.scan("https://example.test/webhook", {"models": ["13"], "min": 0, "max": None}, report)
            self.assertEqual(report["alerts"], 1)
