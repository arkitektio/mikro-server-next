def get_assignation_id_or_none(headers: dict):
    return headers.get("x-assignation-id", None)
