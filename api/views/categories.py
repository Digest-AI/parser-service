from __future__ import annotations

from django.db.models import Count
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import Event


@extend_schema(
    summary="List categories",
    description=(
        "Returns all available event categories with their display name and "
        "the count of active events in each category."
    ),
    responses={
        200: {
            "type": "object",
            "properties": {
                "categories": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "slug": {"type": "string", "example": "concert"},
                            "label": {"type": "string", "example": "Концерт"},
                            "count": {"type": "integer", "example": 42},
                        },
                    },
                }
            },
        }
    },
)
class CategoryListView(APIView):
    """GET /categories/ — list of all categories with event counts."""

    def get(self, request: Request) -> Response:
        # Count active events per category
        counts: dict[str, int] = {
            row["category"]: row["total"]
            for row in (
                Event.objects.filter(is_active=True)
                .values("category")
                .annotate(total=Count("id"))
            )
        }

        label_map = dict(Event.Category.choices)

        categories = [
            {
                "slug": slug,
                "label": label_map.get(slug, slug),
                "count": counts.get(slug, 0),
            }
            for slug, _label in Event.Category.choices
        ]

        return Response({"categories": categories})
