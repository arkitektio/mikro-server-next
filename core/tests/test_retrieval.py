import pytest
from core.models import Image, Dataset
from django.contrib.auth import get_user_model
from authentikate.models import App
from core.schema import schema
from guardian.shortcuts import get_perms
from asgiref.sync import sync_to_async
from kante.context import ChannelsContext, EnhancendChannelsHTTPRequest


@pytest.mark.asyncio
async def test_simple_query(db):
    user = await get_user_model().objects.acreate(
        username="testuser", password="123456789"
    )

    dataset = await Dataset.objects.acreate(
        name="Test Model", description="This is a test model"
    )
    my_model = await Image.objects.acreate(
        dataset=dataset,
        creator=user,
    )

    t = sync_to_async(get_perms)(user, my_model)
    print(await t)


@pytest.mark.asyncio
async def test_client(db):
    user = await get_user_model().objects.acreate(username="fart", password="123456789")

    app = await App.objects.acreate(client_id="oinsoins")

    dataset = await Dataset.objects.acreate(
        name="Test Model", description="This is a test model"
    )
    my_model = await Image.objects.acreate(
        dataset=dataset,
        creator=user,
    )

    t = sync_to_async(get_perms)(user, my_model)
    print(await t)

    query = """
        query {
            image(id: 1) {
                id
                dataset {
                    name @upper
                }
            }
        }
    """

    sub = await schema.execute(
        query,
        context_value=ChannelsContext(
            request=EnhancendChannelsHTTPRequest(
                user=user,
                app=app,
                body=query,
                scopes=["openid"],
                consumer=None,
            ),
            response=None,
        ),
    )

    assert sub.data, sub.errors

    assert sub.data["image"]["dataset"]["name"] == "TEST MODEL"
