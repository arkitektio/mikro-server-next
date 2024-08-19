import strawberry
from core import models


@strawberry.type
class EntityNodeMetric:
    data_kind: str
    kind: str
    metric_id: str
    value: str


@strawberry.type
class EntityNode:
    id: str
    is_root: bool = False
    subtitle: str
    label: str
    color: str = "#FF0000"
    metrics: list[EntityNodeMetric]


@strawberry.type
class EntityRelationEdge:
    id: str
    label: str
    source: str
    target: str
    metrics: list[EntityNodeMetric]

@strawberry.type
class EntityGraph:
    nodes: list[EntityNode]
    edges: list[EntityRelationEdge]



def entity_graph(id: strawberry.ID) -> EntityGraph:
    """
    Query the knowledge graph for information about a given entity.

    Args:
        query: The entity to search for in the knowledge graph.

    Returns:
        A dictionary containing information about the entity.
    """

    nodes = []
    edges = []

    entity = models.Entity.objects.get(id=id)


    def parse_entity(entity: models.Entity, is_root=False):

        node = EntityNode(id=entity.id, subtitle=entity.name, metrics=[], label=entity.kind.label, is_root=is_root, color=entity.kind.rgb_color_string)

        metric_map = {}

        relation_metric_map = {}

        for key, value  in  entity.metrics.items():

            if key not in metric_map:
                metric_map[key] = models.EntityMetric.objects.get(id=key)

            metric = metric_map[key]
            node.metrics.append(EntityNodeMetric(data_kind=metric.data_kind, kind=metric.kind.label, value=value, metric_id=key))

        nodes.append(node)

        outgoing_relations = []
        first_partners_nodes = []


        for entity_relation in models.EntityRelation.objects.prefetch_related('kind__kind', "right__kind", "left__kind").filter(left=entity):
            outgoing_relations.append(entity_relation)
            edge = EntityRelationEdge(id=entity_relation.id, label=entity_relation.kind.kind.label, source=entity.id, target=entity_relation.right.id, metrics=[])
            first_partners_nodes.append(entity_relation.right)


            node = EntityNode(id=entity_relation.right.id, label=entity_relation.right.kind.label, subtitle=entity_relation.right.name, metrics=[], color=entity_relation.right.kind.rgb_color_string)

            if node.id not in [n.id for n in nodes]:
                nodes.append(node)
            if edge.id not in [n.id for n in edges]:
                edges.append(edge)

            
        for entity_relation in models.EntityRelation.objects.prefetch_related('kind__kind', "right__kind", "left__kind").filter(right=entity):
            outgoing_relations.append(entity_relation)
            edge = EntityRelationEdge(id=entity_relation.id, label=entity_relation.kind.kind.label, source=entity_relation.left.id, target=entity.id, metrics=[])
            first_partners_nodes.append(entity_relation.left)


            node = EntityNode(id=entity_relation.left.id, label=entity_relation.left.kind.label, subtitle=entity_relation.left.name, metrics=[], color=entity_relation.left.kind.rgb_color_string)
            
            if node.id not in [n.id for n in nodes]:
                nodes.append(node)
            if edge.id not in [n.id for n in edges]:
                edges.append(edge)




    parse_entity(entity, is_root=True)


    return EntityGraph(nodes=nodes, edges=edges)