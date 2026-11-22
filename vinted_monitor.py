"""Read a public Vinted search and post new iPhone listings to Discord."""
import json
import os
from pathlib import Path
import re
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

ORIGIN = "https://www.vinted.pl"
STATE = Path(".vinted-state.json")
PHONE = re.compile(r"\biphone[ -]*(?:\d{1,2}|se|xs?|xr|air)\b", re.I)
ACCESSORY = re.compile(r"\b(?:etui|case|cover|husa|husă|hülle|protector|pokrowiec|folia|"
                       r"koque|coque|obudowa|ładowarka|kabel|szkło|wyświetlacz|dummy)\b", re.I)
LINK = re.compile(r"/items/(\d+)(?:-[^/?#]+)?/?")
HOOK = re.compile(r"https://discord\.com/api/webhooks/\d{15,22}/[A-Za-z0-9_-]+")


class Catalog(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cards = {}

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        attrs = dict(attrs)
        if not attrs.get("data-testid", "").endswith("--overlay-link"):
            return
        path = urlsplit(attrs.get("href", "")).path
        match = LINK.fullmatch(path)
        title = attrs.get("title", "")
        if match and title:
            self.cards[match[1]] = (ORIGIN + path, title)


def save(seen):
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(seen[-2500:]), encoding="utf-8")
    temporary.replace(STATE)


def scan(hook):
    query = urlencode({"search_text": "iPhone", "order": "newest_first"})
    request = Request(ORIGIN + "/catalog?" + query, headers={
        "User-Agent": "iPhoneSniper/1.0 (public listing alerts)",
        "Accept": "text/html",
    })
    try:
        with urlopen(request, timeout=25) as response:
            page = response.read(12_000_000)
    except HTTPError as error:
        raise SystemExit(f"Katalog Vinted: HTTP {error.code}.") from None
    catalog = Catalog()
    catalog.feed(page.decode("utf-8", errors="replace"))
    if not catalog.cards:
        raise RuntimeError("Vinted nie zwrócił kart wyników. Sprawdź dostęp do katalogu.")
    if not STATE.exists() or os.environ.get("GITHUB_EVENT_NAME") in {"push", "workflow_dispatch"}:
        request = Request(hook, headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=15) as response:
                if not json.load(response).get("channel_id"):
                    raise RuntimeError("Discord nie potwierdził kanału webhooka.")
        except HTTPError as error:
            raise SystemExit(f"Sprawdzenie webhooka Discord: HTTP {error.code}.") from None
        print("Discord potwierdził kanał webhooka.")
    if not STATE.exists():
        save(list(catalog.cards))
        print(f"Zapisano punkt startowy: {len(catalog.cards)} pozycji.")
        return
    seen = json.loads(STATE.read_text(encoding="utf-8"))
    known = set(seen)
    cutoff = max(map(int, seen), default=0)
    sent = 0
    fresh = 0
    for item_id in sorted(catalog.cards, key=int):
        if item_id in known or int(item_id) <= cutoff:
            continue
        fresh += 1
        url, details = catalog.cards[item_id]
        title = details.split(", Marka:", 1)[0].split(", Stan:", 1)[0]
        if PHONE.search(title) and not ACCESSORY.search(title):
            payload = {"embeds": [{"title": title[:250], "url": url,
                        "description": details[:500], "color": 0x007782}],
                       "allowed_mentions": {"parse": []}}
            request = Request(hook + "?wait=true", json.dumps(payload).encode(),
                              {"Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=15) as response:
                response.read()
            sent += 1
        seen.append(item_id)
        save(seen)
    print(f"Karty: {len(catalog.cards)}. Nowe pozycje: {fresh}. Wysłane alerty Vinted: {sent}.")


if __name__ == "__main__":
    hook = os.environ.get("DISCORD_VINTED_WEBHOOK_URL", "").strip()
    if not HOOK.fullmatch(hook):
        raise SystemExit("Ustaw sekret DISCORD_VINTED_WEBHOOK_URL z webhookiem kanału Vinted.")
    try:
        scan(hook)
    except Exception as error:
        print(f"Skan Vinted nieudany: {type(error).__name__} {getattr(error, 'code', '')}")
        raise SystemExit(1) from None
