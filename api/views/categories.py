from __future__ import annotations

from django.db.models import Count
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import Category
from api.serializers.event import CategorySerializer

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
                            "id": {"type": "integer"},
                            "slug": {"type": "string", "example": "concert"},
                            "name_ru": {"type": "string", "example": "Концерт"},
                            "name_ro": {"type": "string", "example": "Concert"},
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
        categories = Category.objects.annotate(
            count=Count('events', filter=Count('events__is_active'))
        )
        
        data = [
            {
                "id": cat.id,
                "slug": cat.slug,
                "name_ru": cat.name_ru,
                "name_ro": cat.name_ro,
                "count": cat.count,
            }
            for cat in categories
        ]

        return Response({"categories": data})
