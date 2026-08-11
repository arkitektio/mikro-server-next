"""Everything fileable can be filed: the four containers carry a folder.

``Image``, ``File`` and ``Table`` have always had one. ``ADataset``, ``TableDataset``,
``MeshCollection`` and ``AnnotationCollection`` -- the same four ``FileLink`` calls "a
container holding data" -- now do too, so the folder tree is a complete view of a user's
data rather than a view of the older half of it.

The invariant these tests defend is that filing and *placement* stay separate. A folder
says where a user keeps a thing; it never says anything about the space the thing is in.
Nothing here touches a coordinate system, and nothing in the coordinate-graph tests should
ever need to touch a folder.
"""

from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from datalayer.models import ZarrStore
from kante.context import HttpContext

from core import models
from mikro_server.schema import schema
from tests import seed

CREATE_ADATASET = """
mutation Create($input: CreateADatasetInput!) {
  createADataset(input: $input) { id folder { id name } }
}
"""

CREATE_TABLE = """
mutation Create($input: CreateTableDatasetInput!) {
  createTableDataset(input: $input) { id folder { id name } }
}
"""

CREATE_MESH = """
mutation Create($input: CreateMeshCollectionInput!) {
  createMeshCollection(input: $input) { id folder { id name } }
}
"""

CREATE_ANNOTATION_COLLECTION = """
mutation Create($input: CreateAnnotationCollectionInput!) {
  createAnnotationCollection(input: $input) { id folder { id name } }
}
"""

_YX = [{"name": "y", "type": "SPACE"}, {"name": "x", "type": "SPACE"}]


async def _zarr(ctx: HttpContext, key: str) -> ZarrStore:
    return await ZarrStore.objects.acreate(
        organization=ctx.request.organization,
        key=key,
        bucket="zarr",
        shape=[32, 32],
        chunks=[32, 32],
        version="3",
        dtype="uint8",
        populated=True,
    )


async def _parquet(ctx: HttpContext, key: str) -> models.ParquetStore:
    return await sync_to_async(models.ParquetStore.objects.create)(path=f"s3://parquet/{key}", bucket="parquet", key=key, organization=ctx.request.organization)


async def _create_adataset(ctx: HttpContext, name: str, folder=None) -> dict[str, object]:
    store = await _zarr(ctx, f"zarr-{name}")
    payload = {"name": name, "data": str(store.id), "scales": [], "axes": _YX}
    if folder is not None:
        payload["folder"] = str(folder.pk)
    with patch("datalayer.models.ZarrStore.fill_info", return_value=None):
        result = await schema.execute(CREATE_ADATASET, context_value=ctx, variable_values={"input": payload})
    assert not result.errors, result.errors
    assert result.data
    return result.data["createADataset"]


async def _create_table(ctx: HttpContext, name: str, folder=None) -> dict[str, object]:
    store = await _parquet(ctx, f"table-{name}")
    payload = {
        "name": name,
        "data": str(store.pk),
        "columns": [{"name": "object", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"}],
    }
    if folder is not None:
        payload["folder"] = str(folder.pk)
    result = await schema.execute(CREATE_TABLE, context_value=ctx, variable_values={"input": payload})
    assert not result.errors, result.errors
    assert result.data
    return result.data["createTableDataset"]


async def _create_mesh(ctx: HttpContext, version: str, folder=None) -> dict[str, object]:
    catalog = await _parquet(ctx, f"catalog-{version}")
    payload = {"axes": _YX, "version": version, "specVersion": "1.0", "catalog": str(catalog.pk)}
    if folder is not None:
        payload["folder"] = str(folder.pk)
    result = await schema.execute(CREATE_MESH, context_value=ctx, variable_values={"input": payload})
    assert not result.errors, result.errors
    assert result.data
    return result.data["createMeshCollection"]


async def _create_annotation_collection(ctx: HttpContext, name: str, folder=None) -> dict[str, object]:
    payload = {"name": name, "axes": _YX}
    if folder is not None:
        payload["folder"] = str(folder.pk)
    result = await schema.execute(CREATE_ANNOTATION_COLLECTION, context_value=ctx, variable_values={"input": payload})
    assert not result.errors, result.errors
    assert result.data
    return result.data["createAnnotationCollection"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_every_container_files_into_a_named_folder(authenticated_context: HttpContext):
    """All four containers accept a folder on create and read it back."""
    ctx = authenticated_context
    folder = await seed.create_folder(ctx, "Experiment A")

    created = [
        await _create_adataset(ctx, "Acquired", folder=folder),
        await _create_table(ctx, "Measurements", folder=folder),
        await _create_mesh(ctx, "v1", folder=folder),
        await _create_annotation_collection(ctx, "Drawn", folder=folder),
    ]

    for container in created:
        assert container["folder"] is not None, "a container created with a folder must report it"
        assert container["folder"]["name"] == "Experiment A"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_container_created_without_a_folder_lands_in_the_default(authenticated_context: HttpContext):
    """Omitting the folder files it in the user's default, exactly as an image has always been.

    The column is nullable and unfiled rows are legal -- migration 0007 does not backfill --
    but nothing created *through the API* is left unfiled.
    """
    dataset = await _create_adataset(authenticated_context, "Unfiled")

    assert dataset["folder"] is not None, "a container created without a folder still gets the default one"
    assert dataset["folder"]["name"] == "Default"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_folder_lists_every_kind_of_container_it_holds(authenticated_context: HttpContext):
    """The reverse lists on Folder, one per container type."""
    ctx = authenticated_context
    folder = await seed.create_folder(ctx, "Everything")

    await _create_adataset(ctx, "Acquired", folder=folder)
    await _create_table(ctx, "Measurements", folder=folder)
    await _create_mesh(ctx, "v1", folder=folder)
    await _create_annotation_collection(ctx, "Drawn", folder=folder)

    result = await schema.execute(
        """
        query Contents($id: ID!) {
          folder(id: $id) {
            adatasets { name }
            tableDatasets { name }
            meshCollections { version }
            annotationCollections { name }
          }
        }
        """,
        context_value=ctx,
        variable_values={"id": str(folder.pk)},
    )
    assert not result.errors, result.errors
    assert result.data

    contents = result.data["folder"]
    assert [d["name"] for d in contents["adatasets"]] == ["Acquired"]
    assert [t["name"] for t in contents["tableDatasets"]] == ["Measurements"]
    assert [m["version"] for m in contents["meshCollections"]] == ["v1"]
    assert [a["name"] for a in contents["annotationCollections"]] == ["Drawn"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_children_returns_the_containers_alongside_images_and_files(authenticated_context: HttpContext):
    """`children` is the folder's contents, so it has to include what folders can now hold.

    It returned only sub-folders, images and files while the containers were unfileable;
    leaving it that way would have made a folder's contents list quietly incomplete.
    """
    ctx = authenticated_context
    folder = await seed.create_folder(ctx, "Mixed")
    await seed.create_image(ctx, "Img", folder)
    await seed.create_file(ctx, "raw.czi", folder)
    await _create_adataset(ctx, "Acquired", folder=folder)
    await _create_table(ctx, "Measurements", folder=folder)
    await _create_mesh(ctx, "v1", folder=folder)
    await _create_annotation_collection(ctx, "Drawn", folder=folder)

    result = await schema.execute(
        """
        query Children($parent: ID!) {
          children(parent: $parent) { __typename }
        }
        """,
        context_value=ctx,
        variable_values={"parent": str(folder.pk)},
    )
    assert not result.errors, result.errors
    assert result.data

    kinds = {child["__typename"] for child in result.data["children"]}
    assert kinds == {"Image", "File", "ADataset", "TableDataset", "MeshCollection", "AnnotationCollection"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_children_orders_and_searches_across_every_source(authenticated_context: HttpContext):
    """The `order` and `search` branches, which fan across all seven sources.

    Worth its own test because `children` builds its querysets from a table now, and both
    branches ask each source a question it has to be able to answer. `MeshCollection` is the
    one that cannot answer `name` -- it has no such column, it is identified by `version` --
    so it is ordered and searched by that instead. Without this test the rewrite was only
    ever exercised on the branch where neither runs.
    """
    ctx = authenticated_context
    folder = await seed.create_folder(ctx, "Sortable")
    await _create_adataset(ctx, "Beta", folder=folder)
    await _create_table(ctx, "Alpha", folder=folder)
    await _create_mesh(ctx, "v9", folder=folder)
    await _create_annotation_collection(ctx, "Gamma", folder=folder)

    ordered = await schema.execute(
        """
        query Children($parent: ID!, $order: ChildrenOrder) {
          children(parent: $parent, order: $order) { __typename }
        }
        """,
        context_value=ctx,
        variable_values={"parent": str(folder.pk), "order": {"field": "NAME", "direction": "ASC"}},
    )
    assert not ordered.errors, ordered.errors
    assert ordered.data
    assert len(ordered.data["children"]) == 4, "ordering by name must not drop the source that has no name column"

    by_created = await schema.execute(
        """
        query Children($parent: ID!, $order: ChildrenOrder) {
          children(parent: $parent, order: $order) { __typename }
        }
        """,
        context_value=ctx,
        variable_values={"parent": str(folder.pk), "order": {"field": "CREATED_AT", "direction": "DESC"}},
    )
    assert not by_created.errors, by_created.errors
    assert by_created.data
    assert len(by_created.data["children"]) == 4

    searched = await schema.execute(
        """
        query Children($parent: ID!, $filters: FolderChildrenFilter) {
          children(parent: $parent, filters: $filters) { __typename }
        }
        """,
        context_value=ctx,
        variable_values={"parent": str(folder.pk), "filters": {"search": "Alpha"}},
    )
    assert not searched.errors, searched.errors
    assert searched.data
    assert [c["__typename"] for c in searched.data["children"]] == ["TableDataset"], "search must reach the containers, and only match one here"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_containers_are_filterable_by_folder(authenticated_context: HttpContext):
    """`folder` and `folders` on each container filter, and they filter independently."""
    ctx = authenticated_context
    here = await seed.create_folder(ctx, "Here")
    there = await seed.create_folder(ctx, "There")

    await _create_adataset(ctx, "Mine", folder=here)
    await _create_adataset(ctx, "Theirs", folder=there)
    await _create_table(ctx, "MyTable", folder=here)
    await _create_table(ctx, "TheirTable", folder=there)

    result = await schema.execute(
        """
        query ByFolder($here: ID!, $both: [ID!]) {
          here: adatasets(filters: {folder: $here}) { name }
          both: adatasets(filters: {folders: $both}) { name }
          tables: tableDatasets(filters: {folder: $here}) { name }
        }
        """,
        context_value=ctx,
        variable_values={"here": str(here.pk), "both": [str(here.pk), str(there.pk)]},
    )
    assert not result.errors, result.errors
    assert result.data

    assert [d["name"] for d in result.data["here"]] == ["Mine"]
    assert {d["name"] for d in result.data["both"]} == {"Mine", "Theirs"}
    assert [t["name"] for t in result.data["tables"]] == ["MyTable"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_deleting_a_folder_takes_what_is_filed_in_it(authenticated_context: HttpContext):
    """`on_delete=CASCADE`, matching `Image.folder`, and worth pinning down because it bites.

    Deleting a folder now destroys the containers filed in it -- and it does so through the
    database relation, so the per-object delete guards (`self_owner` on `deleteADataset`)
    never run. That was already true of images; it is a wider blast radius now that a
    dataset and its arrays can be on the other end. If this should become SET_NULL, this is
    the test that says so out loud.

    All four, not just a dataset: the failure this guards against is not "does CASCADE
    work" -- it does -- but "does a PROTECT FK pointing at a container turn folder deletion
    into a ProtectedError". `AnnotationCollection` is the one to watch, since it holds a
    PROTECT reference to its coordinate system.
    """
    ctx = authenticated_context
    folder = await seed.create_folder(ctx, "Doomed")

    dataset = await _create_adataset(ctx, "GoesWithIt", folder=folder)
    table = await _create_table(ctx, "AlsoGoes", folder=folder)
    mesh = await _create_mesh(ctx, "v1", folder=folder)
    collection = await _create_annotation_collection(ctx, "AndThis", folder=folder)

    await sync_to_async(models.Folder.objects.filter(pk=folder.pk).delete)()

    assert not await models.ADataset.objects.filter(pk=dataset["id"]).aexists()
    assert not await models.TableDataset.objects.filter(pk=table["id"]).aexists()
    assert not await models.MeshCollection.objects.filter(pk=mesh["id"]).aexists()
    assert not await models.AnnotationCollection.objects.filter(pk=collection["id"]).aexists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_filing_says_nothing_about_placement(authenticated_context: HttpContext):
    """Two datasets in one folder share no space, and one dataset's folder is not its system.

    The point of the whole feature: `folder` is organisational and the coordinate graph is
    geometric. If these two ever start informing each other, this test is the one that
    should fail first.
    """
    ctx = authenticated_context
    folder = await seed.create_folder(ctx, "One Folder")

    first = await _create_adataset(ctx, "First", folder=folder)
    second = await _create_adataset(ctx, "Second", folder=folder)

    result = await schema.execute(
        """
        query Systems($a: ID!, $b: ID!) {
          a: adataset(id: $a) { folder { id } intrinsicSystem { id } }
          b: adataset(id: $b) { folder { id } intrinsicSystem { id } }
        }
        """,
        context_value=ctx,
        variable_values={"a": first["id"], "b": second["id"]},
    )
    assert not result.errors, result.errors
    assert result.data

    a, b = result.data["a"], result.data["b"]
    assert a["folder"]["id"] == b["folder"]["id"], "same folder"
    assert a["intrinsicSystem"]["id"] != b["intrinsicSystem"]["id"], "sharing a folder must not mean sharing a space"
