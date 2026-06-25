"""Custom GraphQL scalars.

Each scalar is a plain ``NewType`` used in annotations across types, inputs
and filters; the matching GraphQL definition lives in :data:`SCALAR_MAP`,
which the schema registers via ``StrawberryConfig(scalar_map=...)`` in
``mikro_server/schema.py`` (the deprecated class-wrapping ``strawberry.scalar``
form is gone).
"""

from typing import NewType

import strawberry
from strawberry.types.scalar import ScalarDefinition

ArrayLike = NewType("ArrayLike", str)
ImageLike = NewType("ImageLike", str)
LabelsLike = NewType("LabelsLike", str)
RGBAColor = NewType("RGBAColor", list)
UntypedPlateChild = NewType("UntypedPlateChild", object)
FileLike = NewType("FileLike", str)
ImageFileLike = NewType("ImageFileLike", str)
MeshLike = NewType("MeshLike", str)
StructureString = NewType("StructureString", str)
ParquetLike = NewType("ParquetLike", str)
Matrix = NewType("Matrix", object)
MikroStore = NewType("MikroStore", str)
Milliseconds = NewType("Milliseconds", float)
Micrometers = NewType("Micrometers", float)
Microliters = NewType("Microliters", float)
Micrograms = NewType("Micrograms", float)
FourByFourMatrix = NewType("FourByFourMatrix", object)
FiveDVector = NewType("FiveDVector", list)
FourDVector = NewType("FourDVector", list)
ThreeDVector = NewType("ThreeDVector", list)
TwoDVector = NewType("TwoDVector", list)
UntypedRender = NewType("UntypedRender", object)
Metric = NewType("Metric", object)
MetricMap = NewType("MetricMap", object)
Any = NewType("Any", object)


def _identity(v: object) -> object:
    """Pass-through serialization: these scalars carry their JSON value unchanged."""
    return v


def _definition(name: str, description: str) -> ScalarDefinition:
    """A pass-through ScalarDefinition for :data:`SCALAR_MAP`."""
    return strawberry.scalar(name=name, description=description, serialize=_identity, parse_value=_identity)


SCALAR_MAP: dict[object, ScalarDefinition] = {
    ArrayLike: _definition("ArrayLike", "The `ArrayLike` scalar type represents a reference to a store previously created by the user n a datalayer"),
    ImageLike: _definition("ImageLike", "The `ImageLike` scalar type represents a reference to an image previously created by the user in a datalayer"),
    LabelsLike: _definition("LabelsLike", "The `LabelsLike` scalar type represents a reference to a labels object previously created by the user n a datalayer"),
    RGBAColor: _definition("RGBAColor", "The Color scalar type represents a color as a list of 4 values RGBA"),
    UntypedPlateChild: _definition("UntypedPlateChild", "The `UntypedPlateChild` scalar type represents a plate child"),
    FileLike: _definition("FileLike", "The `FileLike` scalar type represents a reference to a big file storage previously created by the user n a datalayer"),
    ImageFileLike: _definition("ImageFileLike", "The `ImageFileLike` scalar type represents a reference to a snapshot image previously created by the user n a datalayer"),
    MeshLike: _definition("MeshLike", "The `MeshLike` scalar type represents a reference to a mesh previously created by the user n a datalayer"),
    StructureString: _definition("StructureString", "The `StructureString` scalar type represents a reference to a strucutre outside of this service previously created by the user n a datalayer"),
    ParquetLike: _definition("ParquetLike", "The `ParquetLike` scalar type represents a reference to a parquet objected stored previously created by the user on a datalayer"),
    Matrix: _definition("Matrix", "The `Matrix` scalar type represents a matrix values as specified by"),
    MikroStore: _definition("MikroStore", "The `MikroStore` scalar type represents a matrix values as specified by"),
    Milliseconds: _definition("Milliseconds", "The `Matrix` scalar type represents a matrix values as specified by"),
    Micrometers: _definition("Micrometers", "The `Micrometers` scalar type represents a matrix valuesas specified by"),
    Microliters: _definition("Microliters", "The `Microliters` scalar type represnts a volume of liquidas specified by"),
    Micrograms: _definition("Micrograms", "The `Micrograms` scalar type represents a mass of a substance"),
    FourByFourMatrix: _definition("FourByFourMatrix", "The `FourByFourMatrix` scalar type represents a matrix values as specified by"),
    FiveDVector: _definition("FiveDVector", "The `Vector` scalar type represents a matrix values as specified by"),
    FourDVector: _definition("FourDVector", "The `Vector` scalar type represents a matrix values as specified by"),
    ThreeDVector: _definition("ThreeDVector", "The `Vector` scalar type represents a matrix values as specified by"),
    TwoDVector: _definition("TwoDVector", "The `Vector` scalar type represents a matrix values as specified by"),
    UntypedRender: _definition("UntypedRender", "The `UntypedRender` scalar type represents a matrix values as specified by"),
    Metric: _definition("Metric", "The `Metric` scalar type represents a matrix values as specified by"),
    MetricMap: _definition("MetricMap", "The `MetricMap` scalar type represents a matrix values as specified by"),
    Any: _definition("Any", "The `Any` scalar any type"),
}
