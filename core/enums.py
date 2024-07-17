from django.db.models import TextChoices
import strawberry
from enum import Enum


class ImageKind(TextChoices):
    """Variety expresses the Type of Representation we are dealing with"""

    MASK = "MASK", "Mask (Value represent Labels)"
    VOXEL = "VOXEL", "Voxel (Value represent Intensity)"
    RGB = "RGB", "RGB (First three channel represent RGB)"
    UNKNOWN = "UNKNOWN", "Unknown"


class ProvenanceAction(TextChoices):
    CREATE = "CREATE", "Create"
    UPDATE = "UPDATE", "Update"
    DELETE = "DELETE", "Delete"
    RELATE = "RELATE", "Relate"


class TransformationKind(TextChoices):
    AFFINE = "AFFINE", "Affine"
    NON_AFFINE = "NON_AFFINE", "Non Affine"



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



@strawberry.enum
class Blending(str, Enum):
    ADDITIVE = "additive"
    MULTIPLICATIVE = "multiplicative"



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

    FRAME = "frame",
    SLICE = "slice"
    POINT = "point"

