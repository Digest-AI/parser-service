from django.conf import settings
from django.http import HttpRequest
from django.utils.deprecation import MiddlewareMixin


class I18nMiddleware(MiddlewareMixin):
    """
    Middleware to determine preferred language from Accept-Language header.
    """

    def process_request(self, request: HttpRequest) -> None:
        accept_language = request.META.get("HTTP_ACCEPT_LANGUAGE", "")
        language = self._select_language(accept_language)
        request.language = language  # type: ignore[attr-defined]

    def _select_language(self, header_value: str) -> str:
        default_language: str = getattr(settings, "DEFAULT_LANGUAGE", "en")
        if not header_value:
            return default_language

        supported_set = set[str](getattr(settings, "SUPPORTED_LANGUAGES", ["en", "ru", "ro"]))
        for item in header_value.split(","):
            lang = item.split(";")[0].strip().lower()
            if not lang:
                continue

            lang = lang.lower()

            if lang in supported_set:
                return lang

            # Accept forms like "en-US" -> "en"
            primary = lang.split("-")[0]
            if primary in supported_set:
                return primary

        return default_language
