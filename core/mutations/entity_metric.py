from kante.types import Info
import strawberry
from core import types, models, enums, scalars


@strawberry.input
class EntityMetricInput:
    kind: strawberry.ID
    data_kind: enums.MetricDataType


@strawberry.input
class AttachEntityMetricInput:
    value: scalars.Metric 
    entity: strawberry.ID
    metric: strawberry.ID | None = None
    kind_name: str | None = None
    kind: strawberry.ID | None = None
    data_kind: enums.MetricDataType | None = None

@strawberry.input
class DeleteEntityMetricInput:
    id: strawberry.ID



def create_entity_metric(
    info: Info,
    input: EntityMetricInput,
) -> types.EntityMetric:
    item, _ = models.EntityMetric.objects.get_or_create(
        kind=models.EntityKind.objects.get(id=input.kind),
        defaults=dict(data_kind=input.data_kind),
    )
    assert item.data_kind == input.data_kind, f"Data kind mismatch: {item.data_kind} != {input.data_kind}. Metric was already created with another kind"
    return item


def attach_entity_metric(
        info: Info,
        input: AttachEntityMetricInput,
) -> types.Entity:
    entity = models.Entity.objects.get(id=input.entity)

    if input.metric:
        metric = models.EntityMetric.objects.get(id=input.metric)
    else:
        if input.kind:
            metric = models.EntityMetric.objects.get_or_create(kind=entity.kind)
        elif input.kind_name:
            metric = models.EntityMetric.objects.get_or_create(kind_name=input.kind_name)
        else:
            raise ValueError("Either kind or kind_name must be provided")
        
        if input.data_kind:
            assert metric.data_kind == input.data_kind, f"Data kind mismatch: {metric.data_kind} != {input.data_kind}. Metric was already created with another kind"


    entity.metrics[metric.id] = input.value
    entity.save()
    return entity
    
        
def delete_entity_metric(
    info: Info,
    input: DeleteEntityMetricInput,
) -> strawberry.ID:
    item = models.EntityGroup.objects.get(id=input.id)
    item.delete()
    return input.id

