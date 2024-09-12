from contextlib import contextmanager, asynccontextmanager
import json
from django.db import connections
from core import models
from dataclasses import dataclass
from core import filters, pagination

@dataclass
class RetrievedMetric:
    graph_name: str
    key: str
    value: str



@dataclass
class RetrievedEntity:
    graph_name: str
    id: int
    kind_age_name: str | None
    properties: dict[str, str] | None

    def retrieve_relations(self):
        return get_age_relations(self.graph_name, self.id)

    @property
    def unique_id(self):
        return f"{self.graph_name}:{self.id}"
    
    def retrieve_metrics(self):
        try:
            return [RetrievedMetric(key=key, value=value, graph_name=self.graph_name) for key, value in self.properties.items() if key != "id" and key != "labels"]
        except Exception as e:
            raise ValueError(f"Error retrieving metrics {e} {self.properties}")
        
    def retrieve_properties(self):
        return {key: value for key, value in self.properties.items() if key != "id" and key != "labels"}



@dataclass
class RetrievedRelation:
    graph_name: str
    id: int
    kind_age_name: str | None
    left_id: int
    right_id: int
    properties: dict[str, str] | None

    def retrieve_left(self):
        return get_age_entity(self.graph_name, self.left_id)
    
    def retrieve_right(self):
        return get_age_entity(self.graph_name, self.right_id)
    
    @property
    def unique_left_id(self):
        return f"{self.graph_name}:{self.left_id}"
    
    @property
    def unique_right_id(self):
        return f"{self.graph_name}:{self.right_id}"
    
    @property
    def unique_id(self):
        return f"{self.graph_name}:{self.id}"
    
    def retrieve_metrics(self):
        try:
            return [RetrievedMetric(key=key, value=value, graph_name=self.graph_name) for key, value in self.properties.items() if key != "id" and key != "labels"]
        except Exception as e:
            raise ValueError(f"Error retrieving metrics {e} {self.properties}")
        
    def retrieve_properties(self):
        return {key: value for key, value in self.properties.items() if key != "id" and key != "labels"}




@contextmanager
def graph_cursor():
    with connections["default"].cursor() as cursor:
        cursor.execute("LOAD 'age';")
        cursor.execute('SET search_path = ag_catalog, "$user", public')
        yield cursor



def create_age_graph(name: str):
    with graph_cursor() as cursor:
        cursor.execute(
            "SELECT EXISTS(SELECT 1 FROM ag_catalog.ag_graph WHERE name = %s);",
            [name]
        )
        exists = cursor.fetchone()[0]
        if exists:
            return exists
        else:
            cursor.execute(
                "SELECT create_graph(%s);",
                [name]
            )
            print(cursor.fetchone())

def delete_age_graph(name: str):
    with graph_cursor() as cursor:
        cursor.execute(
            "SELECT drop_graph(%s, true);",
            [name]
        )
        print(cursor.fetchone())


def create_age_entity_kind(graph_name, kind_name):
    with graph_cursor() as cursor:
            try:
                cursor.execute(
                    "SELECT create_vlabel(%s, %s);",
                    (graph_name, kind_name)
                )
                print(cursor.fetchone())
            except Exception as e:
                print(e)


def create_age_relation_kind(graph_name, kind_name):
    with graph_cursor() as cursor:
            try:
                cursor.execute(
                    "SELECT create_elabel(%s, %s);",
                    (graph_name, kind_name)
                )
                print(cursor.fetchone())
            except Exception as e:
                print(e)


def vertex_ag_to_retrieved_entity(graph_name, vertex):
    trimmed_neighbour = vertex.replace("::vertex", "")
    print("timmed neighbour", trimmed_neighbour)

    parsed_neighbour = json.loads(trimmed_neighbour)
    return RetrievedEntity(graph_name=graph_name, id=parsed_neighbour["id"], kind_age_name=parsed_neighbour["label"], properties=parsed_neighbour["properties"])

def edge_ag_to_retrieved_relation(graph_name, edge):
    trimmed_relationship = edge.replace("::edge", "")
    print("timmed", trimmed_relationship)
    parsed_relationship = json.loads(trimmed_relationship)
    return RetrievedRelation(graph_name=graph_name, id=parsed_relationship["id"], kind_age_name=parsed_relationship["label"], left_id=parsed_relationship["start_id"], right_id=parsed_relationship["end_id"], properties=parsed_relationship["properties"])


def get_neighbors_and_edges(graph_name, node_id):
    with graph_cursor() as cursor:
        print(graph_name, int(node_id))
        cursor.execute(
            """
            SELECT * 
            FROM cypher(%s, $$
                MATCH (n)-[r]-(neighbor)
                WHERE id(n) = %s
                RETURN DISTINCT r, neighbor 
            $$) as (relationship agtype, neighbor agtype);
            """,
            [graph_name, int(node_id)]
        )

        results = cursor.fetchall()
        print("Thre results", results)

        nodes: list[RetrievedEntity] = []
        relation_ships: list[RetrievedRelation] = []


        for result in results:
            print(result)
            relationship = result[0]  # Edge connecting the nodes
            neighbour = result[1]  # Starting node


            if neighbour:
                nodes.append(vertex_ag_to_retrieved_entity(graph_name, neighbour))

            if relationship:
                relation_ships.append(edge_ag_to_retrieved_relation(graph_name, relationship))
                
        print(nodes, relation_ships)
        return nodes, relation_ships




def create_age_entity(graph_name, kind_age_name) -> RetrievedEntity:
    with graph_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT * 
            FROM cypher(%s, $$
                CREATE (n:{kind_age_name})
                RETURN n
            $$) as (n agtype);
            """,
            (graph_name,)
        )
        result = cursor.fetchone()
        if result:
            entity = result[0]
            return vertex_ag_to_retrieved_entity(graph_name, entity)
        else:
            raise ValueError("No entity created or returned by the query.")
        

def get_age_entity(graph_name, entity_id) -> RetrievedEntity:

    with graph_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT * 
            FROM cypher(%s, $$
                MATCH (n) WHERE id(n) = %s
                RETURN n
            $$) as (n agtype);
            """,
            (graph_name, int(entity_id))
        )
        result = cursor.fetchone()
        if result:
            entity = result[0]
            return vertex_ag_to_retrieved_entity(graph_name, entity)
        raise ValueError("No entity created or returned by the query.")
        
def get_age_entity_relation(graph_name, edge_id) -> RetrievedRelation:

    with graph_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT * 
            FROM cypher(%s, $$
                MATCH [e] WHERE id(e) = %s
                RETURN e
            $$) as (e agtype);
            """,
            (graph_name, int(edge_id))
        )
        result = cursor.fetchone()
        if result:
            entity = result[0]
            return edge_ag_to_retrieved_relation(graph_name, entity)


def create_age_metric(graph_name,  metric_name, node_id, value):
    with graph_cursor() as cursor:
        cursor.execute(
            f"""SELECT * FROM cypher(%s, $$
                MATCH (n) WHERE id(n) = %s
                SET n.{metric_name} = %s
                RETURN n
            $$) AS (n agtype);
            """,
            (graph_name, int(node_id), value)
        )
        result = cursor.fetchone()
        if result:
            entity = result[0]
            return vertex_ag_to_retrieved_entity(graph_name, entity)
        else:
            raise ValueError("No entity created or returned by the query.")
    
def create_age_relation_metric(graph_name, metric_name, edge_id, value):
    with graph_cursor() as cursor:
        cursor.execute(
            f"""SELECT * FROM cypher(%s, $$
                MATCH ()-[r]-() WHERE id(r) = %s
                SET r.{metric_name} = %s
                RETURN r
            $$) AS (r agtype)
            """,
            (graph_name, int(edge_id), value)
        )
        result = cursor.fetchone()

        if result:
            edge = result[0]
            return edge_ag_to_retrieved_relation(graph_name, edge)
        
        else:
            existence_query = """
                SELECT count(*)
                FROM cypher(%s, $$
                    MATCH ()-[r]-()
                    WHERE id(r) = %s
                    RETURN count(*)
                $$) as (count agtype);
            """

            cursor.execute(existence_query, (graph_name, int(edge_id)))

            edge_count = cursor.fetchone()[0]

            if edge_count < 1:
                raise ValueError(f"Edge does not exist. {edge_id}")
            


            raise ValueError("No entity created or returned by the query.")


def create_age_relation(graph_name, relation_kind_age_name, left_id, right_id):
    with graph_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT * 
            FROM cypher(%s, $$
                MATCH (a) WHERE id(a) = %s
                MATCH (b) WHERE id(b) = %s
                CREATE (a)-[r:{relation_kind_age_name}]->(b)
                RETURN id(r), properties(r)
            $$) as (id agtype, properties agtype);
            """,
            (graph_name, int(left_id), int(right_id))
        )
        result = cursor.fetchone()
        if result:
            entity_id = result[0]
            properties = result[1]
            print(entity_id, relation_kind_age_name, properties)
            return RetrievedRelation(id=entity_id, kind_age_name=relation_kind_age_name, properties=properties, graph_name=graph_name, left_id=left_id, right_id=right_id)
        else:
            existence_query = """
                SELECT count(*)
                FROM cypher(%s, $$
                    MATCH (a), (b)
                    WHERE id(a) = %s AND id(b) = %s
                    RETURN count(*)
                $$) as (count agtype);
            """

            cursor.execute(existence_query, (graph_name, left_id, right_id))
            node_count = cursor.fetchone()[0]
            
            if node_count < 2:
                raise ValueError(f"One or both of the nodes do not exist. {left_id}, {right_id}, {graph_name}")


            raise ValueError("No entity created or returned by the query.")

def to_entity_id(id):
    return id.split(":")[1]

def to_graph_id(id):
    return id.split(":")[0]

def select_all_entities(graph_name, pagination: pagination.GraphPaginationInput,  filter: filters.EntityFilter):
    with graph_cursor() as cursor:

        WHERE = ""

        and_clauses = []

        if filter:

            if filter.ids:
                and_clauses.append(f'id(n) IN [ {", ".join([to_entity_id(id) for id in filter.ids])}]')

            if filter.search:
                and_clauses.append(f'n.Label STARTS WITH "{filter.search}"')

            if filter.linked_expression:
                expression = models.LinkedExpression.objects.get(id=filter.linked_expression)
                and_clauses.append(f'label(n) = "{expression.age_name}"')

            if and_clauses:
                WHERE = "WHERE " + " AND ".join(and_clauses)



        print(WHERE)



        cursor.execute(
            f"""
            SELECT * 
            FROM cypher(%s, $$
                MATCH (n)
                {WHERE}
                RETURN n
                ORDER BY id(n)
                SKIP %s
                LIMIT %s
            $$) as (n agtype);
            """,
            [graph_name, pagination.offset or 0 , pagination.limit or 200]
        )

        if cursor.rowcount == 0:
            return []

        for result in cursor.fetchall():
            print(result)
            yield vertex_ag_to_retrieved_entity(graph_name, result[0])

def select_all_relations(graph_name, pagination: pagination.GraphPaginationInput,  filter: filters.EntityRelationFilter):
    with graph_cursor() as cursor:

        WHERE = ""

        and_clauses = []

        if filter:

            if filter.left_id:
                and_clauses.append(f'id(a) = {to_entity_id(filter.left_id)}')

            if filter.right_id:
                and_clauses.append(f'id(b) = {to_entity_id(filter.right_id)}')

            if filter.ids:
                and_clauses.append(f'id(e) IN [ {", ".join([to_entity_id(id) for id in filter.ids])}]')

            if filter.search:
                and_clauses.append(f'e.Label STARTS WITH "{filter.search}"')

            if filter.linked_expression:
                expression = models.LinkedExpression.objects.get(id=filter.linked_expression)
                and_clauses.append(f'label(e) = "{expression.age_name}"')

            if and_clauses:
                WHERE = "WHERE " + " AND ".join(and_clauses)



        print(WHERE)

        try:

            cursor.execute(
                f"""
                SELECT * 
                FROM cypher(%s, $$
                    MATCH (a) - [e] - (b)
                    {WHERE}
                    RETURN e
                    ORDER BY id(e)
                    SKIP %s
                    LIMIT %s
                $$) as (e agtype);
                """,
                [graph_name, pagination.offset or 0 , pagination.limit or 200]
            )

            print("here")

            if cursor.rowcount == 0:
                print("No results")
                return []

            for result in cursor.fetchall():
                print(result)
                yield edge_ag_to_retrieved_relation(graph_name, result[0])

        except Exception as e:
            print("Error", e)
            print(e)
            return []


def get_age_relations(graph_name, entity_id):
    with graph_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT * 
            FROM cypher(%s, $$
                MATCH (a)-[r]-(b) WHERE id(a) = %s
                RETURN id(r), type(r), id(a), id(b), properties(r)
            $$) as (id agtype, type agtype, left agtype, right agtype, properties agtype);
            """,
            [graph_name, entity_id]
        )
        print(cursor.fetchall())
        for result in cursor.fetchall():
            yield RetrievedRelation(id=result[0], kind_age_name=result[1], left_id=result[2], right_id=result[3], properties=result[4], graph_name=graph_name)