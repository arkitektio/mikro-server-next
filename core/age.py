from contextlib import contextmanager
import json
from django.db import connections
from core import models
from dataclasses import dataclass



@dataclass
class RetrievedEntity:
    graph_name: str
    id: int
    kind_age_name: str | None
    properties: dict[str, str] | None

    def retrieve_relations(self):
        return get_age_relations(self.graph_name, self.id)


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

        nodes = []
        relation_ships = []

        try:

            for result in results:
                print(result)
                relationship = result[0]  # Edge connecting the nodes
                neighbour = result[1]  # Starting node



                if neighbour:
                    trimmed_neighbour = neighbour.replace("::vertex", "")
                    print(trimmed_neighbour)

                    parsed_neighbour = json.loads(trimmed_neighbour)
                    print(parsed_neighbour)
                    nodes.append(RetrievedEntity(graph_name=graph_name, id=parsed_neighbour["id"], kind_age_name=parsed_neighbour["label"], properties=parsed_neighbour["properties"]))

                if relationship:
                    trimmed_relationship = relationship.replace("::edge", "")
                    print(trimmed_relationship)
                    parsed_relationship = json.loads(trimmed_relationship)
                    print(parsed_relationship)
                    relation_ships.append(RetrievedRelation(graph_name=graph_name, id=parsed_relationship["id"], kind_age_name=parsed_relationship["label"], left_id=parsed_relationship["start_id"], right_id=parsed_relationship["end_id"], properties=parsed_relationship["properties"]))

            print(nodes, relation_ships)
        except Exception as e:
        
            print(e)

            raise e
        return nodes, relation_ships




def create_age_entity(graph_name, kind_age_name) -> RetrievedEntity:
    with graph_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT * 
            FROM cypher(%s, $$
                CREATE (n:{kind_age_name})
                RETURN id(n), properties(n)
            $$) as (id agtype, properties agtype);
            """,
            (graph_name,)
        )
        result = cursor.fetchone()
        if result:
            entity_id = result[0]
            properties = result[1]  # Assuming you want to retrieve properties as well
            print(entity_id, properties)
            return RetrievedEntity(id=entity_id, kind_age_name=kind_age_name, properties=properties, graph_name=graph_name)
        else:
            raise ValueError("No entity created or returned by the query.")
        

def get_age_entity(graph_name, entity_id) -> RetrievedEntity:

    with graph_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT * 
            FROM cypher(%s, $$
                MATCH (n) WHERE id(n) = %s
                RETURN id(n), labels(n)[0], properties(n)
            $$) as (id agtype, labels text, properties agtype);
            """,
            (graph_name, int(entity_id))
        )
        result = cursor.fetchone()
        if result:
            entity_id = result[0]
            kind_age_name = result[1]
            properties = result[2]
            print(entity_id, kind_age_name, properties)
            return RetrievedEntity(id=entity_id, kind_age_name=kind_age_name, properties=properties, graph_name=graph_name)


def create_age_metric(graph_name,  metric_name, node_id, value):
    with graph_cursor() as cursor:
        cursor.execute(
            f"""SELECT * FROM cypher(%s, $$
                MATCH (n) WHERE id(n) = %s
                SET n.{metric_name} = %s
                RETURN n
            $$) AS (n agtype)
            """,
            (graph_name, node_id, value)
        )
        id = cursor.fetchone()
        return id
    
def create_age_relation_metric(graph_name, metric_name, edge_id, value):
    with graph_cursor() as cursor:
        cursor.execute(
            f"""SELECT * FROM cypher(%s, $$
                MATCH ()-[r]-() WHERE id(r) = %s
                SET r.{metric_name} = %s
                RETURN r
            $$) AS (r agtype)
            """,
            (graph_name, edge_id, value)
        )
        id = cursor.fetchone()
        return id


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


def select_all_entities(graph_name, limit, offset):
    with graph_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT * 
            FROM cypher(%s, $$
                MATCH (n)
                RETURN id(n), labels(n)[0], properties(n)
                ORDER BY id(n)
                SKIP %s
                LIMIT %s
            $$) as (id agtype, labels text, properties agtype);
            """,
            [graph_name, offset, limit]
        )

        if cursor.rowcount == 0:
            raise ValueError("No entities found. {} {} {}".format(graph_name, limit, offset))

        for result in cursor.fetchall():
            print(result)
            yield RetrievedEntity(id=result[0], kind_age_name=result[1], properties=result[2], graph_name=graph_name)




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