"""Read a public Vinted search and post new iPhone listings to Discord."""
import argparse
import json
import os
from pathlib import Path
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from html.parser import HTMLParser
from threading import Event
from urllib.error import HTTPError
from urllib.parse import unquote, urlencode, urlsplit
from urllib.request import Request, urlopen

import requests

from bot import Listing, detect_model, phone_model, resale_estimate
from polling import remaining_slots, retry_delay, stream_workers, trace

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


def is_phone_title(title, url="", category="", model_title=None):
    slug = LINK.fullmatch(urlsplit(url).path)
    slug_title = unquote(slug[2]) if slug and slug[2] else ""
    return bool(
        detect_model(model_title or title)
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


def save(seen, legacy_cutoff=None, **metadata):
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"seen": seen[-8000:], "legacy_cutoff": legacy_cutoff, **metadata}), encoding="utf-8")
    temporary.replace(STATE)


PRICE = re.compile(r"(?<![\d.,])(\d[\d \u00a0\u202f]*(?:[,.]\d{1,2})?)\s*zł", re.I)
META = re.compile(r",\s*(?:Marka|Model|Stan|Rozmiar|Kolor|Kategoria):\s*", re.I)
CONDITION = re.compile(r",\s*Stan:\s*([^,]+)", re.I)
CATEGORY = re.compile(r", Kategoria: ([^,]+)", re.I)
MODEL = re.compile(r",\s*Model:\s*([^,]+)", re.I)


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
    if not model or model not in settings["models"] or not is_phone_title(title, url, category[1] if category else "", model_title):
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


def fetch_catalog(page_number, phones=False):
    if phones:
        path = "/catalog/3661-mobile-phones/brand/54661-apple"
        query = {"order": "newest_first", "page": page_number}
    else:
        path = "/catalog"
        query = {"search_text": "iPhone", "order": "newest_first", "page": page_number}
    request = Request(ORIGIN + path + "?" + urlencode(query), headers={
        "User-Agent": "iPhoneSniper/1.0 (public listing alerts)",
        "Accept": "text/html",
    })
    with urlopen(request, timeout=15) as response:
        page = response.read(12_000_000)
    catalog = Catalog()
    catalog.feed(page.decode("utf-8", errors="replace"))
    return catalog.cards


class DiscordLimited(RuntimeError):
    def __init__(self, wait):
        super().__init__("Discord ograniczył wysyłkę.")
        self.wait = wait


def send_listing(hook, payload):
    request = Request(hook + "?wait=true", json.dumps(payload).encode(),
                      {"Content-Type": "application/json", "User-Agent": "DiscordBot (https://github.com/igorpud2011-pixel/iphone-sniper, 1.0)"}, method="POST")
    try:
        with urlopen(request, timeout=12) as response:
            receipt = json.load(response)
            if not isinstance(receipt, dict) or not receipt.get("id"):
                raise RuntimeError("Discord nie zwrócił potwierdzenia wiadomości.")
    except HTTPError as error:
        if error.code == 429:
            wait = retry_delay(error.headers.get("Retry-After"), 2)
            try:
                wait = max(wait, float(json.load(error).get("retry_after", 0)))
            except (ValueError, TypeError, OSError, AttributeError):
                pass
            raise DiscordLimited(wait) from None
        raise RuntimeError(f"Wysyłka na Discord: HTTP {error.code}.") from None


def catalogue_window(read, pages, phones):
    """Keep each front page on its own clock while recovery pages are being read."""
    first_page = Event()
    limited = Event()
    started = time.monotonic()

    def fetch(page, focused, emit):
        if limited.is_set():
            return
        result = read(page, focused)
        error = result[1]
        if isinstance(error, HTTPError) and error.code in (403, 429):
            limited.set()
        emit((page, focused, result))

    def watch_head(focused, emit):
        try:
            fetch(1, focused, emit)
        finally:
            if not focused:
                first_page.set()
        for _ in remaining_slots(started):
            fetch(1, focused, emit)

    def recover_pages(emit):
        first_page.wait()
        for page in range(2, pages + 1):
            fetch(page, False, emit)

    tasks = [partial(watch_head, False)]
    if phones:
        tasks.append(partial(watch_head, True))
    if pages > 1:
        tasks.append(recover_pages)
    yield from stream_workers(tasks, len(tasks))


def scan(hook, settings, report, *, front_only=False, phones=False, window=False):
    if not STATE.exists():
        request = Request(hook, headers={"Accept": "application/json"})
        with urlopen(request, timeout=12) as response:
            if not json.load(response).get("channel_id"):
                raise RuntimeError("Discord nie potwierdził kanału webhooka.")
    previous = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    if isinstance(previous, list):
        previous = {"seen": previous, "legacy_cutoff": max(map(int, previous), default=0)}
    seen = previous.get("seen", [])
    legacy_cutoff = previous.get("legacy_cutoff")
    known = set(seen)
    metadata = {key: previous[key] for key in ("phones_baseline", "retry_until", "baseline_pages", "discord_until", "pending") if key in previous}
    blocked = metadata.get("retry_until", 0) > time.time()
    # Older state files already have a broad-catalogue baseline on all pages.
    baseline_pages = set(metadata.get("baseline_pages", [] if "seen" in previous else range(1, CATALOG_PAGES + 1)))
    if baseline_pages:
        front_only = False
    fetched = set()
    processed = set()
    checked = 0
    fresh = 0
    pending = metadata.setdefault("pending", {})
    pages = 1 if front_only else CATALOG_PAGES
    report["searches_total"] = pages - 1 + (1 + int(phones)) * (3 if window else 1)

    def checkpoint():
        save(seen, legacy_cutoff, baseline_pages=sorted(baseline_pages),
             **{key: value for key, value in metadata.items() if key != "baseline_pages"})

    def read(page, focused=False):
        started = time.time()
        try:
            cards = fetch_catalog(page, phones=True) if focused else fetch_catalog(page)
            if not cards:
                raise ValueError("brak rozpoznanych kart")
        except (HTTPError, OSError, TimeoutError, ValueError) as error:
            return {}, error, time.time()
        observed = time.time()
        if page == 1:
            trace("vinted", "phones_read" if focused else "front_read", started=round(started, 3), cards=len(cards))
        return cards, None, observed

    def deliver(item_id, url, details, observed):
        payload = alert_payload(item_id, details, url, settings)
        if not payload:
            if pending.pop(item_id, None) is not None:
                checkpoint()
            return
        report["matched"] += 1
        if metadata.get("discord_until", 0) <= time.time():
            try:
                send_listing(hook, payload)
            except DiscordLimited as error:
                metadata["discord_until"] = time.time() + max(1, error.wait)
                report["errors"].append("Discord ograniczył wysyłkę. Zachowuję kolejkę.")
            except (OSError, ValueError, RuntimeError) as error:
                metadata["discord_until"] = time.time() + 10
                report["errors"].append(f"Wysyłka Vinted: {type(error).__name__}.")
            else:
                report["alerts"] += 1
                trace("vinted", "accepted", since_detection=round(max(0, time.time() - observed), 2))
                seen.append(item_id)
                known.add(item_id)
                pending.pop(item_id, None)
                checkpoint()
                return
        if item_id not in pending:
            pending[item_id] = [url, details, observed]
            checkpoint()

    # Confirmed receipts survive restarts. A Discord limit does not discard
    # other newly seen listings, and a pending item can outlive a catalogue page.
    retry_started = time.monotonic()
    for item_id, (url, details, observed) in list(pending.items()):
        if metadata.get("discord_until", 0) > time.time() or time.monotonic() - retry_started >= 3:
            break
        deliver(item_id, url, details, observed)
    if blocked:
        report["errors"].append("Vinted: przerwa po ograniczeniu dostępu.")
        return
    metadata.pop("retry_until", None)

    def consume(page, focused, result):
        nonlocal checked, fresh, blocked
        cards, error, observed = result
        if error:
            status = error.code if isinstance(error, HTTPError) else None
            reason = f"HTTP {status}" if status else type(error).__name__
            report["errors"].append(f"Vinted {'telefony Apple' if focused else 'katalog'}, strona {page}: {reason}.")
            if status in (403, 429):
                blocked = True
                pause = retry_delay(error.headers.get("Retry-After"), 300 if status == 403 else 60)
                metadata["retry_until"] = max(metadata.get("retry_until", 0), time.time() + pause)
                checkpoint()
            return
        checked += 1
        report["searches_ok"] += 1
        fetched.update(cards)
        report["fetched"] = len(fetched)
        # Introducing the faster category must not send its pre-existing inventory.
        # Its initial IDs stay eligible if the original broad search reports them.
        initial_category = focused and "phones_baseline" not in metadata
        if initial_category:
            metadata["phones_baseline"] = list(cards)
        category_baseline = set(metadata.get("phones_baseline", [])) if focused else set()
        initial_page = not focused and page in baseline_pages
        for item_id in sorted(cards, key=int, reverse=True):
            if item_id in known or item_id in category_baseline or item_id in pending:
                continue
            if initial_page or (legacy_cutoff is not None and int(item_id) <= legacy_cutoff):
                seen.append(item_id)
                known.add(item_id)
                continue
            url, details = cards[item_id]
            if (item_id, details) in processed:
                continue
            processed.add((item_id, details))
            fresh += 1
            deliver(item_id, url, details, observed)
        if initial_page:
            baseline_pages.remove(page)
        checkpoint()

    if window:
        for page, focused, result in catalogue_window(read, pages, phones):
            consume(page, focused, result)
    elif phones:
        with ThreadPoolExecutor(max_workers=2) as pool:
            heads = {pool.submit(read, 1, focused): focused for focused in (False, True)}
            for future in as_completed(heads):
                consume(1, heads[future], future.result())
    else:
        consume(1, False, read(1))

    if not window and not front_only:
        for page in range(2, CATALOG_PAGES + 1):
            if blocked:
                break
            result = read(page)
            consume(page, False, result)
    if not checked:
        raise RuntimeError("Vinted nie zwrócił kart wyników. Sprawdź dostęp do katalogu.")
    if pending and not report["errors"]:
        report["errors"].append("Wiadomości oczekują na ponowienie wysyłki do Discorda.")
    if not front_only and not report["errors"]:
        legacy_cutoff = None
    checkpoint()
    print(f"Karty: {len(fetched)}. Nowe pozycje: {fresh}. Wysłane alerty Vinted: {report['alerts']}.", flush=True)


def run_scan(hook, window):
    started = time.monotonic()
    report = dict(status="error", searches_total=0, searches_ok=0, fetched=0, matched=0, alerts=0, errors=[])
    try:
        settings = settings_request("settings")
        if settings["enabled"]:
            scan(hook, settings, report, phones=True, window=window)
            report["status"] = "partial" if report["errors"] else "ok"
        else:
            report["status"] = "paused"
    except (Exception, SystemExit) as error:
        message = str(error) if isinstance(error, (SystemExit, RuntimeError)) else type(error).__name__
        report["errors"].append(message)
        print(f"Skan Vinted nieudany: {message}", flush=True)
    finally:
        report.update(finished_at=int(time.time()), duration_seconds=round(time.monotonic()-started, 2))
        try:
            settings_request("health", report)
        except Exception:
            print("Nie udało się przesłać statusu Vinted do panelu.", flush=True)
    return int(bool(report["errors"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--window", action="store_true", help="Sprawdzaj pierwsze strony co 20 s przez minutę.")
    options = parser.parse_args()
    hook = os.environ.get("DISCORD_VINTED_WEBHOOK_URL", "").strip()
    if not HOOK.fullmatch(hook):
        raise SystemExit("Ustaw sekret DISCORD_VINTED_WEBHOOK_URL z webhookiem kanału Vinted.")
    return run_scan(hook, options.window)


if __name__ == "__main__":
    raise SystemExit(main())
