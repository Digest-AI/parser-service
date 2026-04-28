"""
iTicket.md scraper.

Extracts events directly from the listing cards.
iTicket provides excellent schema.org/Event metadata directly in the DOM,
which makes extraction highly reliable.

Pagination is handled via `?page=X`.
"""

from __future__ import annotations

import logging
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
        Visit the individual event page and enrich *event* with:
        - Full description (RO or RU depending on language)
        - Venue address (full, not just name)
        - date_end
        - og:image fallback
        """
        if not self._navigate(page, event.url):
            return event

        try:
            page.wait_for_selector(
                ".event-page, .event-detail, [itemprop='description'], main",
                timeout=8_000,
            )
        except Exception:
            self.logger.debug("Detail page selector not found for %s", event.url)

        try:
            details: dict = page.evaluate("""
                () => {
                    // --- Description (prefer schema.org, fallback to visible text) ---
                    let description = '';
                    const schemDesc = document.querySelector('[itemprop="description"]');
                    if (schemDesc) {
                        description = schemDesc.getAttribute('content') ||
                                      schemDesc.textContent.trim();
                    }
                    if (!description) {
                        const candidates = [
                            '.event-description', '.description',
                            '.event-content', '.event-text',
                            'article p',
                        ];
                        for (const sel of candidates) {
                            const el = document.querySelector(sel);
                            if (el && el.textContent.trim().length > 20) {
                                description = el.textContent.trim();
                                break;
                            }
                        }
                    }

                    // --- Full venue address ---
                    let venueAddress = '';
                    const addrEl = document.querySelector(
                        '[itemprop="address"], .venue-address, .event-address, .location-address'
                    );
                    if (addrEl) {
                        venueAddress = addrEl.getAttribute('content') ||
                                       addrEl.textContent.trim();
                    }

                    // --- Date end ---
                    let dateEndRaw = '';
                    const endEl = document.querySelector('[itemprop="endDate"]');
                    if (endEl) {
                        dateEndRaw = endEl.getAttribute('content') || endEl.textContent.trim();
                    }

                    // --- OG image fallback ---
                    let imageUrl = '';
                    const ogImg = document.querySelector('meta[property="og:image"]');
                    if (ogImg) imageUrl = ogImg.getAttribute('content') || '';

                    return { description, venueAddress, dateEndRaw, imageUrl };
                }
            """)
        except Exception as exc:
            self.logger.warning("Detail extraction failed for %s: %s", event.url, exc)
            return event

        if details.get("description"):
            if self.language == "ro":
                event.description_ro = details["description"]
            else:
                event.description_ru = details["description"]

        if details.get("venueAddress") and not event.address:
            event.address = details["venueAddress"]

        if details.get("imageUrl") and not event.image_url:
            event.image_url = details["imageUrl"]

        if details.get("dateEndRaw"):
            date_end = self._parse_date(details["dateEndRaw"])
            if date_end:
                event.date_end = date_end

        self.logger.debug("Enriched: %s", event.url)
        return event

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
        Parse ISO 8601 date strings from schema.org:
        e.g., "2026-05-03T11:00:00+03:00"
        """
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw)
            # Make it aware using Django TZ if it's naive (fromisoformat preserves TZ if present)
            if tz.is_naive(dt):
                return tz.make_aware(dt)
            return dt
        except ValueError:
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
