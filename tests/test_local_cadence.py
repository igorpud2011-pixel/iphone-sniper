import os
import tempfile
from pathlib import Path
import unittest
from threading import Event

import polling
from unittest.mock import call, patch
from urllib.parse import parse_qs, urlsplit

import bot


class LocalCadenceTest(unittest.TestCase):
    def test_fast_scan_uses_only_broad_local_feed(self):
        with patch.dict(os.environ, {"ALERT_PROFILE": "local", "OLX_LOCAL_FAST_SCAN": "1"}, clear=True):
            config = bot.load_config()

        self.assertEqual(len(config["searches"]), 1)
        search = config["searches"][0]
        url = urlsplit(search["url"])
        self.assertIn("/bielsko-biala/q-iphone/", url.path)
        query = parse_qs(url.query)
        self.assertEqual(query["search[dist]"], ["30"])
        self.assertEqual(query["search[private_business]"], ["private"])
        self.assertEqual(query["search[order]"], ["created_at:desc"])
        self.assertEqual(search["source"], "rss")

    def test_both_secondary_ticks_use_absolute_time(self):
        with patch.object(polling.time, "monotonic", side_effect=[105, 122]), patch.object(polling.time, "sleep") as sleep:
            self.assertEqual(list(polling.remaining_slots(100)), [20, 40])
        self.assertEqual(sleep.call_args_list, [call(15), call(18)])

    def test_overdue_ticks_do_not_start_a_burst(self):
        with patch.object(polling.time, "monotonic", side_effect=[126, 127]), patch.object(polling.time, "sleep") as sleep:
            self.assertEqual(list(polling.remaining_slots(100)), [40])
            sleep.assert_called_once_with(13)

    def test_broad_reads_continue_while_deep_source_is_busy(self):
        for profile in ("local", "polska"):
            with self.subTest(profile=profile):
                release_deep, head_read = Event(), Event()
                initial = {"url": "https://www.olx.pl/telefony/q-iphone/?q=1", "source": "rss"}
                slow = {"url": "https://www.olx.pl/telefony/q-iphone-13/", "source": "rss"}
                def fetch(search):
                    if search is slow:
                        if not release_deep.wait(3):
                            raise AssertionError("The full scan blocked the first-page reader")
                    return []
                def ticks(started):
                    if not head_read.wait(3):
                        raise AssertionError("No initial result")
                    yield 20
                    yield 40
                results = []
                with patch.dict(os.environ, {"ALERT_PROFILE": profile}), patch.object(bot, "remaining_slots", ticks):
                    for index, items, error, repeated in bot.source_reads([initial, slow], fetch, True):
                        self.assertIsNone(error)
                        results.append((index, repeated))
                        if index == 0:
                            head_read.set()
                        if results.count((0, True)) == 2:
                            release_deep.set()
                self.assertEqual(results.count((0, True)), 2)
                self.assertEqual(results[-1], (1, False))

    def test_head_not_requested_again_during_long_retry_after(self):
        from requests import HTTPError, Response
        response = Response()
        response.status_code = 429
        response.headers["Retry-After"] = "360"
        observed = Event()
        def ticks(started):
            observed.wait(2)
            yield 20
            yield 40
        with tempfile.TemporaryDirectory() as tmp, patch.object(bot, "STATE_PATH", Path(tmp) / "seen.json"), patch.object(bot, "remaining_slots", ticks):
            read = {"url": "https://www.olx.pl/telefony/q-iphone/?q=1", "source": "rss"}
            with patch.object(bot, "fetch_search", side_effect=HTTPError(response=response)) as fetch:
                for result in bot.source_reads([read], fetch, True):
                    self.assertIsInstance(result[2], HTTPError)
                    observed.set()
                for result in bot.source_reads([read], fetch, True):
                    self.assertIsInstance(result[2], RuntimeError)
                self.assertEqual(fetch.call_count, 1)
