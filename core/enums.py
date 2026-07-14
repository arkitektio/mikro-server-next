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


class TransformKindChoices(TextChoices):
    """The RFC-5 transformation kinds. One table, discriminated by this column.

    Replaces the former ``TransformationKind`` (``AFFINE`` / ``NON_AFFINE``), which
    was never referenced by a model, a migration or a resolver.

    ``UNMAPPABLE`` is ours, not RFC-5's, and it is the only kind that asserts a
    *non*-correspondence: every other kind says how a point maps, and there was no
    way to say that none does. Without it, data whose geometry a task destroyed --
    a phasor array whose arrival-time axis collapsed, a per-object measurement --
    could only be recorded by lying with an IDENTITY or by recording nothing at
    all, and recording nothing loses the lineage with it.
    """

    IDENTITY = "IDENTITY", "Identity"
    SCALE = "SCALE", "Scale"
    TRANSLATION = "TRANSLATION", "Translation"
    MAP_AXIS = "MAP_AXIS", "Map Axis"
    AFFINE = "AFFINE", "Affine"
    ROTATION = "ROTATION", "Rotation"
    SEQUENCE = "SEQUENCE", "Sequence"
    BY_DIMENSION = "BY_DIMENSION", "By Dimension"
    DISPLACEMENTS = "DISPLACEMENTS", "Displacements"
    COORDINATES = "COORDINATES", "Coordinates"
    BIJECTION = "BIJECTION", "Bijection"
    UNMAPPABLE = "UNMAPPABLE", "Unmappable (a declared non-correspondence)"


class CoordinateSystemKindChoices(TextChoices):
    """What a coordinate system denotes: voxel indices, the dataset's pixel grid, a calibrated physical space, or a shared space."""

    ARRAY = "ARRAY", "Array (voxel index space of one pyramid level or lens)"
    INTRINSIC = "INTRINSIC", "Intrinsic (the dataset's level-0 pixel grid)"
    PHYSICAL = "PHYSICAL", "Physical (a calibrated space derived from metadata)"
    WORLD = "WORLD", "World (a scene's shared space)"
    ATLAS = "ATLAS", "Atlas (a shared reference space)"
    MESH = "MESH", "Mesh (the space a mesh collection's vertices are expressed in)"
    FEATURE = "FEATURE", "Feature (a table's row space: rows are objects, not positions)"


class AxisTypeChoices(TextChoices):
    """The semantic axis types, inspired by RFC-5's.

    ``MICROTIME`` and ``SPECTRUM`` are ours, not RFC-5's; the spec explicitly
    permits types beyond its own enum. There is deliberately no ``ARRAY`` type:
    whether an axis holds pixel indices or physical positions is a property of its
    *system* (kind and unit nullability), and keeping the semantic types on every
    system is what makes render-axis derivation work anywhere in the graph.
    """

    SPACE = "SPACE", "Space"
    TIME = "TIME", "Time"
    CHANNEL = "CHANNEL", "Channel"
    COORDINATE = "COORDINATE", "Coordinate"
    DISPLACEMENT = "DISPLACEMENT", "Displacement"
    MICROTIME = "MICROTIME", "Microtime (FLIM arrival-time bin)"
    SPECTRUM = "SPECTRUM", "Spectrum (wavelength bin)"
    INDEX = "INDEX", "Index (an enumeration with no metric: an object id, a row number)"


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
    NORMAL = "normal", "Normal (Alpha Over)"


class LayerKindChoices(TextChoices):
    IMAGE = "image", "Image (array data)"
    SHAPE = "shape", "Shape (ROI geometry)"
    POINT = "point", "Point (tabular point cloud)"
    TRACK = "track", "Track (tabular trajectories)"
    MESH = "mesh", "Mesh (3D surface)"


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
    NORMAL = "normal"


_describe(
    Blending,
    ADDITIVE="Additive blending, where the color values of overlapping layers are summed.",
    MULTIPLICATIVE="Multiplicative blending, where the color values of overlapping layers are multiplied.",
    NORMAL="Alpha-over compositing: the layer is blended over the layers below using its opacity.",
)


@strawberry.enum(description="The kind of a layer, discriminating which data source it renders and which rendering settings apply.")
class LayerKind(str, Enum):
    """The kind of a layer, discriminating which data source it renders and which rendering settings apply."""

    IMAGE = "image"
    SHAPE = "shape"
    POINT = "point"
    TRACK = "track"
    MESH = "mesh"


_describe(
    LayerKind,
    IMAGE="An image layer rendering array (lens) data through a composable render graph.",
    SHAPE="A shape layer rendering the vector geometry of a data ROI (polygons, boxes, ellipses, lines, paths).",
    POINT="A point layer rendering a point cloud (e.g. SMLM localisations, centroids) from columns of a table.",
    TRACK="A track layer rendering trajectories from columns of a table, grouped by a track id.",
    MESH="A mesh layer rendering a 3D surface reconstruction.",
)


@strawberry.enum(description="The render recipe a bootstrapped scene stages over its dataset: which default image layer createSceneFromDataset builds.")
class BootstrapLayerKind(str, Enum):
    """The render recipe a bootstrapped scene stages over its dataset.

    An input-only vocabulary for `createSceneFromDataset` (never a DB column, so a
    strawberry enum only): the layer it names is an ordinary image layer whose
    render graph carries the recipe. When omitted, the kind is inferred from the
    dataset's axes -- and inference is a default, not a truth: a wrong guess costs
    one `updateLayer`, never a migration.
    """

    RGB = "rgb"
    INTENSITY = "intensity"
    VOLUME = "volume"
    LABEL = "label"


_describe(
    BootstrapLayerKind,
    RGB="Composite three channels as red, green and blue. Inferred for a 2D dataset whose channel axis has exactly three positions -- a photograph, a brightfield slide.",
    INTENSITY="One colormapped source per channel, additively blended (grey for a single channel). The fluorescence default, and the fallback when nothing else is inferred.",
    VOLUME="The channel sources under a maximum-intensity projection over z. Inferred when the dataset has a z axis with more than one plane.",
    LABEL="A single categorical source mapping discrete integer labels to distinct colors. Never inferred -- nothing structural distinguishes a label map from an image, so it is override-only.",
)


@strawberry.enum(description="The 3D projection / rendering mode applied to a volumetric (z-stacked) render node.")
class ProjectionMode(str, Enum):
    """The 3D projection / rendering mode applied to a volumetric (z-stacked) render node.

    This lives only inside a layer's render_graph JSON (never a DB column), so it
    is a strawberry enum only, with no Django TextChoices twin.
    """

    MIP = "mip"
    ATTENUATED_MIP = "attenuated_mip"
    VOLUME = "volume"
    ISOSURFACE = "isosurface"


_describe(
    ProjectionMode,
    MIP="Maximum intensity projection: each output pixel takes the maximum value along the z-axis.",
    ATTENUATED_MIP="Attenuated maximum intensity projection, weighting samples by depth so nearer samples dominate.",
    VOLUME="Alpha volume rendering: samples along z are alpha-composited front-to-back.",
    ISOSURFACE="Isosurface rendering: a surface is extracted at a threshold value.",
)


@strawberry.enum(description="What a phasor render node derives a pixel's color from.")
class PhasorColorMode(str, Enum):
    """What a phasor render node derives a pixel's color from.

    A phasor reduces a pixel's profile to a point (g, s); this says which property of
    that point becomes the hue. Over a MICROTIME axis PHASE and MODULATION are the two
    apparent lifetimes -- tau_phi and tau_m -- which differ exactly when the decay is
    not a single exponential; over a SPECTRUM axis the same phase is a spectral centre
    of mass. That is why this is not named after either reading.

    Lives only inside a layer's render_graph JSON (never a DB column), so it is a
    strawberry enum only, with no Django TextChoices twin.
    """

    PHASE = "phase"
    MODULATION = "modulation"
    AVERAGE = "average"


_describe(
    PhasorColorMode,
    PHASE="The angle of the phasor. Over a microtime axis this is the phase lifetime (tau_phi); over a spectrum axis, the spectral centre of mass.",
    MODULATION="The modulus of the phasor. Over a microtime axis this is the modulation lifetime (tau_m); it exceeds tau_phi exactly when the decay is multi-exponential.",
    AVERAGE="The mean of the phase- and modulation-derived values.",
)


@strawberry.enum(description="The shape of a region selected in phasor space.")
class PhasorCursorKind(str, Enum):
    """The shape of a region selected in phasor space.

    Lives only inside a layer's render_graph JSON, so it is a strawberry enum only.
    """

    CIRCLE = "circle"
    POLYGON = "polygon"


_describe(
    PhasorCursorKind,
    CIRCLE="A disc, given by its centre (g, s) and a radius.",
    POLYGON="An arbitrary closed region, given by at least three (g, s) vertices.",
)


@strawberry.enum(description="What a coordinate system denotes: voxel indices, the dataset's pixel grid, a calibrated physical space, or a space shared between datasets.")
class CoordinateSystemKind(str, Enum):
    """What a coordinate system denotes: voxel indices, the dataset's pixel grid, a calibrated physical space, or a shared space."""

    ARRAY = "ARRAY"
    INTRINSIC = "INTRINSIC"
    PHYSICAL = "PHYSICAL"
    WORLD = "WORLD"
    ATLAS = "ATLAS"
    MESH = "MESH"
    FEATURE = "FEATURE"


_describe(
    CoordinateSystemKind,
    ARRAY="The raw voxel index space of a single pyramid level or lens. Its axes are unitless indices.",
    INTRINSIC="The dataset's level-0 pixel grid. Every pyramid level and lens maps into this one system, so it is the space in which a dataset's geometry is unambiguous — and it is stable: recalibrating the dataset never moves it.",
    PHYSICAL="A calibrated physical space derived from metadata (pixel size, stage pose, ...). Its axes carry the units; a single transformation edge maps the dataset's intrinsic pixels into it. A dataset can have zero or many.",
    WORLD="A scene's shared space, into which each of its layers is registered.",
    ATLAS="A reference space shared across scenes, e.g. an anatomical atlas.",
    MESH="The space a mesh collection's vertex coordinates are expressed in. The collection owns it, and an edge relates it to the dataset the meshes were extracted from — usually an identity, but a mesh extracted from a downsampled grid is a scale, and that is a fact the edge can carry and a borrowed system could not.",
    FEATURE="A feature table's row space: its rows are objects, not positions, so its one axis enumerates rather than measures. Nothing maps a pixel to a row, which is why the edge relating it to the image it came from is UNMAPPABLE.",
)


@strawberry.enum(description="The semantic kind of an axis. A system's axes must be ordered by type: time first, then channel and custom types, then space.")
class AxisType(str, Enum):
    """The semantic kind of an axis, inspired by RFC-5."""

    SPACE = "SPACE"
    TIME = "TIME"
    CHANNEL = "CHANNEL"
    COORDINATE = "COORDINATE"
    DISPLACEMENT = "DISPLACEMENT"
    MICROTIME = "MICROTIME"
    SPECTRUM = "SPECTRUM"
    INDEX = "INDEX"


_describe(
    AxisType,
    INDEX="An enumerating axis with no metric: an object id, a row number. It has no unit because there is nothing to measure — the distance between object 3 and object 4 means nothing.",
    SPACE="A spatial axis. Unitless pixel indices in an INTRINSIC/ARRAY system; carries a physical length unit in a calibrated system.",
    TIME="A time axis. Frame indices in an INTRINSIC/ARRAY system; carries a physical duration unit in a calibrated system.",
    CHANNEL="A categorical channel axis: its coordinates index acquisitions, not positions. Never downsampled.",
    COORDINATE="An axis of a coordinate-valued array (as used by a displacement field's target).",
    DISPLACEMENT="An axis of a displacement-valued array.",
    MICROTIME="A FLIM arrival-time bin. Continuous, so a pyramid may re-bin it, and a phasor may be taken over it.",
    SPECTRUM="A wavelength bin of a spectrally resolved acquisition. Continuous -- unlike a CHANNEL axis, whose coordinates index acquisitions rather than positions -- so a pyramid may re-bin it, and a phasor may be taken over it.",
)


@strawberry.enum(description="The kind of a coordinate transformation, discriminating how its parameters are interpreted. Direction is always forward: input -> output.")
class TransformKind(str, Enum):
    """The kind of a coordinate transformation, discriminating how its parameters are interpreted."""

    IDENTITY = "IDENTITY"
    SCALE = "SCALE"
    TRANSLATION = "TRANSLATION"
    MAP_AXIS = "MAP_AXIS"
    AFFINE = "AFFINE"
    ROTATION = "ROTATION"
    SEQUENCE = "SEQUENCE"
    BY_DIMENSION = "BY_DIMENSION"
    DISPLACEMENTS = "DISPLACEMENTS"
    COORDINATES = "COORDINATES"
    BIJECTION = "BIJECTION"
    UNMAPPABLE = "UNMAPPABLE"


_describe(
    TransformKind,
    IDENTITY="The identity map. Input and output coordinates are the same.",
    SCALE="A per-axis multiplication. Its `scale` has one entry per input axis.",
    TRANSLATION="A per-axis offset. Its `translation` has one entry per input axis.",
    MAP_AXIS="A permutation of axes, mapping each input axis to an output axis by name.",
    AFFINE="A general affine map, given as an M x (N+1) matrix with rows outermost.",
    ROTATION="A rotation, given as an orthonormal matrix.",
    SEQUENCE="An ordered composition of child transformations, applied first to last.",
    BY_DIMENSION="A composition of child transformations, each acting on a named subset of the axes.",
    DISPLACEMENTS="A non-affine map given by a displacement field: a Zarr array of per-point OFFSETS. Not invertible in closed form, so a placement path never walks it backwards.",
    COORDINATES="A non-affine map given by a coordinate field: a Zarr array of absolute output POSITIONS, where DISPLACEMENTS stores offsets. Not invertible in closed form.",
    BIJECTION="A pair of child transformations giving an explicit forward and inverse map. This is how an inverse that cannot be derived is instead *given*.",
    UNMAPPABLE="A declared NON-correspondence: the two systems are related — one was derived from the other — and no point of either maps to a point of the other. It carries no parameters, is constrained by no rank, has no matrix, and is never walked by a placement search, in either direction. Recording an IDENTITY instead would be a lie; recording nothing would lose the lineage.",
)


@strawberry.enum(description="Whether a layer has a place in its scene's world, and if not, why not. Derived, never stored.")
class PlacementState(str, Enum):
    """Whether a layer has a place in its scene's world, and if not, why not."""

    PLACED = "PLACED"
    UNREGISTERED = "UNREGISTERED"
    UNMAPPABLE = "UNMAPPABLE"


_describe(
    PlacementState,
    PLACED="The layer's data reaches the scene's world: `pathToWorld` is the route.",
    UNREGISTERED="Nothing yet relates this layer's data to the scene's world. `pathToWorld` is null because the registration is *missing* — this is a gap in the data, and authoring the edge closes it.",
    UNMAPPABLE="This layer's data can never be placed: it reaches the world only across an UNMAPPABLE edge, which declares that no point correspondence exists. `pathToWorld` is null because there is nothing to find — badge it, and do not go looking for the missing registration.",
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
