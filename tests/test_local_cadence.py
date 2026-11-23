import os
import unittest
from types import SimpleNamespace
from unittest.mock import call, patch
from urllib.parse import parse_qs, urlsplit

import bot
import run_profiles


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

    def test_local_checks_at_twenty_and_forty_seconds(self):
        with patch.object(run_profiles.time, "monotonic", side_effect=[100, 105, 122]), \
             patch.object(run_profiles.time, "sleep") as sleep, \
             patch.object(run_profiles.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
            result = run_profiles.run_local("bot.py", {"ALERT_PROFILE": "local"})
        self.assertEqual(result, 0)
        self.assertEqual(sleep.call_args_list, [call(15), call(18)])
        self.assertEqual(run.call_count, 3)
        self.assertEqual(run.call_args.kwargs["env"]["OLX_LOCAL_FAST_SCAN"], "1")

    def test_slow_or_failed_full_scan_does_not_add_extra_scan(self):
        for elapsed, code in ((42, 0), (3, 2)):
            with self.subTest(elapsed=elapsed, code=code), \
                 patch.object(run_profiles.time, "monotonic", side_effect=[100, 100 + elapsed, 100 + elapsed]), \
                 patch.object(run_profiles.time, "sleep") as sleep, \
                 patch.object(run_profiles.subprocess, "run", return_value=SimpleNamespace(returncode=code)) as run:
                self.assertEqual(run_profiles.run_local("bot.py", {}), code)
                run.assert_called_once()
                sleep.assert_not_called()


    def test_partial_quick_scan_leaves_recovery_to_the_full_scan(self):
        runs = [SimpleNamespace(returncode=0), SimpleNamespace(returncode=2)]
        with patch.object(run_profiles.time, "monotonic", side_effect=[100, 105]), \
             patch.object(run_profiles.time, "sleep"), \
             patch.object(run_profiles.subprocess, "run", side_effect=runs) as run:
            self.assertEqual(run_profiles.run_local("bot.py", {"ALERT_PROFILE": "local"}), 0)
            self.assertEqual(run.call_count, 2)
