"""Read a public Vinted search and post new iPhone listings to Discord."""
import json
import os
from pathlib import Path
import re
import time
import unicodedata
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import unquote, urlencode, urlsplit
from urllib.request import Request, urlopen

import requests

from bot import Listing, detect_model, phone_model, resale_estimate

ORIGIN = "https://www.vinted.pl"
STATE = Path(".vinted-state.json")
ACCESSORY = re.compile(
    r"\b(?:etui\w*|eutui\w*|etiu\w*|etu[ij]?|(?:back|flip|phone|silicone|magsafe)?cases?|"
    r"bumper\w*|cover\w*|coques?|housses?|fundas?|husa|hull[ae]|hoesjes?|skal|protector\w*|"
    r"pokrow\w*|foli\w*|szkl\w*|obudow\w*|korpus\w*|ladowar\w*|kab(?:el|l\w*)|"
    r"przewod\w*|uchwyt\w*|adapter\w*|portfel\w*|smycz\w*|powerbank\w*|sluchawk\w*|"
    r"airpods|airtag|pop(?:socket|grip)\w*|stojak\w*|wyswietlacz\w*|ekran\w*|digitizer|"
    r"lcd|oled|akumulator\w*|czesci|plyt[ay] glown\w*|tasm[ay]|pudelk\w*|klapk\w*|dummy|"
    r"atrap\w*|samo szklo|nakladk\w*|pancerz\w*|futeraly?|screen protector)\b"
)
PART = re.compile(
    r"^(?:(?:now\w*|oryginaln\w*|uzywan\w*|zamiennik)\s+)*"
    r"(?:bateri\w*|aparat|kamera|modul|glosnik|szybk\w*)\b|"
    r"\b(?:bateri\w*|aparat|kamera|glosnik|szybk\w*)\s*(?:$|oryginaln\w*\b|zamiennik\b|now[ay]\b)"
)
BUNDLE = re.compile(
    r"(?:\s+(?:z|w zestawie z|plus|gratis)\s+|\s*\+\s*)"
    r"(?=(?:etui\w*|cases?|cover|coque|pokrow\w*|ladowar\w*|pudelk\w*)\b)"
)
ACCESSORY_ONLY = re.compile(r"\b(?:bez telefonu|bez iphona|telefonu brak|telefon nie jest|telefon nie wchodzi|tylko etui|samo etui|same etui|only case|case only|phone not included|bez smartfona)\b")
ACCESSORY_CATEGORY = re.compile(r"\b(?:akcesoria|accessories|cases|etui|pokrowce|czesci|spare parts|ochrona ekranu)\b")


def normalize_title(title):
    folded = unicodedata.normalize("NFD", title.lower().replace("ł", "l"))
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9%+]+", " ", folded).strip()


def is_accessory(title):
    title = normalize_title(title)
    subject = BUNDLE.split(title, maxsplit=1)[0]
    return bool(ACCESSORY_ONLY.search(title) or ACCESSORY.search(subject) or PART.search(subject))


def is_phone_title(title, url="", category=""):
    slug = LINK.fullmatch(urlsplit(url).path)
    slug_title = unquote(slug[2]) if slug and slug[2] else ""
    return bool(
        detect_model(title)
        and not is_accessory(title)
        and (not is_accessory(slug_title) or normalize_title(title.replace("+", " ")) == normalize_title(slug_title))
        and not ACCESSORY_CATEGORY.search(normalize_title(category))
    )


LINK = re.compile(r"/items/(\d+)(?:-([^/?#]+))?/?")
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


def save(seen, legacy_cutoff=None):
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"seen": seen[-8000:], "legacy_cutoff": legacy_cutoff}), encoding="utf-8")
    temporary.replace(STATE)


PRICE = re.compile(r"(?<![\d.,])(\d[\d \u00a0\u202f]*(?:[,.]\d{1,2})?)\s*zł", re.I)
META = re.compile(r", (?:Marka|Model|Stan|Rozmiar|Kolor|Kategoria): ")
CONDITION = re.compile(r", Stan: ([^,]+)")
CATEGORY = re.compile(r", Kategoria: ([^,]+)", re.I)
MODEL = re.compile(r", Model: ([^,]+)")


def item_details(details):
    title = META.split(details, maxsplit=1)[0]
    price = PRICE.search(details[len(title):])
    if not price:
        price = PRICE.search(details)
        if price:
            title = details[:price.start()].rstrip(", ")
    condition = CONDITION.search(details)
    model = MODEL.search(details)
    model_title = title
    if not detect_model(title) and model and detect_model(model[1]):
        model_title = f"{model[1]} {title}"
    raw_price = re.sub(r"\s", "", price[1]).replace(",", ".") if price else ""
    return title, model_title, (float(raw_price) if raw_price else None), (condition[1] if condition else "")


def alert_payload(item_id, details, url, settings):
    title, model_title, amount, condition = item_details(details)
    model = detect_model(model_title)
    category = CATEGORY.search(details)
    if not model or model not in settings["models"] or not is_phone_title(title, url, category[1] if category else ""):
        return None
    minimum, maximum = settings["min"], settings["max"]
    if amount is None and (minimum or maximum is not None):
        return None
    if amount is not None and (amount < minimum or (maximum is not None and amount > maximum)):
        return None
    price = f"{amount:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " zł" if amount is not None else "Nie podano"
    valuation = resale_estimate(Listing(item_id, model_title, url, price=price))
    lines = [f"📱 **Model:** {phone_model(model_title)}", f"🏷️ **Cena ogłoszenia:** **{price}**"]
    if condition:
        lines.append(f"📦 **Stan:** {condition[:100]}")
    for line in valuation.splitlines():
        if line.startswith("Twoja cena sprzedaży:"):
            lines.append("💰 **Cena z cennika:** " + line.split(": ", 1)[1])
        elif line.startswith("Zysk przed kosztami:"):
            lines.append("📈 **Zysk przed kosztami:** " + line.split(": ", 1)[1])
        elif not line.startswith("Cennik:"):
            lines.append(line)
    lines.append(f"⚡ **Bot wykrył:** <t:{int(time.time())}:t>")
    return {"username": "Łowca • Vinted",
            "avatar_url": "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f4f1.png",
            "embeds": [{"title": f"📱 {title}"[:250], "url": url,
            "description": "\n".join(lines), "color": 0x007782,
            "footer": {"text": "iPhone Sniper • Vinted • Wycena bez prowizji, napraw i wysyłki"}}],
            "allowed_mentions": {"parse": []}}


def settings_request(path, data=None):
    base = os.environ["SETTINGS_URL"].strip()
    location = urlsplit(base)
    if location.scheme != "https":
        raise ValueError("Nieprawidłowy adres panelu ustawień.")
    headers = {"Authorization": "Bearer " + os.environ["SETTINGS_KEY"].strip()}
    if data is not None:
        headers["Content-Type"] = "application/json"
    endpoint = base if path == "settings" else base.split("?", 1)[0].rsplit("/", 1)[0] + "/health"
    response = requests.request("GET" if data is None else "POST", endpoint,
                                params={"profile": "vinted"}, headers=headers, json=data, timeout=12)
    if not response.ok:
        raise RuntimeError(f"Panel Vinted /{path}: HTTP {response.status_code}.")
    return response.json()


CATALOG_PAGES = 3


def fetch_catalog(page_number):
    query = urlencode({"search_text": "iPhone", "order": "newest_first", "page": page_number})
    request = Request(ORIGIN + "/catalog?" + query, headers={
        "User-Agent": "iPhoneSniper/1.0 (public listing alerts)",
        "Accept": "text/html",
    })
    with urlopen(request, timeout=15) as response:
        page = response.read(12_000_000)
    catalog = Catalog()
    catalog.feed(page.decode("utf-8", errors="replace"))
    return catalog.cards


def scan(hook, settings, report):
    cards = {}
    report["searches_total"] = CATALOG_PAGES
    for number in range(1, CATALOG_PAGES + 1):
        try:
            batch = fetch_catalog(number)
        except HTTPError as error:
            report["errors"].append(f"Katalog Vinted, strona {number}: HTTP {error.code}.")
            if error.code in (403, 429):
                break
            continue
        except (OSError, TimeoutError) as error:
            report["errors"].append(f"Katalog Vinted, strona {number}: {type(error).__name__}.")
            continue
        if not batch:
            report["errors"].append(f"Katalog Vinted: brak rozpoznanych kart na stronie {number}.")
            break
        report["searches_ok"] += 1
        if batch.keys() <= cards.keys():
            break
        for item_id, card in batch.items():
            cards.setdefault(item_id, card)
    report["fetched"] = len(cards)
    if not cards:
        raise RuntimeError("Vinted nie zwrócił kart wyników. Sprawdź dostęp do katalogu.")
    if not STATE.exists():
        request = Request(hook, headers={"Accept": "application/json", "User-Agent": "DiscordBot (https://github.com/igorpud2011-pixel/iphone-sniper, 1.0)"})
        try:
            with urlopen(request, timeout=15) as response:
                if not json.load(response).get("channel_id"):
                    raise RuntimeError("Discord nie potwierdził kanału webhooka.")
        except HTTPError as error:
            raise SystemExit(f"Sprawdzenie webhooka Discord: HTTP {error.code}.") from None
        print("Discord potwierdził kanał webhooka.")
    if not STATE.exists():
        save(list(cards))
        print(f"Zapisano punkt startowy: {len(cards)} pozycji.")
        return
    previous = json.loads(STATE.read_text(encoding="utf-8"))
    if isinstance(previous, list):
        seen = previous
        # One migration pass records the expanded history without alerting old batches.
        legacy_cutoff = max(map(int, seen), default=0)
    else:
        seen = previous["seen"]
        legacy_cutoff = previous.get("legacy_cutoff")
    known = set(seen)
    if legacy_cutoff is not None:
        seen.extend(item_id for item_id in cards if item_id not in known and int(item_id) <= legacy_cutoff)
        known = set(seen)
        if not report["errors"]:
            legacy_cutoff = None
        save(seen, legacy_cutoff)
    sent = 0
    fresh = 0
    for item_id in sorted(cards, key=int):
        if item_id in known:
            continue
        fresh += 1
        url, details = cards[item_id]
        payload = alert_payload(item_id, details, url, settings)
        if payload:
            report["matched"] += 1
            request = Request(hook + "?wait=true", json.dumps(payload).encode(),
                              {"Content-Type": "application/json", "User-Agent": "DiscordBot (https://github.com/igorpud2011-pixel/iphone-sniper, 1.0)"}, method="POST")
            for attempt in range(2):
                try:
                    with urlopen(request, timeout=15) as response:
                        response.read()
                    break
                except HTTPError as error:
                    if error.code != 429 or attempt:
                        raise SystemExit(f"Wysyłka na Discord: HTTP {error.code}.") from None
                    try:
                        delay = float(error.headers.get("Retry-After", "2"))
                    except ValueError:
                        delay = 2
                    if not 0 <= delay <= 15:
                        raise SystemExit("Discord ograniczył wysyłkę. Kolejny skan ponowi próbę.") from None
                    time.sleep(delay + 0.5)
            sent += 1
            report["alerts"] += 1
            time.sleep(0.7)
        seen.append(item_id)
        save(seen, legacy_cutoff)
    print(f"Karty: {len(cards)}. Nowe pozycje: {fresh}. Wysłane alerty Vinted: {sent}.")


if __name__ == "__main__":
    hook = os.environ.get("DISCORD_VINTED_WEBHOOK_URL", "").strip()
    if not HOOK.fullmatch(hook):
        raise SystemExit("Ustaw sekret DISCORD_VINTED_WEBHOOK_URL z webhookiem kanału Vinted.")
    started = time.monotonic()
    report = dict(status="error", searches_total=1, searches_ok=0, fetched=0, matched=0, alerts=0, errors=[])
    try:
        settings = settings_request("settings")
        if settings["enabled"]:
            scan(hook, settings, report)
            report["status"] = "partial" if report["errors"] else "ok"
        else:
            report["status"] = "paused"
            print("Alerty Vinted wstrzymane w ustawieniach.")
    except (Exception, SystemExit) as error:
        message = str(error) if isinstance(error, (SystemExit, RuntimeError)) else type(error).__name__
        report["errors"].append(message)
        print(f"Skan Vinted nieudany: {message}")
        raise SystemExit(1) from None
    finally:
        report.update(finished_at=int(time.time()), duration_seconds=round(time.monotonic()-started, 2))
        try:
            settings_request("health", report)
        except Exception:
            print("Nie udało się przesłać statusu Vinted do panelu.")
