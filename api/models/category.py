from django.db import models

class Category(models.Model):
    """Event category."""
    slug = models.CharField(max_length=64, unique=True, db_index=True)
    name_ru = models.CharField(max_length=128)
    name_ro = models.CharField(max_length=128)

    class Meta:
        db_table = "categories"
        verbose_name = "Category"
        verbose_name_plural = "Categories"

    def __str__(self) -> str:
        return self.name_ru
