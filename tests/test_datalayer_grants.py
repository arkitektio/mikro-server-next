"""What a grant is scoped to, and why a prefix store needs a different one.

Nothing covered the policy builder before this. That mattered more than it looks: the two
halves of "this store is a directory" were stated in different places -- deletion read
`is_prefix` off the model, the grant builder tested `bucket_key == "zarr"` -- so they could
disagree, and the disagreement was **silent in both directions**. A prefix store granted an
object-scoped policy cannot list or write its own children; an object store granted a prefix
policy hands out more than it should. Neither raises, and in a deployment with no `role_arn`
configured no policy is attached at all, so nothing would surface until the day one is.

These tests read the policy document directly rather than asserting on a live S3, because the
document *is* the contract -- the same reason `test_store_purging` asserts against real bucket
contents where the bug it guards is a call that succeeded and deleted nothing.
"""

import pytest

from datalayer.datalayer import Datalayer
from datalayer.models import BigFileStore, DatalayerStore, MediaStore, FabriksStore, ParquetStore, ZarrStore


@pytest.fixture()
def layer(settings) -> Datalayer:
    """A datalayer with every logical bucket configured, pointing nowhere in particular."""
    settings.DATALAYER = {
        "access_key": "key",
        "secret_key": "secret",
        "host": "minio",
        "port": 9000,
        "protocol": "http",
        "bigfile": {"bucket": "files"},
        "media": {"bucket": "files"},
        "zarr": {"bucket": "arrays"},
        "parquet": {"bucket": "tables"},
    }
    return Datalayer()


def _statements(policy: dict) -> list[dict]:
    return policy["Statement"]  # type: ignore[return-value]


def test_the_prefix_buckets_are_derived_from_the_store_classes():
    """The set is a consequence of the models, not a literal anyone has to remember.

    `FabriksStore` is the evidence rather than the example: it joined this set by declaring
    `bucket_key` and `is_prefix = True` on the model, **without an edit to the grant builder**.
    Under the previous `bucket_key == "zarr"` test it would have been deleted correctly and
    granted credentials that could neither list nor write its own children -- and nothing would
    have raised, because a deployment with no role to assume attaches no policy at all, so the
    breakage only surfaces on the day one is configured.
    """
    assert Datalayer.prefix_bucket_keys() == {"zarr", "fabriks"}

    by_key = {subclass.bucket_key: subclass for subclass in DatalayerStore.__subclasses__()}
    assert set(by_key) == {"bigfile", "media", "zarr", "parquet", "fabriks"}, "every store type declares which bucket it belongs to"
    assert by_key["zarr"] is ZarrStore
    assert by_key["fabriks"] is FabriksStore
    assert [subclass.is_prefix for subclass in (BigFileStore, MediaStore, ParquetStore)] == [False, False, False]


def test_an_object_store_is_granted_exactly_its_own_key(layer: Datalayer):
    """One object, one resource, and no bucket listing -- a parquet is a single file."""
    policy = layer._build_policy("tables", "parquet", "abc123", "read")
    statements = _statements(policy)

    assert len(statements) == 1, "no ListBucket statement for a single object"
    assert statements[0]["Resource"] == ["arn:aws:s3:::tables/abc123"]
    assert statements[0]["Action"] == ["s3:GetObject"]


def test_a_prefix_store_is_granted_its_whole_tree_and_may_list_it(layer: Datalayer):
    """A zarr is a directory: the grant must cover the children and permit listing them.

    Without the `/*` resource a reader can fetch `zarr.json` and not one chunk; without the
    conditional `ListBucket` a client cannot discover what is there, which is also what any
    glob-based reader needs.
    """
    policy = layer._build_policy("arrays", "zarr", "abc123", "read")
    statements = _statements(policy)

    assert statements[0]["Resource"] == ["arn:aws:s3:::arrays/abc123", "arn:aws:s3:::arrays/abc123/*"]

    listing = statements[1]
    assert listing["Action"] == ["s3:ListBucket", "s3:GetBucketLocation"]
    assert listing["Resource"] == ["arn:aws:s3:::arrays"]
    assert listing["Condition"]["StringLike"]["s3:prefix"] == ["abc123", "abc123/*"]


def test_a_prefix_upload_may_read_back_and_delete_inside_its_own_tree(layer: Datalayer):
    """A tree is written incrementally, so the writer needs more than PutObject.

    It reads back and rewrites objects as it goes, and a failed multipart leaves garbage only
    DeleteObject can clear. An object upload gets neither, deliberately: there is nothing to
    read back and nothing to clean up but the one key.
    """
    prefix_upload = _statements(layer._build_policy("arrays", "zarr", "abc123", "upload"))[0]
    assert prefix_upload["Action"] == ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload"]

    object_upload = _statements(layer._build_policy("tables", "parquet", "abc123", "upload"))[0]
    assert object_upload["Action"] == ["s3:PutObject", "s3:AbortMultipartUpload"]


def test_a_fabriks_store_is_granted_its_whole_prefix_and_may_write_inside_it(layer: Datalayer, settings):
    """The fifth store type gets prefix treatment because of what it declares, not who it is."""
    settings.DATALAYER = {**settings.DATALAYER, "fabriks": {"bucket": "meshes"}}
    layer = Datalayer()

    read = _statements(layer._build_policy("meshes", "fabriks", "abc123", "read"))
    assert read[0]["Resource"] == ["arn:aws:s3:::meshes/abc123", "arn:aws:s3:::meshes/abc123/*"]
    assert read[1]["Action"] == ["s3:ListBucket", "s3:GetBucketLocation"], "a reader globs level partitions, so it must be able to list"

    upload = _statements(layer._build_policy("meshes", "fabriks", "abc123", "upload"))[0]
    assert "s3:DeleteObject" in upload["Action"], "a tree written incrementally needs to clean up after a failed part"


def test_every_store_type_has_an_organization_wide_read_grant(layer: Datalayer, settings):
    """`requestGeneral*Access` exists per store type, and fabriks is one of them.

    There is no single `requestGeneralAccess`: the grants are per logical bucket, because each
    names the bucket it is for and a client asks for the one it is about to read. So "does
    general access cover fabriks" is answered by there *being* a fabriks one -- and by the
    resolver being registered in the schema, which is a separate mistake to make.
    """
    settings.DATALAYER = {**settings.DATALAYER, "fabriks": {"bucket": "meshes"}}
    layer = Datalayer()

    grant = layer.generate_general_fabriks_access_grant(organization_id="1", user_id="1")

    assert grant.bucket == "meshes", "the grant names the bucket it is for"
    assert grant.access_key and grant.secret_key, "and carries usable credentials"
    assert grant.status == "granted"


def test_a_general_grant_refuses_a_bucket_the_deployment_has_not_configured(layer: Datalayer, settings):
    """`fabriks` is optional in the config, so asking for it unconfigured must say so.

    The alternative -- handing out credentials naming a bucket that does not exist -- fails
    later and further away, at whichever client tries to read through them.
    """
    settings.DATALAYER = {key: value for key, value in settings.DATALAYER.items() if key != "fabriks"}
    layer = Datalayer()

    with pytest.raises(ValueError, match="not configured"):
        layer.generate_general_fabriks_access_grant(organization_id="1", user_id="1")


def test_a_bucket_subpath_is_carried_into_the_grant(layer: Datalayer, settings):
    """Two logical buckets can share a physical one, so the subpath must reach the resource.

    `config.yaml` already points media and bigfile at the same bucket. Nothing sets `subpath`
    today, which is exactly why it is worth a test before something does.
    """
    settings.DATALAYER = {**settings.DATALAYER, "zarr": {"bucket": "arrays", "subpath": "meshes"}}
    layer = Datalayer()

    statements = _statements(layer._build_policy("arrays", "zarr", "abc123", "read"))
    assert statements[0]["Resource"] == ["arn:aws:s3:::arrays/meshes/abc123", "arn:aws:s3:::arrays/meshes/abc123/*"]
    assert statements[1]["Condition"]["StringLike"]["s3:prefix"] == ["meshes/abc123", "meshes/abc123/*"]
