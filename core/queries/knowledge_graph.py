import strawberry
from core import models


@strawberry.type
class EntityNodeMetric:
    data_kind: str
    kind: str


@strawberry.type
class EntityNode:
    id: str
    label: str
    metrics: list[EntityNodeMetric]


@strawberry.type
class EntityRelationEdge:
    id: str
    label: str
    source: str
    target: str
    metrics: list[EntityNodeMetric]

@strawberry.type
class KnowledgeGraph:
    nodes: list[EntityNode]
    edges: list[EntityRelationEdge]



def knowledge_graph(id: strawberry.ID) -> KnowledgeGraph:
    """
    Query the knowledge graph for information about a given entity.

    Args:
        query: The entity to search for in the knowledge graph.

    Returns:
        A dictionary containing information about the entity.
    """

    nodes = []
    edges = []

    entity_kinds = models.EntityKind.objects.filter(ontology__id=id)


    # Get the entity kind
    for entity_kind in entity_kinds:
        node = EntityNode(id=entity_kind.id, label=entity_kind.label, metrics=[])


        for metric in models.EntityMetric.objects.filter(kind=entity_kind):
            node.metrics.append(EntityNodeMetric(data_kind=metric.data_kind, kind=metric.kind.label))

        nodes.append(node)

    for entity_relation_kind in models.EntityRelationKind.objects.filter(left_kind__in=entity_kinds, right_kind__in=entity_kinds):
        edge = EntityRelationEdge(id=entity_relation_kind.id, label=entity_relation_kind.kind.label, source=entity_relation_kind.left_kind.id, target=entity_relation_kind.right_kind.id, metrics=[])
        
        for metric in models.RelationMetric.objects.filter(kind=entity_relation_kind.kind):
            edge.metrics.append(EntityNodeMetric(data_kind=metric.data_kind, kind=metric.kind.label))
        
        edges.append(edge)



    return KnowledgeGraph(nodes=nodes, edges=edges)