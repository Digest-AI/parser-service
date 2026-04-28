from django.db import models

class Provider(models.Model):
    """Event source/provider."""
    slug = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=128)
    url = models.URLField(max_length=512)

    class Meta:
        db_table = "providers"
        verbose_name = "Provider"
        verbose_name_plural = "Providers"

    def __str__(self) -> str:
        return self.name
