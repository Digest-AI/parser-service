"""
iTicket.md scraper.

Extracts events directly from the listing cards.
iTicket provides excellent schema.org/Event metadata directly in the DOM,
which makes extraction highly reliable.

Pagination is handled via `?page=X`.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterator

from django.utils import timezone as tz

from api.scrapers.base import BaseScraper, EventData

logger = logging.getLogger(__name__)

BASE_URL = "https://iticket.md"

# Mapping from iticket.md category URL slugs to our internal categories
CATEGORY_MAP: dict[str, str] = {
    "concert": "concert",
    "teatru": "theatre",
    "festival": "festival",
    "divers": "other",
    "training": "training",
    "copii": "kids",
    "movies": "movie",
    "all": "other",
}

ALL_CATEGORIES: list[str] = [
    "all",
    "concert",
    "teatru",
    "festival",
    "divers",
    "training",
    "copii",
    "movies",
]


class ITicketMdScraper(BaseScraper):
    """
    Scrapes events from https://iticket.md/events using Playwright.

    Requirements
    ------------
    ::
        pip install playwright
        playwright install chromium

    Usage
    -----
    ::
        from api.scrapers.iticket_md import ITicketMdScraper

        scraper = ITicketMdScraper(categories=["all"])
        created, updated = scraper.run_and_save()
    """

    source_id = "iticket_md"
    source_name = "iTicket.md"
    source_url = "https://iticket.md"

    def __init__(
        self,
        categories: list[str] | None = None,
        language: str = "ro",  # Default language for iTicket
        headless: bool = True,
        max_pages_per_category: int = 5,
        slow_mo: int = 0,
        deep: bool = False,
    ):
        super().__init__(language=language)
        # Default to "all" to scrape everything in one go unless specified
        self.categories = categories or ["all"]
        self.headless = headless
        self.max_pages_per_category = max_pages_per_category
        self.slow_mo = slow_mo
        self.deep = deep

    def scrape(self) -> Iterator[EventData]:
        """Yield EventData objects for all events across all categories."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ImportError(
                "playwright is required. Run: pip install playwright && playwright install chromium"
            ) from exc

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless, slow_mo=self.slow_mo)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="ro-RO",
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()

            seen_ids: set[str] = set()

            try:
                for category in self.categories:
                    yield from self._scrape_category(page, category, seen_ids)
            finally:
                context.close()
                browser.close()

    def _scrape_category(
        self, page: Any, category: str, seen_ids: set[str]
    ) -> Iterator[EventData]:
        """Load listing pages for *category* and yield EventData from cards."""
        base_url = f"{BASE_URL}/events/{category}"
        self.logger.info("Scraping category: %s", base_url)

        for page_num in range(1, self.max_pages_per_category + 1):
            # Using query parameter pagination ?page=X
            url = f"{base_url}?page={page_num}" if page_num > 1 else base_url

            if not self._navigate(page, url):
                break

            # Wait for either the results list or the empty state message
            try:
                page.wait_for_selector(
                    ".cards-list, .empty-results",
                    timeout=10_000,
                )
            except Exception:
                self.logger.warning("Events list not found on %s", url)
                break

            cards = self._extract_cards(page, category)
            new_cards = [c for c in cards if c.external_id not in seen_ids]

            for card in new_cards:
                if card.external_id:
                    seen_ids.add(card.external_id)
                
                if self.deep:
                    card = self._enrich_with_details(page, card)
                
                # Validation: Always require at least one title
                has_title = bool(card.title_ro or card.title_ru)
                if not has_title:
                    continue

                # In deep mode, we require descriptions on BOTH languages 
                # (or at least one if the other is truly missing on the site)
                if self.deep:
                    has_desc = bool(card.description_ro or card.description_ru)
                    if not has_desc:
                        self.logger.warning("Skipping event %s: no description found in deep mode", card.url)
                        continue
                    
                yield card

            self.logger.info(
                "Category %-20s  page %d: %d cards (%d new)",
                category,
                page_num,
                len(cards),
                len(new_cards),
            )

            # If no cards were found, we reached the end of the pagination
            if not cards:
                break

    def _extract_cards(self, page: Any, category: str) -> list[EventData]:
        """
        Extract all event cards from the current listing page DOM using
        embedded schema.org/Event structured data where available.
        """
        try:
            raw: list[dict] = page.evaluate("""
                () => {
                    const cards = [];
                    const cardElements = document.querySelectorAll('.cards-list .card');

                    cardElements.forEach(card => {
                        const linkEl = card.querySelector('a[data-action="select-event"]');
                        if (!linkEl) return;

                        const externalId = linkEl.getAttribute('data-id') || '';
                        const rawCategory = card.querySelector('.card-category')?.textContent?.trim() || '';
                        
                        // Extract from schema.org meta tags
                        const urlEl = card.querySelector('meta[itemprop="url"]');
                        const titleEl = card.querySelector('meta[itemprop="name"]');
                        const imageEl = card.querySelector('meta[itemprop="image"]');
                        const lowPriceEl = card.querySelector('meta[itemprop="lowPrice"]');
                        const highPriceEl = card.querySelector('meta[itemprop="highPrice"]');
                        const currencyEl = card.querySelector('meta[itemprop="priceCurrency"]');
                        const startDateEl = card.querySelector('meta[itemprop="startDate"]');
                        const endDateEl = card.querySelector('meta[itemprop="endDate"]');
                        const locationNameEl = card.querySelector('div[itemprop="location"] meta[itemprop="name"]');
                        const locationAddressEl = card.querySelector('div[itemprop="location"] meta[itemprop="address"]');

                        // Fallbacks
                        const href = urlEl?.content || linkEl.getAttribute('href') || '';
                        const fallbackTitle = card.querySelector('h4')?.textContent?.trim() || '';
                        
                        cards.push({
                            externalId,
                            url: href.startsWith('http') ? href : 'https://iticket.md' + href,
                            title: titleEl?.content || fallbackTitle,
                            imageUrl: imageEl?.content || '',
                            rawCategory,
                            priceLow: lowPriceEl?.content || '',
                            priceHigh: highPriceEl?.content || '',
                            currency: currencyEl?.content || 'MDL',
                            startDate: startDateEl?.content || '',
                            endDate: endDateEl?.content || '',
                            venueName: locationNameEl?.content || '',
                            venueAddress: locationAddressEl?.content || '',
                        });
                    });

                    return cards;
                }
            """)
        except Exception as exc:
            self.logger.error("JS card extraction failed on %s: %s", category, exc)
            return []

        from django.utils.text import slugify

        results: list[EventData] = []
        for item in raw:
            if not item.get("title") or not item.get("url"):
                continue

            price_from, price_to, is_free = self._parse_price(
                item.get("priceLow", ""), item.get("priceHigh", "")
            )
            date_start = self._parse_date(item.get("startDate", ""))
            date_end = self._parse_date(item.get("endDate", ""))
            
            ext_id = item.get("externalId", "")
            slug = slugify(f"iticket-{ext_id}-{item['title']}")

            results.append(
                EventData(
                    url=item["url"],
                    slug=slug,
                    provider_slug="iticket_md",
                    provider_name="iTicket.md",
                    provider_url="https://iticket.md",
                    title_ro=item["title"] if self.language == "ro" else "",
                    title_ru=item["title"] if self.language == "ru" else "",
                    external_id=ext_id,
                    categories=[CATEGORY_MAP.get(category, "other")],
                    date_start=date_start,
                    date_end=date_end,
                    place=item.get("venueName", ""),
                    address=item.get("venueAddress", ""),
                    city="Chișinău",  # iTicket doesn't clearly split city, assuming Chisinau for now
                    price_from=price_from,
                    price_to=price_to,
                    image_url=item.get("imageUrl", ""),
                    tickets_url=item["url"],
                )
            )

        return results

    # ------------------------------------------------------------------
    # Deep scraping: visit each event page
    # ------------------------------------------------------------------

    def _enrich_with_details(self, page: Any, event: EventData) -> EventData:
        """
        Visit the individual event page and enrich *event* with both RU and RO details.
        """
        # We need to visit both RO and RU versions if possible
        # iTicket URLs: https://iticket.md/event/slug (default/RO) or https://iticket.md/ru/event/slug (RU)
        
        current_url = event.url
        # Determine the alternate language URL
        if "/ru/event/" in current_url:
            ro_url = current_url.replace("/ru/event/", "/event/")
            ru_url = current_url
        else:
            ro_url = current_url
            # it might be /en/event/ or just /event/
            if "iticket.md/en/event/" in current_url:
                ru_url = current_url.replace("iticket.md/en/event/", "iticket.md/ru/event/")
            else:
                ru_url = current_url.replace("iticket.md/event/", "iticket.md/ru/event/")

        # 1. Fetch current page
        self._enrich_from_page(page, event, current_url)
        
        # 2. Fetch alternate page
        alt_url = ru_url if current_url == ro_url else ro_url
        if alt_url != current_url:
            self._enrich_from_page(page, event, alt_url)

        return event

    def _enrich_from_page(self, page: Any, event: EventData, url: str) -> None:
        """Helper to extract localized data from a single detail page."""
        if not self._navigate(page, url):
            return

        lang = "ru" if "/ru/event/" in url else "ro"
        
        try:
            page.wait_for_selector(".event-page, .event-detail, [itemprop='description'], main", timeout=5_000)
        except Exception:
            pass

        try:
            data: dict = page.evaluate(r"""
                () => {
                    const result = {
                        title: '',
                        description: '',
                        dateEndRaw: '',
                        venueAddress: '',
                        timeRaw: ''
                    };

                    // 1. Try to find JSON-LD
                    const ldScripts = document.querySelectorAll('script[type="application/ld+json"]');
                    for (const script of ldScripts) {
                        try {
                            const json = JSON.parse(script.textContent);
                            // Sometimes it's a single object, sometimes an array, sometimes @graph
                            let obj = null;
                            if (Array.isArray(json)) {
                                obj = json.find(o => o['@type'] === 'Event' || o['@type'] === 'MusicEvent');
                            } else if (json['@graph']) {
                                obj = json['@graph'].find(o => o['@type'] === 'Event' || o['@type'] === 'MusicEvent');
                            } else if (json['@type'] === 'Event' || json['@type'] === 'MusicEvent') {
                                obj = json;
                            }
                            
                            if (obj) {
                                result.title = obj.name || '';
                                result.description = obj.description || '';
                                if (obj.startDate) result.timeRaw = obj.startDate; // Full ISO date
                                result.dateEndRaw = obj.endDate || '';
                                if (obj.location) {
                                    result.venueAddress = obj.location.address?.streetAddress || obj.location.name || '';
                                }
                                break; 
                            }
                        } catch (e) {}
                    }

                    // 2. DOM Fallbacks / Overrides
                    if (!result.title) {
                        result.title = document.querySelector('h1.event-title')?.textContent?.trim() 
                                    || document.querySelector('h1')?.textContent?.trim() || '';
                    }
                    
                    // Specific Time Selector from user
                    const timeEl = document.querySelector('.event-date-card-time');
                    if (timeEl) {
                        result.timeRaw = timeEl.textContent.trim();
                    }

                    // --- Description Fallbacks ---
                    if (!result.description || result.description.length < 50) {
                        const candidates = [
                            '.js-event-description-body',
                            '.event-description', 
                            '.description-content', 
                            '#event-description', 
                            '.event-text', 
                            '.description', 
                            '.content', 
                            '.js-event-description',
                            '.event-page-content'
                        ];
                        for (const sel of candidates) {
                            const el = document.querySelector(sel);
                            if (el && el.textContent.trim().length > 30) {
                                result.description = el.textContent.trim();
                                break;
                            }
                        }
                    }
                    
                    // If still empty, try to get text from all paragraphs in the main section
                    if (!result.description || result.description.length < 50) {
                        const main = document.querySelector('main, .event-page, #event-page');
                        if (main) {
                            const ps = main.querySelectorAll('p');
                            let text = '';
                            ps.forEach(p => {
                                if (p.textContent.trim().length > 20) text += p.textContent.trim() + '\n';
                            });
                            if (text.length > 50) result.description = text.trim();
                        }
                    }

                    // --- Venue address fallback ---
                    if (!result.venueAddress) {
                        const addrEl = document.querySelector('[itemprop="address"], .venue-address, .location-address');
                        if (addrEl) {
                            result.venueAddress = addrEl.getAttribute('content') || addrEl.textContent.trim();
                        }
                    }

                    return result;
                }
            """)
        except Exception:
            return

        # Assign values based on detected language
        if lang == "ru":
            if data["title"]: event.title_ru = data["title"]
            if data["description"]: event.description_ru = data["description"]
        else:
            if data["title"]: event.title_ro = data["title"]
            if data["description"]: event.description_ro = data["description"]

        if data.get("venueAddress") and not event.address:
            event.address = data["venueAddress"]

        if data.get("dateEndRaw") and not event.date_end:
            dt_end = self._parse_date(data["dateEndRaw"])
            if dt_end:
                event.date_end = dt_end
        
        # Combine date_start with specific time if found
        if data.get("timeRaw") and event.date_start:
            try:
                t_match = re.search(r"(\d{1,2})[:\.](\d{2})", data["timeRaw"])
                if t_match:
                    hour = int(t_match.group(1))
                    minute = int(t_match.group(2))
                    event.date_start = event.date_start.replace(hour=hour, minute=minute)
            except Exception:
                pass

    # ------------------------------------------------------------------

    def _navigate(self, page: Any, url: str) -> bool:
        """Navigate to *url*, returning True on success."""
        try:
            page.goto(url, wait_until="networkidle", timeout=30_000)
            return True
        except Exception:
            self.logger.warning(
                "networkidle timeout for %s, retrying with domcontentloaded…", url
            )
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                page.wait_for_timeout(3_000)
                return True
            except Exception as exc2:
                self.logger.error("Failed to load %s: %s", url, exc2)
                return False

    def _parse_date(self, raw: str) -> datetime | None:
        """
        Parse date strings from schema (ISO) or text (DD.MM.YYYY).
        """
        if not raw:
            return None
        raw = raw.strip()
        
        # 1. ISO 8601
        try:
            dt = datetime.fromisoformat(raw)
            return tz.make_aware(dt) if tz.is_naive(dt) else dt
        except ValueError:
            pass
            
        # 2. DD.MM.YYYY or DD.MM
        m = re.search(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?", raw)
        if m:
            day = int(m.group(1))
            month = int(m.group(2))
            year = int(m.group(3)) if m.group(3) else tz.now().year
            try:
                dt = datetime(year, month, day)
                return tz.make_aware(dt) if tz.is_naive(dt) else dt
            except ValueError:
                pass
                
        return None

    def _parse_price(
        self, low: str, high: str
    ) -> tuple[Decimal | None, Decimal | None, bool]:
        """
        Parse price values from the schema.
        Returns (price_from, price_to, is_free).
        """
        p_low = None
        p_high = None
        is_free = False

        if low:
            try:
                p_low = Decimal(low)
            except InvalidOperation:
                pass

        if high:
            try:
                p_high = Decimal(high)
            except InvalidOperation:
                pass

        if p_low == Decimal("0") and (p_high is None or p_high == Decimal("0")):
            is_free = True

        return p_low, p_high, is_free
