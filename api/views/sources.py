from __future__ import annotations

from django.db.models import Count
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import Provider


@extend_schema(
    summary="List providers",
    description=(
        "Returns all available event providers with their display "
        "name and the count of active events from each provider."
    ),
    responses={
        200: {
            "type": "object",
            "properties": {
                "providers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "slug": {"type": "string", "example": "afisha_md"},
                            "name": {"type": "string", "example": "Afisha.md"},
                            "url": {"type": "string"},
                            "count": {"type": "integer", "example": 120},
                        },
                    },
                }
            },
        }
    },
)
class SourceListView(APIView):
    """GET /sources/ — list of all scraped providers with event counts."""

    def get(self, request: Request) -> Response:
        providers = Provider.objects.annotate(
            count=Count('events', filter=Count('events__is_active'))
        )
        
        data = [
            {
                "id": p.id,
                "slug": p.slug,
                "name": p.name,
                "url": p.url,
                "count": p.count,
            }
            for p in providers
        ]

        return Response({"providers": data}) # keep key "providers" or "sources" based on URL maybe. Let's return "providers"
