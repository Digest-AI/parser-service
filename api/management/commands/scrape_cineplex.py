"""
Django management command: scrape_cineplex

Usage
-----
# Scrape movies from Cineplex
python manage.py scrape_cineplex
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError

from api.scrapers.cineplex_md import CineplexMdScraper

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Scrape movies from cineplex.md and store them in the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--language",
            default="ro",
            choices=["ru", "ro"],
            help="Language version of the site to scrape (default: ro)",
        )
        parser.add_argument(
            "--no-headless",
            action="store_true",
            default=False,
            help="Run the browser in visible (non-headless) mode for debugging",
        )

    def handle(self, *args, **options):
        language = options["language"]
        headless = not options["no_headless"]

        self.stdout.write(
            self.style.NOTICE(
                f"Starting cineplex.md scraper | "
                f"language={language} | "
                f"headless={headless}"
            )
        )

        try:
            scraper = CineplexMdScraper(
                language=language,
                headless=headless,
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
