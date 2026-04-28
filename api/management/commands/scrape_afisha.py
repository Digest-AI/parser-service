"""
Django management command: scrape_afisha

Usage
-----
# Scrape all categories (fast mode)
python manage.py scrape_afisha

# Scrape specific categories only
python manage.py scrape_afisha --categories concerte teatru

# Deep mode — visit every event page for full description, address, date_end
python manage.py scrape_afisha --deep

# Run in non-headless mode (visible browser, useful for debugging)
python manage.py scrape_afisha --no-headless

# Limit pages per category
python manage.py scrape_afisha --max-pages 2
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError

from api.scrapers.afisha_md import ALL_CATEGORIES, AfishaMdScraper

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Scrape events from afisha.md and store them in the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--categories",
            nargs="*",
            default=None,
            choices=ALL_CATEGORIES,
            metavar="CATEGORY",
            help=(
                f"Which category slugs to scrape. "
                f"Available: {', '.join(ALL_CATEGORIES)}. "
                "Defaults to all categories."
            ),
        )
        parser.add_argument(
            "--language",
            default="ru",
            choices=["ru", "ro"],
            help="Language version of the site to scrape (default: ru)",
        )
        parser.add_argument(
            "--max-pages",
            type=int,
            default=3,
            metavar="N",
            help="Maximum number of listing pages to scrape per category (default: 3)",
        )
        parser.add_argument(
            "--no-headless",
            action="store_true",
            default=False,
            help="Run the browser in visible (non-headless) mode for debugging",
        )
        parser.add_argument(
            "--deep",
            action="store_true",
            default=False,
            help=(
                "Deep mode: visit each event's detail page to collect full description, "
                "venue address, date_end, and ticket links. Slower but collects maximum data."
            ),
        )

    def handle(self, *args, **options):
        categories = options["categories"]
        language = options["language"]
        max_pages = options["max_pages"]
        headless = not options["no_headless"]
        deep = options["deep"]

        mode_label = "DEEP (full details)" if deep else "FAST (cards only)"
        self.stdout.write(
            self.style.NOTICE(
                f"Starting afisha.md scraper | "
                f"mode={mode_label} | "
                f"language={language} | "
                f"categories={categories or 'ALL'} | "
                f"max_pages={max_pages} | "
                f"headless={headless}"
            )
        )

        try:
            scraper = AfishaMdScraper(
                categories=categories,
                language=language,
                headless=headless,
                max_pages_per_category=max_pages,
                deep=deep,
            )
            created, updated = scraper.run_and_save()
        except ImportError as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            logger.exception("Scraper error")
            raise CommandError(f"Scraper failed: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(f"Done. Created: {created}  |  Updated: {updated}")
        )
