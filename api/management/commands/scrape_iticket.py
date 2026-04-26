"""
Django management command: scrape_iticket

Usage
-----
# Scrape the default "all" category
python manage.py scrape_iticket

# Scrape specific categories only
python manage.py scrape_iticket --categories concert teatru

# Limit pages per category
python manage.py scrape_iticket --max-pages 2
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError

from api.scrapers.iticket_md import ALL_CATEGORIES, ITicketMdScraper

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Scrape events from iticket.md and store them in the database."

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
                "Defaults to 'all'."
            ),
        )
        parser.add_argument(
            "--language",
            default="ro",
            choices=["ru", "ro"],
            help="Language version of the site to scrape (default: ro)",
        )
        parser.add_argument(
            "--max-pages",
            type=int,
            default=5,
            metavar="N",
            help="Maximum number of listing pages to scrape per category (default: 5)",
        )
        parser.add_argument(
            "--no-headless",
            action="store_true",
            default=False,
            help="Run the browser in visible (non-headless) mode for debugging",
        )

    def handle(self, *args, **options):
        categories = options["categories"]
        language = options["language"]
        max_pages = options["max_pages"]
        headless = not options["no_headless"]

        self.stdout.write(
            self.style.NOTICE(
                f"Starting iticket.md scraper | "
                f"language={language} | "
                f"categories={categories or 'all'} | "
                f"max_pages={max_pages} | "
                f"headless={headless}"
            )
        )

        try:
            scraper = ITicketMdScraper(
                categories=categories,
                language=language,
                headless=headless,
                max_pages_per_category=max_pages,
            )
            created, updated = scraper.run_and_save()
        except ImportError as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            logger.exception("Scraper error")
            raise CommandError(f"Scraper failed: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created: {created}  |  Updated: {updated}"
            )
        )
