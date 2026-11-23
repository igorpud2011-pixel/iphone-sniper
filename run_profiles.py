"""Run local and nationwide OLX monitors in separate processes and state files."""
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def national_env(original):
    env = dict(original)
    parts = urlsplit(env["SETTINGS_URL"])
    query = dict(parse_qsl(parts.query))
    query["profile"] = "polska"
    env["SETTINGS_URL"] = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
    env["ALERT_PROFILE"] = "polska"
    env["DISCORD_WEBHOOK_URL"] = urlunsplit((parts.scheme, parts.netloc, "/relay/polska", "", ""))
    for name in ("DISCORD_DEALS_WEBHOOK_URL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        env.pop(name, None)
    return env


def main():
    script = str(Path(__file__).with_name("bot.py"))
    local = {**os.environ, "ALERT_PROFILE": "local", "OLX_POLL_WINDOW": "1"}
    local.pop("OLX_LOCAL_FAST_SCAN", None)
    local.pop("OLX_NATIONAL_FAST_SCAN", None)
    profiles = [local]
    if local.get("SETTINGS_URL"):
        profiles.append(national_env(local))
        local["DAMAGED_ROUTED_NATIONALLY"] = "1"
    with ThreadPoolExecutor(max_workers=len(profiles)) as pool:
        runs = [pool.submit(subprocess.run, [sys.executable, "-u", script], env=env) for env in profiles]
        return max(future.result().returncode for future in runs)


if __name__ == "__main__":
    sys.exit(main())
