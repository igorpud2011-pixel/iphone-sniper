import json
import os
import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch
from urllib.error import HTTPError

import vinted_monitor as monitor


def cards(*ids):
    return {str(n): (f"https://www.vinted.pl/items/{n}-iphone-13", "iPhone 13, marka: Apple, model: iPhone 13, stan: Dobry, 550 zł") for n in ids}


def report():
    return dict(searches_ok=0, fetched=0, matched=0, alerts=0, errors=[])


class VintedMinuteTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(monitor, "STATE", Path(folder) / "seen.json"))
        self.settings = {"models": ["13"], "min": 0, "max": None}
        self.hook = "https://example.test/discord"
        monitor.save(["100"])

    def test_two_feeds_share_receipts_without_swallowing_first_public_offer(self):
        def first(page, phones=False):
            return cards(101, 90) if phones else cards(101, 100)
        with patch.object(monitor, "fetch_catalog", side_effect=first), patch.object(monitor, "send_listing") as send:
            monitor.scan(self.hook, self.settings, report(), front_only=True, phones=True)
            self.assertEqual(send.call_count, 1)
        def second(page, phones=False):
            return cards(104, 101, 90) if phones else cards(104, 101, 100)
        with patch.object(monitor, "fetch_catalog", side_effect=second), patch.object(monitor, "send_listing") as send:
            monitor.scan(self.hook, self.settings, report(), front_only=True, phones=True)
            monitor.scan(self.hook, self.settings, report(), front_only=True, phones=True)
            self.assertEqual(send.call_count, 1)
            self.assertIn("/104-", send.call_args.args[1]["embeds"][0]["url"])

    def test_saved_pending_offer_survives_disappearing_and_discord_limits(self):
        with patch.object(monitor, "fetch_catalog", return_value=cards(101, 102)), patch.object(monitor, "send_listing", side_effect=monitor.DiscordLimited(90)) as send:
            monitor.scan(self.hook, self.settings, report(), front_only=True)
            monitor.scan(self.hook, self.settings, report(), front_only=True)
            self.assertEqual(send.call_count, 1)
        backup = json.loads(monitor.STATE.read_text())
        self.assertEqual(set(backup["pending"]), {"101", "102"})
        self.assertEqual(backup["seen"], ["100"])
        with patch.object(monitor.time, "time", return_value=backup["discord_until"] + 1), patch.object(monitor, "fetch_catalog", return_value=cards(100)), patch.object(monitor, "send_listing") as send:
            monitor.scan(self.hook, self.settings, report(), front_only=True)
            self.assertEqual(send.call_count, 2)
        self.assertFalse(json.loads(monitor.STATE.read_text())["pending"])

    def test_catalogue_cooldown_survives_process_restarts(self):
        with patch.object(monitor, "fetch_catalog", side_effect=HTTPError("https://www.vinted.pl", 429, "", {"Retry-After": "300"}, None)) as read:
            with self.assertRaises(RuntimeError):
                monitor.scan(self.hook, self.settings, report(), front_only=True)
            monitor.scan(self.hook, self.settings, report(), front_only=True)
            self.assertEqual(read.call_count, 1)

    def test_apple_model_metadata_finds_generic_phone_titles_but_not_cases(self):
        for title, valid in (("Telefon 128 GB", True), ("Etui przezroczyste", False)):
            with self.subTest(title=title):
                data = f"{title}, marka: Apple, model: iPhone 13, stan: Dobry, 550 zł"
                payload = monitor.alert_payload("123", data, "https://www.vinted.pl/items/123-telefon", self.settings)
                self.assertEqual(bool(payload), valid)
                if payload:
                    self.assertIn("550 zł", payload["embeds"][0]["description"])
                    self.assertIn("Dobry", payload["embeds"][0]["description"])

    def test_no_catchup_burst_and_discord_ack_required(self):
        with patch.dict(os.environ, {"DISCORD_VINTED_WEBHOOK_URL": "https://discord.com/api/webhooks/123456789012345/test"}), patch("sys.argv", ["vinted_monitor.py", "--window"]), patch.object(monitor, "run_scan", return_value=0) as scan:
            self.assertEqual(monitor.main(), 0)
            scan.assert_called_once_with(os.environ["DISCORD_VINTED_WEBHOOK_URL"], True)
        with patch.object(monitor, "urlopen") as send:
            send.return_value.__enter__.return_value.read.return_value = b'{}'
            with self.assertRaisesRegex(RuntimeError, "potwierdzenia"):
                monitor.send_listing(self.hook, {})

    def test_both_front_pages_are_read_while_recovery_is_blocked(self):
        deep_started, release = Event(), Event()
        def read(page, focused):
            if page == 2:
                deep_started.set()
                if not release.wait(3):
                    raise AssertionError("Recovery held up the front pages")
            return cards(page), None, 1
        def ticks(started):
            self.assertTrue(deep_started.wait(2))
            yield 20
            yield 40
        with patch.object(monitor, "remaining_slots", ticks):
            heads = []
            for page, focused, result in monitor.catalogue_window(read, 3, True):
                if page == 1:
                    heads.append(focused)
                    if len(heads) == 6:
                        release.set()
        self.assertEqual(heads.count(True), 3)
        self.assertEqual(heads.count(False), 3)
