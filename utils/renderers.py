from collections.abc import Mapping
from typing import Any

from rest_framework.renderers import JSONRenderer

from utils.transformers import camelize


class CamelCaseJSONRenderer(JSONRenderer):
    def render(
        self,
        data: Any,
        accepted_media_type: str | None = None,
        renderer_context: Mapping[str, Any] | None = None,
    ) -> Any:
        data = camelize(data)
        return super().render(data, accepted_media_type, renderer_context)
