from collections.abc import Mapping
from typing import IO, Any

from rest_framework.parsers import JSONParser

from utils.transformers import pythonize


class CamelCaseJSONParser(JSONParser):
    def parse(
        self,
        stream: IO[bytes],
        media_type: str | None = None,
        parser_context: Mapping[str, Any] | None = None,
    ) -> Any:
        data = super().parse(
            stream, media_type=media_type, parser_context=parser_context
        )
        return pythonize(data)
