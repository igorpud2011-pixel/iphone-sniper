"""Read a public Vinted search and post new iPhone listings to Discord."""
import json
import os
from pathlib import Path
import re
import time
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

import requests

from bot import Listing, detect_model, phone_model, resale_estimate

ORIGIN = "https://www.vinted.pl"
STATE = Path(".vinted-state.json")
ACCESSORY = re.compile(r"\b(?:etui|case|cover|husa|husă|hülle|protector|pokrowiec|folia|"
                       r"koque|coque|obudow[ayę]|korpus|ładowark[ai]|kabel|szkło|szybk[aię]|"
                       r"wyświetlacz\w*|wyswietlacz\w*|ekran\w*|digitizer|lcd|oled|"
                       r"akumulator\w*|płyta główna|plyta glowna|taśm[ayę]|pudełk[oa]|"
                       r"klapk[aię]|dummy|części|czesci)\b", re.I)
PART_AT_START = re.compile(r"^(?:(?:now[yae]|oryginaln[yae])\s+)*(?:bateri[aeę]|aparat|kamera|moduł|głośnik)\b", re.I)
PART_AFTER_MODEL = re.compile(r"\b(?:bateri[aeę]|aparat|kamera|głośnik)\s*(?:$|(?:oryginaln\w*|zamiennik|nowa|nowy)\b)", re.I)
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


PRICE = re.compile(r"(?<![\d.,])(\d[\d \u00a0\u202f]*(?:[,.]\d{1,2})?)\s*zł", re.I)
META = re.compile(r", (?:Marka|Model|Stan|Rozmiar|Kolor): ")
CONDITION = re.compile(r", Stan: ([^,]+)")
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
    if not model or model not in settings["models"] or ACCESSORY.search(title) or PART_AT_START.search(title) or PART_AFTER_MODEL.search(title):
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
    return {"embeds": [{"title": f"📱 {title}"[:250], "url": url,
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


def scan(hook, settings, report):

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
    report["fetched"] = len(catalog.cards)
    if not catalog.cards:
        raise RuntimeError("Vinted nie zwrócił kart wyników. Sprawdź dostęp do katalogu.")
    report["searches_ok"] = 1
    if not STATE.exists() or os.environ.get("GITHUB_EVENT_NAME") in {"push", "workflow_dispatch"}:
        request = Request(hook, headers={"Accept": "application/json", "User-Agent": "DiscordBot (https://github.com/igorpud2011-pixel/iphone-sniper, 1.0)"})
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
        save(seen)
    print(f"Karty: {len(catalog.cards)}. Nowe pozycje: {fresh}. Wysłane alerty Vinted: {sent}.")


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
            report["status"] = "ok"
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
