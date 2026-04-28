from django.db import models

class EventCategory(models.Model):
    """Through table for Event and Category."""
    event = models.ForeignKey("api.Event", on_delete=models.CASCADE)
    category = models.ForeignKey("api.Category", on_delete=models.CASCADE)

    class Meta:
        db_table = "event_categories"
        unique_together = ("event", "category")

    def __str__(self) -> str:
        return f"{self.event_id} - {self.category_id}"
