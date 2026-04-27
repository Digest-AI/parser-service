from __future__ import annotations

from django.db.models import Count
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import Event


@extend_schema(
    summary="List sources",
    description=(
        "Returns all available event sources (scraped sites) with their display "
        "name and the count of active events from each source."
    ),
    responses={
        200: {
            "type": "object",
            "properties": {
                "sources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "slug": {"type": "string", "example": "afisha_md"},
                            "label": {"type": "string", "example": "Afisha.md"},
                            "count": {"type": "integer", "example": 120},
                        },
                    },
                }
            },
        }
    },
)
class SourceListView(APIView):
    """GET /sources/ — list of all scraped sources with event counts."""

    def get(self, request: Request) -> Response:
        counts: dict[str, int] = {
            row["source"]: row["total"]
            for row in (
                Event.objects.filter(is_active=True)
                .values("source")
                .annotate(total=Count("id"))
            )
        }

        label_map = dict(Event.Source.choices)

        sources = [
            {
                "slug": slug,
                "label": label_map.get(slug, slug),
                "count": counts.get(slug, 0),
            }
            for slug, _label in Event.Source.choices
        ]

        return Response({"sources": sources})
