from koherent.models import AppHistoryModel
from django.contrib.contenttypes.fields import GenericRelation
from simple_history.models import HistoricalRecords, HistoricForeignKey


def HistoryField(**kwargs) -> HistoricalRecords:
    return HistoricalRecords(
        bases=[AppHistoryModel], related_name="provenance", **kwargs
    )


__all__ = [
    "HistoryField",
    "HistoricForeignKey",
    "GenericRelation",
]
