from __future__ import annotations

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import filters, status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from api.models import Event
from api.serializers import EventListSerializer, EventSerializer


class EventPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


@extend_schema_view(
    list=extend_schema(
        summary="List events",
        description="Returns a paginated list of scraped events from Moldova.",
        parameters=[
            OpenApiParameter(
                "category",
                description="Filter by category slug",
                enum=[c[0] for c in Event.Category.choices],
            ),
            OpenApiParameter("source", description="Filter by source (e.g. afisha_md)"),
            OpenApiParameter("city", description="Filter by city"),
            OpenApiParameter("is_free", description="Filter free events (true/false)"),
            OpenApiParameter("date_from", description="Filter events starting after date (YYYY-MM-DD)"),
            OpenApiParameter("date_to", description="Filter events starting before date (YYYY-MM-DD)"),
            OpenApiParameter("q", description="Full-text search in title and description"),
        ],
    ),
    retrieve=extend_schema(summary="Get event details"),
)
class EventViewSet(ReadOnlyModelViewSet):
    """
    Read-only API for querying scraped Moldova events.

    Supports filtering by category, source, city, date range and free status.
    """

    queryset = Event.objects.filter(is_active=True).order_by("-date_start")
    pagination_class = EventPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "title_ru", "title_ro", "description", "venue_name"]
    ordering_fields = ["date_start", "price_from", "created_at"]
    ordering = ["-date_start"]

    def get_serializer_class(self):
        if self.action == "list":
            return EventListSerializer
        return EventSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        # Category filter
        category = params.get("category")
        if category:
            qs = qs.filter(category=category)

        # Source filter
        source = params.get("source")
        if source:
            qs = qs.filter(source=source)

        # City filter
        city = params.get("city")
        if city:
            qs = qs.filter(city__icontains=city)

        # Free filter
        is_free = params.get("is_free")
        if is_free is not None:
            qs = qs.filter(is_free=is_free.lower() in ("true", "1", "yes"))

        # Date range filter
        date_from = params.get("date_from")
        if date_from:
            qs = qs.filter(date_start__date__gte=date_from)

        date_to = params.get("date_to")
        if date_to:
            qs = qs.filter(date_start__date__lte=date_to)

        # Full-text search (in addition to DRF filter backend)
        q = params.get("q")
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(title_ru__icontains=q)
                | Q(title_ro__icontains=q)
                | Q(description__icontains=q)
                | Q(venue_name__icontains=q)
            )

        return qs

    @extend_schema(
        summary="Trigger scrape",
        description=(
            "Immediately starts a synchronous scrape for the given source/category. "
            "⚠️ Runs in the request thread — for production use a Celery task instead."
        ),
        parameters=[
            OpenApiParameter("source", description="Source to scrape (afisha_md, iticket_md, cineplex_md). Default: afisha_md"),
            OpenApiParameter("category", description="Category slug to scrape (default: all)"),
        ],
        responses={200: {"type": "object", "properties": {"created": {"type": "integer"}, "updated": {"type": "integer"}}}},
    )
    @action(detail=False, methods=["post"], url_path="scrape")
    def scrape(self, request: Request) -> Response:
        """POST /events/scrape/ — trigger a synchronous scrape (dev only)."""
        source = request.query_params.get("source", "afisha_md")
        category = request.query_params.get("category")

        try:
            if source == "cineplex_md":
                from api.scrapers.cineplex_md import CineplexMdScraper
                scraper = CineplexMdScraper()
            elif source == "iticket_md":
                from api.scrapers.iticket_md import ALL_CATEGORIES, ITicketMdScraper
                categories = [category] if category and category in ALL_CATEGORIES else ["all"]
                scraper = ITicketMdScraper(categories=categories, max_pages_per_category=1)
            else:
                from api.scrapers.afisha_md import ALL_CATEGORIES, AfishaMdScraper
                categories = [category] if category and category in ALL_CATEGORIES else None
                scraper = AfishaMdScraper(categories=categories, max_pages_per_category=1)

            created, updated = scraper.run_and_save()
        except ImportError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({"source": source, "created": created, "updated": updated})

    @extend_schema(
        summary="Get upcoming events",
        description="Returns events starting from today, ordered by date.",
    )
    @action(detail=False, methods=["get"], url_path="upcoming")
    def upcoming(self, request: Request) -> Response:
        """GET /events/upcoming/ — events from today onward."""
        qs = self.get_queryset().filter(date_start__gte=timezone.now())
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = EventListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = EventListSerializer(qs, many=True)
        return Response(serializer.data)
