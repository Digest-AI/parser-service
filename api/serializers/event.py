from rest_framework import serializers

from api.models import Event


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = [
            "id",
            "source",
            "external_id",
            "url",
            "title",
            "title_ru",
            "title_ro",
            "description",
            "description_ru",
            "description_ro",
            "category",
            "raw_categories",
            "date_start",
            "date_end",
            "date_raw",
            "venue_name",
            "venue_address",
            "city",
            "price_from",
            "price_to",
            "currency",
            "is_free",
            "image_url",
            "is_active",
            "created_at",
            "updated_at",
            "last_scraped_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class EventListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list endpoints."""

    class Meta:
        model = Event
        fields = [
            "id",
            "source",
            "url",
            "title",
            "title_ru",
            "title_ro",
            "category",
            "date_start",
            "date_raw",
            "venue_name",
            "city",
            "price_from",
            "price_to",
            "currency",
            "is_free",
            "image_url",
        ]
