from django.contrib import admin

from api.models import Category, Event, EventCategory, Provider


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ("id", "slug", "name", "url")
    search_fields = ("slug", "name")
    ordering = ("slug",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "slug", "name_ru", "name_ro")
    search_fields = ("slug", "name_ru", "name_ro")
    ordering = ("slug",)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "slug",
        "title_ru",
        "provider",
        "city",
        "date_start",
        "is_active",
    )
    list_filter = ("is_active", "provider", "city")
    search_fields = ("slug", "title_ru", "title_ro", "external_id", "place")
    autocomplete_fields = ("provider",)
    readonly_fields = ("created_at",)
    date_hierarchy = "date_start"
    ordering = ("-date_start",)


@admin.register(EventCategory)
class EventCategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "event", "category")
    list_filter = ("category",)
    autocomplete_fields = ("event", "category")
