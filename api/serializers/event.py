from rest_framework import serializers

from api.models import Event, Provider, Category


class ProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Provider
        fields = ["id", "slug", "name", "url"]


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "slug", "name_ru", "name_ro"]


class EventSerializer(serializers.ModelSerializer):
    provider = ProviderSerializer(read_only=True)
    categories = CategorySerializer(many=True, read_only=True)

    class Meta:
        model = Event
        fields = [
            "id",
            "slug",
            "provider",
            "external_id",
            "url",
            "title_ru",
            "title_ro",
            "description_ru",
            "description_ro",
            "categories",
            "date_start",
            "date_end",
            "address",
            "place",
            "city",
            "price_from",
            "price_to",
            "image_url",
            "tickets_url",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class EventListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list endpoints."""
    provider = ProviderSerializer(read_only=True)
    categories = CategorySerializer(many=True, read_only=True)

    class Meta:
        model = Event
        fields = [
            "id",
            "slug",
            "provider",
            "url",
            "title_ru",
            "title_ro",
            "categories",
            "date_start",
            "address",
            "place",
            "city",
            "price_from",
            "price_to",
            "image_url",
        ]
