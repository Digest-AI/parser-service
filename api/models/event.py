from django.db import models


class Event(models.Model):
    """Represents a scraped event from a Moldova event website."""

    class Source(models.TextChoices):
        AFISHA_MD = "afisha_md", "Afisha.md"
        ITICKET_MD = "iticket_md", "iTicket.md"
        MTICKET_MD = "mticket_md", "mTicket.md"
        FEST_MD = "fest_md", "Fest.md"
        CINEPLEX_MD = "cineplex_md", "Cineplex.md"

    class Category(models.TextChoices):
        CONCERT = "concert", "Концерт"
        THEATRE = "theatre", "Театр"
        MOVIE = "movie", "Кино"
        SPORT = "sport", "Спорт"
        PARTY = "party", "Вечеринка"
        KIDS = "kids", "Для детей"
        TRAINING = "training", "Тренинг"
        EXHIBITION = "exhibition", "Выставка"
        FESTIVAL = "festival", "Фестиваль"
        FREE = "free", "Бесплатно"
        OTHER = "other", "Другое"

    # Source identification
    source = models.CharField(max_length=32, choices=Source.choices, db_index=True)
    external_id = models.CharField(max_length=128, blank=True, db_index=True)
    url = models.URLField(max_length=512, unique=True)

    # Basic info
    title = models.CharField(max_length=512)
    title_ru = models.CharField(max_length=512, blank=True)
    title_ro = models.CharField(max_length=512, blank=True)
    description = models.TextField(blank=True)
    description_ru = models.TextField(blank=True)
    description_ro = models.TextField(blank=True)

    # Category
    category = models.CharField(
        max_length=32, choices=Category.choices, default=Category.OTHER, db_index=True
    )
    raw_categories = models.JSONField(default=list, blank=True)

    # Date & time
    date_start = models.DateTimeField(null=True, blank=True, db_index=True)
    date_end = models.DateTimeField(null=True, blank=True)
    date_raw = models.CharField(max_length=256, blank=True)

    # Location
    venue_name = models.CharField(max_length=256, blank=True)
    venue_address = models.CharField(max_length=512, blank=True)
    city = models.CharField(max_length=128, default="Кишинёв", db_index=True)

    # Pricing
    price_from = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price_to = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=8, default="MDL")
    is_free = models.BooleanField(default=False, db_index=True)

    # Media
    image_url = models.URLField(max_length=1024, blank=True)

    # Metadata
    ticket_links = models.JSONField(default=dict, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_scraped_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "events"
        ordering = ["-date_start"]
        indexes = [
            models.Index(fields=["source", "external_id"]),
            models.Index(fields=["category", "date_start"]),
            models.Index(fields=["is_active", "date_start"]),
        ]
        verbose_name = "Event"
        verbose_name_plural = "Events"

    def __str__(self) -> str:
        return f"[{self.source}] {self.title} ({self.date_start})"
