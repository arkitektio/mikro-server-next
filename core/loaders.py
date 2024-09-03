
from strawberry.dataloader import DataLoader
from core import models





async def load_linked_expressions(age_names):

    gotten = []

    for i in age_names:
        graph_name, age_name = i.split(":")

        gotten.append(await models.LinkedExpression.objects.aget(
            graph__age_name=graph_name,
            age_name=age_name,
        ))




    return gotten


async def metric_key_loader(keys):
    gotten = []

    for i in keys:
        graph_name, age_name = i.split(":")

        gotten.append(await models.LinkedExpression.objects.aget(
            graph__age_name=graph_name,
            age_name=age_name,
        ))

    return gotten



linked_expression_loader = DataLoader(load_fn=load_linked_expressions)



metric_key_loader = DataLoader(load_fn=load_linked_expressions)