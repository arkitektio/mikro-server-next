from typing import Any


def get_assignation_id_or_none(headers: dict[str, Any]) -> str | None:
    return headers.get("x-assignation-id", None)
