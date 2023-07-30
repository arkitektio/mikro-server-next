from django.apps import AppConfig
from simple_history.signals import (
    pre_create_historical_record,
    post_create_historical_record,
    pre_create_historical_m2m_records,
    post_create_historical_m2m_records,
)


class KoherentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "koherent"
