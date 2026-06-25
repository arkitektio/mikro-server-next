import strawberry_django
from core import models
from koherent.models import Task as KoherentTask
from strawberry import auto


@strawberry_django.order_type(models.Image)
class ImageOrder:
    created_at: auto
    name: auto
    id: auto


@strawberry_django.order_type(models.Dataset)
class DatasetOrder:
    created_at: auto
    name: auto
    id: auto


@strawberry_django.order_type(models.File)
class FileOrder:
    created_at: auto
    name: auto
    size: auto
    id: auto


@strawberry_django.order_type(models.Table)
class TableOrder:
    created_at: auto
    name: auto
    id: auto


@strawberry_django.order_type(models.Mesh)
class MeshOrder:
    created_at: auto
    name: auto
    id: auto


@strawberry_django.order_type(models.Snapshot)
class SnapshotOrder:
    created_at: auto
    name: auto
    id: auto


@strawberry_django.order_type(models.ROI)
class ROIOrder:
    created_at: auto
    id: auto


@strawberry_django.order_type(models.RenderTree)
class RenderTreeOrder:
    name: auto
    id: auto


@strawberry_django.order_type(models.FileView)
class FileViewOrder:
    id: auto


@strawberry_django.order_type(models.Stage)
class StageOrder:
    created_at: auto
    name: auto
    id: auto


@strawberry_django.order_type(models.Era)
class EraOrder:
    created_at: auto
    begin: auto
    name: auto
    id: auto


@strawberry_django.order_type(models.Experiment)
class ExperimentOrder:
    created_at: auto
    name: auto
    id: auto


@strawberry_django.order_type(models.MultiWellPlate)
class MultiWellPlateOrder:
    name: auto
    id: auto


@strawberry_django.order_type(models.Instrument)
class InstrumentOrder:
    name: auto
    id: auto


@strawberry_django.order_type(models.Objective)
class ObjectiveOrder:
    name: auto
    magnification: auto
    id: auto


@strawberry_django.order_type(models.Camera)
class CameraOrder:
    name: auto
    id: auto


@strawberry_django.order_type(models.RGBRenderContext)
class RGBContextOrder:
    name: auto
    id: auto


@strawberry_django.order_type(models.ADataset)
class ADatasetOrder:
    created_at: auto
    name: auto
    id: auto


@strawberry_django.order_type(models.DataArray)
class DataArrayOrder:
    level: auto
    id: auto


@strawberry_django.order_type(models.DataRoi)
class DataRoiOrder:
    name: auto
    id: auto


@strawberry_django.order_type(models.Lens)
class LensOrder:
    id: auto


@strawberry_django.order_type(models.Layer)
class LayerOrder:
    id: auto


@strawberry_django.order_type(models.Scene)
class SceneOrder:
    name: auto
    id: auto


@strawberry_django.order_type(models.ViewCollection)
class ViewCollectionOrder:
    name: auto
    id: auto


@strawberry_django.order_type(KoherentTask)
class TaskOrder:
    created_at: auto
    id: auto
