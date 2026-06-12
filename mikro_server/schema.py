from kante.types import Info
import strawberry
from strawberry_django.optimizer import DjangoOptimizerExtension
from authentikate.strawberry.extension import AuthentikateExtension
from strawberry import ID as StrawberryID
from core import types, models, filters
from core import mutations
from core import queries
from core import subscriptions
import strawberry_django
from koherent.strawberry.extension import KoherentExtension
from lightpath.constants import interface_types
from core.duck import DuckExtension
from typing import Annotated
from authentikate.strawberry import AuthExtension, AuthSubscribeExtension
from strawberry_django.pagination import OffsetPaginationInput
from authentikate import models as ak_models
from koherent import models as koherent_models
import datalayer.mutations as datalayer_mutations
import kante
from core.scoping import get_for_org

ID = Annotated[StrawberryID, strawberry.argument(description="The unique identifier of an object")]


def field(permission_classes=None, **kwargs):
    "A wrapper for field that adds default permission classes and extensions."
    if permission_classes:
        pass
    else:
        permission_classes = []
    return strawberry_django.field(extensions=[AuthExtension()], **kwargs)


def mutation(roles: list[str] | None = None, **kwargs) -> strawberry.mutation:
    """A wrapper for mutation that adds default permission classes and extensions."""

    return strawberry_django.mutation(extensions=[AuthExtension(any_role_of=roles or ["admin", "bot"])], **kwargs)


def subscription(**kwargs) -> strawberry.subscription:
    """A wrapper for subscription that adds default permission classes and extensions."""
    return strawberry.subscription(extensions=[AuthSubscribeExtension()], **kwargs)


@strawberry.type
class Query:
    images: list[types.Image] = field(description="List images in the current organization, filterable and orderable")
    rois: list[types.ROI] = field(description="List regions of interest drawn on images")
    myimages: list[types.Image] = field(description="List images created by the current user")
    tasks: list[types.Task] = field(description="List the Rekuest tasks under which objects were created or changed")
    datasets: list[types.Dataset] = field(description="List datasets (folder-like collections of images, files and tables)")
    mydatasets: list[types.Dataset] = field(description="List datasets created by the current user")
    timepoint_views: list[types.TimepointView] = field(description="List timepoint views (anchoring image regions in real time)")
    label_views: list[types.LabelView] = field(description="List label views (mapping image channels to labels)")
    channel_views: list[types.ChannelView] = field(description="List channel views (describing the channels of images)")
    continous_scan_views: list[types.ContinousScanView] = field(description="List continuous scan views (recording scan directions)")
    well_position_views: list[types.WellPositionView] = field(description="List well position views (mapping images to multi well plate wells)")
    acquisition_views: list[types.AcquisitionView] = field(description="List acquisition views (recording when and by whom images were acquired)")
    rgb_views: list[types.RGBView] = field(description="List RGB render views (per-channel display settings)")
    file_views: list[types.FileView] = field(description="List file views (linking images to the raw files they were converted from)")
    file_view: types.FileView = field(description="Get a single file view by ID")
    affine_transformation_views: list[types.AffineTransformationView] = field(description="List affine transformation views (placing images in physical stage space)")
    scale_views: list[types.ScaleView] = field(description="List scale views (the levels of multiscale image pyramids)")
    eras: list[types.Era] = field(description="List eras (named time epochs on a microscope that timepoint views anchor to)")
    myeras: list[types.Era] = field(description="List eras created by the current user")

    scenes: list[types.Scene] = field(description="List scenes (compositions of layers over array datasets)")
    scene: types.Scene = field(description="Get a single scene by ID")

    layers: list[types.Layer] = field(description="List layers (placements of a lens inside a scene)")
    layer: types.Layer = field(description="Get a single layer by ID")

    lenses: list[types.Lens] = field(description="List lenses (parameterized ways of looking at an array dataset)")
    lens: types.Lens = field(description="Get a single lens by ID")

    adatasets: list[types.ADataset] = field(description="List array datasets (N-dimensional arrays with named dimensions and anchored metadata)")
    adataset: types.ADataset = field(description="Get a single array dataset by ID")

    data_arrays: list[types.DataArray] = field(description="List data arrays (the multiscale zarr arrays backing array datasets)")
    data_array: types.DataArray = field(description="Get a single data array by ID")

    data_rois: list[types.DataRoi] = field(description="List data ROIs (regions of interest on array datasets)")
    data_roi: types.DataRoi = field(description="Get a single data ROI by ID")

    stages: list[types.Stage] = field(description="List stages (the 3D physical spaces images are positioned in)")
    render_trees: list[types.RenderTree] = field(description="List render trees (saved client-side render configurations)")

    experiments: list[types.Experiment] = field(description="List experiments")
    rgbcontexts: list[types.RGBContext] = field(description="List RGB render contexts (groups of RGB views composing a displayable image)")
    instruments: list[types.Instrument] = field(description="List microscopes/instruments")
    multi_well_plates: list[types.MultiWellPlate] = field(description="List multi well plates")
    objectives: list[types.Objective] = field(description="List microscope objectives")
    myobjectives: list[types.Objective] = field(description="List objectives created by the current user")

    children = field(resolver=queries.children, description="List the child datasets of a dataset")
    rows = field(resolver=queries.rows, description="List the rows of a table")

    tables: list[types.Table] = field(description="List tables (tabular data backed by parquet stores)")
    mytables: list[types.Table] = field(description="List tables created by the current user")

    snapshots: list[types.Snapshot] = field(description="List snapshots (pre-rendered thumbnail images of images)")
    mysnapshots: list[types.Snapshot] = field(description="List snapshots created by the current user")

    files: list[types.File] = field(description="List files (raw microscopy files such as .czi or .ome.tiff)")
    myfiles: list[types.File] = field(description="List files created by the current user")
    random_image: types.Image = field(resolver=queries.random_image, description="Get a random image of the current organization")
    active_views: list[types.View] = field(
        resolver=queries.active_image_views,
        description="Get all active views for a specific image",
    )

    ## Accessors for tables
    label_accessors: list[types.LabelAccessor] = field(description="List label accessors (columns of tables that reference mask labels)")
    image_accessors: list[types.ImageAccessor] = field(description="List image accessors (columns of tables that reference images)")

    meshes: list[types.Mesh] = field(description="List 3D meshes")

    permissions = field(
        resolver=queries.permissions,
        description="Get permissions for a specific object",
    )
    available_permissions = field(
        resolver=queries.available_permissions,
        description="Get available permissions for a specific identifier",
    )

    images_stats: types.ImageStats = field(resolver=types.ImageStatsResolver, description="Get statistics about images")

    @field(permission_classes=[], description="List the memberships of the current organization (excluding bots)")
    def members(self, info: Info) -> list[types.Membership]:
        """Return all memberships for the current organization, excluding those with the 'bot' role."""
        return ak_models.Membership.objects.filter(organization=info.context.request.organization).exclude(roles__contains="bot").distinct()

    @field(permission_classes=[], description="Get one labelled instance of an instance mask by its compound ID (maskId-rowId)")
    def instance_mask_view_label(self, info: Info, id: ID) -> types.InstanceMaskViewLabel:
        mask_id, row_id = id.split("-")
        mask = get_for_org(models.InstanceMaskView, info, id=mask_id)

        parquet_store: models.ParquetStore = mask.labels

        return types.InstanceMaskViewLabel(
            _mask=mask_id,
            _store=parquet_store,
            _values=parquet_store.get_row(int(row_id)),
            _id=id,
        )

    @field(permission_classes=[], description="Get a single RGB render view by ID")
    def rgb_view(self, info: Info, id: ID) -> types.RGBView:
        return get_for_org(models.RGBView, info, id=id)

    @field(permission_classes=[], description="List the rows of a table")
    def table_rows(
        self,
        info: Info,
        filters: filters.TableRowFilter,
        pagination: OffsetPaginationInput,
    ) -> list[types.TableRow]:
        table = get_for_org(models.Table, info, id=id)
        return table.rows.all()

    @field(permission_classes=[], description="List the cells of a table")
    def table_cells(
        self,
        info: Info,
        filters: filters.TableCellFilter,
        pagination: OffsetPaginationInput,
    ) -> list[types.TableCell]:
        table = get_for_org(models.Table, info, id=id)
        return table.cells.all()

    @field(permission_classes=[], description="Get a single 3D mesh by ID")
    def mesh(self, info: Info, id: ID) -> types.Mesh:
        return get_for_org(models.Mesh, info, id=id)

    @field(permission_classes=[], description="Get display information (label and color) for one pixel value of a mask")
    def masked_pixel_info(self, info: Info, id: ID) -> types.MaskedPixelInfo:
        # ID is a compund ID like "partial_mask_view-label"
        raise NotImplementedError("MaskedPixelInfo is not implemented yet")

    @field(permission_classes=[], description="Returns a single image by ID")
    def image(self, info: Info, id: ID) -> types.Image:
        return get_for_org(models.Image, info, id=id)

    @field(permission_classes=[], description="Get a single lightpath view by ID")
    def lightpath_view(self, info: Info, id: ID) -> types.LightpathView:
        return get_for_org(models.LightpathView, info, id=id)

    @field(permission_classes=[], description="Get a single table cell by its compound ID (tableId-rowId-columnId)")
    def table_cell(self, info: Info, id: ID) -> types.TableCell:
        table_id, row_id, column_id = id.split("-")
        table = get_for_org(models.Table, info, id=table_id)

        return types.TableCell(table=table, row_id=row_id, column_id=column_id)

    @field(permission_classes=[], description="Get a single table row by its compound ID (tableId-rowId)")
    def table_row(self, info: Info, id: ID) -> types.TableRow:
        table_id, row_id = id.split("-")
        table = get_for_org(models.Table, info, id=table_id)

        return types.TableRow(table=table, row_id=row_id)

    @field(permission_classes=[], description="Get a single region of interest by ID")
    def roi(self, info: Info, id: ID) -> types.ROI:
        return get_for_org(models.ROI, info, id=id)

    @field(permission_classes=[], description="Get a single Rekuest task by ID")
    def task(self, info: Info, id: ID) -> types.Task:
        return get_for_org(koherent_models.Task, info, id=id)

    @field(permission_classes=[], description="Get a single render tree by ID")
    def render_tree(self, info: Info, id: ID) -> types.RenderTree:
        return get_for_org(models.RenderTree, info, id=id)

    @field(permission_classes=[], description="Get a single RGB render context by ID")
    def rgbcontext(self, info: Info, id: ID) -> types.RGBContext:
        return get_for_org(models.RGBRenderContext, info, id=id)

    @field(permission_classes=[], description="Get a single objective by ID")
    def objective(self, info: Info, id: ID) -> types.Objective:
        return get_for_org(models.Objective, info, id=id)

    @field(permission_classes=[], description="Get a single camera by ID")
    def camera(self, info: Info, id: ID) -> types.Camera:
        return get_for_org(models.Camera, info, id=id)

    @field(permission_classes=[], description="Get a single snapshot by ID")
    def snapshot(self, info: Info, id: ID) -> types.Snapshot:
        return get_for_org(models.Snapshot, info, id=id)

    @field(permission_classes=[], description="Get generic key-value descriptors for an object identified by identifier and ID")
    def describe(self, info: Info, identifier: str, id: strawberry.ID) -> list[types.Descriptor]:
        descriptors = []

        if identifier == "@mikro/file":
            file = get_for_org(models.File, info, id=id)

            if file.name:
                descriptors.append(types.Descriptor(key="name", value=file.name))
            if file.store:
                descriptors.append(types.Descriptor(key="bucket", value=file.store.bucket))
        else:
            raise NotImplementedError(f"Describe not implemented for identifier {identifier}")

        return descriptors

    @field(permission_classes=[], description="Get a single file by ID")
    def file(self, info: Info, id: ID) -> types.File:
        return get_for_org(models.File, info, id=id)

    @field(permission_classes=[], description="Get a single table by ID")
    def table(self, info: Info, id: ID) -> types.Table:
        return get_for_org(models.Table, info, id=id)

    @field(permission_classes=[], description="Get a single instrument by ID")
    def instrument(self, info: Info, id: ID) -> types.Instrument:
        return get_for_org(models.Instrument, info, id=id)

    @field(permission_classes=[], description="Get a single dataset by ID")
    def dataset(self, info: Info, id: ID) -> types.Dataset:
        return get_for_org(models.Dataset, info, id=id)

    @field(permission_classes=[], description="Get a single multi well plate by ID")
    def multi_well_plate(self, info: Info, id: ID) -> types.MultiWellPlate:
        return get_for_org(models.MultiWellPlate, info, id=id)

    @field(permission_classes=[], description="Get a single stage by ID")
    def stage(self, info: Info, id: ID) -> types.Stage:
        return get_for_org(models.Stage, info, id=id)

    @field(permission_classes=[], description="Get a single experiment by ID")
    def experiment(self, info: Info, id: ID) -> types.Experiment:
        return get_for_org(models.Experiment, info, id=id)

    @field(permission_classes=[], description="Get the channel infos of a specific image")
    def channels_for(self, info: Info, image: ID, filters: filters.ChannelInfoFilter | None = None) -> list[types.ChannelInfo]:
        """Get all channels for a specific image."""
        if filters is None:
            filters = filters.ChannelInfoFilter()

        """Get all channels for a specific image."""
        image = get_for_org(models.Image, info, id=image)
        if filters.ids:
            ids = filters.ids
            return [types.ChannelInfo(_image=image, _channel=i) for i in range(0, image.store.shape[0]) if str(i) in ids]
        else:
            return [types.ChannelInfo(_image=image, _channel=i) for i in range(0, image.store.shape[0])]


@strawberry.type
class Mutation:
    # Relation
    relate_to_dataset: types.Image = mutation(
        resolver=mutations.relate_to_dataset,
        description="Relate an image to a dataset",
    )

    request_media_upload = kante.django_mutation(
        description="Upload media and return a URL for access",
        resolver=datalayer_mutations.request_media_upload,
    )
    finish_media_upload = kante.django_mutation(
        description="Finalize a media upload after the client has written the object",
        resolver=datalayer_mutations.finish_media_upload,
    )
    request_media_access = kante.django_mutation(
        description="Request temporary S3 read credentials for a media file",
        resolver=datalayer_mutations.request_media_access,
    )
    request_general_media_access = kante.django_mutation(
        description="Request temporary S3 read credentials for media files in the organization",
        resolver=datalayer_mutations.request_general_media_access,
    )

    request_bigfile_upload = kante.django_mutation(
        description="Request an upload grant for a big file store",
        resolver=datalayer_mutations.request_bigfile_upload,
    )
    finish_bigfile_upload = kante.django_mutation(
        description="Finalize a big file upload after the client has written the object",
        resolver=datalayer_mutations.finish_bigfile_upload,
    )
    request_bigfile_access = kante.django_mutation(
        description="Request temporary S3 read credentials for a big file",
        resolver=datalayer_mutations.request_bigfile_access,
    )

    request_zarr_upload = kante.django_mutation(
        description="Request an upload grant for a Zarr store",
        resolver=datalayer_mutations.request_zarr_upload,
    )
    finish_zarr_upload = kante.django_mutation(
        description="Finalize a Zarr upload after the client has written the object",
        resolver=datalayer_mutations.finish_zarr_upload,
    )
    request_zarr_access = kante.django_mutation(
        description="Request temporary S3 read credentials for a Zarr store",
        resolver=datalayer_mutations.request_zarr_access,
    )
    request_general_zarr_access = kante.django_mutation(
        description="Request temporary S3 read credentials for Zarr files in the organization",
        resolver=datalayer_mutations.request_general_zarr_access,
    )

    request_parquet_upload = kante.django_mutation(
        description="Request an upload grant for a Parquet store",
        resolver=datalayer_mutations.request_parquet_upload,
    )
    finish_parquet_upload = kante.django_mutation(
        description="Finalize a Parquet upload after the client has written the object",
        resolver=datalayer_mutations.finish_parquet_upload,
    )
    request_parquet_access = kante.django_mutation(
        description="Request temporary S3 read credentials for a Parquet file",
        resolver=datalayer_mutations.request_parquet_access,
    )
    request_general_parquet_access = kante.django_mutation(
        description="Request temporary S3 read credentials for Parquet files in the organization",
        resolver=datalayer_mutations.request_general_parquet_access,
    )
    from_array_like = mutation(
        resolver=mutations.from_array_like,
        description="Create an image from array-like data",
    )
    pin_image = mutation(resolver=mutations.pin_image, description="Pin an image for quick access")
    update_image = mutation(
        resolver=mutations.update_image,
        description="Update an existing image's metadata",
    )
    delete_image = mutation(resolver=mutations.delete_image, description="Delete an existing image")

    # Create A Dataset
    create_adataset = mutation(
        resolver=mutations.create_adataset,
        description="Create a new dataset from array-like data with optional choordinate anchors and OME  metadata",
    )

    create_data_roi = mutation(
        resolver=mutations.create_data_roi,
        description="Create a new data ROI from vector or slice definitions with optional choordinate anchors and OME metadata",
    )
    delete_data_roi = mutation(resolver=mutations.delete_data_roi, description="Delete an existing data ROI")

    # Lens

    create_lens = mutation(
        resolver=mutations.create_lens,
        description="Create a new lens from an existing dataset and slicing constraints",
    )

    create_scene = mutation(
        resolver=mutations.create_scene,
        description="Create a new scene from an existing lens with optional blending mode",
    )

    create_layer = mutation(
        resolver=mutations.create_layer,
        description="Create a new layer from an existing lens with optional affine transformation and colormap settings",
    )
    update_layer = mutation(
        resolver=mutations.update_layer,
        description="Update an existing layer's lens, scene, affine transformation, and colormap settings",
    )

    attach_unstructured_meta = mutation(
        resolver=mutations.attach_unstructured_meta,
        description="Attach unstructured metadata to a file",
    )

    create_render_tree = mutation(
        resolver=mutations.create_render_tree,
        description="Create a new render tree for image visualization",
    )

    from_parquet_like = mutation(
        resolver=mutations.from_parquet_like,
        description="Create a table from parquet-like data",
    )

    create_mesh = mutation(
        resolver=mutations.create_mesh,
        description="Create a new mesh",
    )

    delete_mesh = mutation(
        resolver=mutations.delete_mesh,
        description="Delete an existing mesh",
    )

    pin_mesh = mutation(
        resolver=mutations.pin_mesh,
        description="Pin a mesh for quick access",
    )

    from_file_like = mutation(
        resolver=mutations.from_file_like,
        description="Create a file from file-like data",
    )
    delete_file = mutation(resolver=mutations.delete_file, description="Delete an existing file")

    # Stage
    create_stage = mutation(
        resolver=mutations.create_stage,
        description="Create a new stage for organizing data",
    )
    pin_stage = mutation(resolver=mutations.pin_stage, description="Pin a stage for quick access")
    delete_stage = mutation(resolver=mutations.delete_stage, description="Delete an existing stage")

    # RGBContext
    create_rgb_context = mutation(
        resolver=mutations.create_rgb_context,
        description="Create a new RGB context for image visualization",
    )
    delete_rgb_context = mutation(
        resolver=mutations.delete_rgb_context,
        description="Delete an existing RGB context",
    )
    update_rgb_context = mutation(
        resolver=mutations.update_rgb_context,
        description="Update settings of an existing RGB context",
    )

    # Dataset
    create_dataset = mutation(
        resolver=mutations.create_dataset,
        description="Create a new dataset to organize data",
    )
    ensure_dataset = mutation(
        resolver=mutations.ensure_dataset,
        description="Create a new dataset to organize data",
    )
    update_dataset = mutation(resolver=mutations.update_dataset, description="Update dataset metadata")
    revert_dataset = mutation(
        resolver=mutations.revert_dataset,
        description="Revert dataset to a previous version",
    )
    pin_dataset = mutation(resolver=mutations.pin_dataset, description="Pin a dataset for quick access")
    delete_dataset = mutation(resolver=mutations.delete_dataset, description="Delete an existing dataset")
    put_datasets_in_dataset = mutation(
        resolver=mutations.put_datasets_in_dataset,
        description="Add datasets as children of another dataset",
    )
    release_datasets_from_dataset = mutation(
        resolver=mutations.release_datasets_from_dataset,
        description="Remove datasets from being children of another dataset",
    )
    put_images_in_dataset = mutation(resolver=mutations.put_images_in_dataset, description="Add images to a dataset")
    release_images_from_dataset = mutation(
        resolver=mutations.release_images_from_dataset,
        description="Remove images from a dataset",
    )
    put_files_in_dataset = mutation(resolver=mutations.put_files_in_dataset, description="Add files to a dataset")
    release_files_from_dataset = mutation(
        resolver=mutations.release_files_from_dataset,
        description="Remove files from a dataset",
    )

    # MultiWellPlate

    create_multi_well_plate = mutation(
        resolver=mutations.create_multi_well_plate,
        description="Create a new multi-well plate configuration",
    )
    ensure_multi_well_plate = mutation(
        resolver=mutations.ensure_multi_well_plate,
        description="Ensure a multi-well plate exists, creating if needed",
    )
    pin_multi_well_plate = mutation(
        resolver=mutations.pin_multi_well_plate,
        description="Pin a multi-well plate for quick access",
    )
    delete_multi_well_plate = mutation(
        resolver=mutations.delete_multi_well_plate,
        description="Delete an existing multi-well plate configuration",
    )

    # View Collection
    create_view_collection = mutation(
        resolver=mutations.create_view_collection,
        description="Create a new collection of views to organize related views",
    )
    pin_view_collection = mutation(
        resolver=mutations.pin_view_collection,
        description="Pin a view collection for quick access",
    )
    delete_view_collection = mutation(
        resolver=mutations.delete_view_collection,
        description="Delete an existing view collection",
    )

    # Era
    create_era = mutation(
        resolver=mutations.create_era,
        description="Create a new era for temporal organization",
    )
    pin_era = mutation(resolver=mutations.pin_era, description="Pin an era for quick access")
    delete_era = mutation(resolver=mutations.delete_era, description="Delete an existing era")

    # Views
    create_label_view = mutation(
        resolver=mutations.create_label_view,
        description="Create a new view for label data",
    )
    create_timepoint_view = mutation(
        resolver=mutations.create_timepoint_view,
        description="Create a new view for temporal data",
    )
    create_file_view = mutation(
        resolver=mutations.create_file_view,
        description="Create a new view for file data",
    )
    create_roi_view = mutation(
        resolver=mutations.create_roi_view,
        description="Create a new view for region of interest data",
    )
    create_optics_view = mutation(
        resolver=mutations.create_optics_view,
        description="Create a new view for optical settings",
    )
    create_rgb_view = mutation(
        resolver=mutations.create_rgb_view,
        description="Create a new view for RGB image data",
    )
    update_rgb_view = mutation(
        resolver=mutations.update_rgb_view,
        description="Update an existing RGB view",
    )
    delete_rgb_view = mutation(
        resolver=mutations.delete_rgb_view,
        description="Delete an existing RGB view",
    )
    create_channel_view = mutation(
        resolver=mutations.create_channel_view,
        description="Create a new view for channel data",
    )
    create_mask_view = mutation(
        resolver=mutations.create_mask_view,
        description="Create a new view for masked data",
    )
    create_instance_mask_view = mutation(
        resolver=mutations.create_instance_mask_view,
        description="Create a new view for instance mask data",
    )
    create_reference_view = mutation(
        resolver=mutations.create_reference_view,
        description="Create a new reference view for image data",
    )
    create_well_position_view = mutation(
        resolver=mutations.create_well_position_view,
        description="Create a new view for well position data",
    )
    create_continous_scan_view = mutation(
        resolver=mutations.create_continous_scan_view,
        description="Create a new view for continuous scan data",
    )
    create_affine_transformation_view: types.AffineTransformationView = mutation(
        resolver=mutations.create_affine_transformation_view,
        description="Create a new view for affine transformation data",
    )
    create_histogram_view: types.HistogramView = mutation(
        resolver=mutations.create_histogram_view,
        description="Create a new view for histogram data",
    )
    delete_histogram_view = mutation(
        resolver=mutations.delete_histogram_view,
        description="Delete an existing histogram view",
    )

    delete_affine_transformation_view = mutation(
        resolver=mutations.delete_affine_transformation_view,
        description="Delete an existing affine transformation view",
    )
    delete_channel_view = mutation(
        resolver=mutations.delete_channel_view,
        description="Delete an existing channel view",
    )
    delete_timepoint_view = mutation(
        resolver=mutations.delete_timepoint_view,
        description="Delete an existing timepoint view",
    )
    delete_optics_view = mutation(
        resolver=mutations.delete_optics_view,
        description="Delete an existing optics view",
    )
    delete_rgb_view = mutation(resolver=mutations.delete_rgb_view, description="Delete an existing RGB view")

    delete_view = mutation(resolver=mutations.delete_view, description="Delete any type of view")
    pin_view = mutation(resolver=mutations.pin_view, description="Pin a view for quick access")

    # Instrument
    create_instrument = mutation(
        resolver=mutations.create_instrument,
        description="Create a new instrument configuration",
    )
    delete_instrument = mutation(
        resolver=mutations.delete_instrument,
        description="Delete an existing instrument",
    )
    pin_instrument = mutation(
        resolver=mutations.pin_instrument,
        description="Pin an instrument for quick access",
    )
    ensure_instrument = mutation(
        resolver=mutations.ensure_instrument,
        description="Ensure an instrument exists, creating if needed",
    )

    # Objective
    create_objective = mutation(
        resolver=mutations.create_objective,
        description="Create a new microscope objective configuration",
    )
    delete_objective = mutation(resolver=mutations.delete_objective, description="Delete an existing objective")
    pin_objective = mutation(
        resolver=mutations.pin_objective,
        description="Pin an objective for quick access",
    )
    ensure_objective = mutation(
        resolver=mutations.ensure_objective,
        description="Ensure an objective exists, creating if needed",
    )

    # Camera
    create_camera = mutation(
        resolver=mutations.create_camera,
        description="Create a new camera configuration",
    )
    delete_camera = mutation(resolver=mutations.delete_camera, description="Delete an existing camera")
    pin_camera = mutation(resolver=mutations.pin_camera, description="Pin a camera for quick access")
    ensure_camera = mutation(
        resolver=mutations.ensure_camera,
        description="Ensure a camera exists, creating if needed",
    )

    # Snapshot
    create_snapshot = mutation(resolver=mutations.create_snapshot, description="Create a new state snapshot")
    delete_snapshot = mutation(resolver=mutations.delete_snapshot, description="Delete an existing snapshot")
    pin_snapshot = mutation(resolver=mutations.pin_snapshot, description="Pin a snapshot for quick access")

    # ROI
    create_roi = mutation(resolver=mutations.create_roi, description="Create a new region of interest")
    update_roi = mutation(
        resolver=mutations.update_roi,
        description="Update an existing region of interest",
    )
    pin_roi = mutation(
        resolver=mutations.pin_roi,
        description="Pin a region of interest for quick access",
    )
    delete_roi = mutation(
        resolver=mutations.delete_roi,
        description="Delete an existing region of interest",
    )

    assign_user_permission = mutation(
        resolver=mutations.assign_user_permission,
        description="Assign a user permission to an object",
    )


@strawberry.type
class ChatRoomMessage:
    room_name: str
    current_user: str
    message: str


@strawberry.type
class Subscription:
    rois = subscription(resolver=subscriptions.rois, description="Subscribe to real-time ROI updates")
    images = subscription(
        resolver=subscriptions.images,
        description="Subscribe to real-time image updates",
    )
    files = subscription(resolver=subscriptions.files, description="Subscribe to real-time file updates")
    affine_transformation_views = subscription(
        resolver=subscriptions.affine_transformation_views,
        description="Subscribe to real-time affine transformation view updatess",
    )


schema = kante.Schema(
    query=Query,
    subscription=Subscription,
    mutation=Mutation,
    extensions=[
        DjangoOptimizerExtension,
        AuthentikateExtension,
        KoherentExtension,
        DuckExtension,
    ],
    types=interface_types,
)
