import pytest
from core.models import Image, Dataset
from mikro_server.schema import schema
from kante.context import ChannelsContext



@pytest.mark.asyncio
async def test_dataset_upper(db, authenticated_context: ChannelsContext):

    dataset = await Dataset.objects.acreate(
        name="Test Model", description="This is a test model",
        creator=authenticated_context.request.user,
    )
    await Image.objects.acreate(
        dataset=dataset,
        creator=authenticated_context.request.user,
    )


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
        context_value=authenticated_context,
    )

    assert sub.data, sub.errors

    assert sub.data["image"]["dataset"]["name"] == "TEST MODEL"
