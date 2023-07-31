import strawberry
from strawberry import auto
from authentikate.filters import UserFilter
from koherent import models
import strawberry_django


@strawberry.django.order(models.AppHistoryModel)
class ProvenanceOrder:
    history_date: auto


@strawberry_django.filter(models.AppHistoryModel)
class ProvenanceFilter:
    user: UserFilter | None
    during: str | None

    def filter_during(self, queryset, info):
        queryset

        if self.during is None:
            return queryset

        return queryset.filter(provenance__assignation_id=self.during).distinct()
