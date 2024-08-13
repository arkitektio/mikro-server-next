from kante.types import Info
import strawberry
from core import types, models, enums, scalars


@strawberry.input
class RelationMetricInput:
    kind: strawberry.ID
    data_kind: enums.MetricDataType


@strawberry.input
class DeleteRelationMetricInput:
    id: strawberry.ID



def create_relation_metric(
    info: Info,
    input: RelationMetricInput,
) -> types.RelationMetric:
    item, _ = models.RelationMetric.objects.get_or_create(
        kind=models.EntityKind.objects.get(id=input.kind),
        defaults=dict(data_kind=input.data_kind),
    )
    assert item.data_kind == input.data_kind, f"Data kind mismatch: {item.data_kind} != {input.data_kind}. Metric was already created with another kind"
    return item


@strawberry.input
class AttachRelationMetricInput:
    value: scalars.Metric 
    relation: strawberry.ID
    metric: strawberry.ID | None = None
    kind_name: str | None = None
    kind: strawberry.ID | None = None
    data_kind: enums.MetricDataType | None = None


def attach_relation_metric(
        info: Info,
        input: AttachRelationMetricInput,
) -> types.EntityRelation:
    relation = models.EntityRelation.objects.get(id=input.relation)

    if input.metric:
        rel_metric = models.RelationMetric.objects.get(id=input.metric)
    else:
        if input.kind:
            rel_metric = models.RelationMetric.objects.get_or_create(kind=entity.kind)
        elif input.kind_name:
            rel_metric = models.RelationMetric.objects.get_or_create(kind_name=input.kind_name)
        else:
            raise ValueError("Either kind or kind_name must be provided")
        
        if input.data_kind:
            assert rel_metric.data_kind == input.data_kind, f"Data kind mismatch: {metric.data_kind} != {input.data_kind}. Metric was already created with another kind"


    relation.metrics[rel_metric.id] = input.value
    relation.save()
    return relation



