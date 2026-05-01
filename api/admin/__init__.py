from django.contrib import admin
from api.models import Event, Provider, Category, EventCategory

@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "url")
    search_fields = ("name", "slug")

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("slug", "name_ru", "name_ro")
    search_fields = ("slug", "name_ru", "name_ro")

class EventCategoryInline(admin.TabularInline):
    model = EventCategory
    extra = 1

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title_ru", "provider", "date_start", "city")
    list_filter = ("provider", "city", "categories")
    search_fields = ("title_ru", "title_ro", "description_ru", "description_ro", "external_id")
    # autocomplete_fields = ("provider",) # Removed categories from autocomplete since it's an inline now
    date_hierarchy = "date_start"
    ordering = ("-date_start",)
    inlines = [EventCategoryInline]
    
    fieldsets = (
        ("Basic Info", {
            "fields": ("provider", "slug", "external_id", "url")
        }),
        ("Titles", {
            "fields": ("title_ru", "title_ro")
        }),
        ("Descriptions", {
            "fields": ("description_ru", "description_ro")
        }),
        ("Schedule & Location", {
            "fields": ("date_start", "date_end", "place", "address", "city")
        }),
        ("Price & Tickets", {
            "fields": ("price_from", "price_to", "tickets_url", "image_url")
        }),
    )
