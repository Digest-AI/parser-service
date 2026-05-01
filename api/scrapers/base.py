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
    slug: str
    provider_slug: str
    provider_name: str
    provider_url: str

    # Optional fields
    external_id: str = ""
    title_ru: str = ""
    title_ro: str = ""
    description_ru: str = ""
    description_ro: str = ""
    categories: list[str] = field(default_factory=list) # Slugs of categories
    date_start: datetime | None = None
    date_end: datetime | None = None
    place: str = ""
    address: str = ""
    city: str = "Кишинёв"
    price_from: Decimal | None = None
    price_to: Decimal | None = None
    image_url: str = ""
    tickets_url: str = ""


class BaseScraper(ABC):
    """Abstract base for all event scrapers."""

    source_id: str = ""  # override in subclass
    source_name: str = ""
    source_url: str = ""
    cross_source_dedup: bool = True  # merge events by title/date across providers

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
        """
        from django.db.models import Q
        from api.models import Event, Provider, Category

        all_events: list[EventData] = []
        try:
            for event_data in self.scrape():
                all_events.append(event_data)
        except Exception as exc:
            self.logger.error("Scraper raised an exception: %s", exc, exc_info=True)

        self.logger.info(
            "[%s] Collected %d events. Saving…", self.source_id, len(all_events)
        )

        created = 0
        updated = 0

        # Ensure Provider exists
        provider, _ = Provider.objects.get_or_create(
            slug=self.source_id,
            defaults={"name": self.source_name or self.source_id, "url": self.source_url}
        )

        for event_data in all_events:
            try:
                defaults = self._to_model_defaults(event_data)
                
                # Fetch/create Categories
                cats = []
                for cat_slug in event_data.categories:
                    cat, _ = Category.objects.get_or_create(
                        slug=cat_slug,
                        defaults={
                            "name_ru": cat_slug.capitalize(),
                            "name_ro": cat_slug.capitalize()
                        }
                    )
                    cats.append(cat)

                # Find existing event
                existing = None
                if event_data.external_id:
                    existing = Event.objects.filter(
                        provider=provider, external_id=event_data.external_id
                    ).first()
                
                if not existing:
                    existing = Event.objects.filter(url=event_data.url).first()

                # Cross-source deduplication: match by normalized title and date
                if not existing and self.cross_source_dedup and event_data.date_start:
                    # Try matching by title_ru or title_ro
                    for title in [event_data.title_ru, event_data.title_ro]:
                        if not title:
                            continue
                        
                        # Find any event from ANY provider with same title and date
                        # We use __iexact for case-insensitivity
                        existing = Event.objects.filter(
                            Q(title_ru__iexact=title) | Q(title_ro__iexact=title),
                            date_start=event_data.date_start
                        ).first()
                        
                        if existing:
                            self.logger.info(
                                "Cross-source match found: '%s' matches existing event '%s'",
                                title, existing.title_ru or existing.title_ro
                            )
                            break

                if existing:
                    # Update (merge non-empty fields)
                    changed = False
                    for k, v in defaults.items():
                        current_val = getattr(existing, k)
                        # Only update if the new value is not None/empty, 
                        # and it differs from the current value.
                        if v is not None and v != "" and v != current_val:
                            setattr(existing, k, v)
                            changed = True
                    
                    if changed:
                        existing.save()
                        existing.categories.set(cats)
                        updated += 1
                else:
                    # Create
                    defaults["provider"] = provider
                    if event_data.external_id:
                        defaults["external_id"] = event_data.external_id

                    new_event = Event.objects.create(**defaults)
                    new_event.categories.set(cats)
                    created += 1

            except Exception as exc:
                self.logger.error(
                    "Failed to save event %s: %s", event_data.url, exc, exc_info=True
                )

        self.logger.info(
            "[%s] Finished. Created: %d, Updated: %d", self.source_id, created, updated
        )
        return created, updated

    def _to_model_defaults(self, data: EventData) -> dict:
        return {
            "slug": data.slug,
            "url": data.url,
            "title_ru": data.title_ru,
            "title_ro": data.title_ro,
            "description_ru": data.description_ru,
            "description_ro": data.description_ro,
            "date_start": data.date_start,
            "date_end": data.date_end,
            "place": data.place,
            "address": data.address,
            "city": data.city,
            "price_from": data.price_from,
            "price_to": data.price_to,
            "image_url": data.image_url,
            "tickets_url": data.tickets_url,
        }
