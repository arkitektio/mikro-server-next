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
    history_user: UserFilter | None
    assignation_id: str | None

    def filter_assignation_id(self, queryset, info):
        print("filter_assignation_id", self.assignation_id)
        queryset

        if self.assignation_id is None:
            return queryset

        print(queryset, self.assignation_id)
        return queryset.filter(
            provenance__assignation_id=self.assignation_id
        ).distinct()
