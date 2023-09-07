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


class RoiKind(TextChoices):
    ELLIPSIS = "ellipse", "Ellipse"
    POLYGON = "polygon", "POLYGON"
    LINE = "line", "Line"
    RECTANGLE = "rectangle", "Rectangle"
    PATH = "path", "Path"
    UNKNOWN = "unknown", "Unknown"

    FRAME = "frame", "Frame"
    SLICE = "slice", "Slice"
    POINT = "point", "Point"


@strawberry.enum
class ColorFormat(str, Enum):
    RGB = "RGB"
    HSL = "HSL"
