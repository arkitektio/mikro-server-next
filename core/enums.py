from django.db.models import TextChoices
import strawberry
from enum import Enum, EnumMeta


def _describe(enum_cls: EnumMeta, **descriptions: str) -> None:
    """Attach SDL descriptions to the members of an already-decorated strawberry enum.

    ``strawberry.enum_value`` cannot be used on ``(str, Enum)`` classes: the str
    mixin bakes the definition object's repr into the member value before
    strawberry can unwrap it, silently corrupting every runtime comparison and
    Django write. Members therefore keep their plain string values and the
    descriptions are patched onto the strawberry definition afterwards.
    """
    values = {v.name: v for v in enum_cls.__strawberry_definition__.values}
    for name, description in descriptions.items():
        values[name].description = description


@strawberry.enum(description="The visibility scope of an object, determining which users can see it.")
class ScopeKind(str, Enum):
    """The visibility scope of an object, determining which users can see it."""

    PUBLIC = "public"
    ORG = "org"
    SHARED = "shared"
    ME = "me"


_describe(
    ScopeKind,
    PUBLIC="The object is visible to everyone.",
    ORG="The object is visible to everyone in the organization.",
    SHARED="The object is visible only to users it was explicitly shared with.",
    ME="The object is visible only to its creator.",
)


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


@strawberry.enum(description="The color space format used to interpret color component values.")
class ColorFormat(str, Enum):
    """The color space format used to interpret color component values."""

    RGB = "RGB"
    HSL = "HSL"


_describe(
    ColorFormat,
    RGB="Color expressed as red, green and blue components.",
    HSL="Color expressed as hue, saturation and lightness components.",
)


@strawberry.enum(description="The colormap used to map intensity values of a channel to display colors.")
class ColorMap(str, Enum):
    """The colormap used to map intensity values of a channel to display colors."""

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


_describe(
    ColorMap,
    VIRIDIS="The perceptually uniform viridis colormap, ranging from dark purple to yellow.",
    PLASMA="The perceptually uniform plasma colormap, ranging from dark blue to yellow.",
    INFERNO="The perceptually uniform inferno colormap, ranging from black through red to yellow.",
    MAGMA="The perceptually uniform magma colormap, ranging from black through purple to light yellow.",
    RED="A monochromatic colormap from black to pure red.",
    GREEN="A monochromatic colormap from black to pure green.",
    BLUE="A monochromatic colormap from black to pure blue.",
    INTENSITY="A grayscale colormap mapping intensity values directly to brightness.",
    CYAN="A monochromatic colormap from black to cyan.",
    MAGENTA="A monochromatic colormap from black to magenta.",
    YELLOW="A monochromatic colormap from black to yellow.",
    BLACK="A colormap rendering all values as black.",
    WHITE="A monochromatic colormap from black to white.",
    ORANGE="A monochromatic colormap from black to orange.",
    PURPLE="A monochromatic colormap from black to purple.",
    PINK="A monochromatic colormap from black to pink.",
    BROWN="A monochromatic colormap from black to brown.",
    GREY="A grayscale colormap from black to white.",
    RAINBOW="A multi-hue rainbow colormap cycling through the visible spectrum.",
    SPECTRAL="A diverging colormap spanning the spectral colors from red to blue.",
    COOL="A colormap of cool tones ranging from cyan to magenta.",
    WARM="A colormap of warm tones ranging from yellow to red.",
)


@strawberry.enum(description="The blending mode used to combine multiple channels or layers into a composite image.")
class Blending(str, Enum):
    """The blending mode used to combine multiple channels or layers into a composite image."""

    ADDITIVE = "additive"
    MULTIPLICATIVE = "multiplicative"


_describe(
    Blending,
    ADDITIVE="Additive blending, where the color values of overlapping layers are summed.",
    MULTIPLICATIVE="Multiplicative blending, where the color values of overlapping layers are multiplied.",
)


@strawberry.enum(description="The physical unit used to express spatial dimensions, e.g. of pixel sizes or stage positions.")
class SpatialUnit(str, Enum):
    """The physical unit used to express spatial dimensions, e.g. of pixel sizes or stage positions."""

    MICROMETERS = "micrometers"
    NANOMETERS = "nanometers"
    ANGSTROMS = "angstroms"
    PIXELS = "pixels"
    UNKNOWN = "unknown"


_describe(
    SpatialUnit,
    MICROMETERS="Micrometers (1e-6 meters), the typical scale of cells in light microscopy.",
    NANOMETERS="Nanometers (1e-9 meters), the typical scale of subcellular structures.",
    ANGSTROMS="Angstroms (1e-10 meters), the typical scale of atomic and molecular structures.",
    PIXELS="Raw pixel units without a calibrated physical size.",
    UNKNOWN="The spatial unit is not known or not specified.",
)


@strawberry.enum(description="The physical unit used to express temporal dimensions, e.g. of time-lapse intervals.")
class TemporalUnit(str, Enum):
    """The physical unit used to express temporal dimensions, e.g. of time-lapse intervals."""

    NANOSECONDS = "nanoseconds"
    MILLISECONDS = "milliseconds"
    SECONDS = "seconds"
    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"
    UNKNOWN = "unknown"


_describe(
    TemporalUnit,
    NANOSECONDS="Nanoseconds (1e-9 seconds).",
    MILLISECONDS="Milliseconds (1e-3 seconds).",
    SECONDS="Seconds, the SI base unit of time.",
    MINUTES="Minutes (60 seconds).",
    HOURS="Hours (3600 seconds).",
    DAYS="Days (86400 seconds).",
    UNKNOWN="The temporal unit is not known or not specified.",
)


@strawberry.enum(description="The data type of a column in a DuckDB table, as used by tabular data stored alongside images.")
class DuckDBDataType(Enum):
    """The data type of a column in a DuckDB table, as used by tabular data stored alongside images."""

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


@strawberry.enum(description="The axis traversal order of a continuous scan, i.e. the order in which rows, columns and slices are acquired.")
class ScanDirection(str, Enum):
    """The axis traversal order of a continuous scan, i.e. the order in which rows, columns and slices are acquired."""

    ROW_COLUMN_SLICE = "row_column_slice"
    COLUMN_ROW_SLICE = "column_row_slice"
    SLICE_ROW_COLUMN = "slice_row_column"

    ROW_COLUMN_SLICE_SNAKE = "row_column_slice_snake"
    COLUMN_ROW_SLICE_SNAKE = "column_row_slice_snake"
    SLICE_ROW_COLUMN_SNAKE = "slice_row_column_snake"


_describe(
    ScanDirection,
    ROW_COLUMN_SLICE="Scan rows first, then columns, then slices (Row -> Column -> Slice).",
    COLUMN_ROW_SLICE="Scan columns first, then rows, then slices (Column -> Row -> Slice).",
    SLICE_ROW_COLUMN="Scan slices first, then rows, then columns (Slice -> Row -> Column).",
    ROW_COLUMN_SLICE_SNAKE="Scan rows, then columns, then slices, reversing direction on alternate lines (Row -> Column -> Slice, snake).",
    COLUMN_ROW_SLICE_SNAKE="Scan columns, then rows, then slices, reversing direction on alternate lines (Column -> Row -> Slice, snake).",
    SLICE_ROW_COLUMN_SNAKE="Scan slices, then rows, then columns, reversing direction on alternate lines (Slice -> Row -> Column, snake).",
)


@strawberry.enum(description="The geometric kind of a region of interest (ROI), defining how its vectors are interpreted.")
class RoiKind(str, Enum):
    """The geometric kind of a region of interest (ROI), defining how its vectors are interpreted."""

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

    FRAME = "frame"
    SLICE = "slice"
    POINT = "point"


_describe(
    RoiKind,
    ELLIPSIS="An elliptical region in the XY plane.",
    POLYGON="A closed polygon defined by a sequence of vertices.",
    LINE="A straight line between two points.",
    RECTANGLE="An axis-aligned rectangle in the XY plane.",
    SPECTRAL_RECTANGLE="A rectangle extended along the channel axis (XYC).",
    TEMPORAL_RECTANGLE="A rectangle extended along the time axis (XYT).",
    CUBE="A three-dimensional cuboid spanning the spatial axes (XYZ).",
    SPECTRAL_CUBE="A cuboid extended along the channel axis (XYZC).",
    TEMPORAL_CUBE="A cuboid extended along the time axis (XYZT).",
    HYPERCUBE="A four-dimensional region spanning space and time (XYZT).",
    SPECTRAL_HYPERCUBE="A five-dimensional region spanning space, time and channels (XYZTC).",
    PATH="An open path defined by a sequence of connected points.",
    FRAME="A single frame of the image, e.g. one timepoint.",
    SLICE="A single slice of the image, e.g. one Z plane.",
    POINT="A single point.",
)


class DimensionKind(str, Enum):
    SPACE = "space"
    CHANNEL = "channel"
    TIME = "time"
    FREQUENCY = "frequency"
