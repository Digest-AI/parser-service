from __future__ import annotations

from django.db.models import Count
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import Event


@extend_schema(
    summary="List cities",
    description=(
        "Returns all available cities where events are happening, "
        "along with the count of active events in each city."
    ),
    responses={
        200: {
            "type": "object",
            "properties": {
                "cities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "example": "Кишинёв"},
                            "count": {"type": "integer", "example": 150},
                        },
                    },
                }
            },
        }
    },
)
class CityListView(APIView):
    """GET /cities/ — list of all cities with event counts."""

    def get(self, request: Request) -> Response:
        # Count active events per city
        cities_qs = (
            Event.objects.filter(is_active=True, city__isnull=False)
            .exclude(city="")
            .values("city")
            .annotate(total=Count("id"))
            .order_by("-total")
        )

        cities = [
            {
                "name": row["city"],
                "count": row["total"],
            }
            for row in cities_qs
        ]

        return Response({"cities": cities})
