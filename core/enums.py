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


class PlacementValidityChoices(TextChoices):
    """How much a transformation edge's map is actually known: guessed, inferred from metadata, authored by someone, or validated against the data. A layer's validity is derived from it -- the weakest edge on its path to world."""

    MANUAL = "MANUAL", "Manual"
    INFERRED = "INFERRED", "Inferred from Metadata"
    VALIDATED = "VALIDATED", "Validated by User"
    UNKNOWN = "UNKNOWN", "Unknown"


class ValueRelationChoices(TextChoices):
    """What a derivation did to the *values*: the axis the spatial kind deliberately says nothing about. A threshold is spatially IDENTITY with categorized values; a crop is value-identical."""

    IDENTICAL = "IDENTICAL", "Identical (the source's numbers)"
    TRANSFORMED = "TRANSFORMED", "Transformed (same quantity, new numbers)"
    CATEGORIZED = "CATEGORIZED", "Categorized (values became labels)"


class ScaleMethodChoices(TextChoices):
    """How a pyramid level's voxels were computed from the level above it.

    Stated, never derived: two arrays are all that survives a downsample, and nothing about
    the numbers in them says whether they were averaged or picked. It matters because the
    answer is not always allowed. Over an intensity image every one of these is a defensible
    choice; over an array whose values are *object ids* only the ones that return a value
    that was already there are -- the mean of ids 41 and 42 is 41.5, which is no object, and
    an image pyramid built that way paints a border of phantom objects along every boundary.
    """

    NEAREST = "NEAREST", "Nearest neighbour (one source voxel, unchanged)"
    MODE = "MODE", "Mode (the most frequent source voxel)"
    LINEAR = "LINEAR", "Linear interpolation"
    CUBIC = "CUBIC", "Cubic interpolation"
    AREA = "AREA", "Area average (the mean over the source window)"
    GAUSSIAN = "GAUSSIAN", "Gaussian-weighted average"
    MAX = "MAX", "Maximum of the source window"
    MIN = "MIN", "Minimum of the source window"


#: The methods a label pyramid may be built with: the ones whose output value was already a
#: value of the input. Everything else invents numbers, and an invented id is an object that
#: does not exist. MAX and MIN return a real id but not the *right* one -- they bias every
#: boundary toward whichever object happens to sort higher -- so they are excluded too: a
#: label downsample has to answer "which object is here", and only NEAREST and MODE do.
LABEL_COMPLIANT_SCALE_METHODS = frozenset({ScaleMethodChoices.NEAREST.value, ScaleMethodChoices.MODE.value})


class FileLinkDirectionChoices(TextChoices):
    """Which side of a file link was made from the other. Not derivable: nothing else records which existed first."""

    SOURCE = "SOURCE", "Source (the container was made from the file)"
    RENDITION = "RENDITION", "Rendition (the file was written from the container)"


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
    FIELD = "FIELD", "Field (a map given by the values of an array)"
    UNMAPPABLE = "UNMAPPABLE", "Unmappable (a declared non-correspondence)"


class ColumnRoleChoices(TextChoices):
    """What a table dataset's column is for: a coordinate that places the row, or data hanging off it."""

    COORDINATE = "COORDINATE", "Coordinate (a spatial/temporal column that becomes an axis of the table's space)"
    ATTRIBUTE = "ATTRIBUTE", "Attribute (a measurement or property column; data only)"
    ID = "ID", "Id (a per-row identifier)"
    TRACK_ID = "TRACK_ID", "Track id (groups rows into a trajectory)"
    LABEL = "LABEL", "Label (a per-row text label)"
    COLOR = "COLOR", "Color (a per-row color or value to color by)"


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
    # The qualitative half. Every member above maps an ordered value onto a ramp; these map an
    # unordered one onto a palette, which is what a categorical column needs and what
    # `classColors` used to carry as an explicit map the caller had to build itself.
    HUES = "hues"
    DISTINCT = "distinct"
    PASTEL = "pastel"
    VIVID = "vivid"


class BlendingChoices(TextChoices):
    ADDITIVE = "additive", "Additive"
    MULTIPLICATIVE = "multiplicative", "Multiplicative"
    NORMAL = "normal", "Normal (Alpha Over)"


class PreferredViewChoices(TextChoices):
    # TWO_D, not 2D: a python identifier cannot start with a digit.
    TWO_D = "two_d", "2D"
    THREE_D = "three_d", "3D"
    AUTO = "auto", "Auto"


class EasingChoices(TextChoices):
    LINEAR = "linear", "Linear"
    EASE_IN = "ease_in", "Ease in"
    EASE_OUT = "ease_out", "Ease out"
    EASE_IN_OUT = "ease_in_out", "Ease in-out"


class LayerKindChoices(TextChoices):
    IMAGE = "image", "Image (array data)"
    LABEL = "label", "Label (categorical array data)"
    ANNOTATION = "annotation", "Annotation (drawn geometry)"
    POINT = "point", "Point (tabular point cloud)"
    TRACK = "track", "Track (tabular trajectories)"
    MESH = "mesh", "Mesh (3D surface)"


class MeshShadingChoices(TextChoices):
    """How a mesh surface is lit. A DB column on `Layer`, so it needs this twin as well as the strawberry enum."""

    FLAT = "flat", "Flat (one normal per face)"
    SMOOTH = "smooth", "Smooth (interpolated vertex normals)"
    PBR = "pbr", "Physically based (metallic-roughness)"
    MATCAP = "matcap", "Matcap (a lit sphere texture, view-space)"
    UNLIT = "unlit", "Unlit (the material colour, unshaded)"


class AnnotationKindChoices(TextChoices):
    """The shapes an annotation can be drawn as.

    Deliberately *not* ``RoiKindChoices``, which an annotation borrowed while ROI was still
    the drawing model. That vocabulary is written for a fixed (c,t,z,y,x) image -- it spells
    a box six ways (``spectral_rectangle`` "XYC", ``temporal_cube`` "XYZT",
    ``spectral_hypercube`` "XYZTC") because the axes it could span were known in advance. An
    annotation lives in an arbitrary N-D coordinate system with named axes and no c/t/z
    privilege, so which axes a box spans is a property of the coordinate system it is drawn
    in, never of the shape. What is left is the geometry: a box, a round thing, a run of
    points.

    ``ELLIPSE`` also corrects ``RoiKindChoices.ELLIPSIS``, which named the shape after
    Python's ``...``. The stored value is unchanged, so only the member name moves.
    """

    # Points and runs of points.
    POINT = "point", "Point"
    MULTI_POINT = "multi_point", "Multi-point"
    LINE = "line", "Line"
    PATH = "path", "Path"
    POLYGON = "polygon", "Polygon"

    # Boxes, stored as two opposite corners (see `assert_shape_vectors`). Rectangle and cube
    # are kept apart because the vertex count differs, not because the axes are named.
    RECTANGLE = "rectangle", "Rectangle"
    CUBE = "cube", "Cube"

    # Round kinds, also stored as the two opposite corners of their bounding box.
    CIRCLE = "circle", "Circle"
    ELLIPSE = "ellipse", "Ellipse"
    SPHERE = "sphere", "Sphere"
    ELLIPSOID = "ellipsoid", "Ellipsoid"


@strawberry.enum(description="The color space format used to interpret color component values.")
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
    HUES = "hues"
    DISTINCT = "distinct"
    PASTEL = "pastel"
    VIVID = "vivid"


#: The colormaps that map an *unordered* value onto a colour rather than an ordered one onto a
#: ramp. A categorical column takes one of these and a measure column takes one of the others,
#: which is the same rule the column's role has always decided -- it used to be spelled
#: "a colormap or a `classColors` map", and a qualitative colormap is what that map always was.
#:
#: Every one is a golden-ratio hue scatter over the value's rank, so consecutive classes land far
#: apart on the hue wheel and nothing has to enumerate the classes to assign them colours. They
#: differ only in saturation and value, and the names are the viewer's own
#: (`orkestrator-next`'s `INSTANCE_COLORMAPS`), so a palette named here is a palette it already
#: draws.
QUALITATIVE_COLORMAPS = frozenset({ColorMap.HUES, ColorMap.DISTINCT, ColorMap.PASTEL, ColorMap.VIVID})


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
    HUES="Qualitative. A colour per distinct value, scattered around the hue wheel by the golden ratio so consecutive classes land far apart. The default categorical palette, and the one the id hash itself paints with.",
    DISTINCT="Qualitative. The hue scatter with saturation and value tiered by rank as well, so two classes that happen to land on nearby hues still separate -- a palette-free take on glasbey. Reach for it when a mask has many classes.",
    PASTEL="Qualitative. The hue scatter at low saturation, for a colouring meant to sit under something else rather than carry the picture.",
    VIVID="Qualitative. The hue scatter at full saturation, for a colouring meant to carry the picture.",
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


@strawberry.enum(description="How a viewer should open a scene: flat, volumetric, or its own choice.")
class PreferredView(str, Enum):
    """How a viewer should open a scene.

    A statement about how to *look*, which is why it sits on the scene rather than in a
    layer's render graph: that graph says what the pixels are (and its projection node
    collapses z), never where the eye goes.

    A preference, not a constraint. A viewer that cannot render volumes shows the slice
    view and is not wrong to; nothing downstream reads this.
    """

    TWO_D = "two_d"
    THREE_D = "three_d"
    AUTO = "auto"


_describe(
    PreferredView,
    TWO_D="Open flat: the cross-section view, one slice at a time.",
    THREE_D="Open volumetric: the projection view, looking at the data as a body.",
    AUTO="No preference stated -- the viewer decides, e.g. from whether the data has a z axis with depth. The default: a scene nobody has expressed a preference for should not claim one.",
)


@strawberry.enum(description="How a viewer eases the camera along the travel into an animation waypoint.")
class Easing(str, Enum):
    """How a viewer eases the camera along the travel into a waypoint.

    The curve applied over the waypoint's ``durationMs``, not a duration of its own.
    """

    LINEAR = "linear"
    EASE_IN = "ease_in"
    EASE_OUT = "ease_out"
    EASE_IN_OUT = "ease_in_out"


_describe(
    Easing,
    LINEAR="Constant speed the whole way. Right for a leg in the middle of a continuous move, where an ease would read as a stutter.",
    EASE_IN="Start slow, arrive at full speed. Right for the first leg, pulling away from rest.",
    EASE_OUT="Start at full speed, arrive slowly. Right for the last leg, settling onto the final pose.",
    EASE_IN_OUT="Slow at both ends, quick in the middle. The default: it reads as deliberate on a leg that stands alone.",
)


@strawberry.enum(description="The kind of a layer, discriminating which data source it renders and which rendering settings apply.")
class LayerKind(str, Enum):
    """The kind of a layer, discriminating which data source it renders and which rendering settings apply."""

    IMAGE = "image"
    LABEL = "label"
    ANNOTATION = "annotation"
    POINT = "point"
    TRACK = "track"
    MESH = "mesh"


_describe(
    LayerKind,
    IMAGE="An image layer rendering array (lens) data through a composable render graph.",
    LABEL="A label layer rendering array (lens) data whose values are discrete object ids -- a segmentation or instance map. It shares the image layer's source but none of its render settings: contrast limits, gamma, colormaps and intensity projections are all meaningless over ids, and what it carries instead is an id-to-color hashing, a transparent background id, contour-or-fill, a selection, and an optional `colorBy` dereferencing the FIELD edge that keys the mask's pixels to a table of objects.",
    ANNOTATION="An annotation layer rendering the drawn vector geometry (polygons, boxes, ellipses, lines, paths) of an annotation collection.",
    POINT="A point layer rendering a point cloud (e.g. SMLM localisations, centroids) from columns of a table.",
    TRACK="A track layer rendering trajectories from columns of a table, grouped by a track id.",
    MESH="A mesh layer rendering a 3D surface reconstruction.",
)


@strawberry.enum(
    description="Which kind of control a column admits, derived from its declared role. The one split that decides how a value becomes a colour and how it is filtered -- published here so a picker renders the control the write path will actually accept."
)
class ColumnControl(str, Enum):
    """Which kind of control a column admits, derived from its declared role."""

    MEASURE = "MEASURE"
    CATEGORICAL = "CATEGORICAL"


_describe(
    ColumnControl,
    MEASURE="The values are measured and ordered, so they take a colormap over their range and a `min`/`max` bound. Roles COORDINATE and ATTRIBUTE.",
    CATEGORICAL="The values name things rather than measuring them, so they take an explicit value-to-colour map and a `values` set. A colormap or a bound over them would impose an order they do not have. Roles ID, TRACK_ID, LABEL and COLOR.",
)


@strawberry.enum(description="How a mesh surface is lit. Vocabulary a mesh needs and an image has no use for: a raster has no normals to shade with, which is why this sits on the mesh layer rather than anywhere near a render graph.")
class MeshShading(str, Enum):
    """How a mesh surface is lit."""

    FLAT = "flat"
    SMOOTH = "smooth"
    PBR = "pbr"
    MATCAP = "matcap"
    UNLIT = "unlit"


_describe(
    MeshShading,
    FLAT="One normal per face, so every facet reads as a facet. Honest about a decimated surface: it shows the triangles the geometry actually has rather than smoothing them away.",
    SMOOTH="Interpolated vertex normals, so the surface reads as curved. The default, and the one that flatters an isosurface.",
    PBR="A metallic-roughness material lit by the viewer's environment. Costs more and looks like a rendering rather than a measurement -- reach for it for a figure, not for reading data.",
    MATCAP="A pre-lit sphere texture sampled in view space. Lighting does not move with the camera, which makes shape easy to read and comparisons between two views fair.",
    UNLIT="No lighting at all: every fragment takes the material colour or the colour-by value. The right choice when the colour *is* the measurement and shading would be read as one.",
)


@strawberry.enum(description="The render recipe an image layer carries: which default graph createSceneFromCoordinateSystem builds, via `ScenePolicyInput.kind`.")
class BootstrapLayerKind(str, Enum):
    """The render recipe an image layer carries.

    An input-only vocabulary for `ScenePolicyInput.kind` (never a DB column, so a
    strawberry enum only): the layer it names is an ordinary image layer whose
    render graph carries the recipe. When omitted, the kind is inferred per source
    from the data's axes -- and inference is a default, not a truth: a wrong guess
    costs one `updateLayer`, never a migration.
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
    LABEL="A single categorical source mapping discrete integer labels to distinct colors. Never inferred from structure -- nothing about an array distinguishes a label map from an image -- so it comes either from a derivation declared CATEGORIZED or from stating it outright.",
)


@strawberry.enum(description="The kind of layer a lens could source, for narrowing a picker: the two members of `LayerKind` that draw array data. Input-only, and deliberately not `LayerKind` itself -- an annotation, point, track or mesh layer sources from a collection or a table, never from a lens, so four of that enum's members could only ever answer 'no'.")
class LensLayerKind(str, Enum):
    """The kind of layer a lens could source.

    An input-only vocabulary for `LensFilter.placeableIn.asLayer` (never a DB column,
    so a strawberry enum only). It narrows a candidate list, it does not decide
    anything: `createLayer` and `createLabelLayer` both take any lens they can draw,
    and neither reads this.
    """

    IMAGE = "image"
    LABEL = "label"


_describe(
    LensLayerKind,
    IMAGE="Drawable as an image layer -- which is every lens with an x and a y axis of more than one pixel. It is the renderability gate alone, and deliberately *not* the complement of LABEL: a mask drawn through a render graph is a legitimate thing to want, and `createLayer` does not refuse one.",
    LABEL="Drawable as a label layer: renderable, and derived by an edge declaring CATEGORIZED -- the values became object ids. The same signal `createSceneFromCoordinateSystem` infers a label layer from, asked of a candidate instead of a source, so a picker and a bootstrapped scene cannot disagree about what a label is.",
)


@strawberry.enum(description="What a dataset structurally is, materialized from the axes of its intrinsic coordinate system at creation. Specs stack: a 3D timelapse is VOLUME, TIMESERIES and MULTICHANNEL at once. Exactly one spatial member (SCALAR/PROFILE/IMAGE/VOLUME/HYPERVOLUME) ever holds.")
class ArrayDatasetSpec(str, Enum):
    """What a dataset structurally is, materialized from its axes at creation.

    A strawberry enum only, no Django TextChoices twin: it is never chosen or
    validated at a boundary. The values are stored raw on `ArrayDataset.stored_spec`,
    materialized from the intrinsic axes when they are written (see
    `core.logic.graph.create_pixel_axes`) and read back through `ArrayDataset.spec`.
    Storing it is safe -- unlike `CoordinateSystem.kind`, which is still derived
    from ownership on every read -- precisely because the axes are immutable: a
    value computed from immutable inputs cannot disagree with its source. The
    single source of truth for the derivation stays `core.logic.coords.specs_for_axes`.

    Presence, never size: a dataset with a z axis is a VOLUME whether or not z has
    depth, and TIMESERIES means it has a time axis, not that it has more than one
    frame. This is deliberately *not* the rule `core.logic.scene._infer_kind` uses
    -- that one asks what to render and a flat z is worth collapsing there; this
    one asks what the data is, and a one-plane stack is still a stack.
    """

    SCALAR = "SCALAR"
    PROFILE = "PROFILE"
    IMAGE = "IMAGE"
    VOLUME = "VOLUME"
    HYPERVOLUME = "HYPERVOLUME"
    TIMESERIES = "TIMESERIES"
    MULTICHANNEL = "MULTICHANNEL"
    SPECTRAL = "SPECTRAL"
    FLIM = "FLIM"


_describe(
    ArrayDatasetSpec,
    SCALAR="No spatial extent: the array carries no SPACE axis at all.",
    PROFILE="One spatial axis -- a line profile, a depth trace.",
    IMAGE="Two spatial axes: a plane. The ordinary micrograph.",
    VOLUME="Three spatial axes: a stack. Holds whenever a z axis is present, even if it carries a single plane.",
    HYPERVOLUME="Four or more spatial axes.",
    TIMESERIES="Carries a TIME axis -- a timelapse. Presence only: a single-frame time axis still counts.",
    MULTICHANNEL="Carries a CHANNEL axis. Presence only: a one-channel axis still counts.",
    SPECTRAL="Carries a SPECTRUM axis: a spectrally resolved acquisition, a lambda stack.",
    FLIM="Carries a MICROTIME axis: fluorescence-lifetime arrival-time bins.",
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


@strawberry.enum(description="What a table dataset's column is for: a coordinate that places the row, or data hanging off it.")
class ColumnRole(str, Enum):
    """What a table dataset's column is for."""

    COORDINATE = "COORDINATE"
    ATTRIBUTE = "ATTRIBUTE"
    ID = "ID"
    TRACK_ID = "TRACK_ID"
    LABEL = "LABEL"
    COLOR = "COLOR"


_describe(
    ColumnRole,
    COORDINATE="A spatial or temporal column whose values are coordinates. The coordinate columns become the axes of the table's own coordinate system, which is what makes the table placeable.",
    ATTRIBUTE="A measurement or property column — area, an intensity, a marker level. Data only; it does not place the row.",
    ID="A per-row identifier.",
    TRACK_ID="Groups rows into a trajectory. Required to render a table as tracks.",
    LABEL="A per-row text label.",
    COLOR="A per-row color, or a value a layer colors the rows by.",
)


@strawberry.enum(description="The semantic kind of an axis. An array's axes must be ordered by type -- time first, then channel and custom types, then space -- because an array's axis order is its store's dimension order. A table's are not: a parquet column's position is arbitrary, so its coordinate columns are stored in the order they are declared.")
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
    SPACE="A spatial axis. Unitless pixel indices in a pixel-grid system; carries a physical length unit in a unit-carrying system.",
    TIME="A time axis. Frame indices in a pixel-grid system; carries a physical duration unit in a unit-carrying system.",
    CHANNEL="A categorical channel axis: its coordinates index acquisitions, not positions. Never downsampled.",
    COORDINATE="The value axis of a coordinate-valued array: its positions enumerate the components of an absolute output position. This is what makes the array readable as the `field` of a FIELD edge. A scalar-valued field (a label mask, whose one value is an object id) carries no value axis at all -- absent means scalar, and scalar means COORDINATE.",
    DISPLACEMENT="The value axis of a displacement-valued array: its positions enumerate the components of a per-point OFFSET, where COORDINATE enumerates absolute positions. Stating it here rather than on the edge is deliberate: it is a property of the array, and an array that says it twice can disagree with itself.",
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
    FIELD = "FIELD"
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
    FIELD="A non-affine map given by the values of an array rather than by a formula. The array is a `field`: a coordinate system, and so a node of this graph, not a payload on this edge. Whether its values are absolute POSITIONS or per-point OFFSETS is read from the value axis of that node -- COORDINATE or DISPLACEMENT -- never restated here. A label mask is the case where the field IS the input: its own pixels are the map. Not invertible in closed form, so a placement path never walks it backwards -- which is also the right semantics for a dereference, an object being a set of pixels.",
    UNMAPPABLE="A declared NON-correspondence: the two systems are related — one was derived from the other — and no point of either maps to a point of the other. It carries no parameters, is constrained by no rank, has no matrix, and is never walked by a placement search, in either direction. Recording an IDENTITY instead would be a lie; recording nothing would lose the lineage.",
)


@strawberry.enum(description="The kind of a transformation a client can author directly: the discriminator of `TransformInput`. SEQUENCE is absent on purpose -- it is a wrapper the ingest builds together with its children (pyramid levels, stepped lenses), never authored empty.")
class CreatableTransformKind(str, Enum):
    """The directly-creatable subset of :class:`TransformKind`, used only by inputs."""

    IDENTITY = "IDENTITY"
    SCALE = "SCALE"
    TRANSLATION = "TRANSLATION"
    MAP_AXIS = "MAP_AXIS"
    AFFINE = "AFFINE"
    ROTATION = "ROTATION"
    BY_DIMENSION = "BY_DIMENSION"
    FIELD = "FIELD"
    UNMAPPABLE = "UNMAPPABLE"


_describe(
    CreatableTransformKind,
    IDENTITY="The identity map. Input and output coordinates are the same, so it takes no parameters.",
    SCALE="A per-axis multiplication. Takes `scale`, one entry per input axis.",
    TRANSLATION="A per-axis offset. Takes `translation`, one entry per input axis.",
    MAP_AXIS="A permutation of axes, mapping each input axis to an output axis by name. Takes `inputAxes` and `outputAxes`; the matrix is synthesized from them.",
    AFFINE="A general affine map. Takes `affine`, an M x (N+1) matrix with rows outermost.",
    ROTATION="A rotation. Takes `affine`: the orthonormal matrix, in the same layout an AFFINE uses.",
    BY_DIMENSION="A map acting on a named subset of the axes and saying nothing about the rest. Takes `inputAxes` and `outputAxes`, and optionally `scale`, `translation` or `affine` acting on the named axes.",
    FIELD="A non-affine map given by the values of an array rather than by a formula. Takes `field` (the array's coordinate system), `inputAxes` and `outputAxes`.",
    UNMAPPABLE="A declared NON-correspondence: no point of either space maps to a point of the other. Takes only an optional `reason`.",
)


@strawberry.enum(
    description=(
        "Which kind of thing a derivation names as the source its data was computed from: the discriminator of `DerivedFromInput`. The edge itself is the same whichever is chosen -- "
        "child space in, source space out -- so a table named as TABLE_DATASET and the same table named as COORDINATE_SYSTEM write the identical row; the read side reports what "
        "lives at the far end through `CoordinateSystem.residents`, not which member was used to say it"
    )
)
class DerivationSourceKind(str, Enum):
    """Which kind of thing a derivation names as the source its data was computed from."""

    LENS = "LENS"
    DATASET = "DATASET"
    TABLE_DATASET = "TABLE_DATASET"
    MESH_COLLECTION = "MESH_COLLECTION"
    ANNOTATION_COLLECTION = "ANNOTATION_COLLECTION"
    COORDINATE_SYSTEM = "COORDINATE_SYSTEM"


_describe(
    DerivationSourceKind,
    LENS="A selection over an array dataset, and the preferred way to name one: a lens' own edge back to its dataset already carries the crop, so pointing at it gets the rest of the chain for free.",
    DATASET="An array dataset as a whole, through its intrinsic pixel grid. Use it when the source is the entire image and there is no lens worth minting.",
    TABLE_DATASET="A table dataset, through the space its coordinate columns declare -- the direction an image reconstructed from a table of SMLM localizations is derived. A table with no coordinate columns enumerates objects rather than places them, and its only honest edge is UNMAPPABLE.",
    MESH_COLLECTION="A mesh collection, through its vertex coordinate system.",
    ANNOTATION_COLLECTION="An annotation collection, through the space its shapes are drawn in.",
    COORDINATE_SYSTEM="A coordinate system directly, when the source is a space rather than a container -- a physical space, or a world.",
)


@strawberry.enum(
    description=(
        "Which sort of source a colouring reads its value from: the discriminator of `LabelColorByInput` and `MeshColorByInput`. Two members, because there are two ways a set of ids "
        "reaches a number -- a column of a table they key into, or one slice of a sparse matrix they index. Flat with a discriminator rather than an input union, which GraphQL has no "
        "such thing as; the fields the other member reads are refused rather than ignored"
    )
)
class ColorSourceKind(str, Enum):
    """Which sort of source a colouring reads its value from."""

    COLUMN = "COLUMN"
    SPARSE = "SPARSE"


_describe(
    ColorSourceKind,
    COLUMN="A column of a table the source's ids key into, reached by `table`, `column` and any `joinPath`. Every colouring written before sparse datasets existed is one of these, which is why it is the default.",
    SPARSE="One slice of a sparse matrix the source's ids index, reached by `dataset` and the position `at`. Always measured: a slice is a value per object, so it takes a colormap and never a class map.",
)


@strawberry.enum(
    description=(
        "How one axis is identified -- the discriminator of `IdentificationInput`, and the same question whether the axis belongs to a sparse matrix or to a table. An axis of "
        "positions means nothing until something says what those positions *are*, and there are exactly these three ways to answer. Two of them author a FIELD edge, which is "
        "also what makes the data reachable from a layer over that source; `TABLE` authors none and states a foreign key instead, because a table is already in record-land"
    )
)
class IdentificationKind(str, Enum):
    """How one axis is identified, for a sparse dataset or a table alike."""

    DATASET = "DATASET"
    MESH_COLLECTION = "MESH_COLLECTION"
    TABLE = "TABLE"


_describe(
    IdentificationKind,
    DATASET="A label mask, through its intrinsic pixel grid: its pixel values are the positions along this axis. Authors a FIELD edge, so it is also what makes the data reachable from a layer over that mask.",
    MESH_COLLECTION="A mesh collection, through its vertex coordinate system: the ids ride on the geometry rows, so a client that picked a surface is already holding one. Authors a FIELD edge, exactly as DATASET does.",
    TABLE="A table whose rows this axis' positions are -- the relation `Column.references` carries, said of the axis. Authors no edge and touches no coordinate system: a table is already in record-land, where the relation is a foreign key rather than a map between spaces. It is what lets a FIELD edge land beside it, because an axis identified this way is one the edge is not expected to supply. Valid on an INDEX axis only: a SPACE or TIME coordinate's values are positions, and a position in nanometres and a row id are different things.",
)


@strawberry.enum(
    description=(
        "Which geometric properties survive a coordinate transformation. A nested hierarchy -- each class preserves strictly less than the one above it -- so the class of a "
        "composed path is the weakest of its steps. Derived from a transformation's `kind`, never stored: a column could contradict the parameters, and the parameters would be right."
    )
)
class TransformInvariance(str, Enum):
    """Which geometric properties survive a transformation. Derived from `kind`, never stored.

    Declared strongest to weakest, so the SDL reads as the nesting it describes.

    ``AFFINE`` here and ``TransformKind.AFFINE`` share the string ``"AFFINE"``. They are
    distinct GraphQL types and a comparison mixing them would silently succeed, so a
    classifier must dispatch on the kind first and never round-trip through this enum.
    """

    ISOMETRY = "ISOMETRY"
    SIMILARITY = "SIMILARITY"
    AFFINE = "AFFINE"
    DIFFEOMORPHIC = "DIFFEOMORPHIC"
    NONE = "NONE"


_describe(
    TransformInvariance,
    ISOMETRY="Distances, angles and areas all transfer unchanged: a length measured on one side IS that length on the other. An identity, a translation, a rotation, an axis permutation.",
    SIMILARITY="Angles and length *ratios* transfer; every absolute length scales by one common factor. A circle is still a circle, just a different size -- so anything dimensionless carries across untouched, and anything measured needs the one factor.",
    AFFINE="Parallelism and area *ratios* transfer; angles and distances do not. A square may arrive a parallelogram, so an angle or a length read on one side means nothing on the other. Stated for every AFFINE edge, including one whose matrix happens to be rigid: telling those apart needs an SVD, which is numerics inside a metadata answer -- the same line the graph draws when it declines to catch a singular affine.",
    DIFFEOMORPHIC="Topology at best, and only locally: the Jacobian varies with position, so no distance, angle, area or ratio survives anywhere. A ceiling, not a guarantee -- a FIELD is many-to-one on purpose (an object is a set of pixels), and such a map is not a diffeomorphism at all.",
    NONE="Nothing corresponds. On an edge, an UNMAPPABLE: a declared non-correspondence. On a layer, no path to the world at all -- `placement` says which of the two reasons applies.",
)


@strawberry.enum(description="How much a transformation edge's map is actually known: guessed, inferred from metadata, authored by someone, or validated against the data. A layer's validity is derived from it, never stored: the weakest edge on its path to world.")
class PlacementValidity(str, Enum):
    """How much a transformation edge's map is actually known."""

    MANUAL = "MANUAL"
    INFERRED = "INFERRED"
    VALIDATED = "VALIDATED"
    UNKNOWN = "UNKNOWN"


_describe(
    PlacementValidity,
    MANUAL="Someone authored this map -- a registration pipeline, a human with a matrix. It exists on purpose, but nothing has checked it against the data.",
    INFERRED="The numbers were read from acquisition metadata (a pixel size, a stage pose). As right as the metadata is.",
    VALIDATED="Exact or checked: either the server derived the map from shapes and slices, so it cannot be wrong, or someone validated an authored registration against the data.",
    UNKNOWN="This map was assumed, never measured -- badge it. The server writes it nowhere: nothing fabricates a placement any more, so an edge wears UNKNOWN only because a client said so on `createTransformation`, or because it is a historical auto-registered edge.",
)


@strawberry.enum(description="What a derivation did to the values -- the axis the spatial kind says nothing about. A threshold is spatially IDENTITY with categorized values; a crop is value-identical. Stated on the derivation edge (one event, one row, two orthogonal statements); the algorithm and its parameters belong to task provenance, not here.")
class ValueRelation(str, Enum):
    """What a derivation did to the values, orthogonal to its spatial kind."""

    IDENTICAL = "IDENTICAL"
    TRANSFORMED = "TRANSFORMED"
    CATEGORIZED = "CATEGORIZED"


@strawberry.enum(description="How a pyramid level's voxels were computed from the level above it. Stated, never derived -- nothing about two arrays says whether one was averaged or picked out of the other -- and it matters because over an array of object ids only NEAREST and MODE are allowed: every other method returns numbers that were not in the input, and an invented id is an object that does not exist.")
class ScaleMethod(str, Enum):
    """How a pyramid level's voxels were computed from the level above it."""

    NEAREST = "NEAREST"
    MODE = "MODE"
    LINEAR = "LINEAR"
    CUBIC = "CUBIC"
    AREA = "AREA"
    GAUSSIAN = "GAUSSIAN"
    MAX = "MAX"
    MIN = "MIN"


_describe(
    ScaleMethod,
    NEAREST="One source voxel, carried through unchanged. Label-safe: the value was already there.",
    MODE="The most frequent value in the source window. Label-safe, and the better of the two for a mask -- it keeps the object that actually dominates the window rather than whichever one the sampling grid happens to land on.",
    LINEAR="Linear interpolation over the source window. Invents intermediate values, so never over ids.",
    CUBIC="Cubic interpolation. Invents intermediate values, and overshoots past the input range at edges.",
    AREA="The mean over the source window -- the usual image-pyramid default, and the usual way a mask pyramid gets silently ruined.",
    GAUSSIAN="A Gaussian-weighted average over the source window.",
    MAX="The maximum of the source window. Returns a real value, but over ids it biases every boundary toward whichever object sorts higher, so it is not label-safe either.",
    MIN="The minimum of the source window. Not label-safe, for the mirror of MAX's reason.",
)


@strawberry.enum(
    description=(
        "Which side of a file link was made from the other. A file is a store, not a container -- it has no coordinate system -- so this relates bytes to data rather than "
        "two spaces, and it is deliberately not a `DerivedFromInput` kind. Direction has to be stated because nothing else records which side existed first"
    )
)
class FileLinkDirection(str, Enum):
    """Which side of a file link was made from the other."""

    SOURCE = "SOURCE"
    RENDITION = "RENDITION"


_describe(
    FileLinkDirection,
    SOURCE="The container was produced from the file: a CZI a converter read to write a Zarr dataset, a CSV a table was loaded from. This is the ingest direction, and the file existed first.",
    RENDITION="The file was produced from the container: a dataset written out as OME-TIFF, a mesh exported to STL. This is the export direction, and the container existed first.",
)


@strawberry.enum(
    description=(
        "Which sort of container a file link names: the discriminator of `ExportOfInput`. Only the four containers that hold data a file can be written from or read into -- "
        "a lens is a selection over a dataset rather than a thing with its own bytes, and a coordinate system is a space, which no file encodes"
    )
)
class FileLinkContainerKind(str, Enum):
    """Which sort of container a file link names."""

    DATASET = "DATASET"
    TABLE_DATASET = "TABLE_DATASET"
    MESH_COLLECTION = "MESH_COLLECTION"
    ANNOTATION_COLLECTION = "ANNOTATION_COLLECTION"


_describe(
    FileLinkContainerKind,
    DATASET="An array dataset -- the container an image file is converted into, and the one an OME-TIFF is written from.",
    TABLE_DATASET="A table dataset, the container a CSV or parquet file is loaded into.",
    MESH_COLLECTION="A mesh collection, the container an STL or OBJ file is loaded into.",
    ANNOTATION_COLLECTION="An annotation collection, the container a GeoJSON or ROI file is loaded into.",
)


@strawberry.enum(
    description=(
        "A coarse bucket for what sort of thing a file holds, for a picker that wants \"just the images\". **Derived at query time from the file's extension, never stored** -- "
        "so it cannot drift from the file it describes, and it is a filter only. Classified by extension rather than by `contentType` on purpose: a CZI, LIF or ND2 is uploaded "
        "as `application/octet-stream`, so a content-type rule would file every vendor image under OTHER, which is precisely the case worth finding. `contentType` is the "
        "fallback when the extension is unknown. It is a curated list, not an authority: filter on `name` or `contentType` directly when you need an exact answer"
    )
)
class FileMimeGroup(str, Enum):
    """A coarse bucket for what sort of thing a file holds. Derived from the extension, never stored."""

    IMAGE = "IMAGE"
    TABLE = "TABLE"
    MESH = "MESH"
    ANNOTATION = "ANNOTATION"
    DOCUMENT = "DOCUMENT"
    ARCHIVE = "ARCHIVE"
    OTHER = "OTHER"


_describe(
    FileMimeGroup,
    IMAGE="Bioimage and picture formats: the vendor files (czi, lif, nd2, oib, lsm, ims, scn, svs) plus tiff/ome.tiff, png and jpeg.",
    TABLE="Tabular data: csv, tsv, parquet, feather, xlsx.",
    MESH="Surface geometry: stl, obj, ply, off.",
    ANNOTATION="Shapes and regions: geojson, roi, zip-of-rois, xml.",
    DOCUMENT="Human-readable notes and reports: pdf, txt, md, docx.",
    ARCHIVE="Containers of other files: zip, tar, gz, 7z. A zipped acquisition is an ARCHIVE, not an IMAGE -- the extension is all this reads.",
    OTHER="Nothing the curated list recognizes, and no usable `contentType`. Includes every file with no extension at all.",
)


_describe(
    ValueRelation,
    IDENTICAL="The target's numbers are the source's numbers (a crop, an axis reorder): value statistics -- histograms, contrast limits -- transfer across the edge.",
    TRANSFORMED="The same quantity with new numbers (a deconvolution, a normalization, a denoise): still an intensity, but nothing computed on the source's values transfers.",
    CATEGORIZED="The values became labels or classes (a threshold, a segmentation): a different value domain. This is the structural signal that lets a bootstrapped scene render the data as a label map.",
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


@strawberry.enum(description="Whether the server can state where a source sits in a space, and if not, why not. Derived, never stored.")
class ExtentState(str, Enum):
    """Whether a source's extent in a space is computable, and if not, why not.

    A bare null extent conflates a Parquet the server never reads with a warp field on the
    path, and a client cannot tell them apart -- the same reason `PlacementState` exists
    beside a null `pathToWorld`.
    """

    KNOWN = "KNOWN"
    UNREADABLE = "UNREADABLE"
    NON_AFFINE = "NON_AFFINE"
    INVERTED = "INVERTED"


_describe(
    ExtentState,
    KNOWN="The extent is stated, over the axes it names and only those.",
    UNREADABLE="The source's geometry is not something the server holds: a mesh collection's vertices and a table dataset's rows live in Parquet it never opens. `extent` is null because there is no box to push, not because the path failed -- and the source is returned anyway, because refusing to bound something is not the same as knowing it is out of view.",
    NON_AFFINE="A FIELD edge on the path gives the map as the values of an array rather than as a formula, so there is no closed form to push a box through. The path is real and is returned; `invariance` reads DIFFEOMORPHIC.",
    INVERTED="The path walks an edge against its stored direction, and the extent walk composes forward only -- it pushes a box, and re-bounding one through an inverted step is a different calculation. The step *is* invertible: a placement search offers a backwards step only for a map that has an inverse, which is why `Layer.asAffine` composes such a path without difficulty. So compose `path` yourself, inverting the flagged step, or read the layer's `asAffine`.",
)


@strawberry.enum(description="The physical unit used to express spatial dimensions, e.g. of pixel sizes or stage positions.")
@strawberry.enum(description="The physical unit used to express temporal dimensions, e.g. of time-lapse intervals.")
@strawberry.enum(description="The data type of a column in a DuckDB table, as used by tabular data stored alongside images.")
@strawberry.enum(description="The axis traversal order of a continuous scan, i.e. the order in which rows, columns and slices are acquired.")
@strawberry.enum(description="The geometric kind of a region of interest (ROI), defining how its vectors are interpreted.")
@strawberry.enum(description="The shape an annotation is drawn as. Unlike `RoiKind`, which this replaced, the members name geometry only: which axes a shape spans is a property of the coordinate system it is drawn in, not of the shape")
class AnnotationKind(str, Enum):
    """The geometric kind of an annotation, defining how its vectors are read."""

    POINT = "point"
    MULTI_POINT = "multi_point"
    LINE = "line"
    PATH = "path"
    POLYGON = "polygon"

    RECTANGLE = "rectangle"
    CUBE = "cube"

    CIRCLE = "circle"
    ELLIPSE = "ellipse"
    SPHERE = "sphere"
    ELLIPSOID = "ellipsoid"


_describe(
    AnnotationKind,
    POINT="A single point.",
    MULTI_POINT="A set of unconnected points drawn as one region, e.g. a counting click set. Vectors are the points themselves, in no particular order and with no connectivity implied.",
    LINE="A straight line between two points.",
    PATH="An open path defined by a sequence of connected points.",
    POLYGON="A closed polygon defined by a sequence of vertices.",
    RECTANGLE="An axis-aligned box across two axes, stored as the two opposite corners of its bounding box. Which two axes it spans is read from the coordinate system, not from this kind.",
    CUBE="An axis-aligned box across three axes, stored as the two opposite corners of its bounding box.",
    CIRCLE="A round shape across two axes with one radius. Vectors are the two opposite corners of its bounding box; the radius is half the (uniform by construction) extent.",
    ELLIPSE="A round shape across two axes with a radius per axis. Vectors are the two opposite corners of its bounding box; each semi-axis is half that axis' extent.",
    SPHERE="A round shape across three axes with one radius. Vectors are the two opposite corners of its bounding box.",
    ELLIPSOID="A round shape across three axes with a radius per axis. Vectors are the two opposite corners of its bounding box; each semi-axis is half that axis' extent.",
)
