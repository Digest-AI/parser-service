from typing import Any

import inflection


def camelize(data: Any) -> Any:
    if isinstance(data, list):
        return [camelize(item) for item in data]
    if isinstance(data, dict):
        return {inflection.camelize(k, False): camelize(v) for k, v in data.items()}
    return data


def pythonize(data: Any) -> Any:
    if isinstance(data, list):
        return [pythonize(item) for item in data]
    if isinstance(data, dict):
        return {inflection.underscore(k): pythonize(v) for k, v in data.items()}
    return data
