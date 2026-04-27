"""
Base scraper class for all Moldova event scrapers.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Iterator

logger = logging.getLogger(__name__)


@dataclass
class EventData:
    """Normalised event data returned by every scraper."""

    url: str
    title: str
    source: str

    # Optional fields
    external_id: str = ""
    title_ru: str = ""
    title_ro: str = ""
    description: str = ""
    description_ru: str = ""
    description_ro: str = ""
    category: str = "other"
    raw_categories: list[str] = field(default_factory=list)
    date_start: datetime | None = None
    date_end: datetime | None = None
    date_raw: str = ""
    venue_name: str = ""
    venue_address: str = ""
    city: str = "Кишинёв"
    price_from: Decimal | None = None
    price_to: Decimal | None = None
    currency: str = "MDL"
    is_free: bool = False
    image_url: str = ""
    raw_data: dict = field(default_factory=dict)


class BaseScraper(ABC):
    """Abstract base for all event scrapers."""

    source_id: str = ""  # override in subclass

    def __init__(self, language: str = "ru"):
        self.language = language
        self.logger = logging.getLogger(f"scrapers.{self.source_id}")

    @abstractmethod
    def scrape(self) -> Iterator[EventData]:
        """Yield EventData objects one by one."""
        ...

    def run_and_save(self) -> tuple[int, int]:
        """
        Run the scraper and upsert events into the database.

        Playwright runs inside an event loop. Django ORM calls cannot be made
        from inside that same async/greenlet context. We therefore first collect
        *all* EventData objects into a plain list (while the browser is open),
        then close the browser, and only then write to the database.

        Returns (created, updated) counts.
        """
        from django.utils import timezone

        from api.models import Event

        # ---- Phase 1: collect (browser is open here) ----
        all_events: list[EventData] = []
        try:
            for event_data in self.scrape():
                all_events.append(event_data)
        except Exception as exc:
            self.logger.error("Scraper raised an exception: %s", exc, exc_info=True)

        self.logger.info(
            "[%s] Collected %d events. Saving…", self.source_id, len(all_events)
        )

        # ---- Phase 2: save (browser is closed here) ----
        created = 0
        updated = 0
        now = timezone.now()

        import difflib

        for event_data in all_events:
            try:
                defaults = self._to_model_defaults(event_data)
                defaults["last_scraped_at"] = now

                # 1. Check if exact event already exists
                if event_data.external_id:
                    existing = Event.objects.filter(
                        source=event_data.source, external_id=event_data.external_id
                    ).first()
                else:
                    existing = Event.objects.filter(url=event_data.url).first()

                if existing:
                    # Update existing event
                    for k, v in defaults.items():
                        setattr(existing, k, v)
                    existing.save()
                    updated += 1
                    continue

                # 2. Check for cross-source duplicates (fuzzy match by date and title)
                cross_source_match = None
                if getattr(self, "cross_source_dedup", True) and event_data.date_start:
                    same_day_events = Event.objects.filter(
                        date_start__date=event_data.date_start.date()
                    ).exclude(source=event_data.source)

                    for candidate in same_day_events:
                        similarity = difflib.SequenceMatcher(
                            None, event_data.title.lower(), candidate.title.lower()
                        ).ratio()
                        if similarity > 0.7:
                            cross_source_match = candidate
                            break

                if cross_source_match:
                    # Merge with existing event from another source
                    links = (
                        dict(cross_source_match.ticket_links)
                        if cross_source_match.ticket_links
                        else {}
                    )
                    links[event_data.source] = event_data.url
                    cross_source_match.ticket_links = links
                    cross_source_match.save(update_fields=["ticket_links"])
                    updated += 1
                    self.logger.info(
                        "Merged %s with %s (similarity: %.2f)",
                        event_data.url,
                        cross_source_match.url,
                        similarity,
                    )
                    continue

                # 3. No match found, create new event
                defaults["source"] = event_data.source
                if event_data.external_id:
                    defaults["external_id"] = event_data.external_id

                Event.objects.create(**defaults)
                created += 1

            except Exception as exc:
                self.logger.error(
                    "Failed to save event %s: %s", event_data.url, exc, exc_info=True
                )

        self.logger.info(
            "[%s] Finished. Created: %d, Updated: %d", self.source_id, created, updated
        )
        return created, updated

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _to_model_defaults(self, data: EventData) -> dict:
        return {
            "url": data.url,
            "source": data.source,
            "external_id": data.external_id,
            "title": data.title,
            "title_ru": data.title_ru,
            "title_ro": data.title_ro,
            "description": data.description,
            "description_ru": data.description_ru,
            "description_ro": data.description_ro,
            "category": data.category,
            "raw_categories": data.raw_categories,
            "date_start": data.date_start,
            "date_end": data.date_end,
            "date_raw": data.date_raw,
            "venue_name": data.venue_name,
            "venue_address": data.venue_address,
            "city": data.city,
            "price_from": data.price_from,
            "price_to": data.price_to,
            "currency": data.currency,
            "is_free": data.is_free,
            "image_url": data.image_url,
            "raw_data": data.raw_data,
        }
