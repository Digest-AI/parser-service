from django.urls import path
from rest_framework.routers import DefaultRouter

from api.views import CategoryListView, CityListView, EventViewSet, SourceListView

router = DefaultRouter()
router.register(r"events", EventViewSet, basename="event")

urlpatterns = router.urls + [
    path("categories/", CategoryListView.as_view(), name="categories"),
    path(
        "category/<str:category_slug>/",
        EventViewSet.as_view({"get": "list"}),
        name="category-events",
    ),
    path("cities/", CityListView.as_view(), name="cities"),
    path(
        "city/<str:city_name>/",
        EventViewSet.as_view({"get": "list"}),
        name="city-events",
    ),
    path("sources/", SourceListView.as_view(), name="sources"),
]
