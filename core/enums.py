from django.db.models import TextChoices
import strawberry
from enum import Enum


@strawberry.enum
class ScopeKind(str, Enum):
    PUBLIC = "public"
    ORG = "org"
    SHARED = "shared"
    ME = "me"


class ImageKind(TextChoices):
    """Variety expresses the Type of Representation we are dealing with"""

    MASK = "MASK", "Mask (Value represent Labels)"
    VOXEL = "VOXEL", "Voxel (Value represent Intensity)"
    RGB = "RGB", "RGB (First three channel represent RGB)"
    UNKNOWN = "UNKNOWN", "Unknown"


class PlacementStatus(TextChoices):
    """The status of a placement indicates whether it is active, inactive, deleted, or archived. This can be used to filter placements when querying the database and to determine which placements should be displayed in the user interface."""

    ACTIVE = "ACTIVE", "Active"
    INACTIVE = "INACTIVE", "Inactive"
    DELETED = "DELETED", "Deleted"
    ARCHIVED = "ARCHIVED", "Archived"


class PlacementValidity(TextChoices):
    """The status of a placement indicates whether it is active, inactive, deleted, or archived. This can be used to filter placements when querying the database and to determine which placements should be displayed in the user interface."""

    MANUAL = "MANUAL", "Manual"
    INFERRED = "INFERRED", "Inferred from Metadata"
    VALIDATED = "VALIDATED", "Validated by User"
    UNKNOWN = "UNKNOWN", "Unknown"


class ProvenanceAction(TextChoices):
    CREATE = "CREATE", "Create"
    UPDATE = "UPDATE", "Update"
    DELETE = "DELETE", "Delete"
    RELATE = "RELATE", "Relate"


class TransformationKind(TextChoices):
    AFFINE = "AFFINE", "Affine"
    NON_AFFINE = "NON_AFFINE", "Non Affine"


class InstanceKind(TextChoices):
    LOT = "LOT", "Lot"
    BATCH = "BATCH", "Batch"
    SINGLE = "SINGLE", "Single"
    UNKNOWN = "UNKNOWN", "Unknown"


class ColorMapChoices(TextChoices):
    VIRIDIS = "viridis"
    PLASMA = "plasma"
    INFERNO = "inferno"
    MAGMA = "magma"
    RED = "red"
    GREEN = "green"
    BLUE = "blue"
    CYAN = "cyan"
    MAGENTA = "magenta"
    YELLOW = "yellow"
    BLACK = "black"
    WHITE = "white"
    ORANGE = "orange"
    PURPLE = "purple"
    PINK = "pink"
    BROWN = "brown"
    GREY = "grey"
    RAINBOW = "rainbow"
    SPECTRAL = "spectral"
    COOL = "cool"
    WARM = "warm"
    INTENSITY = "intensity"


class BlendingChoices(TextChoices):
    ADDITIVE = "additive", "Additive"
    MULTIPLICATIVE = "multiplicative", "Multiplicative"


class RoiKindChoices(TextChoices):
    ELLIPSIS = "ellipse", "Ellipse"
    POLYGON = "polygon", "POLYGON"
    LINE = "line", "Line"

    # Rectangular Types
    RECTANGLE = "rectangle", "Rectangle (XY)"
    SPECTRAL_RECTANGLE = "spectral_rectangle", "Spectral Rectangle (XYC)"
    TEMPORAL_RECTANGLE = "temporal_rectangle", "Temporal Rectangle (XYT)"
    CUBE = "cube", "Cube (XYZ)"
    SPECTRAL_CUBE = "spectral_cube", "Spectral Cube (XYZC)"
    TEMPORAL_CUBE = "temporal_cube", "Temporal Cube (XYZT)"
    HYPERCUBE = "hypercube", "Hypercube (XYZT)"
    SPECTRAL_HYPERCUBE = "spectral_hypercube", "Spectral Hypercube (XYZTC)"

    # Path Types
    PATH = "path", "Path"
    UNKNOWN = "unknown", "Unknown"

    FRAME = "frame", "Frame"
    SLICE = "slice", "Slice"
    POINT = "point", "Point"


class ContinousScanDirection(TextChoices):
    ROW_COLUMN_SLICE = "row_column_slice", "Row -> Column -> Slice"
    COLUMN_ROW_SLICE = "column_row_slice", "Column -> Row -> Slice"
    SLICE_ROW_COLUMN = "slice_row_column", "Slice -> Row -> Column"

    ROW_COLUMN_SLICE_SNAKE = "row_column_slice_snake", "Row -> Column -> Slice (Snake)"
    COLUMN_ROW_SLICE_SNAKE = "column_row_slice_snake", "Column -> Row -> Slice (Snake)"
    SLICE_ROW_COLUMN_SNAKE = "slice_row_column_snake", "Slice -> Row -> Column (Snake)"


@strawberry.enum
class ColorFormat(str, Enum):
    RGB = "RGB"
    HSL = "HSL"


@strawberry.enum
class ColorMap(str, Enum):
    VIRIDIS = "viridis"
    PLASMA = "plasma"
    INFERNO = "inferno"
    MAGMA = "magma"
    RED = "red"
    GREEN = "green"
    BLUE = "blue"
    INTENSITY = "intensity"
    CYAN = "cyan"
    MAGENTA = "magenta"
    YELLOW = "yellow"
    BLACK = "black"
    WHITE = "white"
    ORANGE = "orange"
    PURPLE = "purple"
    PINK = "pink"
    BROWN = "brown"
    GREY = "grey"
    RAINBOW = "rainbow"
    SPECTRAL = "spectral"
    COOL = "cool"
    WARM = "warm"


@strawberry.enum
class Blending(str, Enum):
    ADDITIVE = "additive"
    MULTIPLICATIVE = "multiplicative"


@strawberry.enum
class SpatialUnit(str, Enum):
    MICROMETERS = "micrometers"
    NANOMETERS = "nanometers"
    ANGSTROMS = "angstroms"
    PIXELS = "pixels"
    UNKNOWN = "unknown"


@strawberry.enum
class TemporalUnit(str, Enum):
    NANOSECONDS = "nanoseconds"
    MILLISECONDS = "milliseconds"
    SECONDS = "seconds"
    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"
    UNKNOWN = "unknown"


@strawberry.enum
class DuckDBDataType(Enum):
    BOOLEAN = strawberry.enum_value("BOOLEAN", description="Represents a True/False value")
    TINYINT = strawberry.enum_value("TINYINT", description="Very small integer (-128 to 127)")
    SMALLINT = strawberry.enum_value("SMALLINT", description="Small integer (-32,768 to 32,767)")
    INTEGER = strawberry.enum_value("INTEGER", description="Standard integer (-2,147,483,648 to 2,147,483,647)")
    BIGINT = strawberry.enum_value("BIGINT", description="Large integer for large numeric values")
    HUGEINT = strawberry.enum_value("HUGEINT", description="Extremely large integer for very large numeric ranges")
    FLOAT = strawberry.enum_value("FLOAT", description="Single-precision floating point number")
    DOUBLE = strawberry.enum_value("DOUBLE", description="Double-precision floating point number")
    VARCHAR = strawberry.enum_value("VARCHAR", description="Variable-length string (text)")
    BLOB = strawberry.enum_value("BLOB", description="Binary large object for storing binary data")
    TIMESTAMP = strawberry.enum_value("TIMESTAMP", description="Date and time with precision")
    DATE = strawberry.enum_value("DATE", description="Specific date (year, month, day)")
    TIME = strawberry.enum_value("TIME", description="Specific time of the day (hours, minutes, seconds)")
    INTERVAL = strawberry.enum_value("INTERVAL", description="Span of time between two dates or times")
    DECIMAL = strawberry.enum_value("DECIMAL", description="Exact decimal number with defined precision and scale")
    UUID = strawberry.enum_value(
        "UUID",
        description="Universally Unique Identifier used to uniquely identify objects",
    )
    VARCHAR_ARRAY = strawberry.enum_value("VARCHAR[]", description="Array of variable-length strings")
    DOUBLE_ARRAY = strawberry.enum_value("DOUBLE[]", description="Array of double-precision floating point numbers")
    BIGINT_ARRAY = strawberry.enum_value("BIGINT[]", description="Array of large integers")
    BIGINT_ARRAY_ARRAY = strawberry.enum_value("BIGINT[][]", description="2D Array of large integers")
    BOOLEAN_ARRAY = strawberry.enum_value("BOOLEAN[]", description="Array of boolean values")
    DATE_ARRAY = strawberry.enum_value("DATE[]", description="Array of dates")
    TIME_ARRAY = strawberry.enum_value("TIME[]", description="Array of times")
    LIST = strawberry.enum_value("LIST", description="A list of values of the same data type")
    MAP = strawberry.enum_value("MAP", description="A collection of key-value pairs where each key is unique")
    ENUM = strawberry.enum_value("ENUM", description="Enumeration of predefined values")
    STRUCT = strawberry.enum_value(
        "STRUCT",
        description="Composite type grouping several fields with different data types",
    )
    JSON = strawberry.enum_value(
        "JSON",
        description="JSON object, a structured text format used for representing data",
    )


@strawberry.enum
class ScanDirection(str, Enum):
    ROW_COLUMN_SLICE = "row_column_slice"
    COLUMN_ROW_SLICE = "column_row_slice"
    SLICE_ROW_COLUMN = "slice_row_column"

    ROW_COLUMN_SLICE_SNAKE = "row_column_slice_snake"
    COLUMN_ROW_SLICE_SNAKE = "column_row_slice_snake"
    SLICE_ROW_COLUMN_SNAKE = "slice_row_column_snake"


@strawberry.enum
class RoiKind(str, Enum):
    ELLIPSIS = "ellipse"
    POLYGON = "polygon"
    LINE = "line"

    # Rectangular Types
    RECTANGLE = "rectangle"
    SPECTRAL_RECTANGLE = "spectral_rectangle"
    TEMPORAL_RECTANGLE = "temporal_rectangle"
    CUBE = "cube"
    SPECTRAL_CUBE = "spectral_cube"
    TEMPORAL_CUBE = "temporal_cube"
    HYPERCUBE = "hypercube"
    SPECTRAL_HYPERCUBE = "spectral_hypercube"

    # Path Types
    PATH = "path"

    FRAME = ("frame",)
    SLICE = "slice"
    POINT = "point"


class DimensionKind(str, Enum):
    SPACE = "space"
    CHANNEL = "channel"
    TIME = "time"
    FREQUENCY = "frequency"
