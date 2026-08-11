import pytest
from core.models import Image, Folder
from mikro_server.schema import schema
from kante.context import HttpContext

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_folder_upper(db, authenticated_context: HttpContext):
    
    assert authenticated_context.request.organization is not None, "Organization should be set"

    folder = await Folder.objects.acreate(
        name="Test Model",
        description="This is a test model",
        creator=authenticated_context.request.user,
        organization=authenticated_context.request.organization,  # type: ignore
        membership=authenticated_context.request.membership,  # type: ignore
    )
    image = await Image.objects.acreate(
        folder=folder,
        creator=authenticated_context.request.user,
        organization=authenticated_context.request.organization,  # type: ignore
    )

    # The id of the image just created, not a literal 1. Sequences are not reset between
    # tests, so a hardcoded id only resolves while this module happens to be collected
    # before anything else that makes an image.
    query = """
        query Image($id: ID!) {
            image(id: $id) {
                id
                folder {
                    name
                }
            }
        }
    """

    sub = await schema.execute(
        query,
        context_value=authenticated_context,
        variable_values={"id": str(image.pk)},
    )

    assert sub.data, sub.errors

    assert sub.data["image"]["folder"]["name"] == "Test Model"
