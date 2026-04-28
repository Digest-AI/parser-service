from django.db import models
from api.models.provider import Provider
from api.models.category import Category
from api.models.event_category import EventCategory

class Event(models.Model):
    """Represents a scraped event."""
    slug = models.SlugField(max_length=256, unique=True, db_index=True)
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name="events")
    external_id = models.CharField(max_length=128, blank=True, db_index=True)
    url = models.URLField(max_length=512, unique=True)

    title_ru = models.CharField(max_length=512, blank=True)
    title_ro = models.CharField(max_length=512, blank=True)
    description_ru = models.TextField(blank=True)
    description_ro = models.TextField(blank=True)

    date_start = models.DateTimeField(null=True, blank=True, db_index=True)
    date_end = models.DateTimeField(null=True, blank=True)

    address = models.CharField(max_length=512, blank=True)
    place = models.CharField(max_length=256, blank=True)
    city = models.CharField(max_length=128, default="Кишинёв", db_index=True)

    price_from = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price_to = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    image_url = models.URLField(max_length=1024, blank=True)
    tickets_url = models.URLField(max_length=1024, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    categories = models.ManyToManyField(Category, through=EventCategory, related_name="events")

    # Extra fields not explicitly asked for but might be useful for Django admin
    # or internal flags. Since prompt asks for strict matching, I kept it minimal.
    is_active = models.BooleanField(default=True, db_index=True) # needed for existing filtering logic

    class Meta:
        db_table = "events"
        ordering = ["-date_start"]
        indexes = [
            models.Index(fields=["provider", "external_id"]),
            models.Index(fields=["is_active", "date_start"]),
        ]
        verbose_name = "Event"
        verbose_name_plural = "Events"

    def __str__(self) -> str:
        title = self.title_ru or self.title_ro or self.slug
        return f"[{self.provider.slug}] {title} ({self.date_start})"
