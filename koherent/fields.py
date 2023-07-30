from koherent.models import AppHistoryModel
from django.contrib.contenttypes.fields import GenericRelation
from simple_history.models import HistoricalRecords


def HistoryField(**kwargs):
    return HistoricalRecords(
        bases=[AppHistoryModel], related_name="provenance", **kwargs
    )
