#!/usr/bin/env python3
"""iPhone Sniper: polite OLX listing monitor with Discord/Telegram alerts."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
STATE_PATH = ROOT / "data" / "seen.json"
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


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        config = json.load(f)
    searches = config.get("searches", [])
    if not searches:
        raise ValueError("config.json nie zawiera żadnych wyszukiwań.")
    for search in searches:
        url = search.get("url", "")
        host = urlsplit(url).hostname or ""
        if host not in {OLX_HOST, "olx.pl"}:
            raise ValueError(f"Dozwolone są tylko adresy OLX.pl. Nieprawidłowy adres: {url}")
    return config


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"initialized": False, "seen_ids": []}
    try:
        with STATE_PATH.open("r", encoding="utf-8") as f:
            state = json.load(f)
        if not isinstance(state.get("seen_ids"), list):
            raise ValueError("Nieprawidłowy format seen_ids")
        return state
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        LOG.warning("Nie można odczytać stanu (%s). Tworzę nowy stan.", exc)
        return {"initialized": False, "seen_ids": []}


def save_state(state: dict[str, Any], max_seen: int = 12000) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ids = list(dict.fromkeys(state.get("seen_ids", [])))[-max_seen:]
    payload = {"initialized": bool(state.get("initialized", False)), "seen_ids": ids,
               "initialized_searches": state.get("initialized_searches", []), "id_format_version": 2}
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
        price = _text(detail.select_one("h1"))
        price = re.sub(r"^Cena:\s*", "", price) or "Cena niepodana"
        location = _text(detail.select_one("p"))
        image = detail.select_one("img")
        image_url = image.get("src", "") if image else ""
        if urlsplit(image_url).scheme != "https":
            image_url = ""
        url = canonical_url(link)
        listings.append(Listing(stable_id(url), title, url, price, location, image_url, source_name))
    if not listings:
        raise RuntimeError("Kanał RSS nie zawiera poprawnych ofert. Historia pozostaje bez zmian.")
    return listings


def fetch_search(session: requests.Session, search: dict[str, str], timeout: int) -> list[Listing]:
    url = search["url"]
    if search.get("source") == "rss":
        response = session.get("https://tedeelock.com/src/get.php", params={"url": url}, timeout=timeout)
        response.raise_for_status()
        return parse_rss(response.text, search.get("name", "OLX") + " · RSS")
    response = session.get(url, timeout=timeout)
    if response.status_code in (403, 429):
        raise RuntimeError(f"OLX odpowiedział kodem {response.status_code}; pomijam to sprawdzenie bez obchodzenia blokady.")
    response.raise_for_status()
    return parse_olx_html(response.text, search.get("name", "OLX"))


def is_flip_candidate(listing: Listing, config: dict[str, Any]) -> bool:
    title = listing.title.casefold()
    include_pattern = config.get("include_title_regex", r"\biphone\s*(11|12|13)\b")
    if not re.search(include_pattern, title, flags=re.IGNORECASE):
        return False
    exclude_words = config.get("exclude_title_words", [])
    if any(str(word).casefold() in title for word in exclude_words):
        return False
    return True


def format_plain(listing: Listing) -> str:
    parts = [f"📱 {listing.title}", f"💰 {listing.price}"]
    if listing.location_date:
        parts.append(f"📍 {listing.location_date}")
    parts.extend([f"🔎 Wyszukiwanie: {listing.source}", listing.url])
    return "\n".join(parts)


def send_discord(webhook_url: str, listing: Listing, timeout: int) -> None:
    embed: dict[str, Any] = {
        "title": listing.title[:256],
        "url": listing.url,
        "description": f"**Cena:** {listing.price}" + (f"\n**Lokalizacja / data:** {listing.location_date}" if listing.location_date else ""),
        "color": 5793266,
        "footer": {"text": f"iPhone Sniper • {listing.source}"},
    }
    if listing.image_url:
        embed["thumbnail"] = {"url": listing.image_url}
    response = requests.post(webhook_url, json={"embeds": [embed], "allowed_mentions": {"parse": []}}, timeout=timeout)
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


def run_once() -> int:
    config = load_config()
    state = load_state()
    if state.get("id_format_version") != 2:
        LOG.info("Aktualizacja identyfikatorów: ustalam nową historię bez alertów o starych ofertach.")
        state = {"initialized": False, "seen_ids": [], "initialized_searches": [], "id_format_version": 2}
    ordered_seen = list(dict.fromkeys(str(x) for x in state.get("seen_ids", [])))
    seen = set(ordered_seen)
    initialized_searches = set(state.get("initialized_searches", []))
    if "initialized_searches" not in state and state.get("initialized"):
        initialized_searches.update(search["url"] for search in config["searches"])
    session = requests.Session()
    session.headers.update({
        "User-Agent": "iPhoneSniper/1.0 (personal listing alert; contact: local-user)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.5",
    })

    found: list[Listing] = []
    fresh_ids: list[str] = []
    successful_searches = 0
    for index, search in enumerate(config["searches"]):
        try:
            listings = fetch_search(session, search, int(config.get("request_timeout_seconds", 20)))
            bootstrap = search["url"] not in initialized_searches and config.get("bootstrap_without_alerts", True)
            initialized_searches.add(search["url"])
            successful_searches += 1
            LOG.info("%s: odczytano %d ofert; pierwsze skanowanie: %s.", search.get("name", "OLX"), len(listings), bootstrap)
            for listing in listings:
                if listing.listing_id in seen:
                    continue
                seen.add(listing.listing_id)
                fresh_ids.append(listing.listing_id)
                if bootstrap:
                    pass
                elif is_flip_candidate(listing, config):
                    found.append(listing)
        except Exception as exc:
            LOG.error("Nie udało się sprawdzić wyszukiwania '%s': %s", search.get("name", "OLX"), exc)
        if index < len(config["searches"]) - 1:
            time.sleep(float(config.get("delay_between_searches_seconds", 1.5)))

    if successful_searches == 0:
        LOG.error("Żadne wyszukiwanie nie zadziałało. Stan pozostaje bez zmian.")
        return 2

    # Do not advance the saved state for a listing if every configured notifier failed.
    successfully_notified: set[str] = set()
    for listing in found:
        try:
            if send_alert(listing, int(config.get("request_timeout_seconds", 20))):
                successfully_notified.add(listing.listing_id)
                LOG.info("Wysłano alert: %s | %s", listing.title, listing.price)
        except Exception as exc:
            LOG.error("Nie wysłano alertu dla '%s': %s", listing.title, exc)

    # Non-matching results can be marked seen immediately. Matching items are stored only after
    # at least one channel confirms the send, so temporary notification errors can be retried.
    state_seen = set(ordered_seen)
    for listing_id in fresh_ids:
        candidate = next((x for x in found if x.listing_id == listing_id), None)
        if candidate is None or listing_id in successfully_notified:
            if listing_id not in state_seen:
                state_seen.add(listing_id)
                ordered_seen.append(listing_id)
    state["initialized"] = True
    state["seen_ids"] = ordered_seen
    state["initialized_searches"] = sorted(initialized_searches)
    save_state(state, int(config.get("max_remembered_ids", 12000)))
    LOG.info("Koniec sprawdzania. Nowe oferty pasujące do iPhone'ów: %d; wysłane alerty: %d.", len(found), len(successfully_notified))
    return 0 if len(successfully_notified) == len(found) and successful_searches == len(config["searches"]) else 1


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
