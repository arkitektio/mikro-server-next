"""What a sparse group states about itself, read back off the artifact.

`createSparseDataset` declares no encoding, no shape and no chunking -- all three are read here,
when the upload is finished, because a fact derived from the artifact cannot be declared wrong.
Which makes this function the one place those facts can be got wrong, and every branch in it a
refusal that is otherwise silent much later, in a reader.

`tests/test_sparse_datasets.py` patches `fill_info` away -- correctly, since a group-backed store
does real S3 work where `ParquetStore.fill_info` does none -- so nothing there reaches this code
at all. That gap is not hypothetical: `get_sparse_metadata` referred to `models` without the
deferred import its neighbours all have, and the first bytes ever to reach it raised `NameError`
against a live server. The stub below is only `get_object`; everything else is the real parse.

The load-bearing case is :func:`test_an_indptr_that_disagrees_with_the_shape_is_refused`. Zarr
writes a group's attributes when the group is created rather than last, so unlike a fabriks
manifest their presence proves nothing about the arrays. Checking `indptr` against the declared
shape is the whole of what covers that difference.
"""

import io
import json

import pytest

from datalayer.datalayer import Datalayer


def _array(nelements: int, dtype: str = "float32", chunk: int = 32_768) -> dict:
    """A zarr v3 array's `zarr.json`, cut down to the keys this reads."""
    return {
        "zarr_format": 3,
        "node_type": "array",
        "shape": [nelements],
        "data_type": dtype,
        "chunk_grid": {"name": "regular", "configuration": {"chunk_shape": [chunk]}},
    }


def _group(encoding: str = "csr_matrix", shape: tuple[int, int] = (4, 3)) -> dict:
    """The group's own `zarr.json`, in the spelling anndata writes."""
    return {
        "zarr_format": 3,
        "node_type": "group",
        "attributes": {"encoding-type": encoding, "encoding-version": "0.1.0", "shape": list(shape)},
    }


class _Store:
    """Enough of a `SparseStore` for the read: it is addressed by its path."""

    path = "s3://zarr/some-prefix"
    key = "some-prefix"


class _S3:
    """Serves the fabricated `zarr.json` bodies, and 404s anything not written."""

    def __init__(self, tree: dict[str, dict]) -> None:
        self.tree = tree

    def get_object(self, Bucket: str, Key: str) -> dict:  # noqa: N803 -- boto3's spelling
        assert Bucket == "zarr"
        suffix = Key[len("some-prefix/") :]
        if suffix not in self.tree:
            raise FileNotFoundError(Key)
        return {"Body": io.BytesIO(json.dumps(self.tree[suffix]).encode())}


def _layer(tree: dict[str, dict]) -> Datalayer:
    layer = Datalayer()
    layer._s3 = _S3(tree)
    return layer


def _tree(encoding: str = "csr_matrix", shape: tuple[int, int] = (4, 3), nnz: int = 5, indptr: int | None = None) -> dict:
    """A complete, consistent sparse group -- the baseline each refusal below breaks one way."""
    axis = 0 if encoding == "csr_matrix" else 1
    return {
        "zarr.json": _group(encoding, shape),
        "data/zarr.json": _array(nnz),
        "indices/zarr.json": _array(nnz, dtype="int32"),
        "indptr/zarr.json": _array(shape[axis] + 1 if indptr is None else indptr, dtype="int32", chunk=shape[axis] + 1),
    }


def test_a_complete_group_reads_back_what_it_states() -> None:
    """The happy path, and the one that would have caught the missing import."""
    metadata = _layer(_tree()).get_sparse_metadata(_Store())

    assert metadata.encoding == "csr_matrix"
    assert metadata.encoding_version == "0.1.0"
    assert metadata.shape == [4, 3]
    assert metadata.nnz == 5
    assert metadata.dtype == "float32"
    assert metadata.chunks == {"data": 32_768, "indices": 32_768, "indptr": 5}


def test_the_other_layout_indexes_the_other_axis() -> None:
    """`indptr` is one per column for CSC, and the check has to follow the encoding."""
    metadata = _layer(_tree(encoding="csc_matrix")).get_sparse_metadata(_Store())

    assert metadata.encoding == "csc_matrix"
    assert metadata.shape == [4, 3]


def test_a_prefix_with_no_group_metadata_is_refused() -> None:
    """What an upload that never started looks like."""
    with pytest.raises(FileNotFoundError, match="not a readable sparse store"):
        _layer({}).get_sparse_metadata(_Store())


def test_a_missing_array_is_refused() -> None:
    """And what one that stopped partway looks like: attributes present, arrays not."""
    tree = _tree()
    del tree["indptr/zarr.json"]

    with pytest.raises(FileNotFoundError, match="not a readable sparse store"):
        _layer(tree).get_sparse_metadata(_Store())


def test_a_group_with_no_encoding_type_is_refused() -> None:
    """Without it there is nothing to derive `indexed_axis` from, so nothing can use the store."""
    tree = _tree()
    tree["zarr.json"]["attributes"].pop("encoding-type")

    with pytest.raises(ValueError, match="declares encoding-type None"):
        _layer(tree).get_sparse_metadata(_Store())


def test_an_unknown_encoding_is_refused() -> None:
    """COO is a sparse encoding and not one of these two: it has no `indptr` to range-read."""
    tree = _tree()
    tree["zarr.json"]["attributes"]["encoding-type"] = "coo_matrix"

    with pytest.raises(ValueError, match="csc_matrix', 'csr_matrix"):
        _layer(tree).get_sparse_metadata(_Store())


def test_a_single_array_is_refused_as_a_zarr_store() -> None:
    """A sparse matrix is a group; the refusal names where a single array belongs instead."""
    tree = _tree()
    tree["zarr.json"] = _array(5)

    with pytest.raises(ValueError, match="register it as one"):
        _layer(tree).get_sparse_metadata(_Store())


def test_a_shape_that_is_not_two_axes_is_refused() -> None:
    """N-D sparse is not built; a declared 3-axis shape is a store nothing here can read."""
    tree = _tree()
    tree["zarr.json"]["attributes"]["shape"] = [4, 3, 2]

    with pytest.raises(ValueError, match="exactly two axes"):
        _layer(tree).get_sparse_metadata(_Store())


def test_values_and_indices_of_different_lengths_are_refused() -> None:
    """They are parallel arrays: one written and not the other is a torn upload."""
    tree = _tree(nnz=5)
    tree["indices/zarr.json"] = _array(4, dtype="int32")

    with pytest.raises(ValueError, match="stopped partway"):
        _layer(tree).get_sparse_metadata(_Store())


def test_an_indptr_that_disagrees_with_the_shape_is_refused() -> None:
    """The check that covers what zarr's attribute timing cannot.

    Everything else here can be satisfied by a group created and then abandoned. `indptr` is
    written with the data, and its length is fixed by the declared shape, so the two disagreeing
    is the one signal that separates a finished matrix from a half-written one.
    """
    tree = _tree(shape=(4, 3), indptr=4)  # csr over 4 rows wants 5 entries, not 4

    with pytest.raises(ValueError, match="disagree about what this matrix is"):
        _layer(tree).get_sparse_metadata(_Store())


def test_the_indptr_check_follows_the_encoding_rather_than_the_first_axis() -> None:
    """A CSC group whose `indptr` is sized for the rows is the layout mix-up, caught here."""
    tree = _tree(encoding="csc_matrix", shape=(4, 3), indptr=5)  # 5 is right for csr, wrong for csc

    with pytest.raises(ValueError, match="holds 4 entries"):
        _layer(tree).get_sparse_metadata(_Store())
