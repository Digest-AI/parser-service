"""
Afisha.md scraper.

Strategy (v2 — fast card extraction)
--------------------------------------
All the data we need is already rendered in the event-grid cards on the
listing page itself:

    <figure class="...card...">
      <a class="...cardLink" href="/ru/events/{category}/{id}/{slug}">
        <img class="...cardImage" src="https://...">
        <div class="...variant-price">500 MDL</div>
        <span class="...cardText">26 апреля</span>     ← date
        <span class="...cardText">Teatrul Geneza Art</span>  ← venue
        <h3 class="...cardTitle">AMEN 26.04.2026</h3>
      </a>
    </figure>

So we:
  1. Load each category listing page with Playwright (JS must render the grid).
  2. Extract all card data from the DOM — no individual-event page visits needed.
  3. Yield EventData objects.

This is 10–20× faster than the previous "visit every event page" approach.
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

BASE_URL = "https://afisha.md"

# Mapping from afisha category URL slugs to our internal categories
CATEGORY_MAP: dict[str, str] = {
    "concerte": "concert",
    "teatru": "theatre",
    "movie": "movie",
    "sport-events": "sport",
    "party": "party",
    "for-kids": "kids",
    "trainings": "training",
    "free": "free",
    "performance": "theatre",
    "other": "other",
    "chisinau-arena": "concert",
    "afisha-recomanda": "other",
    "top-10": "other",
    "evenimente-culturale": "other",
}

# All public category slugs to scrape by default
ALL_CATEGORIES: list[str] = [
    "concerte",
    "teatru",
    "movie",
    "sport-events",
    "party",
    "for-kids",
    "trainings",
    "free",
    "performance",
    "other",
    "chisinau-arena",
    "afisha-recomanda",
    "top-10",
    "evenimente-culturale",
]

# Matches individual-event URLs: /lang/events/{category}/{numeric-id}/{slug}
_EVENT_URL_RE = re.compile(
    r"https://afisha\.md/[a-z]{2}/events/[^/]+/(\d+)/",
    re.IGNORECASE,
)

# Russian month names → month numbers
_RU_MONTHS: dict[str, int] = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}
# Romanian month names
_RO_MONTHS: dict[str, int] = {
    "ianuarie": 1,
    "februarie": 2,
    "martie": 3,
    "aprilie": 4,
    "mai": 5,
    "iunie": 6,
    "iulie": 7,
    "august": 8,
    "septembrie": 9,
    "octombrie": 10,
    "noiembrie": 11,
    "decembrie": 12,
}


# ---------------------------------------------------------------------------
# Main scraper class
# ---------------------------------------------------------------------------


class AfishaMdScraper(BaseScraper):
    """
    Scrapes events from https://afisha.md using Playwright (headless browser).

    Requirements
    ------------
    ::
        pip install playwright
        playwright install chromium

    Usage
    -----
    ::
        from api.scrapers.afisha_md import AfishaMdScraper

        scraper = AfishaMdScraper(categories=["concerte", "teatru"])
        created, updated = scraper.run_and_save()
    """

    source_id = "afisha_md"
    source_name = "Afisha.md"
    source_url = "https://afisha.md"

    def __init__(
        self,
        categories: list[str] | None = None,
        language: str = "ru",
        headless: bool = True,
        max_pages_per_category: int = 3,
        slow_mo: int = 0,
        deep: bool = False,
    ):
        super().__init__(language=language)
        self.categories = categories or ALL_CATEGORIES
        self.headless = headless
        self.max_pages_per_category = max_pages_per_category
        self.slow_mo = slow_mo
        self.deep = deep

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

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
                locale="ru-RU",
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()
            page.set_extra_http_headers({"Accept-Language": "ru-RU,ru;q=0.9"})

            # Track already-yielded URLs across categories (navigation links
            # duplicate events between listing pages)
            seen_urls: set[str] = set()

            try:
                for category in self.categories:
                    yield from self._scrape_category(page, category, seen_urls)
            finally:
                context.close()
                browser.close()

    # ------------------------------------------------------------------
    # Category listing
    # ------------------------------------------------------------------

    def _scrape_category(
        self, page: Any, category: str, seen_urls: set[str]
    ) -> Iterator[EventData]:
        """Load listing pages for *category* and yield EventData from cards."""
        base_url = f"{BASE_URL}/{self.language}/events/{category}"
        self.logger.info("Scraping category: %s (deep=%s)", base_url, self.deep)

        for page_num in range(1, self.max_pages_per_category + 1):
            url = base_url if page_num == 1 else f"{base_url}?page={page_num}"

            if not self._navigate(page, url):
                break

            # Wait for the events grid to appear
            try:
                page.wait_for_selector(
                    "[class*='eventsGrid'], [class*='eventsList'], figure[class*='card']",
                    timeout=10_000,
                )
            except Exception:
                self.logger.warning("Events grid not found on %s", url)
                break

            cards = self._extract_cards(page, category)
            new_cards = [c for c in cards if c.url not in seen_urls]

            for card in new_cards:
                seen_urls.add(card.url)
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

            if not cards or not self._has_next_page(page):
                break

    # ------------------------------------------------------------------
    # Card extraction — the core of the new fast approach
    # ------------------------------------------------------------------

    def _extract_cards(self, page: Any, category: str) -> list[EventData]:
        """
        Extract all event cards from the current listing page DOM.

        Targets the structure shared by the user:
            figure[class*='card'] > a[class*='cardLink']
              img[class*='cardImage']          → image_url
              [class*='variant-price']         → price label
              span[class*='cardText']:first    → date string
              span[class*='cardText']:last     → venue name
              h3[class*='cardTitle']           → title
        """
        try:
            raw: list[dict] = page.evaluate(r"""
                () => {
                    const results = [];
                    
                    // 1. Try to extract from __NEXT_DATA__ for accurate time/id
                    try {
                        const nextData = document.getElementById('__NEXT_DATA__');
                        if (nextData) {
                            const json = JSON.parse(nextData.textContent);
                            const events = json.props?.pageProps?.events || [];
                            
                            events.forEach(ev => {
                                const externalId = String(ev.id);
                                // Construct URL: /ru/events/{category}/{id}/{slug}
                                const lang = document.documentElement.lang || 'ru';
                                const url = `https://afisha.md/${lang}/events/${ev.category?.slug || 'other'}/${externalId}/${ev.slug}`;
                                
                                results.push({
                                    url,
                                    externalId,
                                    title: ev.title || '',
                                    imageUrl: ev.image || '',
                                    priceRaw: ev.price_label || '',
                                    // Use ISO date from JSON for perfect accuracy (no 03:00 issues)
                                    dateIso: ev.date || '', 
                                    venue: ev.venue?.title || '',
                                    description: ev.description || '' // Sometimes available in JSON
                                });
                            });
                            
                            if (results.length > 0) return results;
                        }
                    } catch (e) {
                        console.error("NextData parse failed", e);
                    }

                    // 2. DOM Fallback
                    const figures = document.querySelectorAll("figure[class*='card']");
                    figures.forEach(fig => {
                        const link = fig.querySelector("a[class*='cardLink']");
                        if (!link) return;

                        const href = link.getAttribute('href') || '';
                        const url = href.startsWith('http')
                            ? href
                            : 'https://afisha.md' + href;

                        if (!/\/\d+\//.test(href)) return;

                        const img  = fig.querySelector("img[class*='cardImage']");
                        const priceLbl = fig.querySelector("[class*='variant-price']");
                        const titleEl  = fig.querySelector("h3[class*='cardTitle']");
                        const textSpans = fig.querySelectorAll("span[class*='cardText']");

                        const dateText  = textSpans[0]?.textContent?.trim() || '';
                        const venueText = textSpans[1]?.textContent?.trim() || '';
                        const idMatch = href.match(/\/(\d+)\//);

                        results.push({
                            url,
                            externalId: idMatch ? idMatch[1] : '',
                            title:      titleEl?.textContent?.trim() || '',
                            imageUrl:   img?.src || img?.getAttribute('data-src') || '',
                            priceRaw:   priceLbl?.textContent?.trim() || '',
                            dateRaw:    dateText,
                            venue:      venueText,
                        });
                    });

                    return results;
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
            price_from, price_to, is_free = self._parse_price(item.get("priceRaw", ""))
            
            # Use dateIso if available, else dateRaw
            if item.get("dateIso"):
                date_start = self._parse_date_ru(item["dateIso"])
            else:
                date_start = self._parse_date_ru(item.get("dateRaw", ""))
            
            ext_id = item.get("externalId", "")
            slug = slugify(f"afisha-{ext_id}-{item['title']}")

            results.append(
                EventData(
                    url=item["url"],
                    slug=slug,
                    provider_slug="afisha_md",
                    provider_name="Afisha.md",
                    provider_url="https://afisha.md",
                    title_ru=item["title"] if self.language == "ru" else "",
                    title_ro=item["title"] if self.language == "ro" else "",
                    description_ru=item.get("description", "") if self.language == "ru" else "",
                    description_ro=item.get("description", "") if self.language == "ro" else "",
                    external_id=ext_id,
                    categories=[CATEGORY_MAP.get(category, "other")],
                    date_start=date_start,
                    place=item.get("venue", ""),
                    city="Кишинёв",
                    price_from=price_from,
                    price_to=price_to,
                    image_url=item.get("imageUrl", ""),
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
        current_url = event.url
        # Afisha URLs: https://afisha.md/ru/events/... or https://afisha.md/ro/events/...
        
        if "/ru/" in current_url:
            ru_url = current_url
            ro_url = current_url.replace("/ru/", "/ro/")
        elif "/ro/" in current_url:
            ro_url = current_url
            ru_url = current_url.replace("/ro/", "/ru/")
        else:
            # Fallback if no lang prefix
            ru_url = current_url
            ro_url = current_url

        # 1. Fetch current
        self._enrich_from_page(page, event, current_url)
        
        # 2. Fetch alternate
        alt_url = ro_url if current_url == ru_url else ru_url
        if alt_url != current_url:
            self._enrich_from_page(page, event, alt_url)

        return event

    def _enrich_from_page(self, page: Any, event: EventData, url: str) -> None:
        """Helper to extract localized data from a single afisha detail page."""
        if not self._navigate(page, url):
            return

        lang = "ru" if "/ru/" in url else "ro"

        try:
            page.wait_for_selector("[class*='eventPage'], [class*='event-page'], main", timeout=5_000)
        except Exception:
            pass

        try:
            data: dict = page.evaluate(r"""
                () => {
                    const result = {
                        title: '',
                        description: '',
                        venueAddress: '',
                        dateEndRaw: '',
                        timeRaw: ''
                    };

                    // 1. Try to find JSON-LD (most reliable for title/desc/time)
                    const ldScripts = document.querySelectorAll('script[type="application/ld+json"]');
                    for (const script of ldScripts) {
                        try {
                            const json = JSON.parse(script.textContent);
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
                                if (obj.startDate) result.timeRaw = obj.startDate; 
                                result.dateEndRaw = obj.endDate || '';
                                if (obj.location) {
                                    result.venueAddress = obj.location.address?.streetAddress || obj.location.name || '';
                                }
                                break;
                            }
                        } catch (e) {}
                    }

                    // 2. DOM Fallbacks
                    if (!result.title) {
                        result.title = document.querySelector('h1')?.textContent?.trim() || '';
                    }
                    
                    if (!result.description || result.description.length < 50) {
                        const descSelectors = [
                            '[class*="EventDescription_description"]', '.DescriptionBlock_description__text',
                            '[class*="eventDescription"]', '[class*="description"]',
                            '[class*="eventText"]', '[itemprop="description"]',
                            'article p', 'h3.p1', 'p.p1'
                        ];
                        for (const sel of descSelectors) {
                            const els = document.querySelectorAll(sel);
                            let combinedText = '';
                            els.forEach(el => {
                                if (el.textContent.trim().length > 10) {
                                    combinedText += el.textContent.trim() + '\n';
                                }
                            });
                            if (combinedText.length > 30) {
                                result.description = combinedText.trim();
                                break;
                            }
                        }
                    }

                    if (!result.venueAddress) {
                        const addrSelectors = ['[class*="eventAddress"]', '[class*="address"]', '[itemprop="address"]'];
                        for (const sel of addrSelectors) {
                            const el = document.querySelector(sel);
                            if (el && el.textContent.trim()) {
                                result.venueAddress = el.textContent.trim();
                                break;
                            }
                        }
                    }
                    
                    if (!result.timeRaw) {
                        // User's suggested selector
                        const labelEl = document.querySelector('[class*="detailLabel"]');
                        if (labelEl && labelEl.textContent.includes(':')) {
                            result.timeRaw = labelEl.textContent.trim();
                        }
                    }
                    
                    if (!result.timeRaw) {
                        // Try to find time in the sidebar or main content
                        const text = document.body.innerText;
                        // Look for patterns like "20:00" or "в 20:00"
                        const timeMatch = text.match(/(?:в\s+)?(\d{2}:\d{2})/);
                        if (timeMatch) result.timeRaw = timeMatch[1];
                    }

                    return result;
                }
            """)
        except Exception:
            return

        if lang == "ru":
            if data["title"]: event.title_ru = data["title"]
            if data["description"]: event.description_ru = data["description"]
        else:
            if data["title"]: event.title_ro = data["title"]
            if data["description"]: event.description_ro = data["description"]

        if data.get("venueAddress") and not event.address:
            event.address = data["venueAddress"]

        if data.get("dateEndRaw") and not event.date_end:
            dt_end = self._parse_date_ru(data["dateEndRaw"])
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
    # Navigation helper
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

    def _has_next_page(self, page: Any) -> bool:
        """Return True if a non-disabled 'next page' control is present."""
        try:
            return page.evaluate("""
                () => {
                    const sel = [
                        'a[aria-label="Next"]',
                        'button[aria-label="Next"]',
                        '[class*="paginat"] [class*="next"]:not([disabled])',
                        '[class*="next"]:not([disabled]):not([class*="disabled"])',
                    ].join(', ');
                    const el = document.querySelector(sel);
                    if (!el) return false;
                    if (el.hasAttribute('disabled')) return false;
                    if (el.classList.toString().includes('disabled')) return false;
                    return true;
                }
            """)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    def _parse_date_ru(self, raw: str) -> datetime | None:
        """
        Parse Russian/Romanian short date strings like:
            "26 апреля"        → current-year date (timezone-aware)
            "2 мая"
            "26 апреля, 19:00"
        Also handles ISO strings.
        """
        if not raw:
            return None
        raw = raw.strip()

        def _aware(dt: datetime) -> datetime:
            """Make a naive datetime timezone-aware using Django's active TZ."""
            return tz.make_aware(dt) if tz.is_naive(dt) else dt

        # ISO first: "2026-04-26T18:00" or "2026-04-26"
        m = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})", raw)
        if m:
            try:
                return _aware(datetime.fromisoformat(m.group(1)))
            except ValueError:
                pass
        m = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
        if m:
            try:
                return _aware(datetime.fromisoformat(m.group(1)))
            except ValueError:
                pass

        # "26 апреля" / "2 мая" patterns
        m = re.search(r"(\d{1,2})\s+([а-яёА-ЯЁa-zA-Z]+)", raw, re.IGNORECASE)
        if m:
            day = int(m.group(1))
            month_name = m.group(2).lower()
            month = _RU_MONTHS.get(month_name) or _RO_MONTHS.get(month_name)
            if month:
                now = tz.now()
                year = now.year
                try:
                    dt = datetime(year, month, day)
                    # If date already passed this year → bump to next year
                    if _aware(dt) < now.replace(
                        hour=0, minute=0, second=0, microsecond=0
                    ):
                        dt = datetime(year + 1, month, day)
                    # Extract optional time "19:00"
                    t = re.search(r"(\d{1,2}):(\d{2})", raw)
                    if t:
                        dt = dt.replace(hour=int(t.group(1)), minute=int(t.group(2)))
                    return _aware(dt)
                except ValueError:
                    pass

        # "31.12.2024"
        m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", raw)
        if m:
            try:
                return _aware(
                    datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                )
            except ValueError:
                pass

        return None

    def _parse_price(self, raw: str) -> tuple[Decimal | None, Decimal | None, bool]:
        """
        Parse price strings like:
            "500 MDL"        → (500, None, False)
            "от 100 MDL"     → (100, None, False)
            "от 100 до 500"  → (100, 500, False)
            "1 200 MDL"      → (1200, None, False)
            "Бесплатно"      → (0,   None, True)
        """
        if not raw:
            return None, None, False

        lower = raw.lower().strip()
        
        # 1. Check for free entries using strict word boundaries
        free_patterns = [r'\bбесплатно\b', r'\bfree\b', r'\bgratuit\b', r'\b0\s*mdl\b']
        for p in free_patterns:
            if re.search(p, lower):
                return Decimal("0"), None, True

        # 2. Extract all numbers, handling thousand separators (space or \u202f)
        # This regex matches: 500, 1 200, 100.50, 100,50
        num_pattern = r"(\d+(?:[\s\u202f]\d{3})*(?:[.,]\d+)?)"
        numbers = re.findall(num_pattern, raw)
        
        decimals: list[Decimal] = []
        for n in numbers:
            # Normalize number format for Decimal
            cleaned = n.replace("\u202f", "").replace(" ", "").replace(",", ".").strip()
            if not cleaned:
                continue
            try:
                decimals.append(Decimal(cleaned))
            except InvalidOperation:
                pass

        if not decimals:
            return None, None, False
            
        if len(decimals) == 1:
            return decimals[0], None, False
            
        # If there are multiple numbers (e.g., "from 100 to 500"), 
        # first is 'from', last is 'to'.
        return decimals[0], decimals[-1], False
