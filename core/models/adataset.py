
from django.db import models
from django.contrib.auth import get_user_model
from core import enums
from koherent.fields import ProvenanceField
from django_choices_field import TextChoicesField
from authentikate.models import Organization
from django.db.models import Q
from datalayer.models import MediaStore, ZarrStore
from django.contrib.postgres.indexes import GinIndex
from core import base_models
from core.logic import coords as coords_logic
from core.models.coords import CoordinateSystem, Transformation, MeshCollection  # noqa: F401  (re-exported via core.models)


class ADataset(models.Model):
    """A multi-dimensional array of data, with one or more pyramid levels attached as DataArrays.

    The dataset's dimensions and their types live on the axes of its INTRINSIC
    :class:`~core.models.CoordinateSystem` -- its level-0 pixel grid -- and its
    shape is the shape of its level-0 array. Physical units live on its
    calibrations (PHYSICAL systems), never here. Almost none of it is duplicated on
    columns: the properties below derive it, so there is no second copy that can
    disagree. That includes ``multiscale``, which is simply "more than one level".

    The one materialized exception is ``stored_spec`` (read back through the ``spec``
    property): the list of :class:`~core.enums.ADatasetSpec` the axes satisfy, written
    once at creation. It is safe to store precisely because the axes are immutable (see
    below) -- a value computed from immutable inputs at write time cannot disagree with
    its source, the same reason ``DataArray`` stores its absolute scale on the edge at
    write time rather than re-deriving it. The single source of truth stays
    :func:`core.logic.coords.specs_for_axes`; the column is materialized *from* it by the
    axis writer, never re-derived on read.

    **Only ``name`` and ``description`` are editable**, through ``updateADataset``. Everything
    that says where the data *is* -- the arrays, the axes, the systems built from them -- is
    written at creation and never after: ``Axis.order`` is written by enumeration and the rest
    of the graph is measured against it, so an axis edit is a different space rather than a
    correction, and ``updateCoordinateSystem`` refuses a dataset's own system for that reason
    (it serves shared spaces alone). A recomputation is a new dataset.

    Both editable fields are audited. ``provenance`` records a history row per save, attributed
    to the client, user and task the change happened under, and reads back as
    ``provenanceEntries``. A rename is the only thing about a dataset that can change, which is
    exactly why it is worth knowing who changed it.
    """

    name = models.CharField(max_length=1000, help_text="The name of the data source")
    description = models.CharField(max_length=1000, help_text="The description of the data source", null=True)

    # Residence, not ownership (RFC-9). The dataset lives in a space; the space does not
    # belong to the dataset. A plain FK rather than a one-to-one because several datasets
    # genuinely may share one frame -- a hundred tiles acquired on one stage -- while two
    # unrelated acquisitions get their own because the writer creates one each.
    coordinate_system = models.ForeignKey(
        CoordinateSystem,
        on_delete=models.PROTECT,
        # Nullable in the database only because the `historical*` twin carries rows written
        # before this column existed, and a history row must be allowed to say "not
        # recorded". Every write path sets it, and migration 0043 backfilled every
        # existing row -- including the level-0 arrays and unsliced lenses that used to
        # have no system at all.
        null=True,
        blank=True,
        related_name="datasets",
        help_text="The coordinate system this dataset's pixels are expressed in: its level-0 grid. PROTECT, because a space cannot be deleted while data lives in it",
    )

    created_at = models.DateTimeField(auto_now_add=True, help_text="The time the data source was created")
    creator = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, null=True, blank=True, help_text="The user that created the data source")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, help_text="The organization the data source belongs to")
    created_through = models.ForeignKey(
        "koherent.Task",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_%(class)ss",
        help_text="The task this object was created through, if any",
    )
    created_through_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_%(class)ss",
        help_text="The assigner of the creating task, denormalized for fast filtering",
    )
    provenance = ProvenanceField()

    stored_spec = models.JSONField(
        default=list,
        help_text=(
            "What this dataset structurally is: the raw ADatasetSpec values (one spatial member plus a "
            "modifier per acquisition axis) that its intrinsic axes satisfy, materialized at creation by "
            "the axis writer from core.logic.coords.specs_for_axes. Immutable because the axes are, so it "
            "cannot disagree with them. Read it back as enum members through the `spec` property. Empty "
            "while the intrinsic system does not exist yet."
        ),
    )

    class Meta:
        indexes = [GinIndex(fields=["stored_spec"], name="adataset_spec_gin")]

    @property
    def intrinsic_coordinate_system(self):
        """The dataset's level-0 pixel grid: the system every pyramid level and lens maps into."""
        # The reverse of CoordinateSystem.intrinsic_of, which raises rather than
        # returning None when the system has not been created yet.
        return getattr(self, "intrinsic_system", None)

    @property
    def multiscale(self) -> bool:
        """Whether this dataset carries a resolution pyramid. Derived: more than one level."""
        return self.data_arrays.count() > 1

    @property
    def axes(self) -> list:
        """The dataset's axes, in array order."""
        system = self.intrinsic_coordinate_system
        return list(system.axes.all()) if system else []

    @property
    def axis_specs(self) -> list[coords_logic.AxisSpec]:
        """The dataset's axes, coerced for :mod:`core.logic.coords`."""
        return [coords_logic.AxisSpec(name=axis.name, type=axis.type) for axis in self.axes]

    @property
    def axis_names(self) -> list:
        """The dataset's axis names, in array order. Derived from the intrinsic axes."""
        return [axis.name for axis in self.axes]

    @property
    def spec(self) -> list:
        """Every spec this dataset's axes satisfy: what it structurally is.

        Read from ``stored_spec``, materialized at creation from the intrinsic
        axes -- not re-derived on read. The axes are immutable, so the column
        cannot disagree with them; this is the same write-time materialization as
        ``DataArray``'s absolute scale.

        Empty -- not SCALAR -- when the intrinsic system did not exist at creation:
        a dataset whose axes are unknown has no spatial extent to report, and
        claiming SCALAR would say it has none. A genuine no-SPACE-axis dataset
        stores ``['SCALAR', ...]``, so the two stay distinguishable.
        """
        return [enums.ADatasetSpec(value) for value in self.stored_spec]

    @property
    def shape_list(self) -> list:
        """The dataset's shape: that of its level-0 array."""
        base = self.data_arrays.order_by("level").first()
        return base.shape if base and isinstance(base.shape, list) else []

    def phasor_histogram_at(self, axis: str, harmonic: int):
        """The persisted phasor distribution over an axis at a harmonic, across all this dataset's anchors."""
        return PhasorHistogram.objects.filter(anchor__dataset=self, axis=axis, harmonic=harmonic).first()

    def phasor_calibrations_at(self, axis: str, harmonic: int):
        """The instrument-response correction for an axis at a harmonic, across all this dataset's anchors."""
        return PhasorCalibration.objects.filter(anchor__dataset=self, axis=axis, harmonic=harmonic).first()


class DataArray(models.Model):
    """One level of a dataset's resolution pyramid: a zarr-backed array.

    A downsampled level's voxel-index space is an ARRAY
    :class:`~core.models.CoordinateSystem`, and the map from that space into the
    dataset's intrinsic space is a stored :class:`~core.models.Transformation`.
    Every level maps into the *same* intrinsic system -- a star, not a chain -- so
    no level's placement depends on another's. Level 0 owns no system and no edge:
    the INTRINSIC system *is* the level-0 pixel grid, by definition, and a second
    node for the same space joined by an all-ones SCALE edge would record nothing
    (see :attr:`space`).

    The old ``scale_factors`` column is gone. It stored *nominal* factors
    (1, 2, 4, 8, ...), which a real pyramid does not obey: a 36-voxel axis floors
    to 36, 18, 9, 4, 2, 1, whose true factors are 1, 2, 4, 9, 18, 36. The
    absolute scale is now derived from the actual shapes at write time, by
    :func:`core.logic.coords.pyramid_transform`, and stored on the edge.
    """

    store = models.ForeignKey(
        ZarrStore,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="The store of the data array",
    )
    shape = models.JSONField(help_text="The shape of the data array")
    chunk_shape = models.JSONField(help_text="The chunk shape of the data array")

    dataset = models.ForeignKey(ADataset, on_delete=models.CASCADE, related_name="data_arrays")
    level = models.IntegerField(help_text="The level of the data array in the resolution pyramid, 0 being the highest resolution")

    # Always set, including for level 0 -- which is where this shape pays off. Level 0 used
    # to own *no* system, with a null and a "means the dataset's own grid" convention to
    # explain it; under residence it simply lives in that grid, pointing at the same node the
    # dataset does. The special case is gone rather than ported.
    coordinate_system = models.ForeignKey(
        CoordinateSystem,
        on_delete=models.PROTECT,
        # Nullable in the database only because the `historical*` twin carries rows written
        # before this column existed, and a history row must be allowed to say "not
        # recorded". Every write path sets it, and migration 0043 backfilled every
        # existing row -- including the level-0 arrays and unsliced lenses that used to
        # have no system at all.
        null=True,
        blank=True,
        related_name="data_arrays",
        help_text="The coordinate system this level's voxels are expressed in. Level 0 shares its dataset's; every downsampled level has its own, with a stored edge relating the two",
    )

    class Meta:
        """Meta options for the data array."""

        # Everything -- the dataset's shape, the lens edges, the pyramid
        # derivation -- keys off "the level-0 array". Two arrays claiming the
        # same level would make all of it silently ambiguous.
        constraints = [
            models.UniqueConstraint(fields=["dataset", "level"], name="one_data_array_per_level"),
        ]

    @property
    def space(self):
        """The coordinate system this level's voxels live in.

        Level 0 owns no system: the dataset's INTRINSIC system *is* the level-0 pixel
        grid, by definition, so this resolves to it. Higher levels own an ARRAY system
        and a stored edge into intrinsic.
        """
        return getattr(self, "coordinate_system", None) or (self.dataset.intrinsic_coordinate_system if self.level == 0 else None)

    @property
    def to_parent(self):
        """The stored edge from this level's voxel space into the dataset's intrinsic space.

        None for level 0: its space IS the intrinsic space, and an identity edge between
        one space and itself would be a stored fact carrying no information.
        """
        system = getattr(self, "coordinate_system", None)
        return Transformation.objects.filter(input=system).first() if system else None


# ==========================================
# 2. THE HUB & SPOKES (Metadata)
# ==========================================


class CoordinateAnchor(models.Model):
    """The Axis-Agnostic Hub."""

    id = models.BigAutoField(primary_key=True)
    dataset = models.ForeignKey(ADataset, related_name="anchors", on_delete=models.CASCADE)
    coordinates = models.JSONField(
        default=dict,
        help_text="The coordinates this anchor is pinned to, keyed by axis name, e.g. {'c': 0, 't': 5}. Level-0 pixel indices (the dataset's INTRINSIC space). An omitted axis means global along it",
    )

    class Meta:
        indexes = [GinIndex(fields=["coordinates"], name="anchor_coords_gin")]


class OptikitState(models.Model):
    """1:1 Spoke (Hardware Truth)"""

    anchor = models.OneToOneField(CoordinateAnchor, related_name="microscope", on_delete=models.CASCADE)
    state = models.JSONField(default=dict)


class OmeMetadata(models.Model):
    """N:1 Spoke (Image Truth)"""

    anchor = models.OneToOneField(CoordinateAnchor, related_name="ome_metadata", on_delete=models.CASCADE)
    metadata = models.JSONField(default=dict)


class ValueHistogram(models.Model):
    """N:1 Spoke (Pixel Value Distribution)"""

    anchor = models.OneToOneField(CoordinateAnchor, related_name="value_histogram", on_delete=models.CASCADE)
    histogram = models.JSONField(default=list, help_text="The histogram of the pixel values (y values)")
    bins = models.JSONField(default=list, help_text="The bin indices of the histogram (x values)")
    min = models.FloatField(help_text="The minimum pixel value of the histogram", null=True, blank=True)
    max = models.FloatField(help_text="The maximum pixel value of the histogram", null=True, blank=True)
    p1 = models.FloatField(help_text="The first percentile of the pixel values", null=True, blank=True)
    p99 = models.FloatField(help_text="The 99th percentile of the pixel values", null=True, blank=True)


class ChannelLabel(models.Model):
    """N:1 Spoke (Channel Truth)"""

    anchor = models.OneToOneField(CoordinateAnchor, related_name="channel_label", on_delete=models.CASCADE)
    label = models.CharField(max_length=1000, help_text="The label of the channel", null=True, blank=True)


class LightPath(models.Model):
    """N:1 Spoke (Light Path Truth)"""

    anchor = models.OneToOneField(CoordinateAnchor, related_name="light_graph", on_delete=models.CASCADE)
    graph = models.JSONField(default=dict)


class PhasorHistogram(models.Model):
    """N:1 Spoke (Phasor Distribution).

    The phasor's answer to :class:`ValueHistogram`: a client seeds the contrast limits of an
    intensity channel from the value histogram without reading the array, and it seeds the
    value range of a phasor overlay from this without streaming a whole TCSPC or hyperspectral
    cube.

    A ForeignKey where every other spoke is a OneToOne, because the anchor's ``coordinates``
    dict can only pin *array* coordinates -- and neither the axis a phasor was taken over nor
    the harmonic it was taken at is one. Under a 1:1 spoke, computing the second harmonic
    would silently replace the first rather than sit beside it.
    """

    anchor = models.ForeignKey(CoordinateAnchor, related_name="phasor_histograms", on_delete=models.CASCADE)
    axis = models.CharField(max_length=32, help_text="The axis the phasor was taken over, e.g. 'tau'")
    harmonic = models.PositiveSmallIntegerField(default=1, help_text="The harmonic the phasor was taken at")
    bins = models.PositiveIntegerField(default=256, help_text="The resolution of the square (g, s) density grid")
    g_min = models.FloatField(default=0.0, help_text="The lower g bound of the density grid")
    g_max = models.FloatField(default=1.0, help_text="The upper g bound of the density grid")
    s_min = models.FloatField(default=0.0, help_text="The lower s bound of the density grid")
    s_max = models.FloatField(default=0.6, help_text="The upper s bound of the density grid")
    counts = models.JSONField(default=list, help_text="The flattened bins x bins density, row-major with s outermost")
    total = models.BigIntegerField(null=True, blank=True, help_text="The number of pixels that contributed, so counts can be normalized")
    calibrated = models.BooleanField(default=False, help_text="Whether the g/s were reference-corrected when computed. An uncalibrated density is still a valid distribution, it is just not traceable to an absolute lifetime")
    profile = models.JSONField(default=list, blank=True, help_text="The summed profile along the phasor axis (a decay for a MICROTIME axis, a spectrum for a SPECTRUM one), one value per bin. Calibration-free, so a client can sanity-check or recompute the transform")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["anchor", "axis", "harmonic"], name="unique_phasor_histogram")]


class PhasorCalibration(models.Model):
    """N:1 Spoke (Instrument Response Truth).

    The correction taking a raw phasor to a calibrated one. It lives on the dataset rather than
    on a render node because it is an *acquisition* fact: two layers over one dataset cannot
    coherently disagree about the instrument response. Being anchored makes it per detection
    channel, which is right -- the IRF differs per detector.

    Stored as a phase offset (radians) and a modulation factor (dimensionless), both
    dimension-free, so one model serves a lifetime reference and a spectral one alike. The
    reference *value* ("4.1 ns") is what someone used to derive those two numbers; it is
    recorded descriptively rather than as a quantity the server would have to interpret.

    Absent this spoke a phasor is simply uncalibrated. That is a legitimate state: the overlay
    still renders, its hue just is not traceable to an absolute lifetime.
    """

    anchor = models.ForeignKey(CoordinateAnchor, related_name="phasor_calibrations", on_delete=models.CASCADE)
    axis = models.CharField(max_length=32, help_text="The axis the correction applies to, e.g. 'tau'")
    harmonic = models.PositiveSmallIntegerField(default=1, help_text="The harmonic the correction applies at")
    phase_offset = models.FloatField(null=True, blank=True, help_text="The phase correction in radians, added to each pixel's phase")
    modulation_factor = models.FloatField(null=True, blank=True, help_text="The modulation correction, multiplied into each pixel's modulus")
    reference = models.CharField(max_length=255, null=True, blank=True, help_text="What the correction was measured against, e.g. 'Rhodamine 6G, 4.1 ns'")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["anchor", "axis", "harmonic"], name="unique_phasor_calibration")]


class Lens(models.Model):
    """A selection over a dataset. Nothing else.

    Its shape and dimensions are derived from the dataset and the slices -- they
    were columns, and two people computing them from the same slices are
    guaranteed to agree, so there was no reason for a second copy that could
    drift.

    A *sliced* lens has its own coordinate system, and the edge back to the dataset
    is a stored :class:`~core.models.Transformation`. Before that, slicing shifted
    voxel coordinates and nothing recorded the shift: an ROI drawn on a cropped
    lens had no defined path back to its dataset. An **unsliced** lens selects
    everything, so its space is the dataset's intrinsic space by definition -- it
    owns no system and no edge (see :attr:`space`), because a second node for the
    same space joined by an identity edge would record nothing. Lenses are
    immutable, so the decision is made once, at creation.

    The lens-to-parent edge is **derived from the slices, never authored** --
    recreating a lens from its slices reproduces its geometry exactly. In
    particular, per-channel corrections (chromatic drift) are not lens
    properties: they are acquisition facts, and a correction stored on a view
    would be a second copy free to disagree with the next view of the same
    channel. The supported interim pattern is one lens per channel plus a
    scene-level registration edge authored from the lens' system
    (``createTransformation`` accepts any input system, and the placement BFS in
    :mod:`core.logic.graph` prefers the direct edge). If channel-wise correction
    becomes a first-class need, it will be a dataset-owned ``aligned`` system
    with one channel-wise edge from intrinsic -- the calibration pattern again,
    never per-view state.
    """

    dataset = models.ForeignKey(ADataset, on_delete=models.CASCADE, related_name="lenses")
    slices = models.JSONField(help_text="The selection this lens makes over its dataset, as a list of per-dimension slices", default=list)

    # Always set. An unsliced lens used to own no system, with a null standing for "the
    # dataset's grid"; under residence it lives in that grid and points at the same node.
    coordinate_system = models.ForeignKey(
        CoordinateSystem,
        on_delete=models.PROTECT,
        # Nullable in the database only because the `historical*` twin carries rows written
        # before this column existed, and a history row must be allowed to say "not
        # recorded". Every write path sets it, and migration 0043 backfilled every
        # existing row -- including the level-0 arrays and unsliced lenses that used to
        # have no system at all.
        null=True,
        blank=True,
        related_name="lenses",
        help_text="The coordinate system this lens' voxels are expressed in. An unsliced lens shares its dataset's; a sliced one has its own, with a stored edge carrying the shift",
    )

    provenance = ProvenanceField()

    @property
    def slices_list(self) -> list[base_models.SliceModel]:
        """Return the slices of the lens as a list."""
        return [base_models.SliceModel(**slice_dict) for slice_dict in self.slices] if isinstance(self.slices, list) else []

    @property
    def axis_names(self) -> list:
        """The lens' axis names. A selection never drops or reorders an axis."""
        return self.dataset.axis_names

    @property
    def axis_specs(self) -> list[coords_logic.AxisSpec]:
        """The lens' axes, coerced for :mod:`core.logic.coords`."""
        return self.dataset.axis_specs

    @property
    def shape_list(self) -> list:
        """The shape this lens' slices cut out of its dataset."""
        return coords_logic.lens_shape(self.dataset.shape_list, self.dataset.axis_names, self.slices_list)

    @property
    def space(self):
        """The coordinate system this lens' selection is expressed in.

        A lens with no slices selects everything, so its space is the dataset's
        intrinsic space *by definition* and it owns no system -- the same rule as a
        level-0 array. A sliced lens shifts voxel coordinates, which is a real fact,
        so it owns a system and the derived edge that records the shift.
        """
        return getattr(self, "coordinate_system", None) or self.dataset.intrinsic_coordinate_system

    @property
    def to_parent(self):
        """The stored edge from this lens' space back into its dataset's intrinsic space.

        None for an unsliced lens: its space IS the intrinsic space, and there is no
        shift to record.
        """
        system = getattr(self, "coordinate_system", None)
        return Transformation.objects.filter(input=system).first() if system else None

    def get_size_of_axis(self, axis_name: str) -> int:
        """Get the size of an axis by its name."""
        axis_names, shape = self.axis_names, self.shape_list
        try:
            return shape[axis_names.index(axis_name)]
        except ValueError as error:
            raise ValueError(f"Axis {axis_name} not found in lens axes {axis_names}.") from error

    @property
    def active_anchors(self):
        """
        THE WORKSPACE QUERY:
        Finds all anchors that fall within the boundaries of this Lens.
        Respects the "Axis-Agnostic" rule: If an anchor is global ({})
        or partial ({"c": 0}), it is included as long as it doesn't contradict the Lens.
        """
        qs = CoordinateAnchor.objects.filter(dataset=self.dataset)

        # Loop through the axis constraints of the Lens
        for slc in self.slices_list:
            axis = slc.axis

            # Condition A: The anchor is global for this axis (key doesn't exist)
            axis_is_global = ~Q(coordinates__has_key=axis)

            if slc.start is not None and slc.stop is not None:
                axis_in_range = Q(**{f"coordinates__{axis}__gte": slc.start, f"coordinates__{axis}__lt": slc.stop})
            else:
                continue  # Failsafe for unhandled slice types

            # The anchor must either be global for this axis, OR fall inside the slice limits
            qs = qs.filter(axis_is_global | axis_in_range)

        # OPTIMIZATION: prefetch/select the spokes to prevent N+1 database death
        return qs.select_related("microscope").prefetch_related("ome_metadata", "value_histogram")



class Scene(models.Model):
    """A composition of layers over a shared world coordinate system.

    ``world`` is *which* space the scene composes over, and it is always set. It is
    deliberately not ownership: a scene never owns a space. A scene created bare gets
    an ordinary ownerless SHARED system created for convenience; a scene created over
    an existing system merely references it -- either way many scenes can compose over
    one space, the space outlives every one of them (``on_delete=RESTRICT`` refuses to
    delete a space out from under a scene), and no scene's deletion deletes a space:
    that is ``deleteCoordinateSystem``'s explicit job.

    The scene carries no units: they are per-axis, on the axes of its world
    system. It carries no affine either -- the map to a parent scene is an edge
    between the two scenes' world systems, like every other spatial fact.

    There is deliberately no membership set (RFC-6). Which registrations this
    composition uses is not a scene-level pool: each layer names the one that
    places it (:attr:`Layer.registration`), and two scenes over one world
    disagree about a dataset's position exactly by their layers referencing
    rival registrations. A scene is its world plus its layers, nothing more.
    """

    name = models.CharField(max_length=255)
    world = models.ForeignKey(
        "CoordinateSystem",
        on_delete=models.RESTRICT,
        related_name="scenes",
        help_text=(
            "The space this scene composes its layers over: a shared world system created for "
            "convenience alongside the scene, or an adopted existing system -- a shared space, a "
            "dataset's intrinsic grid, a calibration, a collection's space. Never owned by the "
            "scene: many scenes can share it, it outlives each of them, and deleting a scene "
            "never deletes it. RESTRICT: while a scene is rooted in a space, neither the space "
            "nor its owning container can be deleted"
        ),
    )
    blending = TextChoicesField(
        choices_enum=enums.BlendingChoices,
        default=enums.BlendingChoices.ADDITIVE.value,
        help_text="The blending of the scene",
    )
    # Viewer preferences: how a client should *look* at this composition. Preferences, not
    # constraints -- nothing server-side reads them, and a viewer that ignores them is not
    # wrong. They sit here rather than in a layer's render graph because that graph says
    # what the pixels are; these say where the eye goes, which is a fact about the whole
    # composition and about no layer in particular.
    preferred_view = TextChoicesField(
        choices_enum=enums.PreferredViewChoices,
        default=enums.PreferredViewChoices.AUTO.value,
        help_text="How a viewer should open this scene: flat, volumetric, or its own choice. Defaults to AUTO -- a scene nobody has expressed a preference for should not claim one",
    )
    background_color = models.JSONField(
        null=True,
        blank=True,
        help_text="The viewer background, as RGBA. Null to let the viewer use its own",
    )
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    provenance = ProvenanceField()


class Animation(models.Model):
    """A named camera tour of a scene: the poses a viewer pans through, in order.

    A view artifact, not a spatial fact. It hangs off the scene and cascades with it, and
    no placement walk crosses it: refining a registration moves the data, and it must
    never move the camera. That is the same footing :class:`SceneSnapshot` stands on, and
    deliberately not :class:`~core.models.Annotation`'s -- an annotation is owned by
    its collection and outlives every scene, because it is a claim about where
    something *is*.

    Its waypoints are written as a whole list, never one at a time, which is what makes
    ``AnimationWaypoint.order`` trustworthy -- see the mutation.
    """

    scene = models.ForeignKey(Scene, on_delete=models.CASCADE, related_name="animations", help_text="The scene this tour flies through")
    name = models.CharField(max_length=255, help_text="The name of the tour, e.g. 'overview' or 'dive to the mitochondria'")
    description = models.CharField(max_length=1000, null=True, blank=True, help_text="What the tour shows")

    created_at = models.DateTimeField(auto_now_add=True, help_text="The time the tour was created")
    creator = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, null=True, blank=True, help_text="The user that created the tour")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, help_text="The organization the tour belongs to")
    created_through = models.ForeignKey(
        "koherent.Task",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_%(class)ss",
        help_text="The task this object was created through, if any",
    )
    created_through_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_%(class)ss",
        help_text="The assigner of the creating task, denormalized for fast filtering",
    )
    provenance = ProvenanceField()


class AnimationWaypoint(models.Model):
    """One camera pose in a tour, and how the viewer travels to it.

    Carries no creator, organization or provenance of its own: a waypoint is written by
    its animation's mutation and cascades with it, exactly as an :class:`Axis` is written
    by its coordinate system's. The animation is what a delete guard and org-scoping act
    on; a waypoint is never independently owned.
    """

    animation = models.ForeignKey(Animation, on_delete=models.CASCADE, related_name="waypoints", help_text="The tour this pose belongs to")
    order = models.PositiveSmallIntegerField(help_text="The pose's index in the tour. Written by enumeration from the authored list, never supplied by a caller")
    name = models.CharField(max_length=255, blank=True, default="", help_text="What this stop shows, e.g. 'the nucleus'")
    camera = models.JSONField(help_text="Where the camera is, as a CameraState: a position keyed by the world's axis names, plus the flat and volumetric views of it")
    duration_ms = models.PositiveIntegerField(default=1000, help_text="How long the viewer takes to travel TO this pose, in milliseconds. Ignored for the first pose, which is where the tour starts")
    easing = TextChoicesField(
        choices_enum=enums.EasingChoices,
        default=enums.EasingChoices.EASE_IN_OUT.value,
        help_text="How the viewer eases the camera along that travel",
    )

    class Meta:
        """Meta options for the animation waypoint."""

        ordering = ["order"]
        constraints = [
            # Safe precisely because `order` is written by enumeration over the whole
            # authored list: two waypoints are never swapped in place, so this can never
            # be transiently violated and needs no deferral.
            models.UniqueConstraint(fields=["animation", "order"], name="unique_animation_waypoint_order"),
        ]

    def __str__(self) -> str:
        """The waypoint's position in its tour."""
        return f"{self.animation_id}[{self.order}]"


class SceneSnapshot(models.Model):
    """A pre-rendered picture of a composition: every layer of the scene, blended.

    A picture of the *scene*, and deliberately not of any one dataset in it -- there is
    no lens or dataset FK, because what a single dataset looks like on its own is not a
    question this model answers. It cascades with the scene: once the composition is
    gone, a picture of it depicts nothing that still exists.

    Not a spatial fact, and deliberately not on the coordinate graph: a snapshot
    records that a picture was taken, never a claim about where anything is. Nothing
    walks it, and refining a registration does not move it.

    A dataset can still be previewed from these, but only where the graph says the
    picture shows it and nothing else -- see :func:`core.logic.graph.scenes_showing_only`,
    which is what ``ADataset.latestSnapshot`` is built on.
    """

    scene = models.ForeignKey(Scene, on_delete=models.CASCADE, related_name="snapshots", help_text="The composition this is a picture of")
    store = models.ForeignKey(MediaStore, on_delete=models.CASCADE, related_name="scene_snapshots", help_text="The media store holding the rendered image")
    name = models.CharField(max_length=1000, default="", help_text="The name of the snapshot")
    major_color = models.JSONField(null=True, blank=True, help_text="The dominant color of the image, for tinting a placeholder while it loads")

    created_at = models.DateTimeField(auto_now_add=True, help_text="The time the snapshot was taken")
    creator = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, null=True, blank=True, help_text="The user that took the snapshot")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, help_text="The organization the snapshot belongs to")
    created_through = models.ForeignKey(
        "koherent.Task",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_%(class)ss",
        help_text="The task this object was created through, if any",
    )
    created_through_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_%(class)ss",
        help_text="The assigner of the creating task, denormalized for fast filtering",
    )
    provenance = ProvenanceField()
    pinned_by = models.ManyToManyField(
        get_user_model(),
        related_name="pinned_scene_snapshots",
        blank=True,
        help_text="The users that have pinned the snapshot",
    )

    class Meta:
        indexes = [
            models.Index(fields=["scene", "-created_at"], name="scene_snapshot_latest_idx"),
        ]


class Layer(models.Model):
    """View state, and the unit that gets alpha-blended. No spatial fields.

    A single table discriminated by ``kind``: it carries the shared placement and
    compositing settings plus the source and render settings for every layer kind
    (image / annotation / point / track / mesh). Exactly one source FK is set per
    kind, enforced by the create mutations. In GraphQL this one model is exposed as
    a ``Layer`` interface with concrete ``ImageLayer``/``AnnotationLayer``/
    ``PointLayer``/``TrackLayer``/``MeshLayer`` types resolved by ``kind``.

    **The rule this model exists to obey (RFC-8):** a spatial fact is a node or an
    edge, never a column here, and a layer's spatial questions are answered by
    *deriving over its path* -- stored nowhere. Check any proposed field against it:
    if two layers over one dataset could carry two copies of it and disagree, it
    belongs on the edge.

    Every removal on this model is that rule applied. The layer no longer carries an
    ``affine_matrix``: registration belongs to the dataset, not to a view of it, and
    it is a :class:`~core.models.Transformation` edge into the scene's world -- under
    RFC-6 unique per (data, world), so the layer carries no placement reference at
    all and its path to world is fixed by the graph alone. It no longer carries
    ``validity`` or ``status`` (see migration 0018): how well a placement is known is
    a fact of the *edge*, and the layer derives the weakest one on its path. Nor does
    it carry ``x_dim`` and friends -- those follow from the axis types, and are
    derived by :func:`core.logic.coords.resolve_render_axes`.

    The same rule decides what *stays*. Which columns hold a point layer's
    coordinates is not here either: the table dataset declares them by role, and a
    per-layer copy could disagree with the dataset's own schema. ``size_column`` and
    friends pick among the remaining measure columns for display, which is honestly
    per-layer view state.

    Two scalar lengths below (``point_size``, ``line_width``) are in *scene units*,
    which RFC-8 defines as the world's spatial-axis unit -- meaningful for a layer
    exactly when its path to world preserves lengths up to one factor
    (``placementInvariance`` of SIMILARITY or better).
    """

    # --- shared placement / compositing ---
    scene = models.ForeignKey(Scene, related_name="layers", on_delete=models.CASCADE)
    kind = TextChoicesField(
        choices_enum=enums.LayerKindChoices,
        default=enums.LayerKindChoices.IMAGE.value,
        help_text="The kind of layer, discriminating its data source and render settings",
    )
    blending = TextChoicesField(
        choices_enum=enums.BlendingChoices,
        default=enums.BlendingChoices.ADDITIVE.value,
        help_text="The blending mode used to composite this layer over the layers below it",
    )
    opacity = models.FloatField(default=1.0, help_text="Layer alpha for alpha-over compositing (0..1)")
    visible = models.BooleanField(default=True, help_text="Whether the layer participates in compositing")
    order = models.IntegerField(default=0, help_text="Explicit z-index for deterministic back-to-front compositing")

    # --- source references (exactly one set, per kind) ---
    lens = models.ForeignKey(Lens, on_delete=models.CASCADE, related_name="layers", null=True, blank=True, help_text="(image) The lens that defines the array data source and constraints")
    annotation_collection = models.ForeignKey(
        "AnnotationCollection",
        on_delete=models.CASCADE,
        related_name="layers",
        null=True,
        blank=True,
        help_text="(annotation) The annotation collection, owning its own coordinate system, whose drawn shapes this layer renders",
    )
    table_dataset = models.ForeignKey(
        "TableDataset",
        on_delete=models.CASCADE,
        related_name="layers",
        null=True,
        blank=True,
        help_text="(point/track) The table dataset whose declared coordinate columns provide the coordinates; its own coordinate system is the space, and its column roles are the mapping -- nothing is duplicated per layer",
    )
    mesh_collection = models.ForeignKey(
        "MeshCollection",
        on_delete=models.CASCADE,
        related_name="mesh_layers",
        null=True,
        blank=True,
        help_text="(mesh) The versioned mesh collection, owning its own coordinate system, that this layer renders",
    )
    # --- image / volume render settings ---
    render_graph = models.JSONField(null=True, blank=True, default=None, help_text="(image) The composable render recipe (channels + transfer functions + in-layer blend) that is the single source of truth for how the image layer is rendered.")
    colormap = TextChoicesField(choices_enum=enums.ColorMapChoices, default=enums.ColorMapChoices.VIRIDIS.value, help_text="(point/track) The applying color map", null=True, blank=True)

    # --- point/track render choices. Which columns provide the COORDINATES (and the
    # track/point identity) is never stored here: the table dataset declares them by
    # role, and a second per-layer copy could disagree with the dataset's own schema.
    # These pick among the remaining measure columns for display, which is honestly
    # per-layer view state.
    size_column = models.CharField(max_length=100, null=True, blank=True, help_text="(point) The table column mapped to per-point size")
    color_column = models.CharField(max_length=100, null=True, blank=True, help_text="(point) The table column mapped to per-point color/intensity (used with colormap)")
    point_size = models.FloatField(null=True, blank=True, help_text="(point) The default point size, in scene units -- the world's spatial-axis unit, which is a well-defined length for a layer only when its `placementInvariance` is SIMILARITY or better (RFC-8)")
    color_by_column = models.CharField(max_length=100, null=True, blank=True, help_text="(track) The table column used to color tracks (used with colormap)")
    line_width = models.FloatField(null=True, blank=True, help_text="(track) The width of the track lines, in scene units -- the world's spatial-axis unit, which is a well-defined length for a layer only when its `placementInvariance` is SIMILARITY or better (RFC-8)")

    # --- mesh render settings ---
    material_color = models.JSONField(default=None, null=True, blank=True, help_text="(mesh) The material (surface) color of the mesh (RGBA)")
    wireframe = models.BooleanField(default=False, help_text="(mesh) Whether the mesh is rendered as a wireframe instead of a solid surface")

    provenance = ProvenanceField()
