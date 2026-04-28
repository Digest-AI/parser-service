"""
Django management command: scrape_all

Runs all scrapers (Afisha.md, iTicket.md, Cineplex.md) in sequence.

Usage
-----
# Fast mode — scrape cards only (default)
python manage.py scrape_all

# Deep mode — visit every event page for full description, address, date_end
python manage.py scrape_all --deep

# Skip specific sources
python manage.py scrape_all --skip cineplex

# Limit pages per category (applies to Afisha & iTicket)
python manage.py scrape_all --max-pages 2

# Run with visible browser (debug)
python manage.py scrape_all --no-headless
"""

from __future__ import annotations

import logging
import time

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

ALL_SOURCES = ["afisha", "iticket", "cineplex"]


class Command(BaseCommand):
    help = "Run all event scrapers (Afisha, iTicket, Cineplex) in sequence."

    def add_arguments(self, parser):
        parser.add_argument(
            "--deep",
            action="store_true",
            default=False,
            help=(
                "Deep mode: visit each event's detail page to collect full description, "
                "venue address, date_end and more. Much slower but collects maximum data."
            ),
        )
        parser.add_argument(
            "--skip",
            nargs="*",
            default=[],
            choices=ALL_SOURCES,
            metavar="SOURCE",
            help=f"Sources to skip. Available: {', '.join(ALL_SOURCES)}.",
        )
        parser.add_argument(
            "--max-pages",
            type=int,
            default=5,
            metavar="N",
            help="Maximum listing pages per category for Afisha/iTicket (default: 5).",
        )
        parser.add_argument(
            "--no-headless",
            action="store_true",
            default=False,
            help="Run browsers in visible mode (useful for debugging).",
        )

    def handle(self, *args, **options):
        deep: bool = options["deep"]
        skip: list[str] = options["skip"] or []
        max_pages: int = options["max_pages"]
        headless: bool = not options["no_headless"]

        mode_label = "DEEP (full details)" if deep else "FAST (cards only)"
        sources_to_run = [s for s in ALL_SOURCES if s not in skip]

        self.stdout.write(
            self.style.NOTICE(
                f"\n{'=' * 55}\n"
                f"  scrape_all  |  mode={mode_label}\n"
                f"  sources: {', '.join(sources_to_run)}\n"
                f"  max_pages={max_pages}  headless={headless}\n"
                f"{'=' * 55}\n"
            )
        )

        totals = {"created": 0, "updated": 0, "errors": 0}
        wall_start = time.monotonic()

        # ── Afisha.md ──────────────────────────────────────────────────
        if "afisha" not in skip:
            self._run_source(
                label="Afisha.md",
                totals=totals,
                builder=lambda: self._build_afisha(max_pages, headless, deep),
            )

        # ── iTicket.md ────────────────────────────────────────────────
        if "iticket" not in skip:
            self._run_source(
                label="iTicket.md",
                totals=totals,
                builder=lambda: self._build_iticket(max_pages, headless, deep),
            )

        # ── Cineplex.md ───────────────────────────────────────────────
        if "cineplex" not in skip:
            self._run_source(
                label="Cineplex.md",
                totals=totals,
                builder=lambda: self._build_cineplex(headless),
            )

        # ── Summary ───────────────────────────────────────────────────
        elapsed = time.monotonic() - wall_start
        status = self.style.SUCCESS if totals["errors"] == 0 else self.style.WARNING
        self.stdout.write(
            status(
                f"\n{'=' * 55}\n"
                f"  ALL DONE  in {elapsed:.1f}s\n"
                f"  Created : {totals['created']}\n"
                f"  Updated : {totals['updated']}\n"
                f"  Errors  : {totals['errors']}\n"
                f"{'=' * 55}\n"
            )
        )

    # ------------------------------------------------------------------
    # Source builders
    # ------------------------------------------------------------------

    def _build_afisha(self, max_pages: int, headless: bool, deep: bool):
        from api.scrapers.afisha_md import AfishaMdScraper

        return AfishaMdScraper(
            headless=headless,
            max_pages_per_category=max_pages,
            deep=deep,
        )

    def _build_iticket(self, max_pages: int, headless: bool, deep: bool):
        from api.scrapers.iticket_md import ITicketMdScraper

        return ITicketMdScraper(
            categories=["all"],
            headless=headless,
            max_pages_per_category=max_pages,
            deep=deep,
        )

    def _build_cineplex(self, headless: bool):
        from api.scrapers.cineplex_md import CineplexMdScraper

        return CineplexMdScraper(headless=headless)

    # ------------------------------------------------------------------
    # Runner helper
    # ------------------------------------------------------------------

    def _run_source(self, label: str, totals: dict, builder) -> None:
        self.stdout.write(self.style.HTTP_INFO(f"\n▶  {label} …"))
        t0 = time.monotonic()
        try:
            scraper = builder()
            created, updated = scraper.run_and_save()
            elapsed = time.monotonic() - t0
            totals["created"] += created
            totals["updated"] += updated
            self.stdout.write(
                self.style.SUCCESS(
                    f"   ✓ {label}: created={created}  updated={updated}  ({elapsed:.1f}s)"
                )
            )
        except ImportError as exc:
            totals["errors"] += 1
            self.stdout.write(
                self.style.ERROR(f"   ✗ {label}: missing dependency — {exc}")
            )
        except Exception as exc:
            totals["errors"] += 1
            logger.exception("Scraper error: %s", label)
            self.stdout.write(self.style.ERROR(f"   ✗ {label}: {exc}"))
