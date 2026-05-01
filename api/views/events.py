from __future__ import annotations

import datetime

from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import filters, status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from api.models import Event
from api.serializers import EventIdsRequestSerializer, EventListSerializer, EventSerializer


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
                description="Filter by category slug (can specify multiple separated by commas or repeating the parameter)",
            ),
            OpenApiParameter(
                "provider",
                description="Filter by provider slug",
            ),
            OpenApiParameter("city", description="Filter by city (partial match)"),
            OpenApiParameter(
                "place", description="Filter by place name (partial match)"
            ),
            OpenApiParameter(
                "date_from", description="Filter events starting from date (YYYY-MM-DD)"
            ),
            OpenApiParameter(
                "date_to", description="Filter events starting before date (YYYY-MM-DD)"
            ),
            OpenApiParameter("price_min", description="Minimum ticket price (MDL)"),
            OpenApiParameter("price_max", description="Maximum ticket price (MDL)"),
            OpenApiParameter(
                "q", description="Full-text search in title, description and place"
            ),
        ],
    ),
    retrieve=extend_schema(summary="Get event details"),
)
class EventViewSet(ReadOnlyModelViewSet):
    """
    Read-only API for querying scraped Moldova events.

    Supports filtering by category, provider, city, date range.
    """

    queryset = Event.objects.filter(is_active=True).select_related("provider").prefetch_related("categories").order_by("-date_start")
    pagination_class = EventPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title_ru", "title_ro", "description_ru", "description_ro", "place"]
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
        raw_categories = params.getlist("category")
        category_slug = self.kwargs.get("category_slug")
        
        categories = []
        for cat in raw_categories:
            categories.extend([c.strip() for c in cat.split(",") if c.strip()])
            
        if category_slug and category_slug not in categories:
            categories.append(category_slug)
            
        if categories:
            qs = qs.filter(categories__slug__in=categories).distinct()

        # Provider filter
        provider = params.get("provider") or params.get("source") # support legacy 'source'
        if provider:
            qs = qs.filter(provider__slug=provider)

        # City filter
        city = self.kwargs.get("city_name") or params.get("city")
        if city:
            qs = qs.filter(city__icontains=city)

        # Place filter
        place = params.get("place") or params.get("venue")
        if place:
            qs = qs.filter(place__icontains=place)

        # Date range filter
        date_from = params.get("date_from")
        if date_from:
            qs = qs.filter(date_start__date__gte=date_from)

        date_to = params.get("date_to")
        if date_to:
            qs = qs.filter(date_start__date__lte=date_to)

        # Price range filter
        price_min = params.get("price_min")
        if price_min:
            try:
                qs = qs.filter(price_from__gte=float(price_min))
            except ValueError:
                pass

        price_max = params.get("price_max")
        if price_max:
            try:
                qs = qs.filter(price_from__lte=float(price_max))
            except ValueError:
                pass

        # Full-text search
        q = params.get("q")
        if q:
            from django.db.models import Q

            qs = qs.filter(
                Q(title_ru__icontains=q)
                | Q(title_ro__icontains=q)
                | Q(description_ru__icontains=q)
                | Q(description_ro__icontains=q)
                | Q(place__icontains=q)
            ).distinct()

        return qs

    @extend_schema(
        summary="Get events by ids",
        description=(
            "Returns active events matching the given primary keys as EventListSerializer "
            "items inside the standard paginated envelope (count, next, previous, results). "
            "Same list filters apply when query parameters are passed (category, provider, etc.). "
            "Unknown or inactive ids are omitted. Order inside results follows the request ids "
            "(duplicates removed). At most 100 ids per body; use page / page_size query params "
            "like other event list endpoints."
        ),
        request=EventIdsRequestSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "count": {"type": "integer"},
                    "next": {"type": "string", "nullable": True},
                    "previous": {"type": "string", "nullable": True},
                    "results": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                },
            }
        },
    )
    @action(detail=False, methods=["post"], url_path="by-ids")
    def by_ids(self, request: Request) -> Response:
        """POST /events/by-ids/ — batch fetch by primary key (paginated)."""
        body = EventIdsRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        raw_ids: list[int] = body.validated_data["ids"]
        seen: set[int] = set()
        ordered_ids: list[int] = []
        for pk in raw_ids:
            if pk not in seen:
                seen.add(pk)
                ordered_ids.append(pk)

        whens = [
            When(pk=pk, then=Value(pos)) for pos, pk in enumerate(ordered_ids)
        ]
        order_expr = Case(*whens, output_field=IntegerField())
        qs = (
            self.get_queryset()
            .filter(pk__in=ordered_ids)
            .annotate(_by_ids_order=order_expr)
            .order_by("_by_ids_order")
        )
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = EventListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = EventListSerializer(qs, many=True)
        return Response(
            {
                "count": len(serializer.data),
                "next": None,
                "previous": None,
                "results": serializer.data,
            }
        )

    @extend_schema(
        summary="Trigger scrape",
        description=(
            "Immediately starts a synchronous scrape for the given source/category. "
            "⚠️ Runs in the request thread — for production use a Celery task instead."
        ),
        parameters=[
            OpenApiParameter(
                "source",
                description="Source to scrape (afisha_md, iticket_md, cineplex_md). Default: afisha_md",
            ),
            OpenApiParameter(
                "category", description="Category slug to scrape (default: all)"
            ),
            OpenApiParameter(
                "deep",
                description=(
                    "Set to 'true' for deep mode: visits each event page for full description, "
                    "venue address and date_end. Much slower but collects maximum data."
                ),
            ),
        ],
        responses={
            200: {
                "type": "object",
                "properties": {
                    "created": {"type": "integer"},
                    "updated": {"type": "integer"},
                },
            }
        },
    )
    @action(detail=False, methods=["post"], url_path="scrape")
    def scrape(self, request: Request) -> Response:
        """POST /events/scrape/ — trigger a synchronous scrape (dev only)."""
        source = request.query_params.get("source", "afisha_md")
        category = request.query_params.get("category")
        deep = request.query_params.get("deep", "").lower() in ("true", "1", "yes")

        try:
            if source == "cineplex_md":
                from api.scrapers.cineplex_md import CineplexMdScraper

                scraper = CineplexMdScraper()
            elif source == "iticket_md":
                from api.scrapers.iticket_md import ALL_CATEGORIES, ITicketMdScraper

                categories = (
                    [category] if category and category in ALL_CATEGORIES else ["all"]
                )
                scraper = ITicketMdScraper(
                    categories=categories, max_pages_per_category=1, deep=deep
                )
            else:
                from api.scrapers.afisha_md import ALL_CATEGORIES, AfishaMdScraper

                categories = (
                    [category] if category and category in ALL_CATEGORIES else None
                )
                scraper = AfishaMdScraper(
                    categories=categories, max_pages_per_category=1, deep=deep
                )

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
        description="Returns events starting from now onward, ordered by date.",
    )
    @action(detail=False, methods=["get"], url_path="upcoming")
    def upcoming(self, request: Request) -> Response:
        """GET /events/upcoming/ — events from now onward."""
        qs = (
            self.get_queryset()
            .filter(date_start__gte=timezone.now())
            .order_by("date_start")
        )
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = EventListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = EventListSerializer(qs, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Get today's events",
        description="Returns all active events scheduled for today.",
    )
    @action(detail=False, methods=["get"], url_path="today")
    def today(self, request: Request) -> Response:
        """GET /events/today/ — events happening today."""
        today = timezone.localdate()
        qs = self.get_queryset().filter(date_start__date=today).order_by("date_start")
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = EventListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = EventListSerializer(qs, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Get this week's events",
        description="Returns all active events scheduled within the current calendar week (Mon–Sun).",
    )
    @action(detail=False, methods=["get"], url_path="this-week")
    def this_week(self, request: Request) -> Response:
        """GET /events/this-week/ — events in the current calendar week."""
        today = timezone.localdate()
        week_start = today - datetime.timedelta(days=today.weekday())  # Monday
        week_end = week_start + datetime.timedelta(days=6)  # Sunday
        qs = (
            self.get_queryset()
            .filter(date_start__date__gte=week_start, date_start__date__lte=week_end)
            .order_by("date_start")
        )
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = EventListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = EventListSerializer(qs, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Get events by date",
        description="Returns all active events on a specific date. Pass `date=YYYY-MM-DD` as a query parameter.",
        parameters=[
            OpenApiParameter(
                "date",
                description="Target date in YYYY-MM-DD format (defaults to today)",
                required=False,
            ),
        ],
    )
    @action(detail=False, methods=["get"], url_path="by-date")
    def by_date(self, request: Request) -> Response:
        """GET /events/by-date/?date=YYYY-MM-DD — events on a specific date."""
        raw_date = request.query_params.get("date")
        if raw_date:
            try:
                target = datetime.date.fromisoformat(raw_date)
            except ValueError:
                return Response(
                    {"error": "Invalid date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            target = timezone.localdate()

        qs = self.get_queryset().filter(date_start__date=target).order_by("date_start")
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = EventListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = EventListSerializer(qs, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Get events scraped on a date",
        description=(
            "Returns active events whose database row was created on the given calendar "
            "day (`created_at`, scrape/import time), using EventListSerializer. "
            "Pass `date=YYYY-MM-DD` (defaults to today in server local timezone)."
        ),
        parameters=[
            OpenApiParameter(
                "date",
                description="Calendar date when the event record was first saved (YYYY-MM-DD)",
                required=False,
            ),
        ],
    )
    @action(detail=False, methods=["get"], url_path="scraped-on")
    def scraped_on(self, request: Request) -> Response:
        """GET /events/scraped-on/?date=YYYY-MM-DD — events first scraped/saved on that day."""
        raw_date = request.query_params.get("date")
        if raw_date:
            try:
                target = datetime.date.fromisoformat(raw_date)
            except ValueError:
                return Response(
                    {"error": "Invalid date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            target = timezone.localdate()

        qs = (
            self.get_queryset()
            .filter(created_at__date=target)
            .order_by("-created_at")
        )
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = EventListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = EventListSerializer(qs, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Get events for the next 7 days",
        description="Returns active events scheduled within the next 7 days (including today).",
    )
    @action(detail=False, methods=["get"], url_path="next-7-days")
    def next_7_days(self, request: Request) -> Response:
        """GET /events/next-7-days/ — events for the next 7 days."""
        today = timezone.localdate()
        end_date = today + datetime.timedelta(days=7)
        qs = (
            self.get_queryset()
            .filter(date_start__date__gte=today, date_start__date__lte=end_date)
            .order_by("date_start")
        )
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = EventListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = EventListSerializer(qs, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Get events for the next 14 days",
        description="Returns active events scheduled within the next 14 days (including today).",
    )
    @action(detail=False, methods=["get"], url_path="next-14-days")
    def next_14_days(self, request: Request) -> Response:
        """GET /events/next-14-days/ — events for the next 14 days."""
        today = timezone.localdate()
        end_date = today + datetime.timedelta(days=14)
        qs = (
            self.get_queryset()
            .filter(date_start__date__gte=today, date_start__date__lte=end_date)
            .order_by("date_start")
        )
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = EventListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = EventListSerializer(qs, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Get events for the next month",
        description="Returns active events scheduled within the next 30 days (including today).",
    )
    @action(detail=False, methods=["get"], url_path="next-month")
    def next_month(self, request: Request) -> Response:
        """GET /events/next-month/ — events for the next 30 days."""
        today = timezone.localdate()
        end_date = today + datetime.timedelta(days=30)
        qs = (
            self.get_queryset()
            .filter(date_start__date__gte=today, date_start__date__lte=end_date)
            .order_by("date_start")
        )
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = EventListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = EventListSerializer(qs, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Get events for the next 3 months",
        description="Returns active events scheduled within the next 90 days (including today).",
    )
    @action(detail=False, methods=["get"], url_path="next-3-months")
    def next_3_months(self, request: Request) -> Response:
        """GET /events/next-3-months/ — events for the next 90 days."""
        today = timezone.localdate()
        end_date = today + datetime.timedelta(days=90)
        qs = (
            self.get_queryset()
            .filter(date_start__date__gte=today, date_start__date__lte=end_date)
            .order_by("date_start")
        )
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = EventListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = EventListSerializer(qs, many=True)
        return Response(serializer.data)
