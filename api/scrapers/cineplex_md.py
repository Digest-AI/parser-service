"""
Cineplex.md scraper.

Extracts movie listings from https://cineplex.md/movies#/
Uses Playwright to navigate the SPA and evaluate JS for data extraction.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Iterator

from django.utils import timezone as tz

from api.scrapers.base import BaseScraper, EventData

logger = logging.getLogger(__name__)

BASE_URL = "https://cineplex.md"


class CineplexMdScraper(BaseScraper):
    """
    Scrapes movies from https://cineplex.md/movies#/ using Playwright.
    """

    source_id = "cineplex_md"
    source_name = "Cineplex"
    source_url = "https://cineplex.md"
    cross_source_dedup = False  # Do not merge with Afisha/iTicket

    def __init__(
        self,
        categories: list[str]
        | None = None,  # Not used for Cineplex, but kept for interface compatibility
        language: str = "ro",
        headless: bool = True,
        max_pages_per_category: int = 1,  # Only one page
        slow_mo: int = 0,
    ):
        super().__init__(language=language)
        self.headless = headless
        self.slow_mo = slow_mo

    def scrape(self) -> Iterator[EventData]:
        """Yield EventData objects for movies."""
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

            url = f"{BASE_URL}/movies#/"
            self.logger.info("Scraping Cineplex movies: %s", url)

            try:
                page.goto(url, wait_until="networkidle", timeout=30_000)
                page.wait_for_selector(".movies_fimls_item", timeout=15_000)

                # Scroll a bit to trigger lazy loading if any
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)

                cards = self._extract_cards(page)
                yield from cards

                self.logger.info("Found %d movies on Cineplex", len(cards))

            except Exception as exc:
                self.logger.error("Failed to load or extract Cineplex: %s", exc)

            finally:
                context.close()
                browser.close()

    def _extract_cards(self, page: Any) -> list[EventData]:
        """Extract all movie cards from the DOM."""
        try:
            raw: list[dict] = page.evaluate("""
                () => {
                    const cards = [];
                    const items = document.querySelectorAll('.movies_blcks');

                    items.forEach(block => {
                        const item = block.querySelector('.movies_fimls_item');
                        if (!item) return;

                        const dataHref = item.getAttribute('data-href') || '';
                        if (!dataHref) return;
                        
                        // Extract external_id from URL path (e.g. /movie-details/UUID)
                        const parts = dataHref.split('/');
                        const externalId = parts[parts.length - 1];

                        const imgEl = item.querySelector('.img-movies');
                        const imageUrl = imgEl ? imgEl.getAttribute('src') : '';

                        const titleEl = item.querySelector('.overlay__title');
                        let title = '';
                        if (titleEl) {
                            title = titleEl.innerHTML.replace(/<br\\s*\\/?>/gi, ' ').trim();
                        }

                        const genreEl = item.querySelector('.overlay__genre');
                        const rawCategory = genreEl ? genreEl.textContent.trim() : '';

                        const dateEl = item.querySelector('.startdate');
                        const startDateRaw = dateEl ? dateEl.textContent.trim() : '';

                        cards.push({
                            externalId,
                            url: 'https://cineplex.md' + dataHref,
                            title,
                            imageUrl: imageUrl.startsWith('http') ? imageUrl : 'https://cineplex.md' + imageUrl,
                            rawCategory,
                            startDateRaw,
                        });
                    });

                    return cards;
                }
            """)
        except Exception as exc:
            self.logger.error("JS card extraction failed: %s", exc)
            return []

        from django.utils.text import slugify

        results: list[EventData] = []
        seen_keys = set()

        for item in raw:
            if not item.get("title") or not item.get("url"):
                continue

            # Parse date "DD-MM-YYYY"
            date_start = None
            date_raw = item.get("startDateRaw", "")
            if date_raw:
                try:
                    dt = datetime.strptime(date_raw, "%d-%m-%Y")
                    dt = tz.make_aware(dt)  # Make it timezone aware
                    date_start = dt
                except ValueError:
                    pass

            # In-memory deduplication by title and date to prevent 2D/3D dupes
            dedup_key = (item["title"].lower().strip(), date_raw)
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            ext_id = item.get("externalId", "")
            slug = slugify(f"cineplex-{ext_id}-{item['title']}")

            results.append(
                EventData(
                    url=item["url"],
                    slug=slug,
                    provider_slug="cineplex_md",
                    provider_name="Cineplex",
                    provider_url="https://cineplex.md",
                    title_ro=item["title"] if self.language == "ro" else "",
                    title_ru=item["title"] if self.language == "ru" else "",
                    external_id=ext_id,
                    categories=["movie"],
                    date_start=date_start,
                    place="Cineplex",
                    city="Chișinău",
                    image_url=item.get("imageUrl", ""),
                    tickets_url=item["url"],
                )
            )

        return results
