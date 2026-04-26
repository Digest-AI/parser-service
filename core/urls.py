from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"
    ),
]

if settings.DEBUG:
    if hasattr(settings, "STATIC_URL") and hasattr(settings, "STATIC_ROOT"):
        urlpatterns += static(
            str(settings.STATIC_URL), document_root=settings.STATIC_ROOT
        )

    if hasattr(settings, "MEDIA_URL") and hasattr(settings, "MEDIA_ROOT"):
        urlpatterns += static(
            str(settings.MEDIA_URL), document_root=settings.MEDIA_ROOT
        )
