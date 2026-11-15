#!/usr/bin/env python3
"""iPhone Sniper: polite OLX listing monitor with Discord/Telegram alerts."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import html
import json
import logging
import math
import os
import re
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit, urlencode

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

MODEL_IDS = ['duo', '18 pro max', '18 pro', '17 pro max', '17 pro', '17', '17e', 'air', '16 pro max', '16 pro', '16 plus', '16', '16e', '15 pro max', '15 pro', '15 plus', '15', '14 pro max', '14 pro', '14 plus', '14', '13 pro max', '13 pro', '13 mini', '13', '12 pro max', '12 pro', '12 mini', '12', '11 pro max', '11 pro', '11', 'xs max', 'xs', 'xr', 'x', 'se 2022', 'se 2020', 'se 2016', 'se', '8 plus', '8', '7 plus', '7', '6s plus', '6s', '6 plus', '6', '5s', '5c', '5', '4s', '4', '3gs', '3g', '2g']

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
STATE_PATH = ROOT / "data" / "seen.json"
PLACES_PATH = ROOT / "data" / "wilkowice_places.json"
OLX_HOST = "www.olx.pl"
LOG = logging.getLogger("iphone_sniper")
load_dotenv(ROOT / ".env")


@dataclass
class Listing:
    listing_id: str
    title: str
    url: str
    price: str = "Cena niepodana"
    location_date: str = ""
    image_url: str = ""
    source: str = "OLX"
    location_name: str = ""
    detected_at: int = 0
    fetch_seconds: float | None = None


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        config = json.load(f)
    settings_url = os.getenv("SETTINGS_URL", "").strip()
    if settings_url:
        if urlsplit(settings_url).scheme != "https":
            raise ValueError("SETTINGS_URL musi używać HTTPS.")
        key = os.getenv("SETTINGS_KEY", "").strip()
        if not key:
            raise ValueError("Brak SETTINGS_KEY.")
        try:
            response = requests.get(settings_url, headers={"Authorization": "Bearer " + key}, timeout=15)
            response.raise_for_status()
            remote = response.json()
        except (requests.RequestException, ValueError):
            raise RuntimeError("Nie można odczytać ustawień Discorda. Pomijam przebieg zamiast używać starych filtrów.") from None
        values = remote.get("models")
        if not isinstance(values, list) or not values:
            raise ValueError("Brak wybranych modeli.")
        models = list(dict.fromkeys(m for value in values for m in
            ([m for m in MODEL_IDS if m.split()[0] == str(value)] if type(value) is int else [str(value).lower()])))
        if not models or any(m not in MODEL_IDS for m in models):
            raise ValueError("Niepoprawne modele w ustawieniach.")
        city = remote.get("city", "")
        if not isinstance(city, str) or not re.fullmatch(r"[^\W\d_][^\d_]{1,79}", city):
            raise ValueError("Niepoprawna nazwa miasta.")
        slug = unicodedata.normalize("NFKD", city.lower().replace("ł", "l")).encode("ascii", "ignore").decode()
        slug = re.sub(r"[^a-z]+", "-", slug).strip("-")
        radius = remote.get("radius")
        minimum, maximum = remote.get("min", 0), remote.get("max")
        if type(radius) is not int or radius not in [0,2,5,10,15,30,50,75,100,150,200]:
            raise ValueError("Niepoprawny promień.")
        if type(minimum) is not int or not 0 <= minimum <= 100000 or (maximum is not None and (type(maximum) is not int or not minimum <= maximum <= 100000)):
            raise ValueError("Niepoprawne ceny.")
        if type(remote.get("enabled")) is not bool:
            raise ValueError("Niepoprawny stan monitorowania.")
        query = {"search[dist]": radius, "search[order]": "created_at:desc", "search[filter_float_price:from]": minimum}
        if maximum is not None:
            query["search[filter_float_price:to]"] = maximum
        families = list(dict.fromkeys(m.split()[0] for m in models))
        config["searches"] = [{"name": f"iPhone {n} · {city} +{radius} km", "source": "rss",
            "url": f"https://www.olx.pl/elektronika/telefony/{slug}/q-iphone-{n}/?" + urlencode(query)} for n in families]
        # Additional first-page search catches titles missed by family searches.
        config["searches"].append({"name": f"iPhone · {city} +{radius} km", "source":"rss",
            "url": f"https://www.olx.pl/elektronika/telefony/{slug}/q-iphone/?" + urlencode(query)})
        config["model_ids"] = models
        config["price_min"] = minimum
        config["price_max"] = maximum
        config["area_city"] = city
        config["area_radius"] = radius
        config["enabled"] = remote["enabled"]
    searches = config.get("searches", [])
    if not searches:
        raise ValueError("config.json nie zawiera żadnych wyszukiwań.")
    for search in searches:
        url = search.get("url", "")
        host = urlsplit(url).hostname or ""
        if host not in {OLX_HOST, "olx.pl"}:
            raise ValueError(f"Dozwolone są tylko adresy OLX.pl. Nieprawidłowy adres: {url}")
    # One broad independent feed supplements the existing family feeds.
    # Keep a single request per scan: RSS-Bridge may crawl detail pages on cache miss.
    primary = [search for search in searches if search.get("source") == "rss"]
    if primary and config.get("supplementary_rss_bridge", True):
        broad = next((search for search in primary if "/q-iphone/?" in search["url"]), None)
        if broad is None:
            broad = dict(primary[0])
            broad["url"] = re.sub(r"/q-iphone-[^/]+/", "/q-iphone/", broad["url"])
        config["searches"].append({**broad, "name": "OLX · RSS-Bridge (uzupełniający)", "source": "rss_bridge"})
    return config


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"initialized": False, "seen_ids": []}
    try:
        with STATE_PATH.open("r", encoding="utf-8") as f:
            state = json.load(f)
        if not isinstance(state, dict) or not isinstance(state.get("seen_ids"), list):
            raise ValueError("Nieprawidłowy format seen_ids")
        for key in ("seen_ids", "notified_ids", "rejected_ids", "bootstrap_searches", "initialized_searches"):
            if key in state and (not isinstance(state[key], list) or any(not isinstance(x, str) for x in state[key])):
                raise ValueError("Nieprawidłowy format historii")
        return state
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        # Never silently replace an existing history with a fresh baseline:
        # that could consume new offers without sending any notification.
        raise RuntimeError("Nie można odczytać historii ofert; zachowuję plik do naprawy.") from exc


def save_state(state: dict[str, Any], max_seen: int = 12000) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ids = list(dict.fromkeys(state.get("seen_ids", [])))[-max_seen:]
    payload = {"initialized": bool(state.get("initialized", False)), "seen_ids": ids,
               "initialized_searches": state.get("initialized_searches", []),
               "bootstrap_searches": state.get("bootstrap_searches", []),
               "notified_ids": state.get("notified_ids", [])[-max_seen:],
               "rejected_ids": state.get("rejected_ids", [])[-max_seen:], "id_format_version": 2}
    tmp = STATE_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(STATE_PATH)


def _text(node: Any) -> str:
    return node.get_text(" ", strip=True) if node else ""


def _first_text(card: Any, selectors: list[str]) -> str:
    for selector in selectors:
        node = card.select_one(selector)
        value = _text(node)
        if value:
            return value
    return ""


def extract_location(value: str) -> tuple[str, str]:
    place = re.search(r"Miejscowość:\s*([^,]+)", value, flags=re.IGNORECASE)
    posted = re.search(r"Wystawiono:\s*([^,]+)", value, flags=re.IGNORECASE)
    if place:
        return place.group(1).strip(), posted.group(1).strip() if posted else ""
    # OLX HTML cards commonly show “City - date” in one line.
    return (value.split(" - ", 1)[0].strip(), "") if value else ("", "")


def normalize_phone_title(title: str) -> str:
    title = re.sub(r"\biphone[\s-]*", "iphone ", title, flags=re.IGNORECASE)
    return re.sub(r"(?<=\d)(?=pro|max|mini|plus)", " ", title, flags=re.IGNORECASE)


def detect_model(title: str) -> str | None:
    title = normalize_phone_title(title).casefold()
    title = re.sub(r"(?<=pro)(?=max)", " ", title)
    match = re.search(r"\biphone\s*(.*)", title)
    if not match:
        return None
    rest = match.group(1)
    short_se = re.match(r"se\s*([123])\b", rest)
    if short_se:
        return {"1":"se 2016","2":"se 2020","3":"se 2022"}[short_se[1]]
    if re.match(r"se(?:\b|20\d{2})", rest):
        for year, aliases in [("2022", r"2022|3[ .]*(?:gen|generacja)"), ("2020", r"2020|2[ .]*(?:gen|generacja)"), ("2016", r"2016|1[ .]*(?:gen|generacja)")]:
            if re.search(aliases, rest):
                return "se " + year
        return "se"
    for model in sorted(MODEL_IDS, key=len, reverse=True):
        pattern = re.escape(model).replace(r"\ ", r"\s*")
        if re.match(pattern + r"(?:(?![a-z0-9])|(?=(?:32|64|128|256|512|1024|2048)gb\b))", rest):
            return model
    return None


def phone_model(title: str) -> str:
    model = detect_model(title)
    return "iPhone " + model.upper().replace("PRO", "Pro").replace("MAX", "Max").replace("PLUS", "Plus").replace("MINI", "mini") if model else "Model nieznany"


def _normalized_place(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name.replace("ł", "l").replace("Ł", "l")).encode("ascii", "ignore").decode("ascii").casefold()
    return re.sub(r"[^a-z0-9]+", " ", ascii_name).strip()


@lru_cache(maxsize=1)
def _place_index() -> tuple[tuple[float, float], dict[str, list[tuple[float, float]]]]:
    with PLACES_PATH.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    center = data["center"]
    places: dict[str, list[tuple[float, float]]] = {}
    for place in data.get("places", []):
        key = _normalized_place(str(place.get("name", "")))
        if key:
            places.setdefault(key, []).append((float(place["latitude"]), float(place["longitude"])))
    return (float(center["latitude"]), float(center["longitude"])), places


def distance_from_wilkowice(location_name: str) -> int | None:
    key = _normalized_place(location_name)
    if not key:
        return None
    try:
        (origin_lat, origin_lon), places = _place_index()
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        LOG.warning("Nie można odczytać lokalnej bazy miejscowości (%s).", exc)
        return None
    candidates = places.get(key)
    if not candidates:
        return None
    origin_phi = math.radians(origin_lat)
    distances = []
    for latitude, longitude in candidates:
        phi = math.radians(latitude)
        dphi = phi - origin_phi
        dlambda = math.radians(longitude - origin_lon)
        a = math.sin(dphi / 2) ** 2 + math.cos(origin_phi) * math.cos(phi) * math.sin(dlambda / 2) ** 2
        distances.append(2 * 6371 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))
    return round(min(distances))


def distance_from_city(location: str, city: str) -> float | None:
    try:
        _, places = _place_index()
        centers = places.get(_normalized_place(city), [])
        destinations = places.get(_normalized_place(location), [])
        if len(centers) != 1 or len(destinations) != 1:
            return None  # Unknown or ambiguous place: retain the source's location filter.
        lat, lon = map(math.radians, centers[0])
        lat2, lon2 = map(math.radians, destinations[0])
        a = math.sin((lat2-lat)/2)**2 + math.cos(lat)*math.cos(lat2)*math.sin((lon2-lon)/2)**2
        return 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0,1-a)))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def canonical_url(href: str) -> str:
    absolute = urljoin("https://www.olx.pl", href)
    parts = urlsplit(absolute)
    # Remove tracking parameters while preserving the canonical advert path.
    return urlunsplit(("https", "www.olx.pl", parts.path, "", ""))


def stable_id(url: str) -> str:
    match = re.search(r"-(ID[A-Z0-9]+)(?:\.html)?/?$", urlsplit(url).path, flags=re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]


def parse_olx_html(page_html: str, source_name: str = "OLX") -> list[Listing]:
    soup = BeautifulSoup(page_html, "html.parser")
    title_text = _text(soup.title).lower()
    page_text = _text(soup.body).lower()[:5000]
    blocked_markers = ("verify you are human", "just a moment", "access denied", "captcha")
    if any(marker in title_text or marker in page_text for marker in blocked_markers):
        raise RuntimeError("OLX zwrócił stronę zabezpieczającą zamiast wyników wyszukiwania.")

    cards = soup.select('div[data-cy="l-card"]')
    if not cards:
        # Fallback for older markup versions.
        cards = soup.select(".offer-wrapper")

    if not cards:
        no_results_markers = (
            "nie znaleziono ogłoszeń",
            "brak wyników",
            "nie ma ogłoszeń",
            "no results",
        )
        if not any(marker in page_text for marker in no_results_markers):
            raise RuntimeError("Nie rozpoznaję układu wyników OLX. Nie zapisuję pustego wyniku jako poprawnego.")
        return []

    listings: list[Listing] = []
    for card in cards:
        link = card.select_one('a[href*="/d/oferta/"]')
        if not link:
            link = card.select_one("a[href]")
        href = link.get("href", "").strip() if link else ""
        if not href:
            continue
        url = canonical_url(href)
        title = _first_text(card, [
            '[data-cy="ad-card-title"]',
            '[data-testid="ad-title"]',
            "h6", "h4", "h3",
        ])
        if not title:
            title = (link.get("title") or _text(link)).strip()
        if not title:
            continue

        price = _first_text(card, [
            '[data-testid="ad-price"]',
            '[data-cy="ad-price"]',
            "p.price", ".price",
        ]) or "Cena niepodana"
        location_date = _first_text(card, [
            '[data-testid="location-date"]',
            '[data-cy="location-date"]',
            "p[data-testid]",
        ])
        location_name, _ = extract_location(location_date)
        image_url = ""
        img = card.select_one("img")
        if img:
            candidate = img.get("src") or img.get("data-src") or ""
            if candidate.startswith("http"):
                image_url = candidate

        listings.append(Listing(
            listing_id=stable_id(url),
            title=title,
            url=url,
            price=price,
            location_date=location_date,
            image_url=image_url,
            source=source_name,
            location_name=location_name,
        ))
    return listings


def parse_rss(payload: str, source_name: str = "OLX RSS") -> list[Listing]:
    root = ET.fromstring(payload)
    if root.tag != "rss" or root.find("channel") is None:
        raise ValueError("Źródło nie zwróciło kanału RSS.")
    listings = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        parts = urlsplit(link)
        if parts.scheme != "https" or parts.hostname not in {"olx.pl", OLX_HOST} or "/d/oferta/" not in parts.path:
            continue
        if not title:
            continue
        detail = BeautifulSoup(item.findtext("description") or "", "html.parser")
        price = _text(detail.select_one("h1")) or _text(detail.select_one("p:nth-of-type(2) > span"))
        price = re.sub(r"^Cena:\s*", "", price) or "Cena niepodana"
        location = _text(detail.select_one("p"))
        location_name, _ = extract_location(location)
        image = detail.select_one("img")
        image_url = image.get("src", "") if image else ""
        media = item.find("{http://search.yahoo.com/mrss/}content")
        if media is not None:
            image_url = media.get("url", "").split("#", 1)[0]
        if urlsplit(image_url).scheme != "https":
            image_url = ""
        url = canonical_url(link)
        listings.append(Listing(stable_id(url), title, url, price, location, image_url, source_name, location_name))
    if root.findall("./channel/item") and not listings:
        raise RuntimeError("RSS zawiera wpisy, ale parser nie rozpoznaje ofert.")
    return listings


def stamp_listings(listings: list[Listing], started: float) -> list[Listing]:
    timestamp, duration = int(time.time()), round(time.monotonic()-started, 2)
    for listing in listings:
        listing.detected_at, listing.fetch_seconds = timestamp, duration
    return listings


def fetch_search(session: requests.Session, search: dict[str, str], timeout: int) -> list[Listing]:
    started = time.monotonic()
    url = search["url"]
    if search.get("source") in {"rss", "rss_bridge"}:
        if search.get("source") == "rss_bridge":
            endpoint = "https://rssbridge.sciunto.org/"
            params = {"action": "display", "bridge": "OLX", "url": url,
                      "includePostsWithoutPricetag": "on", "includeFeaturedPosts": "on", "format": "Mrss"}
        else:
            endpoint, params = "https://tedeelock.com/src/get.php", {"url": url}
        response = session.get(endpoint, params=params, timeout=timeout)
        response.raise_for_status()
        listings = parse_rss(response.text, search.get("name", "OLX") + " · RSS")
        return stamp_listings(listings, started)
    response = session.get(url, timeout=timeout)
    if response.status_code in (403, 429):
        raise RuntimeError(f"OLX odpowiedział kodem {response.status_code}; pomijam to sprawdzenie bez obchodzenia blokady.")
    response.raise_for_status()
    return stamp_listings(parse_olx_html(response.text, search.get("name", "OLX")), started)


def is_flip_candidate(listing: Listing, config: dict[str, Any]) -> bool:
    title = normalize_phone_title(listing.title).casefold()
    include_pattern = config.get("include_title_regex", r"\biphone\s*(11|12|13)\b")
    if (detect_model(title) not in config["model_ids"] if "model_ids" in config else not re.search(include_pattern, title, flags=re.IGNORECASE)):
        return False
    # Product names can follow the phone model ("iPhone 13 etui czarne").
    # Preserve bundles such as "iPhone 13 z etui" and storage-first phone titles.
    model = detect_model(title)
    if model:
        normalized = normalize_phone_title(title)
        model_pattern = re.escape(model).replace(r"\ ", r"\s*")
        tail = re.search(r"\biphone\s*" + model_pattern + r"\s+(.+)", normalized)
        if tail and re.match(r"(?:etui|etiu|case|pokrowiec|folia|(?:szkło|szklo) ochronne|(?:wyświetlacz|wyswietlacz|ekran) (?:lcd|oled)|oryginalne części)\b", tail[1]):
            return False
    city, radius = config.get("area_city"), config.get("area_radius")
    if city and radius is not None:
        place = listing.location_name or extract_location(listing.location_date)[0]
        if radius == 0 and place and _normalized_place(place) != _normalized_place(city):
            return False
        distance = distance_from_city(place, city)
        if distance is not None and distance > radius:
            return False
    minimum, maximum = config.get("price_min", 0), config.get("price_max")
    if minimum or maximum is not None:
        price = re.search(r"(\d[\d \u00a0\u202f]*(?:[,.]\d{1,2})?)\s*(?:zł|pln)", listing.price, flags=re.IGNORECASE)
        if not price:
            return False
        amount = float(re.sub(r"\s", "", price[1]).replace(",", "."))
        if amount < minimum or (maximum is not None and amount > maximum):
            return False
    exclude_words = config.get("exclude_title_words", [])
    prefix = title.split("iphone", 1)[0]
    # Accessories at the start are standalone products. A phone bundled with
    # an etui/cable remains a valid phone listing.
    intent_words = {'kupię', 'kupie', 'zamienię', 'zamienie', 'na części', 'na czesci', 'sama bateria'}
    if any((str(word).casefold() in title if str(word).casefold() in intent_words else
            re.search(r"\b" + re.escape(str(word)) + r"\b", prefix, flags=re.IGNORECASE))
           for word in exclude_words):
        return False
    return True


def format_plain(listing: Listing) -> str:
    place = listing.location_name or extract_location(listing.location_date)[0] or "Nie podano"
    distance = distance_from_wilkowice(place)
    parts = [
        f"📱 Model: {phone_model(listing.title)}",
        f"🏷️ Tytuł: {listing.title}",
        f"💰 Cena: {listing.price}",
        f"📍 Miejscowość: {place}",
        f"📏 Od Wilkowic: około {distance} km w linii prostej" if distance is not None else "📏 Od Wilkowic: brak danych o odległości",
    ]
    posted = extract_location(listing.location_date)[1]
    if posted:
        parts.append(f"🕒 Wystawiono: {posted}")
    parts.append(resale_estimate(listing))
    parts.extend([f"🔎 Wyszukiwanie: {listing.source}", listing.url])
    return "\n".join(parts)


def capture_timing(listing: Listing, now: datetime | None = None) -> str:
    timestamp = listing.detected_at or int((now or datetime.now(ZoneInfo("UTC"))).timestamp())
    result = f"Wykryto: <t:{timestamp}:F> (<t:{timestamp}:R>)"
    if listing.fetch_seconds is not None:
        result += f"\nPobranie i odczyt źródła: {listing.fetch_seconds:.2f} s"
    return result + "\nOpóźnienie od publikacji: brak wiarygodnego pomiaru w RSS."


@lru_cache(maxsize=1)
def resale_table() -> dict[str, Any]:
    raw = os.getenv("RESALE_PRICES_JSON", "").strip()
    if not raw:
        raise ValueError("Cennik nie został skonfigurowany.")
    table = json.loads(raw)
    if not isinstance(table, dict) or not isinstance(table.get("date"), str) or not isinstance(table.get("rows"), list):
        raise ValueError("Niepoprawny format cennika.")
    for row in table["rows"]:
        if (not isinstance(row, dict) or not isinstance(row.get("model"), str)
            or type(row.get("storage_gb")) is not int or row["storage_gb"] <= 0
            or type(row.get("sale_price")) not in (int, float)
            or not math.isfinite(row["sale_price"]) or row["sale_price"] < 0
            or type(row.get("suspect")) is not bool):
            raise ValueError("Niepoprawny wiersz cennika.")
    return table


def resale_estimate(listing: Listing) -> str:
    try:
        table = resale_table()
    except (OSError, ValueError):
        return "Cennik niedostępny. Nie wyliczam zysku."
    model = detect_model(listing.title)
    capacity_title = re.sub(r"(?<=\d)(?=(?:32|64|128|256|512|1024|2048)\s*(?:GB|TB)\b)", " ", listing.title, flags=re.IGNORECASE)
    capacities = {int(n)*(1024 if unit.lower()=="tb" else 1) for n,unit in re.findall(r"(?<!\d)(32|64|128|256|512|1024|2048|1|2)\s*(GB|TB)\b", capacity_title, flags=re.IGNORECASE)}
    rows = [r for r in table["rows"] if r["model"]==model]
    exact = len(capacities)==1
    if exact:
        rows = [r for r in rows if r["storage_gb"]==next(iter(capacities))]
    if not rows:
        return "Brak ceny dla tego modelu/pamięci w Twojej tabeli."
    if any(r["suspect"] for r in rows):
        return "⚠️ Podejrzana wartość w tabeli. Wstrzymuję wyliczenie do sprawdzenia ceny."
    prices = [r["sale_price"] for r in rows]
    low, high = min(prices), max(prices)
    money = lambda a,b: f"{a:g} zł" if a==b else f"{a:g}–{b:g} zł"
    result = "Twoja cena sprzedaży: **" + money(low,high) + "**"
    price = re.search(r"(?<![\d.,])(\d[\d \u00a0\u202f]*(?:[,.]\d{1,2})?)\s*(?:zł|pln)", listing.price, flags=re.IGNORECASE)
    if price:
        asking = float(re.sub(r"\s", "", price[1]).replace(",", "."))
        result += "\nZysk przed kosztami: **" + money(low-asking,high-asking) + "**"
    else:
        result += "\nBrak rozpoznanej ceny zakupu."
    if not exact:
        result += "\nNieznana pamięć: zakres obejmuje warianty modelu."
    elif low!=high:
        result += "\nW tabeli są różne ceny tego samego wariantu."
    return result + "\nCennik: " + table["date"] + "; bez napraw, prowizji i transportu."


def send_discord(webhook_url: str, listing: Listing, timeout: int) -> None:
    place = listing.location_name or extract_location(listing.location_date)[0] or "Nie podano"
    distance = distance_from_wilkowice(place)
    estimate = resale_estimate(listing)
    lines = estimate.splitlines()
    prices = []
    notes = []
    for line in lines:
        if line.startswith("Twoja cena sprzedaży:"):
            prices.append("💰 **Sprzedaż:** " + line.split(":", 1)[1].strip())
        elif line.startswith("Zysk przed kosztami:"):
            prices.append("📈 **Zysk przed kosztami:** " + line.split(":", 1)[1].strip())
        elif line.startswith("Cennik:"):
            continue
        else:
            notes.append(line)
    # A single embed keeps all information inside the dark card on mobile.
    price_match = re.search(r"[\d][\d \u00a0\u202f]*(?:[,.]\d{1,2})?\s*zł", listing.price, flags=re.IGNORECASE)
    asking = price_match.group().strip() if price_match else listing.price[:100]
    body = ["🏷️ **Zakup:** **" + asking + "**", *prices]
    if notes:
        body.append("\n" + "\n".join(notes))
    location = f"📍 {place}"
    if distance is not None:
        location += f" · ~{distance} km od Wilkowic"
    body.append("\n" + location)
    posted = extract_location(listing.location_date)[1]
    if posted:
        body.append("🕒 OLX: " + posted[:200])
    timestamp = listing.detected_at or int(time.time())
    timing = f"⚡ Wykryto <t:{timestamp}:t> · <t:{timestamp}:R>"
    if listing.fetch_seconds is not None:
        timing += f" · odczyt {listing.fetch_seconds:.1f} s"
    body.append(timing)
    testing = listing.listing_id in {"test", "pricing-test"}
    if testing:
        capacity = re.search(r"\b(32|64|128|256|512|1|2)\s*(GB|TB)\b", listing.title, flags=re.IGNORECASE)
        title = "🧪 TEST · " + phone_model(listing.title) + (" · " + capacity.group() if capacity else "")
    else:
        title = "📱 " + listing.title[:250]
    embed = {"title":title, "url":listing.url, "description":"\n".join(body)[:4096],
             "color":0x2ECC71, "timestamp":datetime.now(ZoneInfo("UTC")).isoformat(),
             "footer":{"text":"TEST — to nie jest oferta" if testing else "iPhone Sniper • Zysk bez napraw, prowizji i transportu • Opóźnienie publikacji w RSS nieznane"}}
    if listing.image_url:
        embed["image"] = {"url":listing.image_url}
    response = requests.post(webhook_url, json={"content":"", "embeds":[embed], "allowed_mentions":{"parse":[]}}, timeout=timeout)
    response.raise_for_status()


def send_telegram(token: str, chat_id: str, listing: Listing, timeout: int) -> None:
    text = format_plain(listing)
    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(endpoint, json={"chat_id": chat_id, "text": text, "disable_web_page_preview": False}, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError("Telegram nie potwierdził wysłania wiadomości.")


def send_alert(listing: Listing, timeout: int) -> bool:
    results: list[bool] = []
    errors: list[str] = []
    discord_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if discord_url:
        try:
            send_discord(discord_url, listing, timeout)
            results.append(True)
        except Exception as exc:  # continue to the other configured channel
            results.append(False)
            errors.append(f"Discord: {type(exc).__name__}")
    if telegram_token and telegram_chat:
        try:
            send_telegram(telegram_token, telegram_chat, listing, timeout)
            results.append(True)
        except Exception as exc:
            results.append(False)
            errors.append(f"Telegram: {type(exc).__name__}")
    if errors:
        LOG.error("Błąd powiadomienia dla %s: %s", listing.listing_id, "; ".join(errors))
    if not results:
        raise RuntimeError("Brak kanału powiadomień. Ustaw DISCORD_WEBHOOK_URL lub TELEGRAM_BOT_TOKEN i TELEGRAM_CHAT_ID.")
    # Save the listing only if every configured channel accepted the alert. If one fails,
    # retry on the next scan rather than silently losing the notification.
    return all(results)


def _scan_once(report: dict[str, Any]) -> int:
    config = load_config()
    if not config.get("enabled", True):
        report["status"] = "paused"
        LOG.info("Monitoring wstrzymany komendą /pauza.")
        return 0
    report["searches_total"] = len(config["searches"])
    state = load_state()
    if state.get("id_format_version") != 2:
        LOG.info("Aktualizacja identyfikatorów: ustalam nową historię bez alertów o starych ofertach.")
        state = {"initialized": False, "seen_ids": [], "initialized_searches": [], "id_format_version": 2}
    # Only the installation's original searches may establish a silent baseline.
    # Editing city/price/models must never silently consume new listings again.
    if "bootstrap_searches" not in state:
        state["bootstrap_searches"] = [] if state.get("initialized") else [search["url"] for search in config["searches"]]
    bootstrap_searches = set(state["bootstrap_searches"])
    initial_bootstrap = frozenset(bootstrap_searches)
    ordered_seen = list(dict.fromkeys(str(x) for x in state.get("seen_ids", [])))
    rejected = set(state.get("rejected_ids", []))
    seen = set(ordered_seen) - rejected
    initialized_searches = set(state.get("initialized_searches", []))
    if "initialized_searches" not in state and state.get("initialized"):
        initialized_searches.update(search["url"] for search in config["searches"])
    found: list[Listing] = []
    fresh_ids: list[str] = []
    successful_searches = 0

    def fetch_one(search: dict[str, str]) -> list[Listing]:
        with requests.Session() as session:
            session.headers.update({
                "User-Agent": "iPhoneSniper/1.0 (personal listing alert; contact: local-user)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.5",
            })
            return fetch_search(session, search, min(20, int(config.get("request_timeout_seconds", 20))))

    successfully_notified: set[str] = set()

    def checkpoint() -> None:
        pending = {x.listing_id for x in found} - successfully_notified
        known = list(dict.fromkeys(ordered_seen + fresh_ids))
        state["seen_ids"] = [key for key in known if key not in pending]
        state["rejected_ids"] = sorted(rejected)
        state["bootstrap_searches"] = sorted(bootstrap_searches)
        state["initialized_searches"] = sorted(initialized_searches)
        state["notified_ids"] = list(dict.fromkeys(state.get("notified_ids", []) +
            [x.listing_id for x in found if x.listing_id in successfully_notified]))
        state["initialized"] = True
        save_state(state, int(config.get("max_remembered_ids", 12000)))

    # Consume each completed source immediately. A slow supplementary feed must
    # not hold back notifications already available from a healthy source.
    with ThreadPoolExecutor(max_workers=min(8, len(config["searches"]))) as executor:
        futures = {executor.submit(fetch_one, search): index for index, search in enumerate(config["searches"])}
        for future in as_completed(futures):
            index = futures[future]
            search = config["searches"][index]
            try:
                listings = future.result()
                report["fetched"] += len(listings)
                bootstrap = search["url"] in initial_bootstrap and config.get("bootstrap_without_alerts", True)
                bootstrap_searches.discard(search["url"])
                initialized_searches.add(search["url"])
                successful_searches += 1
                report["searches_ok"] = successful_searches
                LOG.info("%s: odczytano %d ofert; pierwsze skanowanie: %s.", search.get("name", "OLX"), len(listings), bootstrap)
                LOG.info("Diagnostyka: %d już znanych, %d odrzuconych przez filtr tytułu.",
                         sum(x.listing_id in seen for x in listings),
                         sum(not is_flip_candidate(x, config) for x in listings))
                for listing in listings:
                    if listing.listing_id in seen:
                        continue
                    fresh_ids.append(listing.listing_id)
                    if bootstrap:
                        seen.add(listing.listing_id)
                    elif is_flip_candidate(listing, config):
                        seen.add(listing.listing_id)
                        rejected.discard(listing.listing_id)
                        found.append(listing)
                        # Deliver while slower providers are still being fetched.
                        try:
                            if send_alert(listing, int(config.get("request_timeout_seconds", 20))):
                                successfully_notified.add(listing.listing_id)
                                checkpoint()
                                LOG.info("Wysłano alert: %s | %s", listing.title, listing.price)
                        except Exception as exc:
                            LOG.error("Nie wysłano alertu dla '%s': %s", listing.title, exc)
                    else:
                        rejected.add(listing.listing_id)
            except Exception as exc:
                report["errors"].append(f"Wyszukiwanie {index+1}: {type(exc).__name__}")
                LOG.error("Nie udało się sprawdzić wyszukiwania '%s': %s", search.get("name", "OLX"), exc)

    if successful_searches == 0:
        LOG.error("Żadne wyszukiwanie nie zadziałało. Stan pozostaje bez zmian.")
        return 2

    # Non-matching results can be marked seen immediately. Matching items are stored only after
    # at least one channel confirms the send, so temporary notification errors can be retried.
    report["matched"] = len(found)
    report["alerts"] = len(successfully_notified)
    if len(successfully_notified) < len(found):
        report["errors"].append("Nie wszystkie alerty zostały dostarczone; bot ponowi wysyłkę.")
    checkpoint()
    LOG.info("Koniec sprawdzania. Nowe oferty pasujące do iPhone'ów: %d; wysłane alerty: %d.", len(found), len(successfully_notified))
    return 0 if len(successfully_notified) == len(found) and successful_searches == len(config["searches"]) else 1


def publish_status(report: dict[str, Any]) -> None:
    settings_url = os.getenv("SETTINGS_URL", "").strip()
    key = os.getenv("SETTINGS_KEY", "").strip()
    if not settings_url or not key:
        return
    try:
        endpoint = urlunsplit((*urlsplit(settings_url)[:2], "/health", "", ""))
        response = requests.post(endpoint, headers={"Authorization": "Bearer " + key}, json=report, timeout=8)
        response.raise_for_status()
    except requests.RequestException:
        LOG.warning("Nie można zapisać statusu. Wynik skanowania pozostaje bez zmian.")


def run_once() -> int:
    report = {"status":"error", "searches_total":0, "searches_ok":0, "fetched":0, "matched":0, "alerts":0, "errors":[]}
    started = time.monotonic()
    try:
        code = _scan_once(report)
        if report["status"] != "paused":
            report["status"] = {0:"ok",1:"partial"}.get(code,"error")
    except Exception as exc:
        report["errors"].append("Nie udało się wykonać skanu: " + type(exc).__name__)
        LOG.error("Skan nieudany: %s", type(exc).__name__)
        code = 2
    report["finished_at"] = int(time.time())
    report["duration_seconds"] = round(time.monotonic()-started, 1)
    publish_status(report)
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor nowych ogłoszeń iPhone na OLX.")
    parser.add_argument("--loop", action="store_true", help="Pracuj stale, zamiast wykonać jedno sprawdzenie.")
    parser.add_argument("--test-discord", action="store_true", help="Wyślij pojedynczy test Discorda bez odczytu OLX.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    if args.test_discord:
        webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
        if not webhook:
            LOG.error("Brak sekretu DISCORD_WEBHOOK_URL.")
            return 1
        try:
            send_discord(webhook, Listing("test", "Test iPhone Sniper: Discord działa", "https://www.olx.pl", price="Wiadomość testowa, nie oferta"), 20)
        except requests.RequestException as exc:
            LOG.error("Test Discorda nieudany: %s", type(exc).__name__)
            return 1
        LOG.info("Discord potwierdził odbiór testu.")
        return 0
    if not args.loop:
        return run_once()

    config = load_config()
    interval = max(60, int(config.get("poll_interval_seconds", 90)))
    LOG.info("Tryb ciągły. Odstęp między sprawdzeniami: %d s.", interval)
    while True:
        started = time.monotonic()
        try:
            run_once()
        except Exception:
            LOG.exception("Nieoczekiwany błąd sprawdzania.")
        remaining = max(1, interval - (time.monotonic() - started))
        time.sleep(remaining)


if __name__ == "__main__":
    sys.exit(main())
