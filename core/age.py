from contextlib import contextmanager
from django.db import connections
from core import models


@contextmanager
def graph_cursor():
    with connections["default"].cursor() as cursor:
        cursor.execute("LOAD 'age';")
        cursor.execute('SET search_path = ag_catalog, "$user", public')
        yield cursor


def create_age_ontology(name: str):
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


def create_age_entity(graph_name, kind_name):
    with graph_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT * 
            FROM cypher(%s, $$
                CREATE (n:{kind_name})
                RETURN id(n)
            $$) as (id agtype);
            """,
            (graph_name,)
        )
        id = cursor.fetchone()
        return id



def create_age_relation(relation_kind: models.EntityRelationKind, left_id, right_id):
    with graph_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT * 
            FROM cypher(%s, $$
                MATCH (a:{relation_kind.left_kind.age_name} {{id: %s}})
                MATCH (b:{relation_kind.right_kind.age_name} {{id: %s}})
                CREATE (a)-[:{relation_kind.age_name}]->(b)
            $$) as (id agtype);
            """,
            (relation_kind.kind.ontology.age_name, left_id, right_id)
        )
        print(cursor.fetchone())


def select_all_entities(graph_name):
    with graph_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT * 
            FROM cypher(%s, $$
                MATCH (n)
                RETURN id(n)
            $$) as (id agtype);
            """,
            [graph_name]
        )
        print(cursor.fetchall())