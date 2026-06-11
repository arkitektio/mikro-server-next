from unittest.mock import patch

import pytest

from asgiref.sync import sync_to_async
from core.models import Dataset, Image
from datalayer.models import ZarrStore
from kante.context import HttpContext
from mikro_server.schema import schema


async def _seed_dataset(ctx: HttpContext, name: str) -> Dataset:
    """Create a Dataset through the ORM."""
    return await Dataset.objects.acreate(
        name=name,
        creator=ctx.request.user,
        organization=ctx.request.organization,  # type: ignore[arg-type]
        membership=ctx.request.membership,  # type: ignore[arg-type]
    )


async def _seed_image(ctx: HttpContext, name: str, dataset: Dataset) -> Image:
    """Create an Image straight through the ORM (no store / mutation needed).

    A dataset is required: the post_save signal (core/signals.py) dereferences
    ``instance.dataset.id`` when broadcasting the create event.
    """
    return await Image.objects.acreate(
        name=name,
        dataset=dataset,
        creator=ctx.request.user,
        organization=ctx.request.organization,  # type: ignore[arg-type]
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_from_array_like_creates_image(db, authenticated_context: HttpContext):
    """The fromArrayLike mutation creates an image and auto-generates RGB views."""
    store = await ZarrStore.objects.acreate(
        key="test-zarr",
        bucket="zarr",
        shape=[3, 1, 1, 512, 512],
        chunks=[1, 1, 1, 256, 256],
        version="3",
        dtype="uint8",
        populated=True,
    )

    mutation = """
        mutation Create($input: FromArrayLikeInput!) {
            fromArrayLike(input: $input) {
                id
                name
                store { id }
            }
        }
    """

    # fill_info() reads zarr metadata from S3; stub it so the pre-set shape stays intact.
    with patch("datalayer.models.ZarrStore.fill_info", return_value=None):
        result = await schema.execute(
            mutation,
            context_value=authenticated_context,
            variable_values={"input": {"array": str(store.id), "name": "My Image"}},
        )

    assert not result.errors, result.errors
    assert result.data["fromArrayLike"]["name"] == "My Image"
    assert result.data["fromArrayLike"]["store"]["id"] == str(store.id)

    image = await Image.objects.aget(name="My Image")
    # c_size == 3 -> auto_create_views builds one RGB context with red/green/blue views.
    rgb_view_count = await sync_to_async(image.rgb_views.count)()
    assert rgb_view_count == 3


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_images_query_returns_all(db, authenticated_context: HttpContext):
    """The images query returns every image owned by the current user."""
    ds = await _seed_dataset(authenticated_context, "DS")
    await _seed_image(authenticated_context, "Alpha", ds)
    await _seed_image(authenticated_context, "Beta", ds)
    await _seed_image(authenticated_context, "Gamma", ds)

    query = "query { images { id name } }"
    result = await schema.execute(query, context_value=authenticated_context)

    assert not result.errors, result.errors
    names = {img["name"] for img in result.data["images"]}
    assert names == {"Alpha", "Beta", "Gamma"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_images_filter_by_name(db, authenticated_context: HttpContext):
    """Filtering by name (contains) narrows the result set."""
    ds = await _seed_dataset(authenticated_context, "DS")
    await _seed_image(authenticated_context, "Alpha", ds)
    await _seed_image(authenticated_context, "Alphabet", ds)
    await _seed_image(authenticated_context, "Beta", ds)

    query = """
        query List($filters: ImageFilter) {
            images(filters: $filters) { id name }
        }
    """
    result = await schema.execute(
        query,
        context_value=authenticated_context,
        variable_values={"filters": {"name": {"contains": "Alph"}}},
    )

    assert not result.errors, result.errors
    names = {img["name"] for img in result.data["images"]}
    assert names == {"Alpha", "Alphabet"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_images_filter_by_ids(db, authenticated_context: HttpContext):
    """Filtering by ids returns exactly the requested images."""
    ds = await _seed_dataset(authenticated_context, "DS")
    a = await _seed_image(authenticated_context, "Alpha", ds)
    b = await _seed_image(authenticated_context, "Beta", ds)
    await _seed_image(authenticated_context, "Gamma", ds)

    query = """
        query List($filters: ImageFilter) {
            images(filters: $filters) { id name }
        }
    """
    result = await schema.execute(
        query,
        context_value=authenticated_context,
        variable_values={"filters": {"ids": [str(a.id), str(b.id)]}},
    )

    assert not result.errors, result.errors
    returned_ids = {img["id"] for img in result.data["images"]}
    assert returned_ids == {str(a.id), str(b.id)}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_images_filter_by_dataset(db, authenticated_context: HttpContext):
    """Filtering by dataset returns only images belonging to that dataset."""
    dataset = await _seed_dataset(authenticated_context, "Dataset A")
    other = await _seed_dataset(authenticated_context, "Dataset B")
    in_ds = await _seed_image(authenticated_context, "InDataset", dataset)
    await _seed_image(authenticated_context, "Elsewhere", other)

    # Filter through the dataset relation by name; strawberry_django relation-prefixes
    # the declarative FilterLookup to ``dataset__name__iexact``.
    query = """
        query List($filters: ImageFilter) {
            images(filters: $filters) { id name }
        }
    """
    result = await schema.execute(
        query,
        context_value=authenticated_context,
        variable_values={"filters": {"dataset": {"name": {"iExact": "Dataset A"}}}},
    )

    assert not result.errors, result.errors
    images = result.data["images"]
    assert {img["id"] for img in images} == {str(in_ds.id)}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_images_filter_by_search(db, authenticated_context: HttpContext):
    """The search filter uses Postgres full-text search on the image name."""
    ds = await _seed_dataset(authenticated_context, "DS")
    await _seed_image(authenticated_context, "Alpha", ds)
    await _seed_image(authenticated_context, "Beta", ds)

    query = """
        query List($filters: ImageFilter) {
            images(filters: $filters) { id name }
        }
    """
    result = await schema.execute(
        query,
        context_value=authenticated_context,
        variable_values={"filters": {"search": "Alpha"}},
    )

    assert not result.errors, result.errors
    names = {img["name"] for img in result.data["images"]}
    assert names == {"Alpha"}
